import posmodel
import posschedule
import posstate
import petalcomm
import posconstants as pc

class PosArrayMaster(object):
    """Maintains a list of instances of the Fiber Positioner software model
    (PosModel). This module is the interface through which the motions of a
    group of positioners (e.g. on a Petal) is coordinated. In general, all
    move requests and scheduling is accomplished with PosArrayMaster.
    """
    def __init__(self, posids):
        self.posmodels = []
        for i in range(len(posids)):
            state = posstate.PosState(posids[i],logging=True)
            model = posmodel.PosModel(state)
            self.posmodels.append(model)
        self.posids = posids
        self.schedule = posschedule.PosSchedule()
        self.comm = petalcomm.PetalComm()

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
        the schedule.
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
        expected_prior_dTdP = [0,0]
        for i in range(len(posids)):
            j = self.posids.index(posids[i])
            move_table = self.posmodels[j].make_move_table(movecmds[i], values1[i], values2[i], expected_prior_dTdP)
            self.schedule.expert_move_request(move_table)
            table_formatted = move_table.for_cleanup
            expected_prior_dTdP[0] += sum(table_formatted['dT'])
            expected_prior_dTdP[1] += sum(table_formatted['dP'])

    def schedule_moves(self,anticollision=True):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available flag to turn the
        anticollision algorithm on or off for the scheduling.
        """
        anticollision = False # temporary, since algorithm is not yet implemented in PosSchedule
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
                    extend_list.append(tbls.pop(j))
                else:
                    j += 1
            for e in extend_list:
                tbls[i].extend(e)
            i += 1
        hw_tables = []
        for m in tbls:
            hw_tables.append(m.for_hardware)
        return hw_tables

    def postmove_cleanup(self):
        """Always call this after performing a set of moves, so that PosModel instances
        can be informed that the hardware move was done.
        """
        for m in self.schedule.move_tables:
            m.posmodel.postmove_cleanup(m.for_cleanup)
            print(m.posmodel.expected_current_position_str)
        self.clear_schedule()

    def clear_schedule(self):
        self.schedule = posschedule.PosSchedule()

    def expected_current_position(self,posid=None,varname=''):
        """Retrieve the current position, for a positioner identied by posid, according
        to the internal tracking of its posmodel object. Valid varnames are:
            'Q', 'S', 'x', 'y', 'obsT', 'obsP', 'shaftT', 'shaftP', 'motorT', 'motorP'
        See comments in posmodel.py for explanation of these values.

        If no posid is specified, then a single value, or list of all positioners' values is returned.
        This can be used either with or without specifying a varname.

        If no varname is specified, a dictionary containing all of them will be
        returned.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of positions. The optional argument varname can be:
            ... a list, of same length as posid
            ... or just a single varname, which gets fetched uniformly for all posid
        """
        (posid, was_not_list) = self._posid_listify(posid)
        (varname, temp) = pc.listify(varname,keep_flat=True)
        (posid, varname) = self._equalize_input_list_lengths(posid,varname)
        vals = []
        for i in range(len(posid)):
            pidx = self.posids.index(posid[i])
            this_val = self.posmodels[pidx].expected_current_position
            if varname[i] == '':
                vals.append(this_val)
            else:
                vals.append(this_val[varname[i]])
        if was_not_list:
            vals = pc.delistify(vals)
        return vals

    def expected_current_position_str(self,posid=None):
        """One-line string summarizing current expected position of a positioner.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of strings.

        If no posid is specified, a list of strings for all positioners is returned.
        """
        (posid, was_not_list) = self._posid_listify(posid)
        strs = []
        for p in posid:
            pidx = self.posids.index(p)
            strs.append(self.posmodels[pidx].expected_current_position_str)
        if was_not_list:
            strs = pc.delistify(strs)
        return strs

    def get(self,posid=None,varname=''):
        """Retrieve the state value identified by string varname, for positioner
        identified by id posid.

        If no varname is specified, return the whole posmodel.

        If no posid is specified, a list of values for all positioners is returned.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of values. The optional argument varname can be:
            ... a list, of same length as posid
            ... or just a single varname, which gets fetched uniformly for all posid
        """
        (posid, was_not_list) = self._posid_listify(posid)
        (varname, temp) = pc.listify(varname,keep_flat=True)
        (posid, varname) = self._equalize_input_list_lengths(posid,varname)
        vals = []
        for i in range(len(posid)):
            pidx = self.posids.index(posid[i])
            if varname[i] == '':
                vals.append(self.posmodels[pidx])
            else:
                vals.append(self.posmodels[pidx].state.read(varname[i]))
        if was_not_list:
            vals = pc.delistify(vals)
        return vals

    def setval(self,posid=None,varname=None,value=None,write_to_disk=None):
        """Set the state value identified by string varname, for positioner unit
        identified by id posid.

        Note comments for posstate.write() method, which explain the optional
        argument 'write_to_disk'.

        If no posid is specified, value is set for all positioners.

        If posid is a list of multiple positioner ids, then this method can handle
        setting multiple values. The other arguments can either:
            ... also be lists, of same length as posid
            ... or just a single value, which gets applied uniformly to all posid.
            ... (except write_to_disk, which is always just a single boolean value, not a list, and applies to all affected posid)
        """
        if varname == None or value == None:
            print('either no varname or no value was specified to setval')
            return
        (posid, temp) = self._posid_listify(posid)
        (varname, temp) = pc.listify(varname,keep_flat=True)
        (value, temp) = pc.listify(value,keep_flat=True)
        (posid,varname) = self._equalize_input_list_lengths(posid,varname)
        (posid,value)   = self._equalize_input_list_lengths(posid,value)
        (posid,varname) = self._equalize_input_list_lengths(posid,varname) # repetition here handles the case where there was 1 posid element, 1 varname, but mulitplie elements in value
        for i in range(len(posid)):
            pidx = self.posids.index(posid[i])
            self.posmodels[pidx].state.write(varname[i],value[i],write_to_disk)

    def _posid_listify(self,posid):
        """Internally-used wrapper method for listification of posid. The additional functionality
        here is the check for whether to auto-fill with all posids known to posarraymaster.
        """
        if posid == None:
            posid = self.posids
            was_not_list = (len(posid) == 1)
        else:
            (posid, was_not_list) = pc.listify(posid,keep_flat=True)
        return posid, was_not_list

    def _equalize_input_list_lengths(self,var1,var2):
        if not(isinstance(var1,list)) or not(isinstance(var2,list)):
            print('both var1 and var2 must be lists, even if single-element')
            return None, None
        if len(var1) != len(var2):
            if len(var1) == 1:
                var1 = var1*len(var2) # note here var1 is starting as a list
            elif len(var2) == 1:
                var2 = var2*len(var1) # note here var2 is starting as a list
            else:
                print('either the var1 or the var2 must be of length 1')
                return None, None
        return var1, var2
