import numpy as np
import PosState
import PosMoveTable

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
 
    def __init__(self, state=PosState.PosState()):
        self.state = state
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

	#	anti-collision keepout polygons (several types...)
	#		ferrule holder and upper housing keepouts are always the same, see DESI-0XXX
	#		petal level keepouts (such as being near edge, or near GFA, may vary per positioner)
	#	(t_start,p_start) best known current position, in each positioner's local (theta,phi) coordinates
	#	calibrated arm lengths (R1,R2)
	#	calibrated angular offsets (t0,p0), e.g. theta clocking angle of mounting
	#	calibrated center offsets, in local (x0,y0), offsets w.r.t. each positioner's nominal center
	#	calibrated limits on travel ranges (tmin,tmax,pmin,pmax)



    def true_move(axisid, distance, should_antibacklash=True, should_final_creep=True):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees. Also there are booleans for whether to do an
        antibacklash submove, and whether to do a final creep submove.
        
        Outputs are quantized distance [deg], speed [deg/sec], integer number
        of motor steps, speed mode ['cruise' or 'creep'], and move time [sec]

        The return values may be lists, i.e. if it's a "final" move, which really consists
        of multiple submoves.
        """

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
        self.posmodel = posmodel
        self.axisid = axisid
        self.set_range()

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
        
    def seek_one_limit_within(self, seek_distance):
        """Use to go hit a hardstop. For the distance argument, direction matters.
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
        #move(0,self.axisid,seek_distance,speed_mode) # not really -- needs to pipe through Axis.move and thence through PosScheduler
        #move(1,self.axisid,debounce_distance,'creep') # not really -- needs to pipe through Axis.move and thence through PosScheduler
        self.posmodel.state.kv('ALLOW_EXCEED_LIMITS') = old_allow_exceed_limits
        return move_table