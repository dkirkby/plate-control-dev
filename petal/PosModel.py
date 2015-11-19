# imports here

class PosModel(object):
	"""Software model of the physical positioner hardware.
	
	Takes in local (x,y) or (th,phi) targets, move speeds, converts
	to degrees of motor shaft rotation, speed, and type of move (such
	as cruise / creep / backlash / hardstop approach).
	
	One instance of PosModel correspond to one PosState to physical positioner.
	But we will consider refactoring to array-wise later on."""

	def __init__(self):
		pass
	
	# getter functions for:
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
		
	def 
		