import numpy as np
import PosState
import PosMoveTable
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
    _spinup_distance      = 628.2  # deg
    _period_creep         = 2.0    # timer intervals
    _shaft_speed_cruise   = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
    _shaft_speed_creep    = _timer_update_rate * _stepsize_creep / _period_creep  # deg/sec
    
    # List of particular PosState parameters that modify internal details of how a move
    # gets divided into cruise / creep, antibacklash moves added, etc. What distinguishes
    # these parameters is that they specify particular *modes* of motion. They are not
    # calibration parameters or id #s or the like.
    default_move_options = {'BACKLASH_REMOVAL_ON'  : True,
                            'FINAL_CREEP_ON'       : True,
                            'ALLOW_EXCEED_LIMITS'  : False,
                            'ONLY_CREEP_TO_LIMITS' : False}
 
    def __init__(self, state=PosState.PosState()):
        self.state = state
        self.trans = PosTransforms.PosTransforms(self.state)
        self.axis = [None,None]
        self.axis[self.T] = Axis(self.state,self.T)
        self.axis[self.P] = Axis(self.state,self.P)

    # getter functions
    @property    
    def speed_cruise_T(self):
        """Phi axis cruise speed at the output shaft in deg / sec."""
        return self._shaft_speed_cruise / self.state.kv['GEAR_T']  
        
    @property    
    def speed_cruise_P(self):
        """Phi axis cruise speed at the output shaft in deg / sec."""
        return self._shaft_speed_cruise / self.state.kv['GEAR_P']        

    @property
    def speed_creep_T(self):
        """Theta axis creep speed at the output shaft in deg / sec."""
        return self.shaft_speed_creep / self.state.kv['GEAR_T']
    
    @property
    def speed_creep_P(self):
        """Phi axis creep speed at the output shaft in deg / sec."""
        return self.shaft_speed_creep / self.state.kv['GEAR_P']
        
    @property
    def position_PQ(self):
        """2x1 current (P,Q) position as seen by an external observer looking toward the focal surface."""
        return self.trans.shaftTP_to_obsQP(self.position_shaftTP) # nomenclature here might change when actually implemented in PosTransforms

    @property
    def position_xy(self):
        """2x1 current (x,y) position as seen by an external observer looking toward the focal surface."""
        return self.trans.shaftTP_to_obsXY(self.position_shaftTP)
    
    @property
    def position_obsTP(self):
        """2x1 current (theta,phi) position as seen by an external observer looking toward the fiber tip."""
        return self.trans.shaftTP_to_obsTP(self.position_shaftTP)
    
    @property
    def position_shaftTP(self):
        """2x1 current (theta,phi) output shaft positions (no offsets or calibrations)."""
        t = self.axis[self.T].pos
        p = self.axis[self.P].pos
        return np.array([[t],[p]])

	#	anti-collision keepout polygons (several types...)
	#		ferrule holder and upper housing keepouts are always the same, see DESI-0XXX
	#		petal level keepouts (such as being near edge, or near GFA, may vary per positioner)
	#	(t_start,p_start) best known current position, in each positioner's local (theta,phi) coordinates
	#	calibrated arm lengths (R1,R2)
	#	calibrated angular offsets (t0,p0), e.g. theta clocking angle of mounting
	#	calibrated center offsets, in local (x0,y0), offsets w.r.t. each positioner's nominal center
	#	calibrated limits on travel ranges (tmin,tmax,pmin,pmax)


    def true_move(self, axisid, distance, options=self.default_move_options):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees.
        
        Outputs are quantized distance [deg], speed [deg/sec], integer number
        of motor steps, speed mode ['cruise' or 'creep'], and move time [sec]

        The return values may be lists, i.e. if it's a "final" move, which really consists
        of multiple submoves.
        """

        if axisid == self.T:
            obs_distance = self.trans.obsT_to_shaftT # does this logic work here? use PosTransforms for a single axis? or just a dumb gear ratio?
                                     # at what point do we do obsTP_to_shaftTP (i.e., both axes simultaneously? is that necessary)
                                     # at what point do the ... offsets ... get figured in?
                                     #                      ... gear ratios ...
                                     #                      ... gear ratio calibrations ...
        elif axisid == self.P:
            obs_distance = self.trans.obsT_to_shaftP
        else:
            print 'bad axisid ' + repr(axisid)
                
        obs_distance = self.axis[axisid].check_limits(obs_distance)
        
        
        # if it's a final move...
        #	get the backlash and creep parameters from PosState
        #   break up the final move into appropriate submoves
        # now in general...
        #	unless it's been defined as a creep move, define it as cruise
        #	(can't remember exact logic, but...) subtract out spin-up / spin-down distances
        #   quantize move(s) into motor steps
        #	estimate the move(s) times
        #	calculate in degrees the quantized distance(s)

        return {'obs_distance' : obs_distance,
                'obs_speed'    : obs_speed,
                'motor_step'   : motor_step,
                'speed_mode'   : speed_mode,
                'move_time'    : move_time}
        

class Axis(object):
    """Handler for a motion axis. Provides move syntax and keeps tracks of position.
    """
    
    # internal parameters
    _last_hardstop_debounce    = 0.0   # used internally for accounting changes to range settings
    _last_primary_hardstop_dir = 0.0   # 0, +1, -1, tells you which if any hardstop was last used to set travel limits
   
    def __init__(self, posmodel, axisid):
        self.maxpos = float("inf")
        self.minpos = -float("inf")
        self.internal_pos = np.mean(self.nominal_positioning_range)
        self.internal_pos_offset = 0.0  # internal_pos + internal_pos_offset --> pos, by definition
        self.posmodel = posmodel
        self.axisid = axisid
        self.set_range()

    @property
    def pos(self):
        """Current position of the axis.
        """
        return self.internal_pos + self.internal_pos_offset

    @property
    def hardstop_debounce(self):
        """Calculated distance to debounce from hardstop when homing.
        Returns 1x2 array of [debounce_at_min_limit,debounce_at_max_limit].
        These are positive quantities (i.e., they don't include any determination of directionality).
        """
        if self.axisid == PosModel.T:
            if self.principle_hardstop_direction < 0:
                return np.array([abs(self.posmodel.state.kv('PRINCIPLE_HARDSTOP_CLEARANCE_T')),
                                 abs(self.posmodel.state.kv('SECONDARY_HARDSTOP_CLEARANCE_T'))])
            else:
                return np.array([abs(self.posmodel.state.kv('SECONDARY_HARDSTOP_CLEARANCE_T')),
                                 abs(self.posmodel.state.kv('PRINCIPLE_HARDSTOP_CLEARANCE_T'))])
        elif self.axisid == PosModel.P:
            if self.principle_hardstop_direction < 0:
                return np.array([abs(self.posmodel.state.kv('PRINCIPLE_HARDSTOP_CLEARANCE_P')),
                                 abs(self.posmodel.state.kv('SECONDARY_HARDSTOP_CLEARANCE_P'))])
            else:
                return np.array([abs(self.posmodel.state.kv('SECONDARY_HARDSTOP_CLEARANCE_P')),
                                 abs(self.posmodel.state.kv('PRINCIPLE_HARDSTOP_CLEARANCE_P'))])
        else:
            print 'bad axisid' + repr(self.axisid)
            return None
    
    @property
    def principle_hardstop_direction(self):
        """The "principle" hardstop is the one which is struck during homing.
        (The "secondary" hardstop is only struck when finding the total available travel range.)
        """
        if self.axisid == PosModel.T:
            return self.posmodel.state.kv['PRINCIPLE_HARDSTOP_DIR_T']
        elif self.axisid == PosModel.P:
            return self.posmodel.state.kv['PRINCIPLE_HARDSTOP_DIR_P']
        else:
            print 'bad axisid' + repr(self.axisid)
            return None
			
    @property
    def nominal_positioning_range(self):
        """Calculated from physical range and hardstop debounce only.
		Returns [1x2] array of [min,max]
        """
        if self.axisid == PosModel.T:
            targetable_range = abs(self.posmodel.state.kv('PHYSICAL_RANGE_T')) - np.sum(self.hardstop_debounce)            
            return np.array([-0.50,0.50])*targetable_range  # split theta range such that 0 is essentially in the middle
        elif self.axisid == PosModel.P:
            targetable_range = abs(self.posmodel.state.kv('PHYSICAL_RANGE_P')) - np.sum(self.hardstop_debounce)    
            return np.array([-0.01,0.99])*targetable_range  # split phi range such that 0 is essentially at the minimum
        else:
            print 'bad axisid' + repr(self.axisid)
            return None
   
    def set_range(self):
        """Updates minpos and maxpos, given the nominal range and the hardstop direction.
        """
        debounce_deltas = self.hardstop_debounce - self._last_hardstop_debounce
        nominal_travel = np.diff(self.nominal_positioning_range)
        if self._last_primary_hardstop_dir == 0.0:
            self.minpos = np.amin(self.nominal_positioning_range)
            self.maxpos = np.amax(self.nominal_positioning_range)
            self._last_hardstop_debounce = self.hardstop_debounce
        elif self._last_primary_hardstop_dir == 1.0:
            self.maxpos = self.maxpos - debounce_deltas[1]
            self.minpos = self.maxpos - nominal_travel
        elif self._last_primary_hardstop_dir== -1.0:
            self.minpos = self.minpos + debounce_deltas[0]
            self.maxpos = self.minpos + nominal_travel
        self._last_hardstop_debounce = self.hardstop_debounce
        
    def check_limits(self, distance):
        """Return distance after first truncating it (if necessary) according to software limits.
        """
        if not(self.posmodel.state.kv['ALLOW_EXCEED_LIMITS']):
            target_pos = self.pos + distance
            if self.maxpos < self.minpos:
                distance = 0
                print('Axis {0} : allow_exceed_limits= {1} and maxpos = {2} is less than minpos = {3}; nomove made'.format(self.axis_idx, self.allow_exceed_limits, self.maxpos, self.minpos))
            elif target_pos > self.maxpos:
                new_distance = self.maxpos - self.pos
                if PosConstants.is_verbose(self.state.verbosity):
                    print(' Axis {0} : allow_exceed_limits = {1} , so no resquested move = {2}was truncated to ( maxpos-pos)= {3} \n'.format(self.axis_idx, self.allow_exceed_limits, distance, new_distance))
                distance = new_distance
            elif target_pos < self.minpos:
                new_distance = self.minpos - self.pos
                if PosConstants.is_verbose(self.state.verbosity):
                    print('Axis {0} : allow_exceed_limits = {1}, so no resquested move = {2} was truncated to (minpos- pos)= {3} \n'.format(self.axis_idx, self.allow_exceed_limits, distance, new_distance))
                distance = new_distance
        return distance       
        
    def add_seek_one_limit_sequence(self, schedule, seek_distance):
        """Use to go hit a hardstop. For the distance argument, direction matters.
        The sequence is added to the argued schedule.
        """
        old_allow_exceed_limits = self.posmodel.state.kv['ALLOW_EXCEED_LIMITS']
        self.posmodel.state.kv('ALLOW_EXCEED_LIMITS') = True
        both_debounce_vals = self.hardstop_debounce
        if seek_distance < 0:
            abs_debounce = both_debounce_vals[0]
        else:
            abs_debounce = both_debounce_vals[1]
        debounce_distance = -np.sign(seek_distance)*self.posmodel.state.kv['SHOULD_DEBOUNCE_HARDSTOPS']*abs_debounce
        #if self.posmodel.state.kv['LIMIT_APPROACH_CREEP_ONLY']:
        #    speed_mode = 'creep'
        #else:
        #    speed_mode = 'cruise'
        #move(0,self.axisid,seek_distance,speed_mode) # not really -- needs to pipe through PosScheduler, maybe with a new move table handled by (whom? PosArrayMaster? PosModel?)
        #move(1,self.axisid,debounce_distance,'creep') # not really -- needs to pipe through PosScheduler, maybe with a new move table handled by (whom? PosArrayMaster? PosModel?)
        s = [0,0]
        d = [0,0]
        s[self.axisid] = seek_distance
        d[self.axisid] = debounce_distance     
        schedule.overall_move_request_with_forced_dtdp(self.posmodel, s[self.posmodel.T], s[self.posmodel.P])
        schedule.overall_move_request_with_forced_dtdp(self.posmodel, d[self.posmodel.T], d[self.posmodel.P])
        
        self.posmodel.state.kv('ALLOW_EXCEED_LIMITS') = old_allow_exceed_limits
        return move_table #?
        
    def add_find_limits_sequence(self, schedule):
        """Typical homing routine to find the max pos, min pos and at least primary hardstop.
        The sequence is added to the argued schedule.
        """
        
        seek_distance = np.absolute(np.diff(self.nominal_positioning_range)*self.state.kv['LIMIT_SEEK_EXCEED_RANGE_FACTOR'])                          
       
        # seek secondary hardstop
        if self.encoder_exists() and self.secondary_hardstop_exists:
            if PosConstants.is_verbose(self.state.verbosity):
                print('Axis {0}: seeking secondary limit \n'.format(self.axis_idx))
            direction = -np.sign(self.principle_hardstop_direction)
            self.add_seek_one_limit_sequence(schedule, direction*seek_distance)
            if direction > 0:
                self.max_is_here()
            else:
                self.min_is_here()
        
        # seek primary hardstop
        direction = np.sign(self.principle_hardstop_direction)
        if direction != 0:
            if PosConstants.is_verbose(self.state.verbosity):
                print('Axis {0}: seeking primary limit \n'.format(self.axis_idx))
            self.add_seek_one_limit_sequence(schedule, direction*seek_distance)
            if self.encoder_exists() and direction > 0:
                self.max_is_here()
                self.last_primary_hardstop_dir = +1.0
            elif self.encoder_exists():
                self.min_is_here()
                self.last_primary_hardstop_dir = -1.0
            elif direction > 0:
                self.this_pos_is(self.maxpos)
                self.last_primary_hardstop_dir = +1.0
            else:
                self.this_pos_is(self.minpos)
                self.last_primary_hardstop_dir = -1.0
