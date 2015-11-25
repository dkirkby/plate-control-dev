import PosModel
import PosScheduler
import PosState

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
        #for i in posid:
        #    pos = self.positioners[i]
			# use PosModel to get calibration values
			# use PosModel to get current local theta,phi
			# use PosTransforms to convert current local theta,phi to Pstart, Qstart
        # Now for the full array, pass all the start and target (P,Q) to PosScheduler,
        # (as well as calibration values).
        self.move_tables = PosScheduler.schedule_moves(Ptarg,Qtarg,anticollision)
        
    def expert_setup_move_tables(self, posid, movecmd, val1, val2):
        """Given a list of positioner ids, and corresponding move command strings,
        and argument value pairs, generates the move tables to execute the commands.
        Multiple commands to the same positioner are permitted, and will be executed
        in sequence. There is NO anticollision calculation performed! Therefore
        this function is generally recommended only for expert usage.
        """
        
        
			
    def hardware_ready_move_tables(self):
        """Strips out information that isn't necessary to send to petalbox, and
        formats for sending. Any cases of multiple tables for one positioner are
        merged in sequence into a single table.
        
        Output format:
            List of dictionaries.
            
            Each dictionary is the move table for one positioner.
            
            The dictionary has the following fields:
                {'posid':'','nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}
            
            The fields have the following types and meanings:

                posid         ... string                    ... identifies the positioner by 'SERIAL_ID'
                
                nrows         ... unsigned integer          ... number of elements in each of the list fields (i.e. number of rows of the move table)            
                
                motor_steps_T or
                motor_steps_P ... list of signed integers   ... number of motor steps to rotate 
                                                                    ... motor_steps_X > 0 ... ccw rotation
                                                                    ... motor_steps_X < 0 ... cw rotation
                speed_mode_T or
                speed_mode_P  ... list of strings           ... 'cruise' or 'creep'
                
                movetime      ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
                
                postpause     ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
                
        """
        tbls = self.move_tables
        i = 0
        while i < len(tbls):
            j = i + 1
            extend_list = []
            while j < len(tbls):
                if tbls[i].posmodel.state.kv['SERIAL_ID'] == tbls[j].posmodel.state.kv['SERIAL_ID']:
                    extend_list.extend(tbls.pop(j))
                else:
                    j += 1
            for e in extend_list:
                tbls[i].extend(e)
            i += 1
        hw_tables = []
        for m in tbls:
            hw_tables.append(m.for_hardware())
        return hw_tables

    def postmove_cleanup(self):
        """Always call this after performing a set of moves, so that PosModel instances
        can be informed that the hardware move was done.
        """
        for m in self.move_tables:
            cleanup_table = m.for_cleanup
            m.posmodel.postmove_cleanup(cleanup_table['dT'],cleanup_table['dP']) 