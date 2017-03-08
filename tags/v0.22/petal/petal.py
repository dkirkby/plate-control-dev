import petalcomm
import posmodel
import posschedule
import posmovetable
import posstate
import posconstants as pc
import numpy as np
import time

class Petal(object):
    """Controls a petal. Communicates with the PetalBox hardware via PetalComm.

    The general sequence to make postioners move is:
        1. request all the desired moves from all the desired positioners
        2. schedule the moves (anti-collision and anti-backlash are automatically calculated here)
        3. send the scheduled move tables out to the positioners
        4. execute the move tables (synchronized start on all the positioners at once.

    Convenience wrapper functions are provided to combine these steps when desirable.

    Initialization inputs:
        petal_id    ... integer id number of the petal
        pos_ids     ... list of positioner unique id strings
        fid_ids     ... list of fiducials ids -- as of April 2016, these are just CAN ids -- this will be changed to unique id strings at a later date

    As of April 2016, the implementation for handling fiducials is kept as simple as possible, for the
    purpose of running test stands only. Later implementations should track fiducials' physical hardware
    by unique id number, log expected and measured positions, log cycles and total on time, etc.
    """
    def __init__(self, petal_id, pos_ids, fid_ids):
        self.verbose = False # whether to print verbose information at the terminal
        self.petal_id = petal_id
        self.comm = petalcomm.PetalComm(self.petal_id)
        self.posmodels = []
        for pos_id in pos_ids:
            state = posstate.PosState(pos_id,logging=True)
            model = posmodel.PosModel(state)
            self.posmodels.append(model)
        self.posids = pos_ids
        self.schedule = posschedule.PosSchedule(self)
        self.sync_mode = 'soft' # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        self.anticollision_default = True # default parameter on whether to schedule moves with anticollision, if not explicitly argued otherwise
        self.anticollision_override = True # causes the anticollision_default value to be used in all cases
        self.canids_where_tables_were_just_sent = []
        self.fid_can_ids = fid_ids # later, implement auto-lookup of pos_ids and fid_ids from database etc
        self.fid_duty_percent = 50 # 0-100 -- later, implement setting on a fiducial-by-fiducial basis
        self.fid_duty_period  = 55 # milliseconds -- later, implement setting on a fiducial-by-fiducial basis

# METHODS FOR POSITIONER CONTROL

    def request_targets(self, pos, commands, values):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for requests to perform complete repositioning sequence to get
        to the targets.

            - Anticollision is enabled.
            - Only one requested target per positioner.
            - Theta angles are wrapped across +/-180 deg
            - Contact of hard limits is prevented.

        INPUTS:
            pos      ... list of positioner ids
            commands ... corresponding list of move command strings, each element is 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
            values   ... corresponding list of move arguements, in the form [[u1,v1],[u2,v2],...]
                         ... 1st move arguments are values for q, dq, x, dx, t, or dt
                         ... 2nd move arguments are values for s, ds, y, dy, p, or dp

        It is allowed to argue a list of positioner ids, and only one command and one value. Then
        this command and value will be done identically on all the positioners.
        """
        pos = pc.listify(pos,True)[0]
        commands = pc.listify(commands,True)[0]
        values = pc.listify2d(values)
        if len(commands) != len(pos):
            commands = [commands[0]]*len(pos)
        if len(values) != len(pos):
            values = [values[0]]*len(pos)
        for i in range(len(pos)):
            posmodel = self.get_model_for_pos(pos[i])
            if self.schedule.already_requested(posmodel):
                print('Positioner ' + str(posmodel.posid) + ' already has a target scheduled. Extra target request ' + str(commands[i]) + '(' + str(values[i][0]) + ',' + str(values[i][1]) + ') ignored')
            else:
                self.schedule.request_target(posmodel, commands[i], values[i][0], values[i][1])

    def request_direct_dtdp(self, pos, dtdp, cmd_prefix=''):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for direct requests of rotations by the theta and phi shafts.
        This method is generally recommended only for expert usage.

            - Anticollision is disabled.
            - Multiple moves allowed per positioner.
            - Theta angles are not wrapped across +/-180 deg
            - Contact of hard limits is allowed.

        INPUTS:
            pos   ... list of positioner ids
            dtdp  ... corresponding list of delta theta and delta phi values
                      ... list is in the form [[dt1,dp1],[dt2,dp2],...]

        The optional argument cmd_prefix allows adding a descriptive string to the log.
        
        It is allowed to argue a list of positioner ids, and only one dtdp. Then this
        identical dtdp will be done on all the positioners.
        """
        pos = pc.listify(pos,True)[0]
        dtdp = pc.listify2d(dtdp)
        if len(dtdp) != len(pos):
            dtdp = [dtdp[0]]*len(pos)
        for i in range(len(pos)):
            posmodel = self.get_model_for_pos(pos[i])
            table = posmovetable.PosMoveTable(posmodel)
            table.set_move(0, pc.T, dtdp[i][0])
            table.set_move(0, pc.P, dtdp[i][1])
            table.store_orig_command(0,cmd_prefix + 'direct_dtdp',dtdp[i][0],dtdp[i][1])
            table.allow_exceed_limits = True
            self.schedule.add_table(table)

    def request_limit_seek(self, pos, axisid, direction, anticollision=True, cmd_prefix=''):
        """Request hardstop seeking sequence for positioners in list pos.
        The optional argument cmd_prefix allows adding a descriptive string to the log.
        This method is generally recommended only for expert usage.
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
            p.axis[axisid].postmove_cleanup_cmds += 'self.axis[' + repr(axisid) + '].total_limit_seeks += 1\n'
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
        # retraction_time = self.schedule.total_scheduled_time()
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
            self.request_direct_dtdp(p, hardstop_debounce, cmd_prefix='debounce ')

    def schedule_moves(self,anticollision=None):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available boolean to turn the
        anticollision algorithm on or off for the scheduling. If that flag is
        None, then the default anticollision parameter is used.
        """
        if anticollision == None or self.anticollision_override:
            anticollision = self.anticollision_default
        self.schedule.schedule_moves(anticollision)

    def send_move_tables(self):
        """Send move tables that have been scheduled out to the positioners.
        """
        hw_tables = self._hardware_ready_move_tables()
        canids = []
        for tbl in hw_tables:
            canids.append(tbl['canid'])
        self.canids_where_tables_were_just_sent = canids
        self._wait_while_moving()
        self.comm.send_tables(hw_tables)

    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        """
        self.comm.execute_sync(self.sync_mode)
        self._wait_while_moving()
        self._postmove_cleanup()

    def quick_move(self, pos, commands, values):
        """Convenience wrapper to request, schedule, send, and execute a list of moves
        to a list of positioners, all in one shot.
        """
        self.request_targets(pos, commands, values)
        self.schedule_send_and_execute_moves()

    def quick_dtdp(self, pos, dtdp, cmd_prefix=''):
        """Convenience wrapper to request, schedule, send, and execute a list of direct
        delta theta, delta phi moves. There is NO anti-collision calculation. This
        method is intended for expert usage only.
        """
        self.request_direct_dtdp(pos, dtdp, cmd_prefix)
        self.schedule_send_and_execute_moves()

    def schedule_send_and_execute_moves(self):
        """Convenience wrapper to schedule, send, and execute the pending requested
        moves, all in one shot.
        """
        self.schedule_moves()
        self.send_and_execute_moves()

    def send_and_execute_moves(self):
        """Convenience wrapper to send and execute the pending moves (that have already
        been scheduled).
        """
        self.send_move_tables()
        self.execute_moves()

    def clear_schedule(self):
        """Clear out any existing information in the move schedule.
        """
        self.schedule = posschedule.PosSchedule(self)

# METHODS FOR FIDUCIAL CONTROL

    def fiducials_on(self):
        """Turn all the fiducials on.
        """
        duty_percents = [self.fid_duty_percent]*len(self.fid_can_ids)
        duty_periods = [self.fid_duty_period]*len(self.fid_can_ids)
        self.comm.set_fiducials(self.fid_can_ids, duty_percents, duty_periods)

    def fiducials_off(self):
        """Turn all the fiducials off.
        """
        duty_percents = [0]*len(self.fid_can_ids)
        duty_periods = [self.fid_duty_period]*len(self.fid_can_ids)
        self.comm.set_fiducials(self.fid_can_ids, duty_percents, duty_periods)

# GETTERS, SETTERS, STATUS METHODS

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

    def expected_current_position(self,posid=None,key=''):
        """Retrieve the current position, for a positioner identied by posid, according
        to the internal tracking of its posmodel object. Valid keys are:
            'Q', 'S', 'flatX', 'flatY', 'obsX', 'obsY', 'obsT', 'obsP', 'shaftT', 'shaftP', 'motorT', 'motorP'
            'QS','flatXY','obsXY','obsTP','shaftTP','motorTP'
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
            elif key[i] == 'QS':
                vals.append([this_val['Q'],this_val['S']])
            elif key[i] == 'flatXY':
                vals.append([this_val['flatX'],this_val['flatY']])
            elif key[i] == 'obsXY':
                vals.append([this_val['obsX'],this_val['obsY']])
            elif key[i] == 'obsTP':
                vals.append([this_val['obsT'],this_val['obsP']])
            elif key[i] == 'shaftTP':
                vals.append([this_val['shaftT'],this_val['shaftP']])
            elif key[i] == 'motorTP':
                vals.append([this_val['motorT'],this_val['motorP']])
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

    def get_model_for_pos(self, pos):
        """Returns the posmodel object corresponding to a posid, or if the argument
        is a posmodel, just returns itself.
        """
        if isinstance(pos, posmodel.PosModel):
            return pos
        else:
            pidx = self.posids.index(pos)
            return self.posmodels[pidx]

# INTERNAL METHODS

    def _hardware_ready_move_tables(self):
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
                move_time     ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
                postpause     ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
        """
        hw_tables = []
        for m in self.schedule.move_tables:
            hw_tbl = m.for_hardware
            hw_tables.append(hw_tbl)
        return hw_tables

    def _postmove_cleanup(self):
        """This always gets called after performing a set of moves, so that PosModel instances
        can be informed that the move was physically done on the hardware.
        """
        for m in self.schedule.move_tables:
            m.posmodel.postmove_cleanup(m.for_cleanup)
        if self.verbose:
            print(self.expected_current_position_str())
        self.clear_schedule()
        self.canids_where_tables_were_just_sent = []

    def _wait_while_moving(self):
        """Blocking implementation, to not send move tables while any positioners are still moving.

        Inputs:     canids ... integer CAN id numbers of all the positioners to check whether they are moving

        The implementation has the benefit of simplicity, but it is acknowledged there may be 'better',
        i.e. multi-threaded, ways to achieve this, to be implemented later.
        """
        timeout = 30.0 # seconds
        poll_period = 0.5 # seconds
        keep_waiting = True
        start_time = time.time()

        while keep_waiting:

            if (time.time()-start_time) >= timeout:
                print('Timed out at ' + str(timeout) + ' seconds waiting to send next move table.')
                keep_waiting = False

            if self.comm.ready_for_tables(self.canids_where_tables_were_just_sent):
                keep_waiting = False
             
            else:

                time.sleep(poll_period)

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