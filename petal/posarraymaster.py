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
        self.schedule = posschedule.PosSchedule(self)
        self.comm = petalcomm.PetalComm()

    def request_targets(self, pos, commands, vals1, vals2):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for requests to perform complete repositioning sequence to get
        to the targets.

            - Anticollision is enabled.
            - Only one requested target per positioner.
            - Theta angles are wrapped across +/-180 deg
            - Contact of hard limits is prevented.

        INPUTS:
            pos     ... list of positioner ids or posmodel instances
            command ... corresponding list of move command strings, each element is 'qs', 'dqds', 'xy', 'dxdy', 'tp', or 'dtdp'
            val1    ... corresponding list of first move arguments, each element is the value for q, dq, x, dx, t, or dt
            val2    ... corresponding list of second move arguments, each element is the value for s, ds, y, dy, p, or dp
        """
        [pos, commands, vals1, vals2] = [list(arg) for arg in [pos, commands, vals1, vals2] if not(isinstance(arg,list))]
        for i in range(len(pos)):
            pos = self.get_model_for_pos(pos)
            if self.schedule.already_requested(pos):
                print('Positioner ' + str(pos.posid) + ' already has a target scheduled. Extra target request ' + str(commands[i]) + '(' + str(vals1[i]) + ',' + str(vals2[i]) + ') ignored')
            else:
                self.schedule.request_target(pos, commands[i], vals1[i], vals2[i])

    def request_direct_dtdp(self, pos, dt, dp):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for direct requests of rotations by the theta and phi shafts.
        This method is generally recommended only for expert usage.

            - Anticollision is disabled.
            - Multiple moves allowed per positioner.
            - Theta angles are not wrapped across +/-180 deg
            - Contact of hard limits is allowed.

        INPUTS:
            pos ... list of positioner ids or posmodel instances
            dt  ... corresponding list of delta theta values
            dp  ... corresponding list of delta phi values
        """
        [pos, dt, dp] = [list(arg) for arg in [pos, dt, dp] if not(isinstance(arg,list))]
        expected_prior_dtdp = [[0]*2 for x in range(len(self.posmodels))]
        for i in range(len(pos)):
            pos = self.get_model_for_pos(pos)
            j = self.posmodels.index(pos)
            expected_prior_dtdp[j] = self.schedule.total_dtdp(pos)

            # alter for dtdp??
            move_table = pos.make_move_table(movecmds[i], values1[i], values2[i], expected_prior_dTdP[j])

            self.schedule.expert_add_table(move_table)

    def request_limit_seek(self, pos, dir):
        pass

    def request_homing(self, pos):
        pass

    def schedule_moves(self,anticollision=True):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available flag to turn the
        anticollision algorithm on or off for the scheduling.
        """
        anticollision = False # temporary, since algorithm is not yet implemented in PosSchedule
        self.schedule.schedule_moves(anticollision)

    def send_tables_and_execute_moves(self):
        self.comm.send_tables(self.hardware_ready_move_tables()) # return values? threaded with pyro somehow?
        self.comm.execute_moves() # return values? threaded with pyro somehow?
        self.postmove_cleanup()

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
        hw_tables = []
        for m in self.schedule.move_tables:
            hw_tbl = m.for_hardware
            hw_tables.append(hw_tbl)
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

    def expected_current_position(self,posid=None,key=''):
        """Retrieve the current position, for a positioner identied by posid, according
        to the internal tracking of its posmodel object. Valid keys are:
            'Q', 'S', 'obsX', 'obsY', 'obsT', 'obsP', 'shaftT', 'shaftP', 'motorT', 'motorP'
        See comments in posmodel.py for explanation of these values.

        If no posid is specified, then a single value, or list of all positioners' values is returned.
        This can be used either with or without specifying a key.

        If no key is specified, a dictionary containing all of them will be
        returned.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of positions. The optional argument key can be:
            ... a list, of same length as posid
            ... or just a single key, which gets fetched uniformly for all posid
        """
        (posid, was_not_list) = self._posid_listify(posid)
        (key, temp) = pc.listify(key,keep_flat=True)
        (posid, key) = self._equalize_input_list_lengths(posid,key)
        vals = []
        for i in range(len(posid)):
            pidx = self.posids.index(posid[i])
            this_val = self.posmodels[pidx].expected_current_position
            if key[i] == '':
                vals.append(this_val)
            else:
                vals.append(this_val[key[i]])
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

    def get(self,posid=None,key=''):
        """Retrieve the state value identified by string key, for positioner
        identified by id posid.

        If no key is specified, return the whole posmodel.

        If no posid is specified, a list of values for all positioners is returned.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of values. The optional argument key can be:
            ... a list, of same length as posid
            ... or just a single key, which gets fetched uniformly for all posid

        Examples:
            m = posarraymaster.PosArrayMaster(posids)
            m.get('XXXXX','LENGTH_R1') # gets LENGTH_R1 value for positioner XXXXX
            m.get('XXXXX',['SHAFT_T','SHAFT_P']) # gets these values for positioner XXXXX
            m.get(['XXXXX','YYYYY'],'PETAL_ID') # gets PETAL_ID value for positioners XXXXX and YYYYY
            m.get(['XXXXX','YYYYY'],['FINAL_CREEP_ON','DEVICE_ID']) # gets multiple different values on multiple different positioners
            m.get(key=['SHAFT_T']) # gets this value for all positioners identified in posids
            m.get() # gets all posmodel objects for all positioners identified in posids
        """
        (posid, was_not_list) = self._posid_listify(posid)
        (key, temp) = pc.listify(key,keep_flat=True)
        (posid, key) = self._equalize_input_list_lengths(posid,key)
        vals = []
        for i in range(len(posid)):
            pidx = self.posids.index(posid[i])
            if key[i] == '':
                vals.append(self.posmodels[pidx])
            else:
                vals.append(self.posmodels[pidx].state.read(key[i]))
        if was_not_list:
            vals = pc.delistify(vals)
        return vals

    def set(self,posid=None,key=None,value=None,write_to_disk=None):
        """Set the state value identified by string key, for positioner unit
        identified by id posid.

        Note comments for posstate.write() method, which explain the optional
        argument 'write_to_disk'.

        If no posid is specified, value is set for all positioners.

        If posid is a list of multiple positioner ids, then this method can handle
        setting multiple values. The other arguments can either:
            ... also be lists, of same length as posid
            ... or just a single value, which gets applied uniformly to all posid.
            ... (except write_to_disk, which is always just a single boolean value, not a list, and applies to all affected posid)

        Examples:
            m = posarraymaster.PosArrayMaster(posids)
            m.set('XXXXX','LENGTH_R1',3.024) # sets LENGTH_R1 value for positioner XXXXX
            m.set(['XXXXX','YYYYY'],'PETAL_ID',2) # sets PETAL_ID value for positioners XXXXX and YYYYY
            m.set(['XXXXX','YYYYY'],['FINAL_CREEP_ON','DEVICE_ID'],[False,227]) # sets multiple different values on multiple different positioners
            m.set(key=['SHAFT_T','SHAFT_P'],value=[0,180]) # sets these values for all positioners identified in posids
        """
        if key == None or value == None:
            print('either no key or no value was specified to setval')
            return
        (posid, temp) = self._posid_listify_and_fill(posid)
        (key,   temp) = pc.listify(key,keep_flat=True)
        (value, temp) = pc.listify(value,keep_flat=True)
        (posid, key)   = self._equalize_input_list_lengths(posid,key)
        (posid, value) = self._equalize_input_list_lengths(posid,value)
        (posid, key)   = self._equalize_input_list_lengths(posid,key) # repetition here handles the case where there was 1 posid element, 1 key, but mulitplie elements in value
        for i in range(len(posid)):

            self.posmodels[pidx].state.write(key[i],value[i],write_to_disk)

    def get_model_for_pos(self, pos):
        """Returns the posmodel object corresponding to a posid, or if the argument
        is a posmodel, just returns itself.
        """
        if isinstance(pos, posmodel.Posmodel):
            return pos
        else:
            pidx = self.posids.index(pos)
            return self.posmodels[pidx]

    def _posid_listify_and_fill(self,posid):
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
        """Internally-used in setter and getter methods, to consistently handle varying
        lengths of key / value requests.
        """
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
