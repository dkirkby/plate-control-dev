import numpy as np
import PosState
import PosMoveTable
import PosTransforms
import PosScheduler

class PosModel(object):
    """Software model of the physical positioner hardware.
    Takes in local (x,y) or (th,phi) targets, move speeds, converts
    to degrees of motor shaft rotation, speed, and type of move (such
    as cruise / creep / backlash / hardstop approach).
    
    One instance of PosModel corresponds to one PosState to physical positioner.
    But we will consider refactoring to array-wise later on.
    """

    # public motor/driver constants
    T = 0  # theta axis idx
    P = 1  # phi axis idx
    gear_ratio_namiki    = (46.0/14.0+1)**4   # namiki    "337:1", output rotation/motor input
    gear_ratio_maxon     = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
    gear_ratio_faulhaber = 256.0              # faulhaber "256:1", output rotation/motor input
    
    # internal motor/driver constants
    _timer_update_rate    = 18e3   # Hz
    _stepsize_creep       = 0.1    # deg
    _stepsize_cruise      = 3.3    # deg
    
    # List of particular PosState parameters that modify internal details of how a move
    # gets divided into cruise / creep, antibacklash moves added, etc. What distinguishes
    # these parameters is that they specify particular *modes* of motion. They are not
    # calibration parameters or id #s or the like.
    default_move_options = {'BACKLASH_REMOVAL_ON'  : True,
                            'FINAL_CREEP_ON'       : True,
                            'ALLOW_EXCEED_LIMITS'  : False,
                            'ONLY_CREEP'           : False}
 
    def __init__(self, state=PosState.PosState()):
        self.state = state
        self.trans = PosTransforms.PosTransforms(self.state)
        self.axis = [None,None]
        self.axis[self.T] = Axis(self.state,self.T)
        self.axis[self.P] = Axis(self.state,self.P)
        self._motor_speed_cruise = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
        self._motor_speed_creep  = _timer_update_rate * _stepsize_creep / self.state.kv['CREEP_PERIOD']  # deg/sec

    @property
    def position_str(self):
        """One-line string displaying current known position."""
        deg = unichr(176).encode("latin-1")
        mm = 'mm'
        s = 'P:{:7.3f}{}, Q:{:7.3f}{} | X:{:7.3f}{}, Y:{:7.3f}{} | th_obs:{:8.3f}{}, ph_obs:{:8.3f}{} | th_mot:{:8.1f}{}, ph_mot:{:8.1f}{}'. \
            format(self.state.kv['P'],mm,self.state.kv['Q'],deg,
                   self.state.kv['X'],mm,self.state.kv['Y'],mm,
                   self.state.kv['th_obs'],deg,self.state.kv['ph_obs'],deg,
                   self.state.kv['th_mot'],deg,self.state.kv['ph_mot'],deg)
        return s

    def update_dependent_position_variables(self):
        """Updates position state variables based on internally-tracked axis positions.
        """
        self.state.kv['th_mot'] = self.axis[self.T].pos * self.axis[self.T].gear_ratio
        self.state.kv['ph_mot'] = self.axis[self.P].pos * self.axis[self.P].gear_ratio
        shaftTP = np.array([[self.posmodel.state.kv['th_shaft']],[self.posmodel.state.kv['ph_shaft']]])        
        obsTP = self.trans.shaftTP_to_obsTP(shaftTP)
        self.state.kv['th_obs'] = obsTP[0,0]
        self.state.kv['ph_obs'] = obsTP[1,0]
        XY = self.trans.shaftTP_to_obsXY(shaftTP)        
        self.state.kv['X'] = obsXY[0,0]
        self.state.kv['Y'] = obsXY[1,0]        
        PQ = self.trans.obsXY_to_obsPQ(obsXY) # nomenclature here might change when actually implemented in PosTransforms
        self.state.kv['P'] = obsPQ[0,0]
        self.state.kv['Q'] = obsPQ[1,0]

    # POSSIBLE DATA GETTERS NEEDED FOR ANTI-COLLISION?
    #   anti-collision keepout polygons (several types...)
    #		ferrule holder and upper housing keepouts are always the same, see DESI-0XXX
    #		petal level keepouts (such as being near edge, or near GFA, may vary per positioner)
    # ARE THESE NEEDED INDEPENDENTLY FOR ANTI-COLLISION, OR ARE THEY AUTO HANDLED BY THE POSTRANSFORMS MODULE?
    #	calibrated arm lengths (R1,R2) 
    #	calibrated angular offsets (t0,p0), e.g. theta clocking angle of mounting
    #	calibrated center offsets, in local (x0,y0), offsets w.r.t. each positioner's nominal center
    #	calibrated limits on travel ranges (tmin,tmax,pmin,pmax)

    def true_move(self, axisid, distance, options=[]):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees.
        
        Outputs are quantized distance [deg], speed [deg/sec], integer number of
        motor steps, speed mode ['cruise' or 'creep'], and move time [sec]

        The return values are formatted as a dictionary of lists. (This handles the
        case where if it's a "final" move, it really consists of multiple submoves.)
        """
        if not(options):
            options = self.default_move_options
        if axisid == self.T:
            dist = self.trans.obsT_to_shaftT(distance)
        elif axisid == self.P:
            dist = self.trans.obsP_to_shaftP(distance)
        else:
            print 'bad axisid ' + repr(axisid)
        if not(options['ALLOW_EXCEED_LIMITS']):
            dist = self.axis[axisid].truncate_to_limits(dist)
        gear_ratio = self.axis[axisid].gear_ratio
        ccw_sign = self.axis[axisid].ccw_sign
        dist *= gear_ratio
        dist *= ccw_sign
        antibacklash_final_move_dir = ccw_sign * self.axis[axisid].antibacklash_final_move_dir
        backlash_magnitude = gear_ratio * self.state.kv['BACKLASH'] * options['BACKLASH_REMOVAL_ON']
        if np.sign(dist) == antibacklash_final_move_dir:
            final_move  = np.sign(dist) * backlash_magnitude
            undershoot  = -final_move * self.state.kv['BACKLASH_REMOVAL_BACKUP_FRACTION']
            backup_move = -(final_move + undershoot)
            overshoot   = 0;
        else:
            final_move  = -np.sign(dist) * backlash_magnitude
            undershoot  = 0
            backup_move = 0
            overshoot   = -final_move        
        primary_move = dist + overshoot + undershoot
        
        opt = {}
        move_data = {}
        opt['primary'] = options.copy()
        opt['backup']  = options.copy()
        opt['final']   = options.copy()
        opt['backup']['ONLY_CREEP'] = True
        opt['final'] ['ONLY_CREEP'] = True
        for m in [[primary_move,opt['primary']], [backup_move,opt['backup']], [final_move,opt['final']]]:
            true_move = self.motor_true_move(axisid, m[0], m[1])
            for key in true_move.keys():
                if not(key in move_data.keys()):
                    move_data[key] = []
                move_data[key].extend(true_move[key])
        n_submoves = len(move_data['obs_distance'])
        for i in range(n_submoves):
            move_data['obs_distance'][i] *= ccw_sign / gear_ratio
            move_data['obs_speed'][i]    *= ccw_sign / gear_ratio
        return move_data
                
    def motor_true_move(self, axisid, distance, options):
        move_data = {'obs_distance' : [],
                     'obs_speed'    : [],
                     'motor_step'   : [],
                     'speed_mode'   : [],
                     'move_time'    : []}
        dist_spinup = 2 * np.sign(distance) * self.state.kv['SPINUPDOWN_DISTANCE']
        if options['ONLY_CREEP'] or (abs(distance) <= (abs(dist_spinup) + self.state.kv['NOM_FINAL_CREEP_DIST'])):
            dist_spinup     = 0
            dist_cruise     = 0
            steps_cruise    = 0
            dist_cruisespin = 0
            net_dist_creep  = distance
        else:                    
            dist_creep      = np.sign(distance) * self.state.kv['FINAL_CREEP_DIST'] * options['FINAL_CREEP_ON'] # initial guess at how far to creep
            dist_cruise     = distance - dist_spinup - dist_creep                # initial guess at how far to cruise
            steps_cruise    = round(dist_cruise / self._stepsize_cruise)         # quantize cruise steps
            dist_cruisespin = steps_cruise * self._stepsize_cruise + dist_spinup # actual distance covered while cruising
            net_dist_creep  = distance - dist_cruisespin
        steps_creep = round(net_dist_creep / self._stepsize_creep)
        dist_creep = steps_creep * self._stepsize_creep
        if steps_cruise:
            move_data['obs_distance'].append(dist_cruisespin)
            move_data['obs_speed'].append(self._motor_speed_cruise)
            move_data['motor_step'].append(steps_cruise)
            move_data['speed_mode'].append('cruise')
            move_data['move_time'].append((abs(steps_cruise)*self._stepsize_cruise + 4*self.state.kv['SPINUPDOWN_DISTANCE']) / self._motor_speed_cruise)
        if steps_creep:
            move_data['obs_distance'].append(dist_creep)
            move_data['obs_speed'].append(self._motor_speed_creep)
            move_data['motor_step'].append(steps_creep)
            move_data['speed_mode'].append('creep')
            move_data['move_time'].append(abs(steps_creep)*self._stepsize_creep / self._motor_speed_creep)
        return move_data
    
    def postmove_cleanup(self, dT, dP):
        """Always perform this after positioner physical moves have been completed,
        to update the internal tracking of shaft positions and variables.
        """
        self.axis[self.T].pos += dT
        self.axis[self.P].pos += dP
        for axis in self.axis:
            exec(axis.postmove_cleanup_cmds)
            axis.postmove_cleanup_cmds = ''
    
    def make_move_table(self, movecmd, val1, val2):
        """Generate a move table for a given move command string. Generally
        for expert or internal use only.

        Move command strings:
        
          'pq'        ... move to absolute position (P,Q)

          'xy'        ... move to absolute position (x,y)

          'tp'        ... move to absolute position (theta, phi)

          'dpdq'      ... move by a relative amount (delta P, delta Q)

          'dxdy'      ... move by a relative amount (delta x, delta y)

          'dtdp'      ... move by a relative amount (delta theta, delta phi
          
          'home'      ... find the primary hardstops on both axes, then debounce off them
                              ... val1 and val2 are both ignored
                              
          'seeklimit' ... find the argued hardstop, but do NOT debounce off it
                              ... sign of val1 or val2 says which direction to seek
                              ... finite magnitudes of val1 or val2 are ignored
                              ... val1 == 0 or val2 == 0 says do NOT seek on that axis
        """
        table = PosMoveTable.PosMoveTable(self)
        vals = np.array([[val1],[val2]])
        start_tp = np.array([[self.axis[self.T].pos,[self.axis[self.P].pos]])
        if   movecmd == 'pq':
            targt_tp = self.trans.obsPQ_to_shaftTP(vals) # check format after PosTransforms updated
        elif movecmd == 'dpdq':
            start_PQ = self.trans.shaftTP_to_obsPQ(start_tp) # check format after PosTransforms updated
            targt_PQ = start_PQ + vals
            targt_tp = self.trans.obsPQ_to_shaftTP(targt_PQ) # check format after PosTransforms updated
        elif movecmd == 'xy':
            targt_tp = self.trans.obsXY_to_shaftTP(vals)
        elif movecmd == 'dxdy':
            start_xy = self.trans.shaftTP_to_obsXY(start_tp)
            targt_xy = start_xy + vals
            targt_tp = self.trans.obsXY_to_shaftTP(targt_xy)
        elif movecmd == 'tp':
            targt_tp = vals
        elif movecmd == 'dtdp':
            targt_tp = start_tp + vals
        elif movecmd == 'home':
            for a in self.axis:
                table.extend(a.seek_and_set_limits_sequence())
            return table
        elif movecmd == 'seeklimit':
            search_dist(self.T) = np.sign(val1) * self.axis[self.T].limit_seeking_search_distance
            search_dist(self.P) = np.sign(val2) * self.axis[self.P].limit_seeking_search_distance
            old_SHOULD_DEBOUNCE_HARDSTOPS = self.state.kv['SHOULD_DEBOUNCE_HARDSTOPS']
            self.state.kv['SHOULD_DEBOUNCE_HARDSTOPS'] = 0
            for i in [self.T,self.P]:
                table.extend(self.axis[i].seek_one_limit_sequence(search_dist[i]))
            return table
        else:
            print 'move command ' + repr(movecmd) + ' not recognized'
            return []
        
        delta_tp = targt_tp - start_tp
        table.set_move(0, self.T, delta_tp[self.T,0])
        table.set_move(0, self.P, delta_tp[self.P,0])
        return table

class Axis(object):
    """Handler for a motion axis. Provides move syntax and keeps tracks of position.
    """    
   
    def __init__(self, posmodel, axisid, pos=0):
        self._last_primary_hardstop_dir = 0   # 0, +1, -1, tells you which if any hardstop was last used to set travel limits
        self.posmodel = posmodel
        if not(axisid == self.posmodel.T or axisid == self.posmodel.P):
            print 'warning: bad axis id ' + repr(axisid)
        self.axisid = axisid
        self.postmove_cleanup_cmds = ''
        self._pos = pos
        self.posmodel.update_dependent_position_variables()

    @property
    def pos(self):
        """Internally-tracked angular position of the axis.
        By definition pos = (motor shaft position) / (gear ratio).
        """
        return self._pos
    
    @pos.setter
    def pos(self,value):
        """Set the internally-tracked angular position of the axis, and update
        all the dependent position state variables.
        """
        self._pos = value        
        self.posmodel.update_dependent_position_variables()

    @property
    def full_range(self):    
        """Calculated from physical range only, with no subtraction of debounce
        distance.
        Returns [1x2] array of [min,max]
        """
        if self.axisid == self.posmodel.T:
            targetable_range = abs(self.posmodel.state.kv['PHYSICAL_RANGE_T'])
            return np.array([-0.50,0.50])*targetable_range  # split theta range such that 0 is essentially in the middle
        else:
            targetable_range = abs(self.posmodel.state.kv['PHYSICAL_RANGE_P'])
            return np.array([-0.01,0.99])*targetable_range  # split phi range such that 0 is essentially at the minimum
    @property
    def debounced_range(self):
        """Calculated from full range, accounting for removal of both the hardstop
        clearance distances and the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        return self.full_range + self.hardstop_debounce
           
    @property
    def maxpos(self):
        if self._last_primary_hardstop_dir >= 0:
            return np.amax(self.debounced_range)
        else:
            return self.minpos + self.debounced_range

    @property
    def minpos(self):
        if self._last_primary_hardstop_dir < 0:
            return np.amin(self.debounced_range)
        else:
            return self.maxpos - self.debounced_range

    @property
    def hardstop_debounce(self):
        """This is the amount to debounce off the hardstop after striking it.
        It is the hardstop clearance distance plus the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        return self.hardstop_clearance + self.backlash_clearance

    @property
    def hardstop_clearance(self):
        """Minimum distance to stay clear from hardstop.
        Returns 1x2 array of [clearance_at_min_limit, clearance_at_max_limit].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        in which one would debounce after hitting the given hardstop, to get
        back into the accessible range).
        """
        if self.axisid == self.posmodel.T:
            if self.principle_hardstop_direction < 0:
                return np.array([+self.posmodel.state.kv['PRINCIPLE_HARDSTOP_CLEARANCE_T'],
                                 -self.posmodel.state.kv['SECONDARY_HARDSTOP_CLEARANCE_T']])
            else:
                return np.array([+self.posmodel.state.kv['SECONDARY_HARDSTOP_CLEARANCE_T'],
                                 -self.posmodel.state.kv['PRINCIPLE_HARDSTOP_CLEARANCE_T']])
        else:
            if self.principle_hardstop_direction < 0:
                return np.array([+self.posmodel.state.kv['PRINCIPLE_HARDSTOP_CLEARANCE_P'],
                                 -self.posmodel.state.kv['SECONDARY_HARDSTOP_CLEARANCE_P']])
            else:
                return np.array([+self.posmodel.state.kv['SECONDARY_HARDSTOP_CLEARANCE_P'],
                                 -self.posmodel.state.kv['PRINCIPLE_HARDSTOP_CLEARANCE_P']])
    
    @property    
    def backlash_clearance(self):
        """Minimum clearance distance required for backlash removal moves.
        Returns 1x2 array of [clearance_from_low_side_of_range, clearance_from_high_side].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        similarly as the hardstop clearance directions).
        """
        if self.antibacklash_final_move_dir > 0:
            return np.array([[+self.posmodel.state.kv['BACKLASH']],[0]])
        else:
            return np.array([[0],[-self.posmodel.state.kv['BACKLASH']]])
            
    @property
    def gear_ratio(self):
        if self.axisid == self.posmodel.T:
            return self.posmodel.state.kv['GEAR_T']
        else:
            return self.posmodel.state.kv['GEAR_P']
        
    @property
    def ccw_sign(self):
        if self.axisid == self.posmodel.T:
            return self.posmodel.state.kv['MOTOR_CCW_DIR_T']
        else:
            return self.posmodel.state.kv['MOTOR_CCW_DIR_P']

    @property
    def antibacklash_final_move_dir(self):
        if self.axisid == self.posmodel.T:
            return self.posmodel.state.kv['ANTIBACKLASH_FINAL_MOVE_DIR_T']
        else:
            return self.posmodel.state.kv['ANTIBACKLASH_FINAL_MOVE_DIR_P']
            
    @property
    def principle_hardstop_direction(self):
        """The "principle" hardstop is the one which is struck during homing.
        (The "secondary" hardstop is only struck when finding the total available travel range.)
        """
        if self.axisid == self.posmodel.T:
            return self.posmodel.state.kv['PRINCIPLE_HARDSTOP_DIR_T']
        else:
            return self.posmodel.state.kv['PRINCIPLE_HARDSTOP_DIR_P']
            
    @property
    def limit_seeking_search_distance(self):
        """A distance magnitude that guarantees hitting a hard limit in either direction.
        """
        return np.abs(np.diff(self.full_range)*self.state.kv['LIMIT_SEEK_EXCEED_RANGE_FACTOR'])
        
    def truncate_to_limits(self, distance):
        """Return distance after first truncating it (if necessary) according to software limits.
        """
        if not(self.posmodel.state.kv['ALLOW_EXCEED_LIMITS']):
            target_pos = self.pos + distance
            if self.maxpos < self.minpos:
                distance = 0
            elif target_pos > self.maxpos:
                new_distance = self.maxpos - self.pos
                distance = new_distance
            elif target_pos < self.minpos:
                new_distance = self.minpos - self.pos
                distance = new_distance
        return distance       

    def seek_and_set_limits_sequence(self):
        """Typical routine used in homing to find the max pos, min pos and
        primary hardstop. The sequence is returned in a move table.
        """
        direction = np.sign(self.principle_hardstop_direction)
        table = self.seek_one_limit_sequence(direction * self.limit_seeking_search_distance)
        if direction > 0:
            self.postmove_cleanup_cmds = ''
            self.postmove_cleanup_cmds += 'self.pos = self.maxpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = +1.0\n'
        elif direction < 0:
            self.postmove_cleanup_cmds = ''
            self.postmove_cleanup_cmds += 'self.pos = self.minpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = -1.0\n'
        else:
            print 'bad direction ' + repr(direction)
        return table
      
    def seek_one_limit_sequence(self, seek_distance):
        """Use to go hit a hardstop. For the distance argument, direction matters.
        The sequence is returned in a move table.
        """
        table = PosMoveTable.PosMoveTable(self.posmodel)
        old_allow_exceed_limits = self.posmodel.state.kv['ALLOW_EXCEED_LIMITS']
        self.posmodel.state.kv['ALLOW_EXCEED_LIMITS'] = True
        old_only_creep = self.posmodel.state.kv['ONLY_CREEP']
        if self.posmodel.state.kv['CREEP_TO_LIMITS']:
            self.posmodel.state.kv['ONLY_CREEP'] = True
        both_debounce_vals = self.hardstop_debounce
        if self.posmodel.state.kv['SHOULD_DEBOUNCE_HARDSTOPS']:
            if seek_distance < 0:
                debounce_distance = both_debounce_vals[0]
            else:
                debounce_distance = both_debounce_vals[1]
        else:
            debounce_distance = 0
        for dist in [seek_distance,debounce_distance]:
            if self.axisid == self.posmodel.T:
                val1 = dist
                val2 = 0
            else:
                val1 = 0
                val2 = dist
            table.extend(self.posmodel.make_move_table('dtdp',val1,val2))
        self.posmodel.state.kv['ALLOW_EXCEED_LIMITS'] = old_allow_exceed_limits
        self.posmodel.state.kv['ONLY_CREEP'] = old_only_creep
        return table