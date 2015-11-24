import PosModel

class PosArrayMaster(object):
    """Orchestrates the modules to generate fiber positioner move sequences.
	"""
 
    def __init__(self, posids):
        self.positioners = []
        for i in range(len(posids)):
            posstate = PosState.PosState(posids[i]) # or other appropriate syntax for loading that config
            posmodel = PosModel.PosModel(posstate)
            self.positioners.append(posmodel)
        self.posids = posids

    def setup_move_tables(posid, Ptarg, Qtarg, anticollision=True):
        """Given a list of positioner ids, and corresponding target positions, returns
        the move tables (one for each positioner) that get from start to target. Only
        one set of target coordinates per posid.
        
        Note flag available to turn off anticollision algorithm when move tables
        get scheduled.
        """
        anticollision = False # temporary, since algorithm is not implemented yet in PosScheduler
        for i in posid:
            pos = self.positioners[i]
			# use PosModel to get calibration values
			# use PosModel to get current local theta,phi
			# use PosTransforms to convert current local theta,phi to Pstart, Qstart
			
		# now for the full array, pass all the start and target (P,Q) to PosScheduler,
		# (as well as calibration values). You get back move tables.
		move_tables = PosScheduler.schedule_moves(Pstart,Qstart,Ptarget,Qtarget,anticollision)

		return move_tables
		
	def update_encoded_positions(posid, P, Q):
		"""Generally used after performing moves, so the PosModel instances can be
		informed that the hardware move was done. The argued (P,Q) get stored to each
		positioner. These aren't measured (FVC) positions."""
		for pos in self.positioners:
			# use PosTransforms to convert the (P,Q) into local theta,phi
			# update the PosState (via PosModel?) for each
			
	def hardware_ready_move_tables(move_tables):
		"""Strips out information that isn't necessary to send to petalbox, and
		formats for sending."""
		return move_tables.for_hardware