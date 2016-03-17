import posmodel
import posschedule
import posmovetable
import posstate
import petalcomm
import posconstants as pc
import numpy as np

class PosArrayMaster(object):
    """Maintains a list of instances of the Fiber Positioner software model
    (PosModel). This module is the interface through which the motions of a
    group of positioners (e.g. on a Petal) is coordinated. In general, all
    move requests and scheduling is accomplished with PosArrayMaster.
    """
    def __init__(self, posids, petal_id):
        self.posmodels = []
        for posid in posids:
            state = posstate.PosState(posid,logging=True)
            model = posmodel.PosModel(state)
            self.posmodels.append(model)
        self.posids = posids
        self.schedule = posschedule.PosSchedule(self)
        self.comm = petalcomm.PetalComm(petal_id)

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
            command ... corresponding list of move command strings, each element is 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
            val1    ... corresponding list of first move arguments, each element is the value for q, dq, x, dx, t, or dt
            val2    ... corresponding list of second move arguments, each element is the value for s, ds, y, dy, p, or dp
        """
        pos = pc.listify(pos,True)[0]
        commands = pc.listify(commands,True)[0]
        vals1 = pc.listify(vals1,True)[0]
        vals2 = pc.listify(vals2,True)[0]
        for i in range(len(pos)):
            posmodel = self.get_model_for_pos(pos[i])
            if self.schedule.already_requested(posmodel):
                print('Positioner ' + str(posmodel.posid) + ' already has a target scheduled. Extra target request ' + str(commands[i]) + '(' + str(vals1[i]) + ',' + str(vals2[i]) + ') ignored')
            else:
                self.schedule.request_target(posmodel, commands[i], vals1[i], vals2[i])

    def request_direct_dtdp(self, pos, dt, dp, cmd_prefix='', override_prev_settings=True):
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

        The optional argument cmd_prefix allows adding a descriptive string to the log.
        """
        pos = pc.listify(pos,True)[0]
        dt = pc.listify(dt,True)[0]
        dp = pc.listify(dp,True)[0]
        for i in range(len(pos)):
            posmodel = self.get_model_for_pos(pos[i])
            table = posmovetable.PosMoveTable(posmodel)
            table.set_move(0, pc.T, dt[i])
            table.set_move(0, pc.P, dp[i])
            table.store_orig_command(0,cmd_prefix + 'direct_dtdp',dt[i],dp[i])
            table.allow_exceed_limits = True
            self.schedule.add_table(table)

    def request_limit_seek(self, pos, axisid, direction, anticollision=True, cmd_prefix=''):
        """Request hardstop seeking sequence for positioners in list pos.
        The optional argument cmd_prefix allows adding a descriptive string to the log.
        """
        pos = pc.listify(pos,True)[0]
        posmodels = []
        for p in pos:
            posmodels.append(self.get_model_for_pos(p))
        if anticollision:
            if axisid == pc.P and direction == -1:
                # calculate thetas where extended phis do not interfere
                # request anticollision-safe moves to these thetas and phi = 0
                pass
            else:
                # request anticollision-safe moves to current thetas and all phis within Eo
                pass
        for p in posmodels:
            search_dist = np.sign(direction)*p.axis[axisid].limit_seeking_search_distance
            table = posmovetable.PosMoveTable(p)
            table.should_antibacklash = False
            table.should_final_creep  = False
            table.allow_exceed_limits = True
            table.allow_cruise = not(p.state.read('CREEP_TO_LIMITS'))
            dist = [0,0]
            dist[axisid] = search_dist
            table.set_move(0,pc.T,dist[0])
            table.set_move(0,pc.P,dist[1])
            table.store_orig_command(0,cmd_prefix + 'limit seek',direction*(axisid == pc.T),direction*(axisid == pc.P))
            self.schedule.add_table(table)

    def request_homing(self, pos):
        """Request homing sequence for positioners in list pos to find the primary hardstop
        and set values for the max position and min position.
        """
        pos = pc.listify(pos,True)[0]
        posmodels = []
        for p in pos:
            posmodels.append(self.get_model_for_pos(p))
        hardstop_debounce = [0,0]
        dir = [0,0]
        dir[pc.P] = +1 # force this, because anticollision logic depends on it
        for p in posmodels:
            self.request_limit_seek(p, pc.P, dir[pc.P], anticollision=True, cmd_prefix='homing P ')
        self.schedule_moves(anticollision=True)
        retraction_time = self.schedule.total_scheduled_time()
        for p in posmodels:
            dir[pc.T] = p.axis[pc.T].principle_hardstop_direction
            self.request_limit_seek(p, pc.T, dir[pc.T], anticollision=False, cmd_prefix='homing T ')
            for i in [pc.T,pc.P]:
                axis_cmd_prefix = 'self.axis[' + repr(i) + ']'
                if dir[i] < 0:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[0]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + '.minpos\n'
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = -1.0\n'
                else:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[1]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + '.maxpos\n'
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = +1.0\n'
                p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.total_limit_seeks += 1\n'
            self.request_direct_dtdp(p, hardstop_debounce[pc.T], hardstop_debounce[pc.P], cmd_prefix='debounce ')

    def schedule_moves(self,anticollision=True):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available flag to turn the
        anticollision algorithm on or off for the scheduling.
        """
        anticollision = False # temporary, since algorithm is not yet implemented in PosSchedule
        self.schedule.schedule_moves(anticollision)

    def schedule_send_and_execute_moves(self):
        """Convenience wrapper to schedule, send, execute, and cleanup.
        """
        self.schedule_moves()
        self.send_and_execute_moves()

    def send_and_execute_moves(self):
        """Convenience wrapper to send, execute, and cleanup.
        """
        hw_tables = self.hardware_ready_move_tables()
        self.comm.send_tables(hw_tables) # return values? threaded with pyro somehow?
        self.comm.set_led(13,'on')
        print(hw_tables)
        self.comm.execute_sync('soft') # return values? threaded with pyro somehow?
        self.postmove_cleanup()

    def postmove_cleanup(self):
        """Always call this after performing a set of moves, so that PosModel instances
        can be informed that the hardware move was done.
        """
        for m in self.schedule.move_tables:
            m.posmodel.postmove_cleanup(m.for_cleanup)
        print(self.expected_current_position_str())
        self.clear_schedule()

    def clear_schedule(self):
        self.schedule = posschedule.PosSchedule(self)

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

                canid         ... unsigned integer          ... identifies the positioner by 'CAN_ID'
                nrows         ... unsigned integer          ... number of elements in each of the list fields (i.e. number of rows of the move table)
                motor_steps_T ... list of signed integers   ... number of motor steps to rotate on theta axis
                                                                    ... motor_steps_T > 0 ... ccw rotation
                                                                    ... motor_steps_T < 0 ... cw rotation
                motor_steps_P ... list of signed integers   ... number of motor steps to rotate on phi axis
                                                                    ... motor_steps_P > 0 ... ccw rotation
                                                                    ... motor_steps_P < 0 ... cw rotation
                speed_mode_T  ... list of strings           ... 'cruise' or 'creep' mode on theta axis
                speed_mode_P  ... list of strings           ... 'cruise' or 'creep' mode on phi axis
                movetime      ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
                postpause     ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
        """
        hw_tables = []
        for m in self.schedule.move_tables:
            hw_tbl = m.for_hardware
            hw_tables.append(hw_tbl)
        return hw_tables

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
            m.get('XXXXX',['POS_T','POS_P']) # gets these values for positioner XXXXX
            m.get(['XXXXX','YYYYY'],'PETAL_ID') # gets PETAL_ID value for positioners XXXXX and YYYYY
            m.get(['XXXXX','YYYYY'],['FINAL_CREEP_ON','DEVICE_ID']) # gets multiple different values on multiple different positioners
            m.get(key=['POS_T']) # gets this value for all positioners identified in posids
            m.get() # gets all posmodel objects for all positioners identified in posids
        """
        (posid, was_not_list) = self._posid_listify_and_fill(posid)
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
            m.set(key=['POS_T','POS_P'],value=[0,180]) # sets these values for all positioners identified in posids
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
            p = self.get_model_for_pos(posid[i])
            p.state.write(key[i],value[i],write_to_disk)

    def get_model_for_pos(self, pos):
        """Returns the posmodel object corresponding to a posid, or if the argument
        is a posmodel, just returns itself.
        """
        if isinstance(pos, posmodel.PosModel):
            return pos
        else:
            pidx = self.posids.index(pos)
            return self.posmodels[pidx]

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
        (posid, was_not_list) = self._posid_listify_and_fill(posid)
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
        (posid, was_not_list) = self._posid_listify_and_fill(posid)
        strs = []
        for p in posid:
            pidx = self.posids.index(p)
            strs.append(self.posmodels[pidx].expected_current_position_str)
        if was_not_list:
            strs = pc.delistify(strs)
        return strs

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
