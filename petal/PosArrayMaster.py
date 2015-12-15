import PosModel
import PosScheduler
import PosState
#import PetalComm

class PosArrayMaster(object):
    """Maintains a list of instances of the Fiber Positioner software model
    (PosModel). This module is the interface through which the motions of a
    group of positioners (e.g. on a Petal) is coordinated. In general, all
    move requests and scheduling is accomplished with PosArrayMaster.
    """
    def __init__(self, posids, configs=[]):
        self.posmodels = []
        if len(configs) != len(posids):
            configs = ['DEFAULT']*len(posids)
        for i in range(len(posids)):
            posstate = PosState.PosState(posids[i],configs[i])
            posmodel = PosModel.PosModel(posstate)
            self.posmodels.append(posmodel)
        self.posids = posids
        self.schedule = PosScheduler.PosScheduler()
        #self.comm = PetalComm.PetalComm() # syntax? arguments?

    def request_schedule_execute_moves(self, posids, Qtargs, Stargs, anticollision=True):
        """Convenience wrapper for the complete sequence to cause an array of
        positioners to go to targets (Qtargs, Stargs).

        The sequence of calls is executed directly in order, from request through
        scheduling to executing the move and post-move cleanup. In practice, with
        multiple petals and significant anti-collision algorithm processing time
        and communication overhead time, it is anticipated that a simple call like
        this will not be sufficiently multi-threaded, and furthermore that scheduling
        may need to have been accomplished separately ahead of time. However, this
        method gives the basic sequence of events that need to occur, and it should
        be of value for testing and for scenarios where moves should be immediately
        executed.
        """
        self.request_moves(posids, Qtargs, Stargs)
        self.schedule_moves(anticollision)
        self.send_tables_and_execute_moves()

    def expert_request_schedule_execute_moves(self, posids, movecmds, values1, values2):
        """Convenience wrapper for the complete sequence to cause an array of
        positioners to move in expert mode (with no anti-collision).

        The sequence of calls is executed directly in order, from request through
        scheduling to executing the move and post-move cleanup. See similar comments
        in the method "request_schedule_execute_moves", regarding usage of this
        simplistic method.
        """
        self.expert_request_moves(posids, movecmds, values1, values2)
        self.schedule_moves(anticollision=False)
        self.send_tables_and_execute_moves()

    def send_tables_and_execute_moves(self):
        self.comm.send_tables(self.hardware_ready_move_tables()) # return values? threaded with pyro somehow?
        self.comm.execute_moves() # return values? threaded with pyro somehow?
        self.postmove_cleanup()

    def request_moves(self, posids, Qtargs, Stargs):
        """Input a list of positioner ids and corresponding target positions to
        the scheduler.
        """
        for i in range(len(posids)):
            j = self.posids.index(posids[i])
            self.schedule.move_request(self.posmodels[j], Qtargs[i], Stargs[i])

    def expert_request_moves(self, posids, movecmds, values1, values2):
        """Input a list to the scheduler of positioner ids and corresponding
        move command strings and argument value pairs.

        Usage of this method by design forces anticollision calculations to be
        turned off for the entire schedule. This method is generally recommended
        only for expert usage.
        """
        for i in range(len(posids)):
            j = self.posids.index(posids[i])
            move_table = self.posmodels[j].make_move_table(movecmds[i], values1[i], values2[i])
            self.schedule.expert_move_request(move_table)

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
                if tbls[i].posmodel.state.read('SERIAL_ID') == tbls[j].posmodel.state.read('SERIAL_ID'):
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
            print(m.posmodel.expected_current_position_str)
        self.clear_schedule()

    def clear_schedule(self):
        self.schedule = PosScheduler.PosScheduler()

    def get(self,posid,varname=''):
        """Retrieve the state value identified by string varname, for positioner
        identified by id posid. If no varname is specified, return the whole
        posmodel.
        """
        i = self.posids.index(posid)
        if varname == '':
            return self.posmodels[i]
        else:
            return self.posmodels[i].state.read[varname]


