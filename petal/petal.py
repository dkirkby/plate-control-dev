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
        fid_ids     ... list of fiducials unique id strings
    """
    def __init__(self, petal_id, pos_ids, fid_ids, simulator_on=False, printfunc=print):
        # petal setup
        self.petal_id = petal_id
        self.verbose = False # whether to print verbose information at the terminal
        self.simulator_on = simulator_on # controls whether in software-only simulation mode
        if not(self.simulator_on):
            import petalcomm
            self.comm = petalcomm.PetalComm(self.petal_id)
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)

        # positioners setup
        self.posmodels = []
        for pos_id in pos_ids:
            state = posstate.PosState(pos_id, logging=True, device_type='pos', printfunc=self.printfunc)
            model = posmodel.PosModel(state)
            self.posmodels.append(model)
        self.posids = pos_ids
        self.schedule = posschedule.PosSchedule(self)
        self.sync_mode = 'soft' # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        self.anticollision_default = True  # default parameter on whether to schedule moves with anticollision, if not explicitly argued otherwise
        self.anticollision_override = True # causes the anticollision_default value to be used in all cases
        self.canids_where_tables_were_just_sent = []
        self.busids_where_tables_were_just_sent = []
        self.set_motor_parameters()
        
        # fiducials setup
        self.fidstates = {}
        for fid_id in fid_ids:
            state = posstate.PosState(fid_id, logging=False, device_type='fid', printfunc=self.printfunc)
            self.fidstates[fid_id] = state
        
        # power suppliees setup?
        # to-do
        
        # fans setup?
        # to-do
        
        # sensors setup?
        # to-do

 
# METHODS FOR POSITIONER CONTROL

    def request_targets(self, requests):
        """Put in requests to the scheduler for specific positioners to move to specific targets.
        
        This method is for requesting that each robot does a complete repositioning sequence to get
        to the desired target. This means:

            - Anticollision is possible. (See schedule_moves method.)
            - Only one requested target per positioner.
            - Theta angles are wrapped across +/-180 deg
            - Contact of hard limits is prevented.
        
        INPUT:
            requests ... dictionary of dictionaries
            
                dictionary format:
                
                    key     ... pos_id (referencing a single subdictionary for that positioner)
                    value   ... subdictionary (see below)

                subdictionary format:
                
                    KEYS        VALUES
                    ----        ------
                    command     move command string
                                    ... valid values are 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
                    target      pair of target coordinates or deltas, of the form [u,v]
                                    ... the elements u and v can be floats or integers
                                    ... 1st element (u) is the value for q, dq, x, dx, t, or dt
                                    ... 2nd element (v) is the value for s, ds, y, dy, p, or dp
                    log_note    optional string to store alongside in the log data for this move
                                    ... gets stored in the 'NOTE' field
                                    ... if the subdict contains no note field, then '' will be added automatically
            
        OUTPUT:
            Same dictionary, but with the following new entries in each subdictionary:
            
                    KEYS        VALUES
                    ----        ------
                    posmodel    object handle for the posmodel corresponding to pos_id
                    log_note    same as log_note above, or '' is added automatically if no note was argued in requests
            
            In cases where this is a second request to the same robot (which is not allowed), the
            subdictionary will be deleted from the return.
            
            In cases where the request was made to a disabled positioner, the subdictionary will be
            deleted from the return.
        """
        mark_for_delete = set()
        for pos_id in requests.keys():
            requests[pos_id]['posmodel'] = self.get_model_for_pos(pos_id)
            if 'log_note' not in requests[pos_id]:
                requests[pos_id]['log_note'] = ''
            if not(self.get(pos_id,'CTRL_ENABLED')):
                self.printfunc(self._request_denied_disabled_str(pos_id,requests[pos_id]))
                mark_for_delete.add(pos_id)
            elif self.schedule.already_requested(requests[pos_id]['posmodel']):
                self.printfunc('Positioner ' + str(pos_id) + ' already has a target scheduled. Extra target request ' + self._target_str(requests[pos_id]) + ' ignored.')
                mark_for_delete.add(pos_id)
            else:
                self.schedule.request_target(requests[pos_id]['posmodel'], requests[pos_id]['command'], requests[pos_id]['target'][0], requests[pos_id]['target'][1], requests[pos_id]['log_note'])
        for pos_id in mark_for_delete:
            del requests[pos_id]
        return requests

    def request_direct_dtdp(self, requests, cmd_prefix=''):
        """Put in requests to the scheduler for specific positioners to move by specific rotation
        amounts at their theta and phi shafts.

        This method is generally recommended only for expert usage.

            - Anticollision is disabled.
            - Multiple moves allowed per positioner.
            - Theta angles are not wrapped across +/-180 deg
            - Contact of hard limits is allowed.

        INPUT:
            requests ... dictionary of dictionaries
            
                dictionary format:
                
                    key     ... pos_id (referencing a single subdictionary for that positioner)
                    value   ... subdictionary (see below)

                subdictionary format:
                
                    KEYS        VALUES
                    ----        ------
                    target      pair of target deltas, of the form [dT,dP]
                                    ... the elements dT and dP can be floats or integers
                    log_note    optional string to store alongside in the log data for this move
                                    ... gets embedded in the  in the 'NOTE' field
                                    ... if the subdict contains no note field, then '' will be added automatically
            
            cmd_prefix ... Optional argument, allows embedding a descriptive string to the log, embedded
                           in the 'LAST_MOVE_CMD' field. This is different from log_note. Generally,
                           log_note is meant for users, whereas cmd_prefix is meant for internal lower-
                           level detailed logging.

        OUTPUT:
            Same dictionary, but with the following new entries in each subdictionary:
            
                    KEYS        VALUES
                    ----        ------
                    command     'direct_dTdP'
                    posmodel    object handle for the posmodel corresponding to pos_id
                    log_note    same as log_note above, or '' is added automatically if no note was argued in requests
                    
            In cases where the request was made to a disabled positioner, the subdictionary will be
            deleted from the return.
            
        It is allowed to repeatedly request_direct_dtdp on the same positioner, in cases where one
        wishes a sequence of theta and phi rotations to all be done in one shot. (This is unlike the
        request_targets command, where only the first request to a given positioner would be valid.)
        """
        mark_for_delete = set()
        for pos_id in requests.keys():
            if not(self.get(pos_id,'CTRL_ENABLED')):
                self.printfunc(self._request_denied_disabled_str(pos_id,requests[pos_id]))
                mark_for_delete.add(pos_id)
        for pos_id in mark_for_delete:
            del requests[pos_id]
        for pos_id in requests.keys():
            requests[pos_id]['posmodel'] = self.get_model_for_pos(pos_id)
            if 'log_note' not in requests[pos_id]:
                requests[pos_id]['log_note'] = ''
            table = posmovetable.PosMoveTable(requests[pos_id]['posmodel'])
            table.set_move(0, pc.T, requests[pos_id]['target'][0])
            table.set_move(0, pc.P, requests[pos_id]['target'][1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'direct_dtdp'
            table.store_orig_command(0,cmd_str,requests[pos_id]['target'][0],requests[pos_id]['target'][1])
            table.log_note += (' ' if table.log_note else '') + requests[pos_id]['log_note']
            table.allow_exceed_limits = True
            self.schedule.add_table(table)
        return requests            

    def request_limit_seek(self, pos, axisid, direction, anticollision=True, cmd_prefix='', log_note=''):
        """Request hardstop seeking sequence for positioners in list pos.
        The optional argument cmd_prefix allows adding a descriptive string to the log.
        This method is generally recommended only for expert usage.
        Requests to disabled positioners will be ignored.
        """
        pos = pc.listify(pos,True)[0]
        posmodels = []
        for p in pos:
            posmodel = self.get_model_for_pos(p)
            if posmodel.state.read('CTRL_ENABLED'):
                posmodels.append(posmodel)
            else:
                self.printfunc('Positioner ' + str(posmodel.state.read('POS_ID')) + ' is disabled. Limit seek request ignored.')
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
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'limit seek'
            table.store_orig_command(0,cmd_str,direction*(axisid == pc.T),direction*(axisid == pc.P))
            table.log_note += (' ' if table.log_note else '') + log_note
            p.axis[axisid].postmove_cleanup_cmds += 'self.axis[' + repr(axisid) + '].total_limit_seeks += 1\n'
            axis_cmd_prefix = 'self.axis[' + repr(axisid) + ']'
            if direction < 0:
                direction_cmd_suffix = '.minpos\n'
            else:
                direction_cmd_suffix = '.maxpos\n'
            p.axis[axisid].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + direction_cmd_suffix
            self.schedule.add_table(table)

    def request_homing(self, pos):
        """Request homing sequence for positioners in list pos to find the primary hardstop
        and set values for the max position and min position.
        Requests to disabled positioners will be ignored.
        """
        pos = pc.listify(pos,True)[0]
        posmodels = []
        for p in pos:
            posmodel = self.get_model_for_pos(p)
            if posmodel.state.read('CTRL_ENABLED'):
                posmodels.append(posmodel)
            else:
                self.printfunc('Positioner ' + str(posmodel.state.read('POS_ID')) + ' is disabled. Homing request ignored.')
        hardstop_debounce = [0,0]
        direction = [0,0]
        direction[pc.P] = +1 # force this, because anticollision logic depends on it
        for p in posmodels:
            self.request_limit_seek(p, pc.P, direction[pc.P], anticollision=True, cmd_prefix='P', log_note='homing')
        self.schedule_moves(anticollision=True)
        for p in posmodels:
            direction[pc.T] = p.axis[pc.T].principle_hardstop_direction
            self.request_limit_seek(p, pc.T, direction[pc.T], anticollision=False, cmd_prefix='T') # no repetition of log note here
            pos_id = self.posids[self.posmodels.index(p)]                      
            for i in [pc.T,pc.P]:
                axis_cmd_prefix = 'self.axis[' + repr(i) + ']'
                if direction[i] < 0:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[0]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = -1.0\n'
                else:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[1]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = +1.0\n'
                hardstop_debounce_request = {pos_id:{'target':hardstop_debounce}}
                self.request_direct_dtdp(hardstop_debounce_request, cmd_prefix='debounce')

    def schedule_moves(self,anticollision=None):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available boolean to turn the
        anticollision algorithm on or off for the scheduling. If that flag is
        None, then the default anticollision parameter is used.
        """
        if anticollision == None or self.anticollision_override:
            anticollision = self.anticollision_default
        # Should add here gathering list of all the disabled positioners and generating false zero-distance
        # move requests? to get them into the anticollision? Will this need any special flag known to anti-
        # collision, to make sure it knows these are fixed, and can't for example move out of a neighbor's
        # way, then back to where it started.
        self.schedule.schedule_moves(anticollision)

    def send_move_tables(self):
        """Send move tables that have been scheduled out to the positioners.
        """
        if self.simulator_on:
            if self.verbose:
                print('Simulator skips sending move tables to positioners.')
            return
        hw_tables = self._hardware_ready_move_tables()
        canids = []
        busids = []
        for tbl in hw_tables:
            canids.append(tbl['canid'])
            busids.append(tbl['busid'])
        self.canids_where_tables_were_just_sent = canids
        self.busids_where_tables_were_just_sent = busids
        self._wait_while_moving()
        self.comm.send_tables(hw_tables)

    def set_motor_parameters(self):
        """Send the current and period parameter settings to the positioners"""
        # Set the duty cycle currents and creep or accel/decel speeds.
        # Currently this function needs to be called each time parameters change after petal
        # initialization or if a positioner is plugged in/powered on after petal initialization
        if self.simulator_on:
            if self.verbose:
                print('Simulator skips sending motor parameters to positioners.')
            return
        parameter_keys = ['CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CURR_HOLD', 'CREEP_PERIOD','SPINUPDOWN_PERIOD']
        for p in self.posmodels:
            state = p.state
            can_id = p.canid
            bus_id = p.busid
            parameter_vals = []
            for parameter_key in parameter_keys:
                parameter_vals.append(state.read(parameter_key))
            #syntax for setting currents: comm.set_currents(can_id, [curr_spin_p, curr_cruise_p, curr_creep_p, curr_hold_p], [curr_spin_t, curr_cruise_t, curr_creep_t, curr_hold_t])
            self.comm.set_currents(bus_id, can_id, [parameter_vals[0], parameter_vals[1], parameter_vals[2], parameter_vals[3]], [parameter_vals[0], parameter_vals[1], parameter_vals[2], parameter_vals[3]])
            #syntax for setting periods: comm.set_periods(can_id, creep_period_p, creep_period_t, spin_period)
            self.comm.set_periods(bus_id, can_id, parameter_vals[4], parameter_vals[4], parameter_vals[5])
            vals_str =  [' ' + parameter_keys[i] + '=' + str(parameter_vals[i]) for i in range(len(parameter_keys))]
            self.printfunc(p.posid + ' (bus=' + str(bus_id) + ', canid=' + str(can_id) + '): motor currents and periods set:' + vals_str)

    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        """
        if self.simulator_on:
            if self.verbose:
                print('Simulator skips sending execute moves command to positioners.')
            self._postmove_cleanup()
        else:
            self.comm.execute_sync(self.sync_mode)
            self._postmove_cleanup()
            self._wait_while_moving()
        self.canids_where_tables_were_just_sent = []
        self.busids_where_tables_were_just_sent = []

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

    def quick_move(self, pos_ids, command, target, log_note=''):
        """Convenience wrapper to request, schedule, send, and execute a single move command, all in
        one shot. You can argue multiple pos_ids if you want (as a list), though note they will all
        get the same command and target sent to them. So for something like a local (theta,phi) coordinate
        this often makes sense, but not for a global coordinate.

        INPUTS:     pos_ids   ... either a single pos_id or a list of pos_ids
                    command   ... string like those usually put in the requests dictionary (see request_targets method)
                    target    ... [u,v] values, note that all positioners here get sent the same [u,v] here
                    log_note  ... optional string to include in the log file
        """
        requests = {}
        pos_ids = pc.listify(pos_ids,True)[0]
        for pos_id in pos_ids:
            requests[pos_id] = {'command':command, 'target':target, 'log_note':log_note}
        self.request_targets(requests)
        self.schedule_send_and_execute_moves()

    def quick_direct_dtdp(self, pos_ids, dtdp, log_note=''):
        """Convenience wrapper to request, schedule, send, and execute a single move command for a
        direct (delta theta, delta phi) relative move. There is NO anti-collision calculation. This
        method is intended for expert usage only. You can argue multiple pos_ids if you want (as a
        list), though note they will all get the same (dt,dp) sent to them.
        
        INPUTS:     pos_ids   ... either a single pos_id or a list of pos_ids
                    dtdp      ... [dt,dp], note that all pos_ids get sent the same [dt,dp] here. i.e. dt and dp are each just one number
                    log_note  ... optional string to include in the log file
        """
        requests = {}
        pos_ids = pc.listify(pos_ids,True)[0]
        for pos_id in pos_ids:
            requests[pos_id] = {'target':dtdp, 'log_note':log_note}
        self.request_direct_dtdp(requests)
        self.schedule_send_and_execute_moves()

    def clear_schedule(self):
        """Clear out any existing information in the move schedule.
        """
        self.schedule = posschedule.PosSchedule(self)

# METHODS FOR FIDUCIAL CONTROL        
    def set_fiducials(self, fid_ids='all', setting='on', save_as_default=False):
        """Set a list of specific fiducials on or off.
        
        fid_ids ... 1 fiducial id string, or a list of fiducial id strings, or 'all'
        
        setting ... what to set the fiducials to, as described below:
            'on'         ... turns each fiducial to its default on value
            'off'        ... turns each fiducial individually to its default off value
            int or float ... a single integer or float from 0-100 sets all the argued fiducials uniformly to that one value
        
        save_as_default ... only used when seting is a number, in which case True means we will store that setting permanently to the fiducials' config file, False means its just a temporary setting this time
        
        Method returns a dictionary of all the settings that were made, where
            key   --> fiducial ids
            value --> duty state that was set
        Fiducials that do not have control enabled would not be in this dictionary.
        """
        if self.simulator_on:
            if self.verbose:
                print('Simulator skips sending out set_fiducials commands.')
            return {}
        fid_ids = pc.listify(fid_ids,keep_flat=True)[0]
        if fid_ids[0] == 'all':
            fid_ids = self.fid_ids
        bus_ids = self.get_fids_val(fid_ids,'BUS_ID')
        can_ids = self.get_fids_val(fid_ids,'CAN_ID')
        if isinstance(setting,int) or isinstance(setting,float):
            if setting < 0:
                setting = 0
            if setting > 100:
                setting = 100
            duties = [setting]*len(fid_ids)
        elif setting == 'on':
            duties = self.get_fids_val(fid_ids,'DUTY_DEFAULT_ON')
        else:
            duties = self.get_fids_val(fid_ids,'DUTY_DEFAULT_OFF')
        enabled = self.get_fids_val(fid_ids,'CTRL_ENABLED')
        rng = range(len(fid_ids))
        fid_ids = [fid_ids[i] for i in rng if enabled[i]]
        bus_ids = [bus_ids[i] for i in rng if enabled[i]]
        can_ids = [can_ids[i] for i in rng if enabled[i]]
        duties  = [duties[i]  for i in rng if enabled[i]]
        self.comm.set_fiducials(bus_ids, can_ids, duties)
        settings_done = {}
        for i in range(len(fid_ids)):
            self.fidstates[fid_ids[i]].write('DUTY_STATE',duties[i])
            settings_done[fid_ids[i]] = duties[i]
            if save_as_default:
                self.fidstates[fid_ids[i]].write('DUTY_DEFAULT_ON',duties[i])
            self.fidstates[fid_ids[i]].log_unit()
        return settings_done
    
    @property
    def n_fiducial_dots(self):
        """Returns number of fixed fiducial dots this petal contributes in the field of view.
        """
        n_dots = self.get_fids_val(self.fid_ids,'N_DOTS')
        return sum(n_dots)
    
    @property
    def fiducial_dots_fvcXY(self):
        """Returns a list of all [x,y] positions of all fiducial dots this petal contributes
        in the field of view. List is of the form [[x1,y1],[x2,y2],...]. The coordinates
        are all given in fiber view camera pixel space.
        """
        x = []
        y = []
        for fid_id in self.fid_ids:
            x.extend(self.get_fids_val(fid_id,'DOTS_FVC_X')[0])
            y.extend(self.get_fids_val(fid_id,'DOTS_FVC_Y')[0])
        xy = [[x[i],y[i]] for i in range(len(x))]
        return xy

    @property
    def fid_ids(self):
        """Returns a list of all the fiducial ids on the petal.
        """
        return list(self.fidstates.keys())

    def fid_bus_ids(self,fid_ids):
        """Returns a list of bus ids where you find each of the fiducials (identified
        in the list fid_ids). These come back in the same order.
        """
        return self.get_fids_val(fid_ids,'BUS_ID')
    
    def fid_can_ids(self,fid_ids):
        """Returns a list of can ids where each fiducial (identified in the list
        fid_ids) is addressed on its bus. These come back in the same order.
        """
        return self.get_fids_val(fid_ids,'CAN_ID')
    
    def fid_default_duties(self,fid_ids):
        """Returns a list of default duty percent settings which each fiducial (identified
        in the list fid_ids) is supposed to be set to when turning it on.
        """
        return self.get_fids_val(fid_ids,'DUTY_DEFAULT_ON')
    
    def get_fids_val(self,fid_ids,key):
        """Returns a list of the values for string key, for all fiducials identified
        in the list fid_ids.
        """
        vals = []
        fid_ids = pc.listify(fid_ids,keep_flat=True)[0]
        for fid_id in fid_ids:
            vals.append(self.fidstates[fid_id].read(key))
        return vals


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

    def set(self,posid=None,key=None,value=None):
        """Set the state value identified by string key, for positioner unit
        identified by id posid.

        If no posid is specified, value is set for all positioners.

        If posid is a list of multiple positioner ids, then this method can handle
        setting multiple values. The other arguments can either:
            ... also be lists, of same length as posid
            ... or just a single value, which gets applied uniformly to all posid.

        Examples:
            m = posarraymaster.PosArrayMaster(posids)
            m.set('XXXXX','LENGTH_R1',3.024) # sets LENGTH_R1 value for positioner XXXXX
            m.set(['XXXXX','YYYYY'],'PETAL_ID',2) # sets PETAL_ID value for positioners XXXXX and YYYYY
            m.set(['XXXXX','YYYYY'],['FINAL_CREEP_ON','DEVICE_ID'],[False,227]) # sets multiple different values on multiple different positioners
            m.set(key=['POS_T','POS_P'],value=[0,180]) # sets these values for all positioners identified in posids
        """
        if key == None or value == None:
            self.printfunc('either no key or no value was specified to setval')
            return
        (posid, temp) = self._posid_listify_and_fill(posid)
        (key,   temp) = pc.listify(key,keep_flat=True)
        (value, temp) = pc.listify(value,keep_flat=True)
        (posid, key)   = self._equalize_input_list_lengths(posid,key)
        (posid, value) = self._equalize_input_list_lengths(posid,value)
        (posid, key)   = self._equalize_input_list_lengths(posid,key) # repetition here handles the case where there was 1 posid element, 1 key, but mulitplie elements in value
        for i in range(len(posid)):
            p = self.get_model_for_pos(posid[i])
            p.state.write(key[i],value[i])

    def expected_current_position(self,posid=None,key=''):
        """Retrieve the current position, for a positioner identied by posid, according
        to the internal tracking of its posmodel object. Valid keys are:
            'Q', 'S', 'flatX', 'flatY', 'obsX', 'obsY', 'obsT', 'obsP', 'posT', 'posP', 'motT', 'motP'
            'QS','flatXY','obsXY','obsTP','posTP','motTP'
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
            elif key[i] == 'posTP':
                vals.append([this_val['posT'],this_val['posP']])
            elif key[i] == 'motorTP':
                vals.append([this_val['motT'],this_val['motP']])
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

    def _wait_while_moving(self):
        """Blocking implementation, to not send move tables while any positioners are still moving.

        Inputs:     canids ... integer CAN id numbers of all the positioners to check whether they are moving

        The implementation has the benefit of simplicity, but it is acknowledged there may be 'better',
        i.e. multi-threaded, ways to achieve this, to be implemented later.
        """
        if self.simulator_on:
            return        
        timeout = 15.0 # seconds
        poll_period = 0.5 # seconds
        keep_waiting = True
        start_time = time.time()
        while keep_waiting:
            elapsed_time = time.time() - start_time
            if elapsed_time >= timeout:
                self.printfunc('Timed out at ' + str(timeout) + ' seconds waiting for positioners to be ready to receive next commands.')
                keep_waiting = False
            if self.comm.ready_for_tables(self.busids_where_tables_were_just_sent, self.canids_where_tables_were_just_sent):
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
    
    def _target_str(self, target_request_dict): 
        """Makes a human readable string describing a target request dictionary.
        """
        cmd = str(target_request_dict['command'])
        val1 = format(target_request_dict['target'][0],'.3f')
        val2 = format(target_request_dict['target'][1],'.3f')
        return cmd + '(' + val1 + ',' + val2 + ')'
        
    def _request_denied_disabled_str(self, pos_id, target_request_dict):
        return 'Positioner ' + str(pos_id) + ' is disabled. Target request ' + self._target_str(target_request_dict) + ' ignored.'
        