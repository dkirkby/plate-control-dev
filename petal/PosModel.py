# imports here

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
    __timer_update_rate    = 18e3   # Hz
    __stepsize_creep       = 0.1    # deg
    __stepsize_cruise      = 3.3    # deg
    __spinup_distance      = 628.2  # deg
    __period_creep         = 2.0    # timer intervals
    __shaft_speed_cruise   = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
    __shaft_speed_creep    = __timer_update_rate * __stepsize_creep / __period_creep  # deg/sec
 
    def __init__(self,state=PosState()):
        self.state = state

    # getter functions
    @property    
    def speed_cruise_T(self):
        """Phi axis cruise speed at the output shaft in deg / sec."""
        return self.__shaft_speed_cruise / self.state.kv['GEAR_T']  
        
    @property    
    def speed_cruise_P(self):
        """Phi axis cruise speed at the output shaft in deg / sec."""
        return self.__shaft_speed_cruise / self.state.kv['GEAR_P']        

    @property
    def speed_creep_T(self):
        """Theta axis creep speed at the output shaft in deg / sec."""
        return self.__shaft_speed_creep / self.state.kv['GEAR_T']
    
    @property
    def speed_creep_P(self):
        """Phi axis creep speed at the output shaft in deg / sec."""
        return self.__shaft_speed_creep / self.state.kv['GEAR_P']

	#	anti-collision keepout polygons (several types...)
	#		ferrule holder and upper housing keepouts are always the same, see DESI-0XXX
	#		petal level keepouts (such as being near edge, or near GFA, may vary per positioner)
	#	(t_start,p_start) best known current position, in each positioner's local (theta,phi) coordinates
	#	calibrated arm lengths (R1,R2)
	#	calibrated angular offsets (t0,p0), e.g. theta clocking angle of mounting
	#	calibrated center offsets, in local (x0,y0), offsets w.r.t. each positioner's nominal center
	#	calibrated limits on travel ranges (tmin,tmax,pmin,pmax)



    def true_move(obs_dT, obs_dP, is_final_move):
        """Input: (theta,phi) move as seen by the observer, in degrees
        if it's a final move (i.e. that will need creep / anti-backlash added in)
        
        Output: sequence of the predicted move times,
                sequence of the integer number of motor steps on each axis
                sequence of the speed modes ("cruise" or "creep")
                sequence of the steps-quantized (theta,phi) distances, in degrees

        The return values may be lists, i.e. if it's a "final" move, which really consists
        of multiple submoves."""

        # if it's a final move...
        #	get the backlash and creep parameters from PosState
        #   break up the final move into appropriate submoves
        # now in general...
        #	unless it's been defined as a creep move, define it as cruise
        #	(can't remember exact logic, but...) subtract out spin-up / spin-down distances
        #   quantize move(s) into motor steps
        #	estimate the move(s) times
        #	calculate in degrees the quantized distance(s)

        return move_times, speed_modes, corrected_obs_dT, corrected_obs_dP, motor_steps_T, motor_steps_P
