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
        self.move_tables = []

    def setup_move_tables(self, posid, Ptarg, Qtarg, anticollision=True):
        """Given a list of positioner ids, and corresponding target positions, generates
        the move tables that get from start to target. Only one set of target coordinates
        per posid. Note the available flag to turn off anticollision algorithm.
        """
        anticollision = False # temporary, since algorithm is not implemented yet in PosScheduler
        for i in posid:
            pos = self.positioners[i]
			# use PosModel to get calibration values
			# use PosModel to get current local theta,phi
			# use PosTransforms to convert current local theta,phi to Pstart, Qstart

        # now for the full array, pass all the start and target (P,Q) to PosScheduler,
        # (as well as calibration values). You get back move tables.
		self.move_tables = PosScheduler.schedule_moves(Pstart,Qstart,Ptarget,Qtarget,anticollision)
			
	def hardware_ready_move_tables(self):
		"""Strips out information that isn't necessary to send to petalbox, and
		formats for sending. Any cases of multiple tables for one positioner are
        merged in sequence into a single table."""
        tbls = self.move_tables
        i = 0
        while i < len(s):
            j = i + 1
            extend_list = []
            while j < len(tbls):
                if tbls[i].posmodel.state.kv['SERIAL_ID'] == tbls[j].posmodel.state.kv['SERIAL_ID']:
                    extend_list.extend(tbls.pop(j))
                else:
                    j += 1
            for e in extend_list
                tbls[i].extend(e)
            i += 1        
        hw_tables = []
		for m in tbls
            hw_tables.append(m.for_hardware())
        return hw_tables
        
	def postmove_cleanup(self):
		"""Always call this after performing a set of moves, so that PosModel instances
        can be informed that the hardware move was done.
        """
        for m in self.move_tables:
            cleanup_table = m.for_cleanup
            m.posmodel.postmove_cleanup(cleanup_table['dT'],cleanup_table['dP']) 