from posmodel import PosModel
import posschedule
import posmovetable
import posstate
import poscollider
import posconstants as pc
import posschedstats
from petaltransforms import PetalTransforms
import time
import collections
import os
try:
    from DBSingleton import * #DBSingleton in the code is a class inside the file DBSingleton of the same name
    DB_COMMIT_AVAILABLE = True
except ImportError:
    DB_COMMIT_AVAILABLE = False
try:
    from DOSlib.constants import ConstantsDB
    CONSTANTSDB_AVAILABLE = True
except ImportError:
    CONSTANTSDB_AVAILABLE = False


class Petal(object):
    """Controls a petal. Communicates with the PetalBox hardware via PetalComm.

    The general sequence to make postioners move is:
        1. request all the desired moves from all the desired positioners
        2. schedule the moves (anti-collision and anti-backlash are automatically calculated here)
        3. send the scheduled move tables out to the positioners
        4. execute the move tables (synchronized start on all the positioners at once.

    Convenience wrapper functions are provided to combine these steps when desirable.

    Required initialization inputs:
        petal_id        ... unique string id of the petal

    Optional initialization inputs:
        posids          ... list, positioner ids. If provided, validate against the ptl_setting file. If empty [], read from the ptl_setting file directly.
        fidids          ... list, fiducial ids. If provided, validate against the ptl_setting file. If empty [], read from the ptl_setting file directly. 
        simulator_on    ... boolean, controls whether in software-only simulation mode
        db_commit_on    ... boolean, controls whether to commit state data to the online system database (can be done with or without local_commit_on (available only if DB_COMMIT_AVAILABLE == True))
        local_commit_on ... boolean, controls whether to commit state data to local .conf files (can be done with or without db_commit_on)
        local_log_on    ... boolean, controls whether to commit timestamped log of state data to local .csv files (can can be done with or without db_commit_on) 
        printfunc       ... method, used for stdout style printing. we use this for logging during tests
        collider_file   ... string, file name of collider configuration file, no directory loction. If left blank will use default.
        sched_stats_on  ... boolean, controls whether to log statistics about scheduling runs
        pb_config       ... boolean or dictionary, boolean controls whether to send configuration settings from backup json file, if dictionary is not passed from DOS
        anticollision   ... string, default parameter on how to schedule moves. See posschedule.py for valid settings.
        petal_loc       ... integer, (option) location (0-9) of petal in FPA
        fpa_metrology   ... dictionary, petal offsets and rotation in FPA, keyed by petal_loc
    """
    def __init__(self, petal_id=None, petal_loc=None, posids=None, fidids=None,
                 simulator_on=False, petalbox_id=None, shape=None,
                 db_commit_on=False, local_commit_on=True, local_log_on=True,
                 printfunc=print, verbose=False,
                 user_interactions_enabled=False, anticollision='freeze',
                 collider_file=None, sched_stats_on=False, pb_config=False,
                 fpa_metrology=None, debug_commit_on=False):
        # specify an alternate to print (useful for logging the output)
        self.printfunc = printfunc
        # petal setup
        self.petal_state = posstate.PosState(
            unit_id=petal_id, device_type='ptl', logging=True,
            printfunc=self.printfunc)
        if petal_id is None:
            self.petal_id = self.petal_state.conf['PETAL_ID'] # this is the string unique hardware id of the particular petal (not the integer id of the beaglebone in the petalbox)
        else:
            self.petal_id = petal_id
        if petalbox_id is None:
            self.petalbox_id = self.petal_state.conf['PETALBOX_ID'] # this is the integer software id of the petalbox (previously known as 'petal_id', before disambiguation)
        else:
            self.petalbox_id = petalbox_id
        if not posids:
            self.printfunc('posids not given, read from ptl_settings file')
            posids = self.petal_state.conf['POS_IDS']
        else:
            posids_file = self.petal_state.conf['POS_IDS'] 
#            if set(posids) != set(posids_file):
#                self.printfunc('WARNING: Input posids are not consistent with ptl_setting file')
#                self.printfunc('Input posids:'+str(posids))
#                self.printfunc('Posids from file:'+str(posids_file))
        if not fidids:
            self.printfunc('fidids not given, read from ptl_settings file')
            fidids = self.petal_state.conf['FID_IDS']
        else:
            fidids_file = self.petal_state.conf['FID_IDS']
#            if set(fidids) != set(fidids_file):
#                self.printfunc('WARNING: Input fidids are not consistent with ptl_setting file')
#                self.printfunc('Input fidids:'+str(fidids))
#                self.printfunc('Fidids from file:'+str(fidids_file))
        if fidids in ['',[''],None,{''}]: # check included to handle simulation cases, where no fidids argued
            fidids = {}

        self.verbose = verbose # whether to print verbose information at the terminal
        self.simulator_on = simulator_on
        if not(self.simulator_on):
            import petalcomm
            self.comm = petalcomm.PetalComm(self.petalbox_id, user_interactions_enabled=user_interactions_enabled)
            self.comm.pbset('non_responsives', 'clear') #reset petalcontroller's list of non-responsive canids
        self.shape = self.petal_state.conf['SHAPE']

        # database setup
        self.db_commit_on = db_commit_on if DB_COMMIT_AVAILABLE else False
        if self.db_commit_on:
            os.environ['DOS_POSMOVE_WRITE_TO_DB'] = 'True'
            self.posmoveDB = DBSingleton(petal_id=self.petal_id)
        self.local_commit_on = local_commit_on
        self.local_log_on = local_log_on
        self.altered_states = set()
        self.altered_calib_states = set()
        self.pb_config = pb_config

        # positioners setup
        self.posmodels = {} # key posid, value posmodel instance
        self.states = {} # key posid, value posstate instance
        self.devices = {} # key device_location_id, value posid
        installed_on_asphere = self.shape == 'petal'
        for posid in posids:
            self.states[posid] = posstate.PosState(posid, logging=True, device_type='pos', printfunc=self.printfunc, petal_id=self.petal_id)
            self.posmodels[posid] = PosModel(self.states[posid], installed_on_asphere)
            self.devices[self.states[posid]._val['DEVICE_LOC']] = posid
        self.posids = set(self.posmodels.keys())
        self.canids_where_tables_were_just_sent = []
        self.busids_where_tables_were_just_sent = []
        self.nonresponsive_canids = set()
        self.sync_mode = 'soft' # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        if self.pb_config == False:
            self.set_motor_parameters()
        self.power_supply_map = self._map_power_supplies_to_posids()
        
        # collider, scheduler, and animator setup
        self.collider = poscollider.PosCollider(configfile=collider_file,
                                                collision_hashpp_exists=False, 
                                                collision_hashpf_exists=False, 
                                                hole_angle_file=None)
        self.collider.set_petal_offsets(x0=self.petal_state.conf['X_OFFSET'],
                                        y0=self.petal_state.conf['Y_OFFSET'],
                                        rot=self.petal_state.conf['ROTATION'])
        self.collider.add_positioners(self.posmodels.values())
        self.animator = self.collider.animator
        self.animator_on = False # this should be turned on/off using the animation start/stop control methods below
        self.animator_total_time = 0 # keeps track of total time of the current animation
        self.schedule_stats = posschedstats.PosSchedStats() if sched_stats_on else None    
        self.schedule = self._new_schedule()
        self.anticollision_default = anticollision
        
        # fiducials setup
        self.fidids = {fidids} if isinstance(fidids,str) else set(fidids)
        for fidid in self.fidids:
            self.states[fidid] = posstate.PosState(fidid, logging=True, device_type='fid', printfunc=self.printfunc, petal_id=self.petal_id)        
            self.devices[self.states[fidid]._val['DEVICE_LOC']] = fidid

        # pos flags setup
        self.pos_bit = 1<<2
        self.fid_bit = 1<<3
        self.bad_fiber_fvc_bit = 1<<5
        self.ctrl_disabled_bit = 1<<16
        self.fiber_broken_bit = 1<<17
        self.comm_error_bit = 1<<18
        self.overlap_targ_bit = 1<<19
        self.frozen_anticol_bit = 1<<20
        self.unreachable_targ_bit = 1<<21
        self.restricted_targ_bit = 1<<22
        self.multi_request_bit = 1<<23
        self.dev_nonfunctional_bit = 1<<24
        self.pos_flags = {} #Dictionary of flags by posid for the FVC, use get_pos_flags() rather than calling directly
        self._initialize_pos_flags()
        #self._apply_state_enable_settings()

        # petalbox setup (temporary until all settings are passed via init by DOS)
        if pb_config == True:
            import json
            with open(pc.dirs['petalbox_configurations']) as json_file:
                self.pb_config = json.load(json_file)[self.petal_id]
        
        # power supplies, fans, sensors setup
        if not self.simulator_on and self.pb_config != False:
            self._map_can_enabled_devices()
            self.setup_petalbox(mode = 'start_up')

        # transformation instance setup for petal
        # these values can be used for boundary calculation in anti-collision
        if petal_loc is None:
            self.petal_loc = 3  # petal local CS aligns with focal plate CS5
        else:
            self.petal_loc = petal_loc
        if CONSTANTSDB_AVAILABLE:
            constants = ConstantsDB().get_constants(
                snapshot='DOS', tag='CURRENT', group='focal_plane_metrology')
            gamma = constants[str(self.petal_loc)]['petal_rot_3']
            Tx = constants[str(self.petal_loc)]['petal_offset_x']
            Ty = constants[str(self.petal_loc)]['petal_offset_y']
        else:  # DB unavailable, read from petal config
            gamma = self.petal_state.conf['ROTATION']
            Tx = self.petal_state.conf['X_OFFSET']
            Ty = self.petalssscss_state.conf['Y_OFFSET']
        self.trans = PetalTransforms(Tx=Tx, Ty=Ty, gamma=gamma)

        # set debug mode flag
        self.debug_commit_on = debug_commit_on

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

            pos_flags ... dict keyed by positioner indicating which flag as indicated below that a
                          positioner should receive going to the FLI camera with fvcproxy
        """
        marked_for_delete = set()
        for posid in requests:
            requests[posid]['posmodel'] = self.posmodels[posid]
            self._initialize_pos_flags(ids = {posid})
            if 'log_note' not in requests[posid]:
                requests[posid]['log_note'] = ''
            if not(self.get_posfid_val(posid,'CTRL_ENABLED')):
                self.pos_flags[posid] |= self.ctrl_disabled_bit
                marked_for_delete.add(posid)
            elif self.schedule.already_requested(posid):
                marked_for_delete.add(posid)
                self.pos_flags[posid] |= self.multi_request_bit
            else:
                accepted = self.schedule.request_target(posid, requests[posid]['command'], requests[posid]['target'][0], requests[posid]['target'][1], requests[posid]['log_note'])            
                if not accepted:
                    marked_for_delete.add(posid)
        for posid in marked_for_delete:
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

            pos_flags ... dictionary, contains appropriate positioner flags for FVC see request_targets()
            
        It is allowed to repeatedly request_direct_dtdp on the same positioner, in cases where one
        wishes a sequence of theta and phi rotations to all be done in one shot. (This is unlike the
        request_targets command, where only the first request to a given positioner would be valid.)
        """
        self._initialize_pos_flags(ids = {posid for posid in requests})
        marked_for_delete = {posid for posid in requests if not(self.get_posfid_val(posid,'CTRL_ENABLED'))}
        for posid in marked_for_delete:
            self.pos_flags[posid] |= self.ctrl_disabled_bit
            del requests[posid]
        for posid in requests:
            requests[posid]['posmodel'] = self.posmodels[posid]
            if 'log_note' not in requests[posid]:
                requests[posid]['log_note'] = ''
            table = posmovetable.PosMoveTable(requests[posid]['posmodel'])
            table.set_move(0, pc.T, requests[posid]['target'][0])
            table.set_move(0, pc.P, requests[posid]['target'][1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'direct_dtdp'
            table.store_orig_command(0,cmd_str,requests[posid]['target'][0],requests[posid]['target'][1])
            table.log_note += (' ' if table.log_note else '') + requests[posid]['log_note']
            table.allow_exceed_limits = True
            self.schedule.expert_add_table(table)
        return requests            

    def request_limit_seek(self, posids, axisid, direction, anticollision='freeze', cmd_prefix='', log_note=''):
        """Request hardstop seeking sequence for a single positioner or all positioners
        in iterable collection posids. The optional argument cmd_prefix allows adding a
        descriptive string to the log. This method is generally recommended only for
        expert usage. Requests to disabled positioners will be ignored.
        """
        self._initialize_pos_flags(ids = posids)
        posids = {posids} if isinstance(posids,str) else set(posids)
        enabled = self.enabled_posmodels(posids)
        for posid in posids:
            if posid not in enabled.keys():
                self.pos_flags[posid] |= self.ctrl_disabled_bit
        if anticollision:
            if axisid == pc.P and direction == -1:
                # calculate thetas where extended phis do not interfere
                # request anticollision-safe moves to these thetas and phi = 0
                pass
            else:
                # request anticollision-safe moves to current thetas and all phis within Ei
                # Eo has a bit more possible collisions, for example against a stuck-extended neighbor. Costs a bit more time/power to go to Ei, but limit-seeking is not a frequent operation.
                pass
        for posid, posmodel in enabled.items():
            search_dist = pc.sign(direction)*posmodel.axis[axisid].limit_seeking_search_distance
            table = posmovetable.PosMoveTable(posmodel)
            table.should_antibacklash = False
            table.should_final_creep  = False
            table.allow_exceed_limits = True
            table.allow_cruise = not(posmodel.state._val['CREEP_TO_LIMITS'])
            dist = [0,0]
            dist[axisid] = search_dist
            table.set_move(0,pc.T,dist[0])
            table.set_move(0,pc.P,dist[1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'limit seek'
            table.store_orig_command(0,cmd_str,direction*(axisid == pc.T),direction*(axisid == pc.P))
            table.log_note += (' ' if table.log_note else '') + log_note
            posmodel.axis[axisid].postmove_cleanup_cmds += 'self.axis[' + repr(axisid) + '].total_limit_seeks += 1\n'
            axis_cmd_prefix = 'self.axis[' + repr(axisid) + ']'
            if direction < 0:
                direction_cmd_suffix = '.minpos\n'
            else:
                direction_cmd_suffix = '.maxpos\n'
            posmodel.axis[axisid].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + direction_cmd_suffix
            self.schedule.expert_add_table(table)

    def request_homing(self, posids, axis = 'both'):
        """Request homing sequence for positioners in single posid or iterable collection of
        posids. Finds the primary hardstop, and sets values for the max position and min position.
        Requests to disabled positioners will be ignored.
        
        axis ... string, 'both' (default), 'theta_only', 'phi_only', optional argument that allows for homing either
                 theta or phi only
        """
        posids = {posids} if isinstance(posids,str) else set(posids)
        self._initialize_pos_flags(ids = posids)
        enabled = self.enabled_posmodels(posids)
        for posid in posids:
            if posid not in enabled.keys():
                self.pos_flags[posid] |= self.ctrl_disabled_bit
        hardstop_debounce = [0,0]
        direction = [0,0]
        direction[pc.P] = +1 # force this, because anticollision logic depends on it
        if not(axis == 'theta_only'):
            for posid in enabled:
                self.request_limit_seek(posid, pc.P, direction[pc.P], anticollision=self.anticollision_default, cmd_prefix='P', log_note='homing')
            self.schedule_moves(anticollision=self.anticollision_default)
        for posid,posmodel in enabled.items():
            if not(axis == 'phi_only'):
                direction[pc.T] = posmodel.axis[pc.T].principle_hardstop_direction
                self.request_limit_seek(posid, pc.T, direction[pc.T], anticollision=None, cmd_prefix='T') # no repetition of log note here
            for i in [pc.T,pc.P]:
                if (i == pc.T and axis != 'phi_only') or (i == pc.P and axis != 'theta_only'):
                    axis_cmd_prefix = 'self.axis[' + repr(i) + ']'
                    if direction[i] < 0:
                        hardstop_debounce[i] = posmodel.axis[i].hardstop_debounce[0]
                        posmodel.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = -1.0\n'
                    else:
                        hardstop_debounce[i] = posmodel.axis[i].hardstop_debounce[1]
                        posmodel.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = +1.0\n'
                    hardstop_debounce_request = {posid:{'target':hardstop_debounce}}
                    self.request_direct_dtdp(hardstop_debounce_request, cmd_prefix='debounce')

    def schedule_moves(self,anticollision='default',should_anneal=True):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods.
        
        See posschedule.py for valid arguments to the anticollision flag. If
        no argument is given, then the petal's default flag is used.
        
        The should_anneal flag should generally be left True. It causes moves
        to be spread out in time to reduce peak current draw by the full array
        of positioners. (But there are certain 'expert use' test cases in the
        lab, where we want this feature turned off.)
        """
        if anticollision not in {None,'freeze','adjust'}:
            anticollision = self.anticollision_default
        self.schedule.should_anneal = should_anneal
        self.schedule.schedule_moves(anticollision)

    def send_move_tables(self):
        """Send move tables that have been scheduled out to the positioners.
        """
        if self.simulator_on:
            if self.verbose:
                self.printfunc('Simulator skips sending move tables to positioners.')
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
        """Send the motor current and period settings to the positioners.
        """
        if self.simulator_on:
            if self.verbose:
                self.printfunc('Simulator skips sending motor parameters to positioners.')
            return

        parameter_keys = ['CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CURR_HOLD', 'CREEP_PERIOD','SPINUPDOWN_PERIOD']
        currents_by_busid = dict((p.busid,{}) for posid,p in self.posmodels.items())
        periods_by_busid =  dict((p.busid,{}) for posid,p in self.posmodels.items())
        enabled = self.enabled_posmodels(self.posids)
        for posid,posmodel in enabled.items():
           canid = posmodel.canid
           busid = posmodel.busid
           p = {key:posmodel.state._val[key] for key in parameter_keys}
           currents = tuple([p[key] for key in ['CURR_SPIN_UP_DOWN','CURR_CRUISE','CURR_CREEP','CURR_HOLD']])
           currents_by_busid[busid][canid] = [currents, currents]
           periods_by_busid[busid][canid] = (p['CREEP_PERIOD'], p['CREEP_PERIOD'], p['SPINUPDOWN_PERIOD'])
           if self.verbose:
               vals_str =  ''.join([' ' + str(key) + '=' + str(p[key]) for key in p])
               self.printfunc(posid + ' (bus=' + str(busid) + ', canid=' + str(canid) + '): motor currents and periods set:' + vals_str)
        self.comm.pbset('currents', currents_by_busid)
        self.comm.pbset('periods', periods_by_busid)

    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        """
        if self.simulator_on:
            if self.verbose:
                self.printfunc('Simulator skips sending execute moves command to positioners.')
            self._postmove_cleanup()
        else:
            self.comm.execute_sync(self.sync_mode)
            #TEMPORARY FIX FOR FIRMWARE NOT RESPONDING WHILE EXECUTING POST PAUSES, REMOVE AFTER
            #FW v4.5 DEPLOYMENT
            hw_tables = self._hardware_ready_move_tables()
            buffer = 1.0 # sec
            table_times = [sum([pp/1000 for pp in hw_table['postpause']]) + sum(hw_table['move_time']) for hw_table in hw_tables] # note postpauses are in ms
            if table_times != []: #Prevent a crash if no move tables were actually sent (IE all positioners in a move are disabled)
                delay = buffer + max(table_times)
                time.sleep(delay)
            #END OF TEMPORARY FIX
            self._postmove_cleanup()
            self._wait_while_moving()
        self.canids_where_tables_were_just_sent = []
        self.busids_where_tables_were_just_sent = []

    def schedule_send_and_execute_moves(self, anticollision='default', should_anneal=True):
        """Convenience wrapper to schedule, send, and execute the pending requested
        moves, all in one shot.
        """
        self.schedule_moves(anticollision,should_anneal)
        self.send_and_execute_moves()

    def send_and_execute_moves(self):
        """Convenience wrapper to send and execute the pending moves (that have already
        been scheduled).
        """
        self.send_move_tables()
        self.execute_moves()

    def quick_move(self, posids, command, target, log_note='', anticollision='default', should_anneal=True):
        """Convenience wrapper to request, schedule, send, and execute a single move command, all in
        one shot. You can argue multiple posids if you want, though note they will all get the same
        command and target sent to them. So for something like a local (theta,phi) coordinate
        this often makes sense, but not for a global coordinate.

        INPUTS:     posids    ... either a single posid or an iterable collection of posids
                    command   ... string like those usually put in the requests dictionary (see request_targets method)
                    target    ... [u,v] values, note that all positioners here get sent the same [u,v] here
                    log_note  ... optional string to include in the log file
                    anticollsion  ... see comments in schedule_moves() function
                    should_anneal ... see comments in schedule_moves() function
        """
        requests = {}
        posids = {posids} if isinstance(posids,str) else set(posids)
        for posid in posids:
            requests[posid] = {'command':command, 'target':target, 'log_note':log_note}
        self.request_targets(requests)
        self.schedule_send_and_execute_moves(anticollision,should_anneal)

    def quick_direct_dtdp(self, posids, dtdp, log_note='', should_anneal=True):
        """Convenience wrapper to request, schedule, send, and execute a single move command for a
        direct (delta theta, delta phi) relative move. There is NO anti-collision calculation. This
        method is intended for expert usage only. You can argue an iterable collection of posids if
        you want, though note they will all get the same (dt,dp) sent to them.
        
        INPUTS:     posids    ... either a single posid or a list of posids
                    dtdp      ... [dt,dp], note that all posids get sent the same [dt,dp] here. i.e. dt and dp are each just one number
                    log_note  ... optional string to include in the log file
                    should_anneal ... see comments in schedule_moves() function
        """
        requests = {}
        posids = {posids} if isinstance(posids,str) else set(posids)
        for posid in posids:
            requests[posid] = {'target':dtdp, 'log_note':log_note}
        self.request_direct_dtdp(requests)
        self.schedule_send_and_execute_moves(None,should_anneal)

# METHODS FOR FIDUCIAL CONTROL        
    def set_fiducials(self, fidids='all', setting='on', save_as_default=False):
        """Set specific fiducials on or off.
        
        fidids ... one fiducial id string, or an iterable collection of fiducial id strings, or 'all'
                   
        setting ... what to set the fiducials to, as described below:
            'on'         ... turns each fiducial to its default on value
            'off'        ... turns each fiducial individually to its default off value
            int or float ... a single integer or float from 0-100 sets all the argued fiducials uniformly to that one value
        
        save_as_default ... only used when seting is a number, in which case True means we will store that setting permanently to the fiducials' config file, False means its just a temporary setting this time
        
        Method returns a dictionary of all the settings that were made, where
            key   --> fiducial id
            value --> duty state that was set
        
        Fiducials that do not have control enabled will not appear in this dictionary.
        """
        if self.simulator_on:
            self.printfunc('Simulator skips sending out set_fiducials commands on petal ' + str(self.petal_id) + '.')
            return {}
        if fidids == 'all':
            fidids = self.fidids
        else:
            fidids = {fidids} if isinstance(fidids,str) else set(fidids)
        enabled = [fidid for fidid in fidids if self.get_posfid_val(fidid,'CTRL_ENABLED')]
        busids = [self.get_posfid_val(fidid,'BUS_ID') for fidid in enabled]
        canids = [self.get_posfid_val(fidid,'CAN_ID') for fidid in enabled]
        if isinstance(setting,int) or isinstance(setting,float):
            if setting < 0:
                setting = 0
            if setting > 100:
                setting = 100
            duties = [setting]*len(enabled)
        elif setting == 'on':
            duties = [self.get_posfid_val(fidid,'DUTY_DEFAULT_ON') for fidid in enabled]
        else:
            duties = [self.get_posfid_val(fidid,'DUTY_DEFAULT_OFF') for fidid in enabled]
        fiducial_settings_by_busid = {busid:{} for busid in set(busids)}
        for idx, busid in enumerate(busids):
            fiducial_settings_by_busid[busid][canids[idx]] = duties[idx]
        self.comm.pbset('fiducials', fiducial_settings_by_busid)
        
        settings_done = {}
        for i in range(len(enabled)):
            self.set_posfid_val(enabled[i], 'DUTY_STATE', duties[i])
            settings_done[enabled[i]] = duties[i]
            if save_as_default:
                self.set_posfid_val(enabled[i], 'DUTY_DEFAULT_ON', duties[i])
        self.commit(log_note='set fiducial parameters')
        return settings_done
    
    @property
    def n_fiducial_dots(self):
        """Returns number of fixed fiducial dots this petal contributes in the field of view.
        """
        n_dots = [self.get_posfid_val(fidid,'N_DOTS') for fidid in self.fidids]
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
            dotids = self.fid_dotids(fidid)
            for i in range(len(dotids)):
                data[dotids[i]] = collections.OrderedDict()
                x = self.get_posfid_val(fidid,'DOTS_FVC_X')[i]
                y = self.get_posfid_val(fidid,'DOTS_FVC_Y')[i]
                data[dotids[i]]['fvcXY'] = [x,y]
        return data
    
    def fid_dotids(self,fidid):
        """Returns a list (in a standard order) of the dot id strings for a particular fiducial.
        """
        return [self.dotid_str(fidid,i) for i in range(self.get_posfid_val(fidid,'N_DOTS'))]
      
    @staticmethod
    def dotid_str(fidid,dotnumber):
        return fidid + '.' + str(dotnumber)

    @staticmethod
    def extract_fidid(dotid):
        return dotid.split('.')[0]

# METHODS FOR CONFIGURING THE PETALBOX
        
    def setup_petalbox(self, mode):
        """Set everything up for the argued petalbox mode.
        The settings controlled by the petalbox are currently 
        set identically for the configure and start of observations modes.  They 
        are also set identically for start up and end observations.  We
        may be making distinctions between these modes at a later date.
        mode ... string specifying the mode that the petalbox should be set up for
                 ('start_up', 'configure', 'start_obs', or 'end_obs')
                 
        returns a status dictionary (read back from petalbox) with the following keys and values:
        'PS1_ENABLED' ... boolean, True if on else False
        'PS2_ENABLED' ... boolean, True if on else False
        'CAN_BRD1_ENABLED' ... boolean, True if on else False
        'CAN_BRD2_ENABLED' ... boolean, True if on else False
        'BUFF1_ENABLED' ... boolean, True if on else False
        'BUFF2_ENABLED' ... boolean, True if on else False
        'TEC_PWR_ENABLED' ... boolean, True if on else False
        'GFA_PWR_ENABLED' ... boolean, True if on else False
        'GFA_FAN_INLET_ENABLED' ... boolean, True if on else False
        'GFA_FAN_OUTLET_ENABLED' ... boolean, True if on else False
        'GFA_FAN_INLET_DUTY_DEFAULT_ON' ... integer, fan duty setting
        'GFA_FAN_OUTLET_DUTY_DEFAULT_ON' ... integer, fan duty setting
        'GFA_FAN_INLET_TACH' ... integer, fan speed in RPM
        'GFA_FAN_OUTLET_TACH' .. integer, fan speed in RPM
        'OVERALL_STATUS' ... string, 'SUCCESS' or 'FAILED' 
          
        The following settings are sent to the petalbox (according to pb_config 
        enable/duty specifications):
        for 'configure' or 'start_obs' mode input:
            Positioner Power - ON
            CAN Power - ON
            SYNC Buffer Enable - ON
            TEC Power Enable - ON
            GFA Power Enable - ON
            GFA Fan Enable - ON 
        for 'start_up' or 'end_obs' mode input:
            Positioner Power - OFF
            CAN Power - OFF
            SYNC Buffer Enable - OFF
            TEC Power Eneble - OFF
            GFA Power Enable - OFF
            GFA Fan Enable - OFF
        This method will take some time (~10 seconds) to return when things are being turned ON 
        due to the time it takes to configure/re-configure CAN channels.
        """
        if self.simulator_on or self.pb_config == False:
            return
        conf = self.pb_config
        if mode in ['configure', 'start_obs']:
            #self.comm.clear_errors() uncomment when updated in petalcontroller, do for configure only
            pospwr_en = 'both' if (conf['PS1_ENABLED'] and conf['PS2_ENABLED'])\
                        else 1 if conf['PS1_ENABLED'] else 2
            can_en = 'both' if (conf['CAN_BRD1_ENABLED'] and conf['CAN_BRD2_ENABLED'])\
                        else 1 if conf['CAN_BD1_ENABLED'] else 2
            buff_en = 'both' if (conf['BUFF1_ENABLED'] and conf['BUFF2_ENABLED'])\
                        else 1 if conf['BUFF1_ENABLED'] else 2
            self.comm.power_up(pospwr_en, can_en, buff_en)
            inlet_settings = ['on', conf['GFA_FAN_INLET_DUTY_DEFAULT_ON']]\
                             if conf['GFA_FAN_INLET_ENABLED'] else ['off', 0]
            outlet_settings = ['on', conf['GFA_FAN_OUTLET_DUTY_DEFAULT_ON']]\
                              if conf['GFA_FAN_OUTLET_ENABLED'] else ['off', 0]
            self.comm.pbset('GFA_FAN', {'inlet': inlet_settings, 'outlet': outlet_settings})
            if conf['GFA_PWR_ENABLED']:
                self.comm.pbset('GFAPWR_EN', 'on')
            if conf['TEC_PWR_ENABLED']:
                self.comm.pbset('TEC_CTRL', 'on')
            self.set_motor_parameters()
        elif mode in ['start_up', 'end_obs']:
            pospwr_en = 'None'
            self.comm.power_down()
            self.comm.pbset('GFA_FAN', {'inlet' : ['off', 0], 'outlet' : ['off', 0]})
        self._update_and_send_can_enabled_info(pospwr_en)
        return self.assess_pb_status(mode)
    
    def assess_pb_status(self, mode):
        """Retrieve petalbox feedback for settings associated with input mode. Use to verify
        that a setup_petalbox call was successful.
        mode ... string specifying the mode that the petalbox should be set up for
                 ('start_up', 'configure', 'start_obs', or 'end_obs')
        returns status dictionary with all settings and a final assessment, see setup_petalbox
        method for format.
        """
        if not self.simulator_on:
            str_to_bool = {'on' : True, 'off' : False}
            pospwr_fbk = self.comm.pbget('POSPWR_FBK')
            canbrd_fbk = self.comm.pbget('CAN_EN')
            buff_fbk = self.comm.pbget('BUFFERS')
            tec_fbk = self.comm.pbget('TEC_CTRL')
            gfa_fbk = self.comm.pbget('GFAPWR_EN')
            fan_fbk = self.comm.pbget('GFA_FAN')
            setup_status = {'PS1_ENABLED' : str_to_bool[pospwr_fbk['PS1']],
                           'PS2_ENABLED' : str_to_bool[pospwr_fbk['PS2']],
                           'CAN_BRD1_ENABLED': str_to_bool[canbrd_fbk[0]],
                           'CAN_BRD2_ENABLED': str_to_bool[canbrd_fbk[1]],
                           'BUFF1_ENABLED' : str_to_bool[buff_fbk[0]],
                           'BUFF2_ENABLED' : str_to_bool[buff_fbk[1]],
                           'TEC_PWR_ENABLED' : str_to_bool[tec_fbk],
                           'GFA_PWR_ENABLED' : str_to_bool[gfa_fbk],
                           'GFA_FAN_INLET_ENABLED' : str_to_bool[fan_fbk['inlet'][0]],
                           'GFA_FAN_OUTLET_ENABLED': str_to_bool[fan_fbk['outlet'][0]],
                           'GFA_FAN_INLET_DUTY_DEFAULT_ON' : fan_fbk['inlet'][1],
                           'GFA_FAN_OUTLET_DUTY_DEFAULT_ON' : fan_fbk['outlet'][1],
                            }
            assessment = {k:v for k,v in setup_status.items() if (v == self.pb_config[k] or mode in ['start_up', 'end_obs'])}
            if mode in ['configure', 'start_obs']:
                success_condition_met = False not in assessment.keys() and (fan_fbk['inlet'][2] > 0 and fan_fbk['outlet'][2] > 0)           
            else:
                success_condition_met = True not in setup_status
            assessment['OVERALL_STATUS'] = 'SUCCESS' if success_condition_met else 'FAILED' 
            assessment['GFA_FAN_INLET_TACH'] = fan_fbk['inlet'][2]
            assessment['GFA_FAN_OUTLET_TACH'] = fan_fbk['outlet'][2]
            return assessment
        
        def reset_petalbox(self):
            """Reset all errors and turn all enables off.  This method
            returns the petalbox to its default safe state (how it comes up prior to 
            communicating with the petal).
            """
            if not self.simulator_on:
                self.comm.configure()
        
# GETTERS, SETTERS, STATUS METHODS

    def get_posfid_val(self, uniqueid, key):
        """Retrieve the state value identified by string key, for positioner or fiducial uniqueid."""
        return self.states[uniqueid]._val[key]
    
    def set_posfid_val(self, uniqueid, key, value):
        """Sets a single value to a positioner or fiducial. In the case of a fiducial, note that
        this call does NOT turn the fiducial physically on or off. It only saves a value."""
        self.states[uniqueid].store(key,value)
        self.altered_states.add(self.states[uniqueid])

    def get_pbconfig_val(self, key):
        """Retrieve petalbox configuration value from the self.pb_config dictionary."""
        return self.pb_config.get(key, None)

    def set_pbconfig_val(self, key, value):
        """Set a configuration value for the petalbox in the self.pb_config dictionary.  
        This value will be applied when the setup_petalbox method is called again.  
        This method does not update the defaults for the petalbox
        (which are loaded from either a configuration file or DOS)."""
        self.pb_config[key] = value
    
    def get_pbdata_val(self, key):
        """Requests data from petalbox using the pbget method.
        key ... string, corresponds to petalbox pbget method keys (eg 'TELEMETRY', 'CONF_FILE')
        """
        return self.comm.pbget(key) 
    
    def get_ptl_performance_telemetry(self):
        """Returns an abbreviated summary of key performance parameters
        to be plotted with the telemetry viewer.  These stats are provided
        for the latest shedule only.
        
        Returns dictionary of anticollision statistic parameters (if self.schedule_stats is initialized, 
        else returns an empty dictionary).
        key ... value
        'found total collisions' ... integer number of total collisions found
        'resolved total collisions' ... integer number of total collisions resolved
        'resolved freeze collisions' ... integer number of collisions resolved via the 'freeze' method
        'n pos' ... integer number of positioners included in the schedule
        'method' ... string name of anticollision method specified for the schedule
        'avg moving simultaneously' ... float describing the average number of positioners moving simulataneously
        'max moving simultaneously' ... float describing the maximum number of positioners moving simultaneously
        'total schedule time' ... float total time (calculation and move) for the schedule
        """
        if not self.schedule_stats:
            return {}
        data = self.schedule_stats.summarize_all()
        idx = -2 if not self.schedule_stats.real_data_yet_in_latest_row else -1
        keys_to_include = ['found total collisions', 'resolved total collisions',\
                          'freeze', 'n pos', 'method', 'avg moving simultaneously', 'max moving simultaneously']
        total_time = data['max table move time'][idx] + data['request_target calc time'][idx]\
                     + data['schedule_moves calc time'][idx] + data['expert_add_table calc time'][idx]
        data_for_telemetry = {k:data[k][idx] for k in keys_to_include if not k == 'freeze'}
        data_for_telemetry['resolved freeze collisions'] = data['freeze'][idx]
        data_for_telemetry['total schedule time'] = total_time
        return data_for_telemetry
    
    def commit(self, log_note='', *args, **kwargs):
        '''Commit data to the local config and log files, and/or the online database.
        A note string may optionally be included to go along with this entry in the logs.
        '''
        if log_note:
            for state in self.altered_states:
                state.next_log_notes.append(log_note)
        if self.db_commit_on:
            pos_commit_list = []
            fid_commit_list = []
            for state in self.altered_states:
                if state.type == 'pos':
                    pos_commit_list.append(state)
                elif state.type == 'fid':
                    fid_commit_list.append(state)
            if len(pos_commit_list) != 0:
                self.posmoveDB.WriteToDB(pos_commit_list,self.petal_id,'pos_move')
            if len(fid_commit_list) != 0:
                self.posmoveDB.WriteToDB(fid_commit_list,self.petal_id,'fid_data')
        # avoid overwriting local config data and logs when testing in simulator mode
        # but stills allows DB commits above
        if not self.simulator_on:
            if self.local_commit_on:
                for state in self.altered_states:
                    state.write()  # this writes posstate to local config
            if self.local_log_on:
                for state in self.altered_states:
                    state.log_unit()  # this writes the local log
        self.altered_states = set()

    def commit_calib_DB(self, *args, **kwargs):
        '''Commit data to the pos_calib table. This is to be called at the end of a calibration
        sequence. No local commit option since local calibration recordings are andled in the
        commit function.
        ''' 
        if self.db_commit_on:
            pos_commit_list = []
            fid_commit_list = []
            for state in self.altered_calib_states:
                if state.type == 'pos':
                    pos_commit_list.append(state)
                elif state.type == 'fid':
                    fid_commit_list.append(state)
            if len(pos_commit_list) != 0:
                self.posmoveDB.WriteToDB(pos_commit_list,self.petal_id,'pos_calib')
            if len(fid_commit_list) != 0:
                self.posmoveDB.WriteToDB(fid_commit_list,self.petal_id,'fid_calib')
        return

    def expected_current_position(self, posid, key):
        """Retrieve the current position, for a positioner identied by posid, according
        to the internal tracking of its posmodel object. Returns a two element
        list. Valid keys are:
            
            'QS', 'flatXY', 'obsXY', 'posXY', 'obsTP', 'posTP', 'motTP'
        
        See comments in posmodel.py for explanation of these values.
        """
        if key == 'posTP':
            return self.posmodels[posid].expected_current_posTP
        elif key == 'obsTP':
            return self.posmodels[posid].expected_current_obsTP
        else:
            vals = self.posmodels[posid].expected_current_position
            if key == 'obsXY':
                return [vals['obsX'],vals['obsY']]
            elif key == 'QS':
                return [vals['Q'],vals['S']]
            elif key == 'posXY':
                return [vals['posX'],vals['posY']]
            elif key == 'flatXY':
                return [vals['flatX'],vals['flatY']]
            elif key == 'motorTP':
                return [vals['motT'],vals['motP']]
            else:
                self.printfunc('Unrecognized key ' + str(key) + ' in request for expected_current_position of posid ' + str(posid) + '.')
                
    def enabled_posmodels(self, posids):
        """Returns dict with keys = posids, values = posmodels, but only for
        those positioners in the collection posids which are enabled.
        """
        return {p:self.posmodels[p] for p in posids if self.posmodels[p].is_enabled}

    def get_pos_flags(self, posids = 'all', should_reset = False):
        '''Getter function for self.pos_flags that carries out a final is_enabed
        check before passing them off. Important in case the PC sets ctrl_enabled = False
        when a positioner is not responding.
        '''
        pos_flags = {}
        if posids == 'all':
            posids = self.posids
        for posid in posids:
            if not(self.posmodels[posid].is_enabled):
                self.pos_flags[posid] |= self.ctrl_disabled_bit #final check for disabled
            if not(self.get_posfid_val(posid, 'FIBER_INTACT')):  
                self.pos_flags[posid] |= self.fiber_broken_bit
                self.pos_flags[posid] |= self.bad_fiber_fvc_bit
            if self.get_posfid_val(posid, 'DEVICE_CLASSIFIED_NONFUNCTIONAL'):
                self.pos_flags[posid] |= self.dev_nonfunctional_bit
            pos_flags[posid] = str(self.pos_flags[posid])
        if should_reset:
            self._initialize_pos_flags()
        return pos_flags

# MOVE SCHEDULING ANIMATOR CONTROLS
        
    def start_gathering_frames(self):
        """Frame data representing scheduled moves will begin to be collected as
        it is generated (during move scheduling) and will be retained for making
        an animation of it in the future. Old frame data from any previous animation
        is cleared out first.
        """
        self.animator.clear()
        self.animator_on = True
        self.animator_total_time = 0
        self.collider.add_fixed_to_animator(self.animator_total_time)        
    
    def stop_gathering_frames(self):
        """Stop collecting frame data of scheduled moves for the animator.
        """
        self.animator_on = False
    
    def generate_animation(self):
        """Use the current collection of move frames in the animator to plot
        the animation.
        """
        self.animator.animate()


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
        for m in self.schedule.move_tables.values():
            hw_tbl = m.for_hardware()
            hw_tables.append(hw_tbl)
        return hw_tables

    def _postmove_cleanup(self):
        """This always gets called after performing a set of moves, so that PosModel instances
        can be informed that the move was physically done on the hardware.
        """
        self._check_and_disable_nonresponsive_pos_and_fid()
        for m in self.schedule.move_tables.values():
            m.posmodel.postmove_cleanup(m.for_cleanup())
            self.altered_states.add(m.posmodel.state)
        self.commit()
        self._clear_temporary_state_values()
        self.schedule = self._new_schedule()

    def _check_and_disable_nonresponsive_pos_and_fid(self):
        """Asks petalcomm for a list of what canids are nonresponsive, and then
        handles disabling those positioners and/or fiducials.
        """
        if self.simulator_on:
            pass
        else:
            status_updated = False
            nonresponsives = self.comm.pbget('non_responsives')
            for canid in nonresponsives:
                if canid not in self.nonresponsive_canids:
                    self.nonresponsive_canids.add(canid)
                    for item_id in self.posids.union(self.fidids):
                        if self.get_posfid_val(item_id,'CAN_ID') == canid:
                            self.set_posfid_val(item_id,'CTRL_ENABLED',False)
                            self.petal_state.conf['DISABLED_BUFFER'].append(item_id)
                            self.petal_state.write()
                            if self.pb_config:
                                self._update_can_enabled_map(item_id, False)
                            self.pos_flags[item_id] |= self.comm_error_bit
                            self.printfunc(str(item_id) + ': was disabled due to a CAN communication error.')
                            self.states[item_id].next_log_notes.append('Disabled sending control commands because device was detected to be nonresponsive.')
                            break
                    status_updated = True
            if status_updated:
                self.commit()
                
    def _clear_temporary_state_values(self):
        '''Clear out any existing values in the state objects that were only temporarily
        held until we could get the state committed to the log / db.
        '''
        resets = {'MOVE_CMD'  : '',
                  'MOVE_VAL1' : '',
                  'MOVE_VAL2' : ''}
        for key in resets:
            for posid in self.posids:
                self.set_posfid_val(posid, key, resets[key])

    def _new_schedule(self):
        """Generate up a new, clear schedule instance.
        """
        schedule = posschedule.PosSchedule(petal=self, stats=self.schedule_stats, verbose=self.verbose)
        schedule.should_check_petal_boundaries = self.shape == 'petal'
        return schedule

    def _wait_while_moving(self):
        """Blocking implementation, to not send move tables while any positioners are
        still moving. The implementation has the benefit of simplicity, but it is
        acknowledged there may be 'better', i.e. multi-threaded, ways to achieve this.
        """
        if self.simulator_on:
            return        
        timeout = 20.0 # seconds
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
    
    def _map_power_supplies_to_posids(self):
        """Reads in data for positioner canids and petal power supply ids, and
        returns a dict mapping power supply ids (keys) to sets of posids (values).
        Any unknown mappings (e.g. a canid that does not match the nominal petal
        mapping) gets assigned a power_supply_id of 'other'. (This could happen
        for example on a non-petal test stand.)
        """
        canids = {posid:posmodel.canid for posid,posmodel in self.posmodels.items()}
        power_supply_map = {}
        already_mapped = set()
        for supply,mapped_cans in pc.power_supply_can_map.items():
            mapped_posids = {posid for posid in canids.keys() if canids[posid] in mapped_cans}
            power_supply_map[supply] = mapped_posids
            already_mapped.union(mapped_posids)
        power_supply_map['other'] = set(canids.keys()).difference(already_mapped)
        return power_supply_map
    
    def _update_and_send_can_enabled_info(self, power_supply_mode = 'both'):
        """Set up CAN and CTRL_ENABLED information based on positioner power supply or supplies being enabled.
        
        power_supply_mode ... string ('both' or 'None') or integer (1 or 2) specifying the power supply or supplies being enabled.
        """
        if power_supply_mode == 'None':
            for devid in self.posids.union(self.fidids):
                self.set_posfid_val(devid, 'CTRL_ENABLED', False)
                self.pos_flags[devid] |= self.comm_error_bit
            self.comm.pbset('CAN_ENABLED', {})
        elif power_supply_mode == 'both':
            for devid in self.posids.union(self.fidids):
                if not devid in self.disabled_devids:
                    self.set_posfid_val(devid, 'CTRL_ENABLED', True)
                    self.pos_flags[devid] &= ~(self.comm_error_bit)
            both_supplies_map = self.can_enabled_map['V1'].copy()
            both_supplies_map.update(self.can_enabled_map['V2'])   
            self.comm.pbset('CAN_ENABLED', both_supplies_map)
        else:
            for devid in self.posids.union(self.fidids):
                if not devid in self.power_supply_map['V{}'.format(power_supply_mode)]:
                    self.set_posfid_val(devid, 'CTRL_ENABLED', False)
                    self.pos_flags[devid] |= self.comm_error_bit
                else:
                    self.set_posfid_val(devid, 'CTRL_ENABLED', True)
                    self.pos_flags[devid] &= ~(self.comm_error_bit)
            self.comm.pbset('CAN_ENABLED', self.can_enabled_map['V{}'.format(power_supply_mode)])
            
    def _map_can_enabled_devices(self):
        """Reads in enable statuses for all devices and builds a formatted for petalbox can 
        id map by power supply key.
        """
        self.disabled_devids = self.petal_state.conf['DISABLED_BUFFER']
        self.can_enabled_map = {}
        for supply in pc.power_supply_can_map.keys():
            self.can_enabled_map[supply] = dict((k, {}) for k in pc.power_supply_can_map[supply])
        for devid in self.posids.union(self.fidids):
            if self.get_posfid_val(devid, 'CTRL_ENABLED') and devid not in self.disabled_devids:
                busid, canid = self.get_posfid_val(devid, 'BUS_ID'), self.get_posfid_val(devid, 'CAN_ID')
                if busid in pc.power_supply_can_map['V1']:
                    self.can_enabled_map['V1'][busid][canid] = 1 if devid.startswith('P') else 0
                elif busid in pc.power_supply_can_map['V2']:
                    self.can_enabled_map['V2'][busid][canid] = 1 if devid.startswith('P') else 0

    def _update_can_enabled_map(self, devid, enabled = False):
        """Update self.can_enabled_map by adding or removing a devid (string unique id of positinoer
        or fiducial).
        """
        busid, canid = self.get_posfid_val(devid, 'BUS_ID'), self.get_posfid_val(devid, 'CAN_ID')
        devtype = 1 if devid.startswith('P') else 0
        for supply in ['V1', 'V2']:
            if self.get_posfid_val(devid, 'BUS_ID') in pc.power_supply_can_map[supply]:
                dev_supply = supply
        if enabled:
            self.can_enabled_map[dev_supply][busid][canid] = devtype
        else:
            self.can_enabled_map[dev_supply][busid].pop(canid, None) 
            
    def _initialize_pos_flags(self, ids = 'all'):
        '''
        Sets pos_flags to initial values: 4 for positioners and 8 for fiducials.

        FVC/Petal bit string

        FVC BITS
        1 - Pinhole Center
        2 - Fiber Center
        3 - Fiducial Center
        4 - 
        5 - Bad Fiber or Fiducial
        6 - 15 reserved

        PETAL BITS    
        16 - CTRL_ENABLED = False
        17 - FIBER_INTACT = False
        18 - Communication error
        19 - Overlapping targets
        20 - Frozen by anticollision
        21 - Unreachable by positioner
        22 - Targeting restricted boundries
        23 - Requested multiple times
        24 - Classified Nonfunctional
        '''
        if ids == 'all':
            ids = self.posids.union(self.fidids)
        for posfidid in ids:
            if posfidid.startswith('M') or posfidid.startswith('D') or posfidid.startswith('UM'):
                self.pos_flags[posfidid] = self.pos_bit
            else:
                self.pos_flags[posfidid] = self.fid_bit
        return

    def _apply_state_enable_settings(self):
        """Read positioner/fiducial configuration settings and disable/set flags accordingly.
        """
        for devid in self.posids.union(self.fidids):
            if self.get_posfid_val(devid, 'DEVICE_CLASSIFIED_NONFUNCTIONAL'):
                self.set_posfid_val(devid, 'CTRL_ENABLED', False)
                self.pos_flags[devid] |= self.ctrl_disabled_bit
                self.pos_flags[devid] |= self.dev_nonfunctional_bit
            if devid in self.posids:
                if not self.get_posfid_val(devid, 'FIBER_INTACT'):
                    self.set_posfid_val(devid, 'CTRL_ENABLED', False)
                    self.pos_flags[devid] |= self.ctrl_disabled_bit
                    self.pos_flags[devid] |= self.broken_fiber_bit
                    self.pos_flags[devid] |= self.bad_fiber_fvc_bit            

