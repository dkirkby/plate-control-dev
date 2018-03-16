import posmodel
import posschedule
import posmovetable
import posstate
import poscollider
import posconstants as pc
import numpy as np
import time
import collections
import os
try:
    from DBSingleton import * 
    DB_COMMIT_AVAILABLE = True
except:
    DB_COMMIT_AVAILABLE = False

class Petal(object):
    """Controls a petal. Communicates with the PetalBox hardware via PetalComm.

    The general sequence to make postioners move is:
        1. request all the desired moves from all the desired positioners
        2. schedule the moves (anti-collision and anti-backlash are automatically calculated here)
        3. send the scheduled move tables out to the positioners
        4. execute the move tables (synchronized start on all the positioners at once.

    Convenience wrapper functions are provided to combine these steps when desirable.

    Required initialization inputs:
        petal_id     ... integer id number of the petal
        posids       ... list of positioner unique id strings
        fidids       ... list of fiducials unique id strings
        
    Optional initialization inputs:
        simulator_on    ... boolean, controls whether in software-only simulation mode
        db_commit_on    ... boolean, controls whether to commit state data to the online system database (can be done with or without local_commit_on (available only if DB_COMMIT_AVAILABLE == True))
        local_commit_on ... boolean, controlw whether to commit state data to local log files (can be done with or without db_commit_on)
        printfunc       ... method, used for stdout style printing. we use this for logging during tests
        collider_file   ... string, file name of collider configuration file, no directory loction. If left blank will use default.
    """
    def __init__(self, petal_id, posids, fidids, simulator_on=False, db_commit_on=False, local_commit_on=True, printfunc=print, verbose=False, user_interactions_enabled=False, collider_file=''):
        # petal setup
        self.petal_id = petal_id
        self.verbose = verbose # whether to print verbose information at the terminal
        self.simulator_on = simulator_on
        if not(self.simulator_on):
            import petalcomm
            self.comm = petalcomm.PetalComm(self.petal_id, user_interactions_enabled=user_interactions_enabled)
            self.comm.reset_nonresponsive_canids() #reset petalcontroller's list of non-responsive canids
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)

        # database setup
        self.db_commit_on = db_commit_on if DB_COMMIT_AVAILABLE else False
        if self.db_commit_on:
            os.environ['DOS_POSMOVE_WRITE_TO_DB'] = 'True'
            self.posmoveDB = DBSingleton(petal_id=self.petal_id)
        self.local_commit_on = local_commit_on
        self.altered_states = set()

        # positioners setup
        self.posmodels = []
        for posid in posids:
            state = posstate.PosState(posid, logging=True, device_type='pos', printfunc=self.printfunc, petal_id=self.petal_id)
            model = posmodel.PosModel(state,is_simulation=simulator_on,user_interactions_enabled=user_interactions_enabled)
            self.posmodels.append(model)
        self.posids = posids.copy()
        self.canids_where_tables_were_just_sent = []
        self.busids_where_tables_were_just_sent = []
        self.nonresponsive_canids = []
        self.sync_mode = 'soft' # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        self.set_motor_parameters()
		
        # collider and scheduler setup
        self.collider = poscollider.PosCollider(configfile=collider_file)
        self.collider.add_positioners(self.posmodels)
        self.schedule = posschedule.PosSchedule(self,verbose=self.verbose)
        self.anticollision_default = True  # default parameter on whether to schedule moves with anticollision, if not explicitly argued otherwise
        self.anticollision_override = True # causes the anticollision_default value to be used in all cases
        
        # fiducials setup
        self.fidstates = {}
        for fidid in fidids:
            state = posstate.PosState(fidid, logging=True, device_type='fid', printfunc=self.printfunc,petal_id=self.petal_id)
            self.fidstates[fidid] = state
        
        # power supplies setup?
        # to-do
        
        # fans setup?
        # to-do
        
        # sensors setup?
        # to-do

 
# METHODS FOR POSITIONER CONTROL

    def request_targets(self, requests, allow_objects = True):
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
                
                    key     ... posid (referencing a single subdictionary for that positioner)
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
                    posmodel    object handle for the posmodel corresponding to posid
                    log_note    same as log_note above, or '' is added automatically if no note was argued in requests
            
            In cases where this is a second request to the same robot (which is not allowed), the
            subdictionary will be deleted from the return.
            
            In cases where the request was made to a disabled positioner, the subdictionary will be
            deleted from the return.
        """
        mark_for_delete = set()
        for posid in requests.keys():
            requests[posid]['posmodel'] = self.posmodel(posid) if allow_objects else posid
            if 'log_note' not in requests[posid]:
                requests[posid]['log_note'] = ''
            if not(self.get(posid,'CTRL_ENABLED')):
                self.printfunc(self._request_denied_disabled_str(posid,requests[posid]))
                mark_for_delete.add(posid)
            elif self.schedule.already_requested(posid):
                self.printfunc('Positioner ' + str(posid) + ' already has a target scheduled. Extra target request ' + self._target_str(requests[posid]) + ' ignored.')
                mark_for_delete.add(posid)
            else:
                self.schedule.request_target(posid, requests[posid]['command'], requests[posid]['target'][0], requests[posid]['target'][1], requests[posid]['log_note'])
        for posid in mark_for_delete:
            del requests[posid]
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
                
                    key     ... posid (referencing a single subdictionary for that positioner)
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
                           in the 'MOVE_CMD' field. This is different from log_note. Generally,
                           log_note is meant for users, whereas cmd_prefix is meant for internal lower-
                           level detailed logging.

        OUTPUT:
            Same dictionary, but with the following new entries in each subdictionary:
            
                    KEYS        VALUES
                    ----        ------
                    command     'direct_dTdP'
                    posmodel    object handle for the posmodel corresponding to posid
                    log_note    same as log_note above, or '' is added automatically if no note was argued in requests
                    
            In cases where the request was made to a disabled positioner, the subdictionary will be
            deleted from the return.
            
        It is allowed to repeatedly request_direct_dtdp on the same positioner, in cases where one
        wishes a sequence of theta and phi rotations to all be done in one shot. (This is unlike the
        request_targets command, where only the first request to a given positioner would be valid.)
        """
        mark_for_delete = set()
        for posid in requests.keys():
            if not(self.get(posid,'CTRL_ENABLED')):
                requests[posid]['command'] = 'direct_dTdP'
                self.printfunc(self._request_denied_disabled_str(posid,requests[posid]))
                mark_for_delete.add(posid)
        for posid in mark_for_delete:
            del requests[posid]
        for posid in requests.keys():
            requests[posid]['posmodel'] = self.posmodel(posid)
            if 'log_note' not in requests[posid]:
                requests[posid]['log_note'] = ''
            table = posmovetable.PosMoveTable(requests[posid]['posmodel'])
            table.set_move(0, pc.T, requests[posid]['target'][0])
            table.set_move(0, pc.P, requests[posid]['target'][1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'direct_dtdp'
            table.store_orig_command(0,cmd_str,requests[posid]['target'][0],requests[posid]['target'][1])
            table.log_note += (' ' if table.log_note else '') + requests[posid]['log_note']
            table.allow_exceed_limits = True
            self.schedule.add_table(table)
        return requests            

    def request_limit_seek(self, posids, axisid, direction, anticollision=True, cmd_prefix='', log_note=''):
        """Request hardstop seeking sequence for positioners in list posids.
        The optional argument cmd_prefix allows adding a descriptive string to the log.
        This method is generally recommended only for expert usage.
        Requests to disabled positioners will be ignored.
        """
        posids = pc.listify(posids,True)[0]
        posmodels = []
        for posid in posids:
            if self.get(posid,'CTRL_ENABLED'):
                posmodels.append(self.posmodel(posid))
            else:
                self.printfunc('Positioner ' + str(posid) + ' is disabled. Limit seek request ignored.')
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

    def request_homing(self, posids):
        """Request homing sequence for positioners in list posids to find the primary hardstop
        and set values for the max position and min position. Requests to disabled positioners
        will be ignored.
        """
        posids = pc.listify(posids,True)[0]
        posmodels = []
        for posid in posids:
            if self.get(posid,'CTRL_ENABLED'):
                posmodels.append(self.posmodel(posid))
            else:
                self.printfunc('Positioner ' + str(posid) + ' is disabled. Homing request ignored.')
        hardstop_debounce = [0,0]
        direction = [0,0]
        direction[pc.P] = +1 # force this, because anticollision logic depends on it
        for p in posmodels:
            self.request_limit_seek(p.posid, pc.P, direction[pc.P], anticollision=True, cmd_prefix='P', log_note='homing')
        self.schedule_moves(anticollision=True)
        for p in posmodels:
            direction[pc.T] = p.axis[pc.T].principle_hardstop_direction
            self.request_limit_seek(p.posid, pc.T, direction[pc.T], anticollision=False, cmd_prefix='T') # no repetition of log note here
            posid = self.posids[self.posmodels.index(p)]                      
            for i in [pc.T,pc.P]:
                axis_cmd_prefix = 'self.axis[' + repr(i) + ']'
                if direction[i] < 0:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[0]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = -1.0\n'
                else:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[1]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = +1.0\n'
                hardstop_debounce_request = {posid:{'target':hardstop_debounce}}
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
        parameter_keys = ['CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CURR_HOLD', 'CREEP_PERIOD','SPINUPDOWN_PERIOD', 'BUMP_CW_FLG', 'BUMP_CCW_FLG']
        for p in self.posmodels:
            state = p.state
            canid = p.canid
            busid = p.busid
            parameter_vals = []
            for parameter_key in parameter_keys:
                parameter_vals.append(state.read(parameter_key))
            #syntax for setting currents: comm.set_currents(busid, canid, [curr_spin_p, curr_cruise_p, curr_creep_p, curr_hold_p], [curr_spin_t, curr_cruise_t, curr_creep_t, curr_hold_t])
            self.comm.set_currents(busid, canid, [parameter_vals[0], parameter_vals[1], parameter_vals[2], parameter_vals[3]], [parameter_vals[0], parameter_vals[1], parameter_vals[2], parameter_vals[3]])
            #syntax for setting periods: comm.set_periods(busid, canid, creep_period_p, creep_period_t, spin_period)
            self.comm.set_periods(busid, canid, parameter_vals[4], parameter_vals[4], parameter_vals[5])
            #syntax for setting bump flags: comm.set_bump_flags(busid, canid, curr_hold, bump_cw_flg, bump_ccw_flg)
            self.comm.set_bump_flags(busid, canid, parameter_vals[3], parameter_vals[6], parameter_vals[7])
            vals_str =  ''.join([' ' + parameter_keys[i] + '=' + str(parameter_vals[i]) for i in range(len(parameter_keys))])
            self.printfunc(p.posid + ' (bus=' + str(busid) + ', canid=' + str(canid) + '): motor currents and periods set:' + vals_str)

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

    def quick_move(self, posids, command, target, log_note=''):
        """Convenience wrapper to request, schedule, send, and execute a single move command, all in
        one shot. You can argue multiple posids if you want (as a list), though note they will all
        get the same command and target sent to them. So for something like a local (theta,phi) coordinate
        this often makes sense, but not for a global coordinate.

        INPUTS:     posids    ... either a single posid or a list of posids
                    command   ... string like those usually put in the requests dictionary (see request_targets method)
                    target    ... [u,v] values, note that all positioners here get sent the same [u,v] here
                    log_note  ... optional string to include in the log file
        """
        requests = {}
        posids = pc.listify(posids,True)[0]
        for posid in posids:
            requests[posid] = {'command':command, 'target':target, 'log_note':log_note}
        self.request_targets(requests)
        self.schedule_send_and_execute_moves()

    def quick_direct_dtdp(self, posids, dtdp, log_note=''):
        """Convenience wrapper to request, schedule, send, and execute a single move command for a
        direct (delta theta, delta phi) relative move. There is NO anti-collision calculation. This
        method is intended for expert usage only. You can argue multiple posids if you want (as a
        list), though note they will all get the same (dt,dp) sent to them.
        
        INPUTS:     posids    ... either a single posid or a list of posids
                    dtdp      ... [dt,dp], note that all posids get sent the same [dt,dp] here. i.e. dt and dp are each just one number
                    log_note  ... optional string to include in the log file
        """
        requests = {}
        posids = pc.listify(posids,True)[0]
        for posid in posids:
            requests[posid] = {'target':dtdp, 'log_note':log_note}
        self.request_direct_dtdp(requests)
        self.schedule_send_and_execute_moves()

# METHODS FOR FIDUCIAL CONTROL        
    def set_fiducials(self, fidids='all', setting='on', save_as_default=False):
        """Set a list of specific fiducials on or off.
        
        fidids ... one fiducial id string, or a list of fiducial id strings, or 'all'
		           (this is the string given by DEVICE_ID in DESI-2724)
        
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
            print('Simulator skips sending out set_fiducials commands on petal ' + str(self.petal_id) + '.')
            return {}
        fidids = pc.listify(fidids,keep_flat=True)[0]
        if fidids[0] == 'all':
            fidids = self.fidids
        busids = self.get_fids_val(fidids,'BUS_ID')
        canids = self.get_fids_val(fidids,'CAN_ID')
        if isinstance(setting,int) or isinstance(setting,float):
            if setting < 0:
                setting = 0
            if setting > 100:
                setting = 100
            duties = [setting]*len(fidids)
        elif setting == 'on':
            duties = self.get_fids_val(fidids,'DUTY_DEFAULT_ON')
        else:
            duties = self.get_fids_val(fidids,'DUTY_DEFAULT_OFF')
        enabled = self.get_fids_val(fidids,'CTRL_ENABLED')
        rng = range(len(fidids))
        fidids = [fidids[i] for i in rng if enabled[i]]
        busids = [busids[i] for i in rng if enabled[i]]
        canids = [canids[i] for i in rng if enabled[i]]
        duties = [duties[i]  for i in rng if enabled[i]]
        self.comm.set_fiducials(busids, canids, duties)
        settings_done = {}
        for i in range(len(fidids)):
            self.store_fid_val(fidids[i], 'DUTY_STATE', duties[i])
            settings_done[fidids[i]] = duties[i]
            if save_as_default:
                self.store_fid_val(fidids[i], 'DUTY_DEFAULT_ON', duties[i])
        self.commit(log_note='set fiducial parameters')
        return settings_done
    
    @property
    def n_fiducial_dots(self):
        """Returns number of fixed fiducial dots this petal contributes in the field of view.
        """
        n_dots = self.get_fids_val(self.fidids,'N_DOTS')
        return sum(n_dots)
    
    @property
    def fiducial_dots_fvcXY(self):
        """Returns an ordered dict of ordered dicts of all [x,y] positions of all
        fiducial dots this petal contributes in the field of view.
        
        Primary keys are the fiducial dot ids, formatted like:
            'F001.0', 'F001.1', etc...
        
        Returned values are accessed with the sub-key 'fvcXY'. So that:
            data['F001.1']['fvcXY'] --> [x,y] floats giving location of dot #1 in fiducial #F001
            
        The coordinates are all given in fiber view camera pixel space.
        
        In some laboratory setups, we have a "extra" fixed reference fibers. These
        are not provided here (instead they are handled in posmovemeasure.py).
        """
        data = collections.OrderedDict()
        for fidid in self.fidids:
            print(fidid)
            dotids = self.fid_dotids(fidid)
            print(dotids)
            for i in range(len(dotids)):
                print(i)
                data[dotids[i]] = collections.OrderedDict()
                x = self.get_fids_val(fidid,'DOTS_FVC_X')[0][i]
                y = self.get_fids_val(fidid,'DOTS_FVC_Y')[0][i]
                data[dotids[i]]['fvcXY'] = [x,y]
        return data

    @property
    def fidids(self):
        """Returns a list of all the fiducial ids on the petal.
        """
        return list(self.fidstates.keys())
    
    def fid_dotids(self,fidid):
        """Returns a list (in a standard order) of the dot id strings for a particular fiducial.
        """
        return [self.dotid_str(fidid,i) for i in range(self.get_fids_val(fidid,'N_DOTS')[0])]
      
    @staticmethod
    def dotid_str(fidid,dotnumber):
        return fidid + '.' + str(dotnumber)

    @staticmethod
    def extract_fidid(dotid):
        return dotid.split('.')[0]
    
    @staticmethod
    def extract_dotnumber(dotid):
        return dotid.split('.')[1]

    def fid_busids(self,fidids):
        """Returns a list of bus ids where you find each of the fiducials (identified
        in the list fidids). These come back in the same order.
        """
        return self.get_fids_val(fidids,'BUS_ID')
    
    def fid_canids(self,fidids):
        """Returns a list of can ids where each fiducial (identified in the list
        fidids) is addressed on its bus. These come back in the same order.
        """
        return self.get_fids_val(fidids,'CAN_ID')
    
    def fid_default_duties(self,fidids):
        """Returns a list of default duty percent settings which each fiducial (identified
        in the list fidids) is supposed to be set to when turning it on.
        """
        return self.get_fids_val(fidids,'DUTY_DEFAULT_ON')
    
    def get_fids_val(self,fidids,key):
        """Returns a list of the values for string key, for all fiducials identified
        in the list fidids.
        """
        vals = []
        fidids = pc.listify(fidids,keep_flat=True)[0]
        for fidid in fidids:
            vals.append(self.fidstates[fidid].read(key))
        return vals
    
    def store_fid_val(self,fidid,key,value):
        '''Sets a single value to a fiducial. This does NOT turn the fiducial physically
        on or off. It only saves a value.
        '''
        self.fidstates[fidid].store(key,value)
        self.altered_states.add(self.fidstates[fidid])


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
        (posids, was_not_list) = self._posid_listify_and_fill(posid)
        (keys, temp) = pc.listify(key,keep_flat=True)
        (posids, keys) = self._equalize_input_list_lengths(posids,keys)
        vals = []
        for i in range(len(posids)):
            pidx = self.posids.index(posids[i])
            if keys[i] == '':
                vals.append(self.posmodels[pidx])
            elif keys[i] == 'expected_current_position':
                vals.append(self.posmodels[pidx].expected_current_position_str)
            else:
                vals.append(self.posmodels[pidx].state.read(keys[i]))
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
        (posids, temp)  = self._posid_listify_and_fill(posid)
        (keys,   temp)  = pc.listify(key,keep_flat=True)
        (values, temp)  = pc.listify(value,keep_flat=True)
        (posids, keys)   = self._equalize_input_list_lengths(posids,keys)
        (posids, values) = self._equalize_input_list_lengths(posids,values)
        (posids, keys)   = self._equalize_input_list_lengths(posids,keys) # repetition here handles the case where there was 1 posid element, 1 key, but mulitplie elements in value
        for i in range(len(posids)):
            p = self.posmodel(posids[i])
            p.state.store(keys[i],values[i])
            self.altered_states.add(p.state)

    def commit(self, log_note='', *args, **kwargs):
        '''Commit data to the local config and log files, and/or the online database.
        A note string may optionally be included to go along with this entry in the logs.
        '''
        if self.db_commit_on:
            pos_commit_list = []
            fid_commit_list = []
            for state in self.altered_states:
                # determine whether it's a positioner state or a fiducial state (these have different data)
                # gather up the data from this state
                if 'POS_ID' in state.unit:
                    pos_commit_list.append(state)
                elif 'FID_ID' in state.unit:
                    fid_commit_list.append(state)
                state.log_unit()
                # do the commit
            if len(pos_commit_list) != 0:
                self.posmoveDB.WriteToDB(pos_commit_list,self.petal_id,'pos_move')
                self.posmoveDB.WriteToDB(pos_commit_list,self.petal_id,'pos_calib')
            if len(fid_commit_list) != 0:
                self.posmoveDB.WriteToDB(fid_commit_list,self.petal_id,'fid_data')
                self.posmoveDB.WriteToDB(fid_commit_list,self.petal_id,'fid_calib')
                pass
        if self.local_commit_on:
            for state in self.altered_states:
                if log_note:
                    state.next_log_notes.append(log_note)
                if 'TIME_RECORDED' in state.unit:
                    del state.unit['TIME_RECORDED']
                    print(state.unit)
                state.write()
                state.log_unit()
        self.altered_states = set()

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
        (posids, was_not_list) = self._posid_listify_and_fill(posid)
        (keys, temp) = pc.listify(key,keep_flat=True)
        (posids, keys) = self._equalize_input_list_lengths(posids,keys)
        vals = []
        for i in range(len(posids)):
            pidx = self.posids.index(posids[i])
            this_val = self.posmodels[pidx].expected_current_position
            if keys[i] == '':
                vals.append(this_val)
            elif keys[i] == 'QS':
                vals.append([this_val['Q'],this_val['S']])
            elif keys[i] == 'flatXY':
                vals.append([this_val['flatX'],this_val['flatY']])
            elif keys[i] == 'obsXY':
                vals.append([this_val['obsX'],this_val['obsY']])
            elif keys[i] == 'obsTP':
                vals.append([this_val['obsT'],this_val['obsP']])
            elif keys[i] == 'posTP':
                vals.append([this_val['posT'],this_val['posP']])
            elif keys[i] == 'motorTP':
                vals.append([this_val['motT'],this_val['motP']])
            else:
                vals.append(this_val[keys[i]])
        if was_not_list:
            vals = pc.delistify(vals)
        return vals

    def expected_current_position_str(self,posid=None):
        """One-line string summarizing current expected position of a positioner.

        If posid is a list of multiple positioner ids, then the return will be a
        corresponding list of strings.

        If no posid is specified, a list of strings for all positioners is returned.
        """
        (posids, was_not_list) = self._posid_listify_and_fill(posid)
        strs = []
        for p in posids:
            pidx = self.posids.index(p)
            strs.append(self.posmodels[pidx].expected_current_position_str)
        if was_not_list:
            strs = pc.delistify(strs)
        return strs

    def posmodel(self, posid):
        """Returns the posmodel object corresponding to a single posid.
        """
        pidx = self.posids.index(posid)
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
        self._check_and_disable_nonresponsive_pos_and_fid()
        for m in self.schedule.move_tables:
            m.posmodel.postmove_cleanup(m.for_cleanup)
            self.altered_states.add(m.posmodel.state)
        if self.verbose:
            print(self.expected_current_position_str())
        self.commit()
        self._clear_temporary_state_values()
        self._clear_schedule()

    def _check_and_disable_nonresponsive_pos_and_fid(self):
        """Asks petalcomm for a list of what canids are nonresponsive, and then
        handles disabling those positioners and/or fiducials.
        """
        if self.simulator_on:
            pass
        else:
            status_updated = False
            nonresponsives = self.comm.get_nonresponsive_canids()
            for canid in nonresponsives:
                if canid not in self.nonresponsive_canids:
                    self.nonresponsive_canids.append(canid)
                    for p in self.posmodels:
                        if p.canid == canid:
                            self.set(p.posid,'CTRL_ENABLED',False)
                            p.state.next_log_notes.append('disabled sending control commands because positioner was detected to be nonresponsive')
                    for fidid in self.fidids:
                        if self.get_fids_val(fidid,'CAN_ID')[0] == canid:
                            self.store_fid_val(fidid,'CTRL_ENABLED',False)
                            self.fidstates[fidid].next_log_notes.append('disabled sending control commands because fiducial was detected to be nonresponsive')
                    status_updated = True
            for canid in self.nonresponsive_canids:
                if canid not in nonresponsives:
                    # placeholder for re-enabling individual positioners, if they somehow become responsive again
                    # not sure if we actually want this, Joe / Irena / Michael to discuss
                    # (there is also the comm.reset_nonresponsive_canids method)
                    pass
            if status_updated:
                self.commit(log_note='device status updated')
                
    def _clear_temporary_state_values(self):
        '''Clear out any existing values in the state objects that were only temporarily
        held until we could get the state committed to the log / db.
        '''
        resets = {'MOVE_CMD'  : '',
                  'MOVE_VAL1' : '',
                  'MOVE_VAL2' : ''}
        for k in resets.keys():
            self.set(key=k,value=resets[k])

    def _clear_schedule(self):
        """Clear out any existing information in the move schedule.
        """
        self.schedule = posschedule.PosSchedule(self,verbose=self.verbose)

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
            posids = self.posids
            was_not_list = False
        else:
            (posids, was_not_list) = pc.listify(posid,keep_flat=True)
        return posids, was_not_list

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
        
    def _request_denied_disabled_str(self, posid, target_request_dict):
        return 'Positioner ' + str(posid) + ' is disabled. Target request ' + self._target_str(target_request_dict) + ' ignored.'
        
