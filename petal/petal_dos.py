#! /usr/bin/env python
import petalcomm
import posmodel
import posschedule
import posmovetable
import posstate
import posconstants as pc
import numpy as np
import time

from DOSlib.application import Application
from DOSlib.discovery import discoverable
from DOSlib.util import dos_parser
from DOSlib.advertise import Seeker

class Petal(Application):
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

        Eventually these can come from some (configuration/constants database). For now we assume that are provide to the constructor.
        
    As of April 2016, the implementation for handling fiducials is kept as simple as possible, for the
    purpose of running test stands only. Later implementations should track fiducials' physical hardware
    by unique id number, log expected and measured positions, log cycles and total on time, etc.
    """
    tag = 'PETAL'
    commands = ['configure',
                'get',
                'set',
                'request_targets',
                'request_direct_dtdp',
                'request_limit_seek',
                'request_homing',
                'schedule_moves',
                'send_move_tables',
                'execute_moves',
                'schedule_send_and_execute_moves',
                'send_and_execute_moves',
                'quick_move',
                'quick_direct_dtdp',
                'clear_schedule',
                'fiducials_on',
                'fiducials_off',
                'expected_current_position',
                'expected_current_position_str',
                'get_model_for_pos',
                'communicate'
                ]

    defaults = {'verbose' : False,
                'simulator_on' : False,
                'sync_mode' : 'soft',
                'anticollision_default' : True,
                'anticollision_override' : True,
                'fid_duty_percent' : 50,
                'fid_duty_period' : 55,
                }
    
    def init(self):
        """
        Initialize petal application.
        petal_id, pos_ids, fid_ids are passed from the command line via self.config
        """
        try:
            self.petal_id = self.config['petal_id']
            self.posids = self.config['pos_ids']
            self.fidids = self.config['fid_ids']
        except:
            return 'FAILED: missing parameter (petal_id, pos_ids, fid_ids)'
        assert isinstance(self.petal_id,int), 'Invalid type for petal id'
        assert isinstance(self.posids, (list, tuple)), 'pos_ids must be a list or tuple'
        assert isinstance(self.fidids, (list, tuple)), 'fid_ids must be a list or tuple'

        self.loglevel('INFO')
        self.info('Initializing')

        # status shared variable
        self.status_sv = self.shared_variable('STATUS')  
        self.status_sv.publish()
        print(repr(self.status_sv))
        # Update user information
        self.add_interlock_information(interlock = 'DOS', key =self.role + '_STATUS',
                                       set_condition=['READY'],
                                       enabled=True)
        
        self.simulator_on = True if 'T' in str(self.config['simulator_on']).upper() else False
        self.verbose = True if 'T' in str(self.config['verbose']).upper() else False
        try:
            self.comm = petalcomm.PetalComm(self.petal_id)
        except Exception as e:
            rstring = 'init: Exception creating PetalComm object: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring
        self.posmodels = []
        for pos_id in self.posids:
            state = posstate.PosState(pos_id,logging=True)
            model = posmodel.PosModel(state)
            self.posmodels.append(model)

        self.schedule = posschedule.PosSchedule(self)
        
        self.sync_mode = str(self.config['sync_mode']).lower()  # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        self.anticollision_default = True  if 'T' in str(self.config['anticollision_default']).upper() else False
        self.anticollision_override = True if 'T' in str(self.config['anticollision_override']).upper() else False
        
        self.canids_where_tables_were_just_sent = []
        self.fid_can_ids = self.fidids # later, implement auto-lookup of pos_ids and fid_ids from database etc
        self.fid_duty_percent = int(self.config['fid_duty_percent'])
        self.fid_duty_period  = int(self.config['fid_duty_period'])  # milliseconds

        # setup discovery, update status and we are done
        if self.connected:
             self._setup_discovery(discovery.discoverable)
        self.info('Initialized')
        self.status_sv.write('INITIALIZED')

    def _setup_discovery(self, discoverable):
        # Setup application for discovery and discover other DOS applications                                                                                               
        discoverable(role = self.role, tag = self.tag, interface = self.role)
        self.info('_setup_discovery: Done')

    def configure(self, *args, **kwargs):
        """
        configure Petal application
        """
        # reset application state
        self.status_sv.write('INITIALIZED')

        # see if we have something to do in configure

        self.info('Configured')
        self.status_sv.write('READY')
        return self.SUCCESS
    
# METHODS FOR POSITIONER CONTROL
    def communicate(self, *args, **kwargs):
        """
        Send a command to petalcomm
        """
        try:
            a, kw = dos_parser(*args, **kwargs)
        except:
            a = []
            kw = {}

        if len(a) == 0:
            return 'FAILED: invalid arguments for comm command'
        try:
            command = a[0]
            del a[0]
            return getattr(self.comm, command)(*a)
        except Exception as e:
            rstring = 'comm: Exception executing command %s: %s' % (str(command),str(e))
            self.error(rstring)
            return 'FAILED: ' + rstring
        
    def request_targets(self, requests):
        """
        Put in requests to the scheduler for specific positioners to move to specific targets.
        
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
        """
        for pos_id in requests.keys():
            requests[pos_id]['posmodel'] = self.get_model_for_pos(pos_id)
            if 'log_note' not in requests[pos_id]:
                requests[pos_id]['log_note'] = ''
            if self.schedule.already_requested(requests[pos_id]['posmodel']):
                self.info('request_targets: Positioner ' + str(pos_id) + ' already has a target scheduled. Extra target request ' + str(requests[pos_id]['command']) + '(' + str(requests[pos_id]['target'][0]) + ',' + str(requests[pos_id]['target'][1]) + ') ignored')
                del requests[pos_id]
            else:
                self.schedule.request_target(requests[pos_id]['posmodel'], requests[pos_id]['command'], requests[pos_id]['target'][0], requests[pos_id]['target'][1], requests[pos_id]['log_note'])
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
                    
        It is allowed to repeatedly request_direct_dtdp on the same positioner, in cases where one
        wishes a sequence of theta and phi rotations to all be done in one shot. (This is unlike the
        request_targets command, where only the first request to a given positioner would be valid.)
        """
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
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'limit seek'
            table.store_orig_command(0,cmd_str,direction*(axisid == pc.T),direction*(axisid == pc.P))
            table.log_note += (' ' if table.log_note else '') + log_note
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
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + '.minpos\n'
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.last_primary_hardstop_dir = -1.0\n'
                else:
                    hardstop_debounce[i] = p.axis[i].hardstop_debounce[1]
                    p.axis[i].postmove_cleanup_cmds += axis_cmd_prefix + '.pos = ' + axis_cmd_prefix + '.maxpos\n'
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

    def get(self,*args, **kwargs):
        """
        Return configuration and positioner information.
        Options include
             status
             posid = < list of positioners>, key = < pos model keyword>
             petal_id
             <any key in self.config>
             
        Retrieve the state value identified by string key, for positioner
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
        try:
            a,kw = dos_parser(*args, **kwargs)
        except Exception as e:
            print('Exception %s'% str(e))
            a = []
            kw = {}

        get_posid = False
        if len(a) == 1:
            param = str(a[0]).lower()

            if param.startswith('petal'):
                return self.petal_id
            elif param == 'status':
                return self.status_sv._value
            elif param in self.config:
                return self.config[param]
            elif param == 'posid':
                get_posid = True
            elif param in ['pos_ids', 'posids']:
                return self.posids
            elif param in ['fid_ids', 'fidids']:
                return self.fidids
            else:
                return 'FAILED: invalid argument for get command'
        if get_posid or 'posid' in kw:
            if get_posid:
                posid = None
            else:
                posid = kw['posid']
            if 'key' not in kw:
                key = ''
            else:
                key = kw['key']
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
            if 'repr' in kw and kw['repr'] == True:
                return repr(vals)
            else:
                return vals
        else:
            return 'FAILED: invalid option(s) for get command'
        
    def set(self,posid=None,key=None,value=None,write_to_disk=None, **kwargs):
        """
        Set positioner state values or configuration variables
        Set the state value identified by string key, for positioner unit
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

        try:
            args = []
            a, kw = dos_parser(*args, **kwargs)
        except:
            a = []
            kw = {}

        # Set a configuration variable?
        if len(kw) != 0:
            for k, v in kw.items():
                if k in self.config:
                    self.config[k] = v
            return self.SUCCESS

        # Set positioner value
        if key == None or value == None:
            rstring = 'set: either no key or no value was specified to setval'
            self.error(rstring)
            return 'FAILED: ' + rstring
        (posid, temp) = self._posid_listify_and_fill(posid)
        (key,   temp) = pc.listify(key,keep_flat=True)
        (value, temp) = pc.listify(value,keep_flat=True)
        (posid, key)   = self._equalize_input_list_lengths(posid,key)
        (posid, value) = self._equalize_input_list_lengths(posid,value)
        (posid, key)   = self._equalize_input_list_lengths(posid,key) # repetition here handles the case where there was 1 posid element, 1 key, but mulitplie elements in value
        for i in range(len(posid)):
            p = self.get_model_for_pos(posid[i])
            p.state.write(key[i],value[i],write_to_disk)
        return self.SUCCESS
    
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

    def main(self):
        """
        Run loop for Petal application
        """
        while not self.shutdown_event.is_set():
            self.sleep(1)

        print('Petal appplication %s exiting' % self.role)
        return

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
            self.info('_postmove_cleanup: ' + self.expected_current_position_str())
        self.clear_schedule()
        self.canids_where_tables_were_just_sent = []

    def _wait_while_moving(self):
        """Blocking implementation, to not send move tables while any positioners are still moving.

        Inputs:     canids ... integer CAN id numbers of all the positioners to check whether they are moving

        The implementation has the benefit of simplicity, but it is acknowledged there may be 'better',
        i.e. multi-threaded, ways to achieve this, to be implemented later.
        """
        if self.simulator_on:
            return        
        timeout = 30.0 # seconds
        poll_period = 0.5 # seconds
        keep_waiting = True
        start_time = time.time()
        while keep_waiting:
            if (time.time()-start_time) >= timeout:
                self.info('_wait_while_moving: Timed out at ' + str(timeout) + ' seconds waiting to send next move table.')
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
            self.info('_equalize_input_list_lengths: both var1 and var2 must be lists, even if single-element')
            return None, None
        if len(var1) != len(var2):
            if len(var1) == 1:
                var1 = var1*len(var2) # note here var1 is starting as a list
            elif len(var2) == 1:
                var2 = var2*len(var1) # note here var2 is starting as a list
            else:
                self.info('_equalize_input_list_lengths: either the var1 or the var2 must be of length 1')
                return None, None
        return var1, var2

###################################################
if __name__ == '__main__':
    import argparse
    import json
    import sys
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--service',action='store',default='DOStest',type=str)
    parser.add_argument('--device_mode',action='store_true')
    parser.add_argument('--role', action='store', nargs = 1, required = True, help = 'Role name (required)', type=str)
    parser.add_argument('--petal', action='store', nargs = 1, help = 'Petal Id [0-9]', type=int)
    parser.add_argument('file', type=argparse.FileType('r'), help = 'file with pos_ids and fid_ids')                        
    args = parser.parse_args()

    # Read positioner and fiducial ids for this petal
    config = json.load(args.file)
    if args.petal:
        pid = args.petal
    else:
        # get petal id from role name
        if args.role[0][-1].isdigit():
            pid = int(args.role[0][-1])
            if args.role[0][-2:-1].isdigit():
                pid = pid + 10* int(args.role[0][-2])
    if str(pid) in config:
        pos_ids = config[str(pid)]['pos_ids']
        fid_ids = config[str(pid)]['fid_ids']
    else:
        print('Configuration file does not include pos and fid ids for petal %s' % str(pid))
        sys.exit()
        
    # Create application instance
    if args.device_mode:
        myPetal = Petal(petal_id = pid, pos_ids = pos_ids, fid_ids = fid_ids, device_mode = True, service = args.service)
    else:
        myPetal = Petal(petal_id = pid, pos_ids = pos_ids, fid_ids = fid_ids)
    # Enter run loop
    myPetal.run()
