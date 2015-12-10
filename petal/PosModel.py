#############################
# Classes: PosModel, Axis   #
# Version: Python 3         #
# Date: Dec. 9, 2015        #
# Author: Joe Silber        #
#############################

import numpy as np
import PosState
import PosMoveTable
#import PosTransforms
import PosScheduler

class PosModel(object):
    """Software model of the physical positioner hardware.
    Takes in local (x,y) or (th,phi) targets, move speeds, converts
    to degrees of motor shaft rotation, speed, and type of move (such
    as cruise / creep / backlash / hardstop approach).
    
    One instance of PosModel corresponds to one PosState to physical positioner.
    But we will consider refactoring to array-wise later on.
    """
    
    
    def __init__(self, state):
        self.state = state #PosState.PosState(pos_id)
        self.trans = PosTransforms.PosTransforms(self.state)

        #Axis identification
        self.T = 0  # theta axis idx
        self.P = 1  # phi axis idx
        self.axis = [None,None]
        self.axis[self.T] = Axis(self,self.T) 
        self.axis[self.P] = Axis(self,self.P)

        # internal motor/driver constants
        self._timer_update_rate    = 18e3   # Hz
        self._stepsize_creep       = 0.1    # deg
        self._stepsize_cruise      = 3.3    # deg
        self._motor_speed_cruise = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
        self._motor_speed_creep  = self._timer_update_rate * self._stepsize_creep / self.state.read('CREEP_PERIOD')  # deg/sec

        # public motor/driver constants
        self.gear_ratio_namiki    = (46.0/14.0+1)**4   # namiki    "337:1", output rotation/motor input
        self.gear_ratio_maxon     = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
        self.gear_ratio_faulhaber = 256.0              # faulhaber "256:1", output rotation/motor input
    

    
        # List of particular PosState parameters that modify internal details of how a move
        # gets divided into cruise / creep, antibacklash moves added, etc. What distinguishes
        # these parameters is that they specify particular *modes* of motion. They are not
        # calibration parameters or id #s or the like.
        self.default_move_options = {'BACKLASH_REMOVAL_ON'  : True,
                                'FINAL_CREEP_ON'       : True,
                                'ALLOW_EXCEED_LIMITS'  : False,
                                'ONLY_CREEP'           : False}

    @property
    def expected_current_position(self):
        """Returns a dictionary of the current expected position in the various coordinate systems.
        The keys are:
            'P'      ... float, deg, dependent variable, expected global P position (syntax may need some refinement after implementing PosTransforms)
            'Q'      ... float, mm,  dependent variable, expected global Q position (syntax may need some refinement after implementing PosTransforms)
            'x'      ... float, mm,  dependent variable, expected global x position
            'y'      ... float, mm,  dependent variable, expected global y position
            'th_obs' ... float, deg, dependent variable, expected position of theta axis, as seen by an external observer (includes offsets, calibrations)
            'ph_obs' ... float, deg, dependent variable, expected position of phi axis, as seen by an external observer (includes offsets, calibrations)
            'th_shaft' ... float, deg, independent variable, the internally-tracked expected position of the theta shaft at the output of the gearbox
            'ph_shaft' ... float, deg, independent variable, the internally-tracked expected position of the phi shaft at the output of the gearbox
            'th_mot' ... float, deg, dependent variable, expected position of theta motor
            'ph_mot' ... float, deg, dependent variable, expected position of phi motor
        """
        shaftTP = np.array([[self.axis[self.T].pos],[self.axis[self.P].pos]])
        r = np.array([[self.state.read('LENGTH_R1')],[self.state.read('LENGTH_R2')]]) #This was added       
        d = {}
        d['th_shaft'] = shaftTP[0,0]
        d['ph_shaft'] = shaftTP[1,0]
        d['th_mot'] = d['th_shaft'] * self.axis[self.T].gear_ratio()
        d['ph_mot'] = d['ph_shaft'] * self.axis[self.P].gear_ratio()
        obsTP = self.trans.shaftTP_to_obsTP(shaftTP)
        d['th_obs'] = obsTP[0]
        d['ph_obs'] = obsTP[1]
        obsXY = self.trans.shaftTP_to_obsXY(shaftTP,r)   #This requires r      
        d['x'] = obsXY[0]
        d['y'] = obsXY[1,]        
        QS = self.trans.obsXY_to_QS(obsXY) #Need to write this
        d['Q'] = obsQS[0,0]
        d['S'] = obsQS[1,0]
        return d

    @property
    def expected_current_position_str(self):
        """One-line string summarizing current expected position.
        """
        deg = unichr(176).encode("latin-1")
        mm = 'mm'
        pos = self.expected_current_position()
        s = 'P:{:7.3f}{}, Q:{:7.3f}{} | x:{:7.3f}{}, y:{:7.3f}{} | th_obs:{:8.3f}{}, ph_obs:{:8.3f}{} | th_mot:{:8.1f}{}, ph_mot:{:8.1f}{}'. \
            format(pos['P'],mm, pos['Q'],deg,
                   pos['x'],mm, pos['y'],mm,
                   pos['th_obs'],deg, pos['ph_obs'],deg,
                   pos['th_mot'],deg, pos['ph_mot'],deg)
        return s

        
    @property
    def targetable_range_T(self):
        """Returns a [1x2] array of theta_min, theta_max."""
        return self.axis[self.T].debounced_range().tolist()
        
    @property
    def targetable_range_P(self):
        """Returns a [1x2] array of phi_min, phi_max."""
        return self.axis[self.P].debounced_range().tolist()  

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
            dist = self.trans.obsTP_to_shaftTP(distance,T=True)
        elif axisid == self.P:
            dist = self.trans.obsTP_to_shaftTP(distance,P=True)
        else:
            print( 'bad axisid ' + repr(axisid))
        if not(options['ALLOW_EXCEED_LIMITS']):
            dist = self.axis[axisid].truncate_to_limits(dist)
        gear_ratio = self.axis[axisid].gear_ratio()
        ccw_sign = self.axis[axisid].ccw_sign()
        dist *= gear_ratio
        dist *= ccw_sign
        antibacklash_final_move_dir = ccw_sign * self.axis[axisid].antibacklash_final_move_dir()
        backlash_magnitude = gear_ratio * self.state.read('BACKLASH') * options['BACKLASH_REMOVAL_ON'] #How are options being called in this function?
        if np.sign(dist) == antibacklash_final_move_dir:
            final_move  = np.sign(dist) * backlash_magnitude
            undershoot  = -final_move * self.state.read('BACKLASH_REMOVAL_BACKUP_FRACTION')
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
        dist_spinup = 2 * np.sign(distance) * self.state.read('SPINUPDOWN_DISTANCE')
        if options['ONLY_CREEP'] or (abs(distance) <= (abs(dist_spinup) + self.state.read('NOM_FINAL_CREEP_DIST'))):
            dist_spinup     = 0
            dist_cruise     = 0
            steps_cruise    = 0
            dist_cruisespin = 0
            net_dist_creep  = distance
        else:                    
            dist_creep      = np.sign(distance) * self.state.read('FINAL_CREEP_DIST') * options['FINAL_CREEP_ON'] # initial guess at how far to creep
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
            move_data['move_time'].append((abs(steps_cruise)*self._stepsize_cruise + 4*self.state.read('SPINUPDOWN_DISTANCE')) / self._motor_speed_cruise)
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
        r = np.array([[self.state.read('LENGTH_R1')],[self.state.read('LENGTH_R2')]])
        shaft_range = np.array([[self.state.read('PHYSICAL_RANGE_T')],[self.state.read('PHYSICAL_RANGE_P')]]) 
        pos = self.expected_current_position()
        start_tp = np.array([[pos['th_shaft']],[pos['ph_shaft']]])
        if   movecmd == 'qs':
            targt_tp = self.trans.QS_to_shaftTP(vals)
        elif movecmd == 'dqds':
            start_PQ = self.trans.shaftTP_to_QS(start_tp)
            targt_PQ = start_PQ + vals
            targt_tp = self.trans.QS_to_shaftTP(targt_PQ)
        elif movecmd == 'xy':
            targt_tp = self.trans.obsXY_to_shaftTP(vals, r, shaft_range) # modified with r, shaft_range
        elif movecmd == 'dxdy':
            start_xy = self.trans.shaftTP_to_obsXY(start_tp, r) # modified with r
            targt_xy = start_xy + vals
            targt_tp = self.trans.obsXY_to_shaftTP(targt_xy, r,shaft_range) # modified with r, shaft_range
        elif movecmd == 'tp':
            targt_tp = vals
        elif movecmd == 'dtdp':
            targt_tp = start_tp + vals
        elif movecmd == 'home':
            for a in self.axis:
                table.extend(a.seek_and_set_limits_sequence())
            return table
        elif movecmd == 'seeklimit':
            search_dist = []
            search_dist[self.T] = np.sign(val1)*self.axis[self.T].limit_seeking_search_distance()
            search_dist[self.P]= np.sign(val2)*self.axis[self.P].limit_seeking_search_distance()
            old_SHOULD_DEBOUNCE_HARDSTOPS = self.state.read('SHOULD_DEBOUNCE_HARDSTOPS')
            self.state.write('SHOULD_DEBOUNCE_HARDSTOPS',0)
            for i in [self.T,self.P]:
                table.extend(self.axis[i].seek_one_limit_sequence(search_dist[i]))
            return table
        else:
            print( 'move command ' + repr(movecmd) + ' not recognized')
            return []
        
        delta_tp = targt_tp - start_tp
        table.set_move(0, self.T, delta_tp[self.T,0])
        table.set_move(0, self.P, delta_tp[self.P,0])
        return table
  

class Axis(object):
    """Handler for a motion axis. Provides move syntax and keeps tracks of position.
    
    """    
   
    def __init__(self, posmodel, axisid, pos=0, last_primary_hardstop_dir=0):
        self.posmodel = posmodel
        if not(axisid == self.posmodel.state.read('MOTOR_ID_T') or axisid == self.posmodel.state.read('MOTOR_ID_P')):
            print( 'warning: bad axis id ' + repr(axisid))
        self.axisid = axisid
        self.postmove_cleanup_cmds = ''
        self._last_primary_hardstop_dir = last_primary_hardstop_dir  # 0, +1, -1, tells you which if any hardstop was last used to set travel limits
        self.pos = pos # Internally-tracked angular position of the axis. By definition pos = (motor shaft position) / (gear ratio).

    @property
    def full_range(self):    
        """Calculated from physical range only, with no subtraction of debounce
        distance.
        Returns [1x2] array of [min,max]
        """
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            targetable_range = abs(self.pomodel.state.read('PHYSICAL_RANGE_T'))
            return np.array([-0.50,0.50])*targetable_range  # split theta range such that 0 is essentially in the middle
        else:
            targetable_range = abs(self.pomodel.state.read('PHYSICAL_RANGE_P'))
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
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            if self.principle_hardstop_direction < 0:
                return np.array([+self.pomodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_T'),
                                 -self.pomodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_T')])
            else:
                return np.array([+self.pomodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_T'),
                                 -self.pomodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_T')])
        else:
            if self.principle_hardstop_direction < 0:
                return np.array([+self.pomodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_P'),
                                 -self.pomodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_P')])
            else:
                return np.array([+self.pomodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_P'),
                                 -self.pomodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_P')])
    
    @property    
    def backlash_clearance(self):
        """Minimum clearance distance required for backlash removal moves.
        Returns 1x2 array of [clearance_from_low_side_of_range, clearance_from_high_side].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        similarly as the hardstop clearance directions).
        """
        if self.antibacklash_final_move_dir > 0:
            return np.array([[+self.pomodel.state.read('BACKLASH')],[0]])
        else:
            return np.array([[0],[-self.pomodel.state.read('BACKLASH')]])
            
    @property
    def gear_ratio(self):
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            return self.pomodel.state.read('GEAR_T')
        else:
            return self.pomodel.state.read('GEAR_P')
        
    @property
    def ccw_sign(self):
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            return self.pomodel.state.read('MOTOR_CCW_DIR_T')
        else:
            return self.pomodel.state.read('MOTOR_CCW_DIR_P')

    @property
    def antibacklash_final_move_dir(self):
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            return self.pomodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_T')
        else:
            return self.pomodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_P')
            
    @property
    def principle_hardstop_direction(self):
        """The "principle" hardstop is the one which is struck during homing.
        (The "secondary" hardstop is only struck when finding the total available travel range.)
        """
        if self.axisid == self.pomodel.state.read('MOTOR_ID_T'):
            return self.pomodel.state.read('PRINCIPLE_HARDSTOP_DIR_T')
        else:
            return self.pomodel.state.read('PRINCIPLE_HARDSTOP_DIR_P')
            
    @property
    def limit_seeking_search_distance(self):
        """A distance magnitude that guarantees hitting a hard limit in either direction.
        """
        return np.abs(np.diff(self.full_range)*self.pomodel.state.read('LIMIT_SEEK_EXCEED_RANGE_FACTOR'))
        
    def truncate_to_limits(self, distance):
        """Return distance after first truncating it (if necessary) according to software limits.
        """
        if not(self.pomodel.state.read('ALLOW_EXCEED_LIMITS')):
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
        direction = np.sign(self.principle_hardstop_direction())
        table = self.seek_one_limit_sequence(direction * self.limit_seeking_search_distance())
        if direction > 0:
            self.postmove_cleanup_cmds = ''
            self.postmove_cleanup_cmds += 'self.pos = self.maxpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = +1.0\n'
        elif direction < 0:
            self.postmove_cleanup_cmds = ''
            self.postmove_cleanup_cmds += 'self.pos = self.minpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = -1.0\n'
        else:
            print( 'bad direction ' + repr(direction))
        return table
      
    def seek_one_limit_sequence(self, seek_distance):
        """Use to go hit a hardstop. For the distance argument, direction matters.
        The sequence is returned in a move table.
        """
        table = PosMoveTable.PosMoveTable(self.posmodel)
        old_allow_exceed_limits = self.posmodel.state.read('ALLOW_EXCEED_LIMITS')
        self.posmodel.state.write('ALLOW_EXCEED_LIMITS',True)
        old_only_creep = self.posmodel.state.read('ONLY_CREEP')
        if self.posmodel.state.read('CREEP_TO_LIMITS'):
            self.posmodel.state.write('ONLY_CREEP',True)
        both_debounce_vals = self.hardstop_debounce
        if self.posmodel.state.read('SHOULD_DEBOUNCE_HARDSTOPS'):
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
        self.posmodel.state.write('ALLOW_EXCEED_LIMITS',old_allow_exceed_limits) 
        self.posmodel.state.write('ONLY_CREEP',old_only_creep)
        return table

