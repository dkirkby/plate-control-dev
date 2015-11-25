import PosModel
import PosScheduler
import PosState

class PosArrayMaster(object):
    """Orchestrates the modules to generate fiber positioner move sequences.
    """
 
    def __init__(self, posids):
        self.posmodels = []
        for i in range(len(posids)):
            posstate = PosState.PosState(posids[i]) # or other appropriate syntax for loading that config
            posmodel = PosModel.PosModel(posstate)
            self.posmodels.append(posmodel)
        self.posids = posids
        self.schedule = PosScheduler.PosScheduler()

    def request_moves(self, posids, Ptargs, Qtargs):
        """Input a list of positioner ids and corresponding target positions to
        the scheduler.
        """
        for i in range(len(posids)):
            j = self.posids.index(posids[i])
            self.schedule.overall_move_request(self.posmodels[j], Ptargs[i], Qtargs[i])

    def expert_request_moves(self, posids, movecmds, values1, values2):
        """Input a list to the scheduler of positioner ids and corresponding
        move command strings and argument value pairs.
        
        Usage of this method by design forces anticollision calculations to be
        turned off for the entire schedule. This method is generally recommended
        only for expert usage.
        """
        for i in range(len(posids)):
            #something
            self.schedule.expert_add_move_table(move_table)
            
    def schedule_moves(self,anticollision=True):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available flag to turn the
        anticollision algorithm on or off for the scheduling.
        """
        anticollision = False # temporary, since algorithm is not yet implemented in PosScheduler
        self.schedule.schedule_moves(anticollision)
        
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
        tbls = self.schedule.move_tables
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
        for m in self.schedule.move_tables:
            cleanup_table = m.for_cleanup
            m.posmodel.postmove_cleanup(cleanup_table['dT'],cleanup_table['dP']) 
        self.clear_schedule()
        
    def clear_schedule(self):
        self.schedule = PosScheduler.PosScheduler()