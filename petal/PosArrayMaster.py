# imports here

class PosArrayMaster(object):
	"""Orchestrates the modules to generate fiber positioner move sequences.
	"""
	
	def __init__(self,list_of_posids):
		self.positioners = some array of PosModel instances
		
	def setup_move_tables(PQtarget)
		"""Given a list of target positions, returns the move tables (one for each
		positioner) that get from start to target."""
		
		for pos in self.positioners
			# use PosModel to get calibration values
			# use PosModel to get current local theta,phi
			# use PosTransforms to convert current local theta,phi to Pstart, Qstart
			
		# now for the full array, pass all the start and target (P,Q) to PosScheduler,
		# (as well as calibration values). You get back move tables.
		move_tables = PosScheduler.schedule_moves(Pstart,Qstart,Ptarget,Qtarget,other?)

		return move_tables
		
	def update_encoded_positions(PQ)
		"""Generally used after performing moves, so the PosModel instances can be
		informed that the hardware move was done. The argued (P,Q) get stored to each
		positioner. These aren't measured (FVC) positions."""
		
		for pos in self.positioners
			# use PosTransforms to convert the (P,Q) into local theta,phi
			# update the PosState (via PosModel?) for each
			
	def hardware_ready_move_tables(move_tables)
		"""Strips out information that isn't necessary to send to petalbox, and
		formats for sending."""
		
		return sanitized_move_tables