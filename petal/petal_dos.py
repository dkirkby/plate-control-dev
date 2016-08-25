#!/usr/bin/env python
"""
   PROTODESI VERSION
   This is the DOS version of petal.py
"""

import posconstants as pc
import posmodel
import petalcomm
import posschedule
import posmovetable
import posstate
import numpy as np
import time
import os
import datetime
import Pyro4

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
        fid_can_ids ... list of can ids of the fiducials
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
                'home',
                'move',
                'general_move',
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
                'anticollision_default' : False,
                'anticollision_override' : True,
                'fid_duty_percent' : 50,
                'fid_duty_period' : 55,
                'logdir' : None,
                'gfa_fan1' : 'on',
                'gfa_fan1_pwm' : 5,
                'gfa_fan2' : 'on',
                'gfa_fan2_pwm' : 20,
                'status_update_rate' : 60,
                }
    
    def init(self):
        """
        Initialize petal application.
        petal_id, pos_ids, fid_ids are passed from the command line via self.config
        They can be set by passing a configuration file which is parsed when before creating
        the Petal object.
        """
        try:
            self.petal_id = self.config['petal_id']
            self.posids = self.config['pos_ids']
            self.fidids = self.config['fid_ids']
            self.fid_can_ids = self.config['fid_can_ids']
        except:
            rstring =  'init: missing parameter (petal_id, pos_ids, fid_ids, fid_can_ids'
            self.error(rstring)
            return 'FAILED: ' + rstring
        assert isinstance(self.petal_id,int), 'Invalid type for petal id'
        assert isinstance(self.posids, (list, tuple)), 'pos_ids must be a list or tuple'
        assert isinstance(self.fidids, (list, tuple)), 'fid_ids must be a list or tuple'
        assert isinstance(self.fid_can_ids, (list, tuple)), 'fid_can_ids must be a list or tuple'

        self.loglevel('INFO')
        self.info('Initializing')

        self.status_update_rate = float(self.config['status_update_rate'])
        self.logdir = self.config['logdir']
        if self.logdir == None:
            if 'POSITIONER_LOGS_PATH' in os.environ:
                self.logdir = os.environ['POSITIONER_LOGS_PATH']
            else:
                rstring = 'init: must specify a log directory on the command line or set POSITIONER_LOGS_PATH'
                self.error(rstring)
                raise RuntimeError(rstring)
        if not os.path.isdir(os.path.join(self.logdir, 'move_logs')):
            os.mkdir(os.path.join(self.logdir,'move_logs'))
        if not os.path.isdir(os.path.join(self.logdir, 'test_logs')):
            os.mkdir(os.path.join(self.logdir,'test_logs'))
        pc.set_logs_directory(self.logdir)
        self.info('init: using log directory %s' % self.logdir)

        # status shared variable
        self.status_sv = self.shared_variable('STATUS')  
        self.status_sv.publish()

        # petalbox status
        self.petalbox_status = {}
        self.petalbox_sv = self.shared_variable('PETALBOX')
        self.petalbox_sv.publish()
        # fiducials status  (also in petal box but this is for the GUI)
        self.fiducials_sv = self.shared_variable('FIDUCIALS', group = 'PETAL')
        self.fiducials_sv.publish(allowMultiplePublishers=True)
    
        # actuator positions
        self.positions_sv = self.shared_variable('POSITIONS')
        self.positions_sv.publish()
        
        # Telemetry information
        # (temperatures, fan pwm duty cycles, GPIO switches)
        self.telemetry_sv = self.shared_variable('TELEMETRY')
        self.telemetry_sv.publish()
        self.telemetry_sv.write({'last_updated' : datetime.datetime.utcnow().isoformat().replace('T',' ')})
        
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

        self.gfa_fan1_on = True if str(self.config['gfa_fan1']).upper() in ['ON', 'TRUE', '1'] else False
        self.gfa_fan2_on = True if str(self.config['gfa_fan2']).upper() in ['ON', 'TRUE', '1'] else False
        self.gfa_fan1_pwm = float(self.config['gfa_fan1_pwm'])
        self.gfa_fan2_pwm = float(self.config['gfa_fan2_pwm'])
        self.fid_duty_percent = int(self.config['fid_duty_percent'])
        self.fid_duty_period  = int(self.config['fid_duty_period'])  # milliseconds
        
        if self.comm.is_connected():
            self.info('init: initializing petalbox hardware.')
            self.fiducials_off()
            self._set_gfafans('GFA_FAN1', state = self.gfa_fan1_on, pwm = self.gfa_fan1_pwm) 
            self._set_gfafans('GFA_FAN2', state = self.gfa_fan2_on, pwm = self.gfa_fan2_pwm)
        else:
            self.warn('init: cannot initalize petalbox hardware at this time.')
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

        # setup discovery, update status and we are done
        if self.connected:
             self._setup_discovery(discoverable)
        self.info('Initialized')
        self.status_sv.write('INITIALIZED')
        # call configure() when in device mode
        if self.device_mode == True:
            self.info('calling configure')
            retcode = self.configure()
            if 'FAILED' in retcode:
                raise RuntimeError('init: ' + retcode)
            
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

        # update telemetry
        self._update_telemetry()
        
        # see if we have anything else to do in configure
        if self.comm.is_connected():
            self.info('init: initializing petalbox hardware.')
            self.fiducials_off()
            self._set_gfafans('GFA_FAN1', state = self.gfa_fan1_on, pwm = self.gfa_fan1_pwm) 
            self._set_gfafans('GFA_FAN2', state = self.gfa_fan2_on, pwm = self.gfa_fan2_pwm)
        else:
            rstring = 'configure: cannot continue until petalcontroller is found.'
            self.error(rstring)
            return 'FAILED: ' + rstring
    
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

    def home(self, positioner = None):
        """
        wrapper functions for request_homing and schedule_send_and_execute_moves
        """
        try:
            self.request_homing(positioner)
            self.schedule_send_and_execute_moves()
        except Exception as e:
            rstring = 'home: Exception homing positioners: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring
        return self.SUCCESS
    
    def request_homing(self, positioner = None):
        """Request homing sequence for positioners in list pos to find the primary hardstop
        and set values for the max position and min position.
        """
        if positioner is None:
            pos = self.get('posids')
        else:
            pos = positioner
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
        return self.SUCCESS
    
    def schedule_moves(self, anticollision=None):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available boolean to turn the
        anticollision algorithm on or off for the scheduling. If that flag is
        None, then the default anticollision parameter is used.
        """
        if anticollision == None or self.anticollision_override:
            anticollision = self.anticollision_default
        self.schedule.schedule_moves(anticollision)
        return self.SUCCESS
    
    def send_move_tables(self):
        """Send move tables that have been scheduled out to the positioners.
        """
        try:
            hw_tables = self._hardware_ready_move_tables()
        except Exception as e:
            self.error('send_move_tables: Exception: %s' % str(e))
        canids = []
        for tbl in hw_tables:
            canids.append(tbl['canid'])
        self.canids_where_tables_were_just_sent = canids
        self._wait_while_moving()
        self.comm.send_tables(hw_tables)
        return self.SUCCESS
    
    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        """
        self.comm.execute_sync(self.sync_mode)
        self._wait_while_moving()
        try:
            self._postmove_cleanup()
            self._update_positions()
        except Exception as e:
            rstring = 'execute_moves: Exception: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring

    def general_move(self, command,targets, posids = None, use_standard_syntax = True):
        """
        A common wrapper function that illustrates the syntax for generating move
        requests and then executing them on the positioners.
        If posids == None, the list of petal postioners is used (self.get('posids'))
        There are several distinct syntaxes, all shown here:
        if should_direct_dtdp:
              general_move('direct_dTdP',[[270,0], [0,-60], [-180,30]])
        if should_move_xy:
              general_move('posXY',[[-4,-4], [-4,0], [-4,4], [0,-4], [0,0], [0,4], [4,-4], [4,0], [4,4]])
        if should_move_dxdy:
              general_move('dXdY',[[2.5,0], [2.5,0], [-10,0], [5,-5], [0,5]])
        if should_move_tp:
              general_move('posTP',[[-90,90], [0,90], [90,90], [0,180]])
        if should_move_dtdp:
              general_move('dTdP',[[180,0], [-90,-90],[180,60],[-90,30]])
              # this is different from 'direct' dTdP. here, the dtdp is treated like any other general move, and anticollision calculations are allowed
        """
        targets = pc.listify2d(targets)
        pos_ids = posids if posids != None else self.get('posids')
        self.info('general_move: using positioners %s' % repr(posids))
        for target in targets:
            self.info('general_move: ' + command + ' (' + str(target[0]) + ',' + str(target[1]) + ')')
            log_note = 'general_move ' + command + ' point ' + str(targets.index(target))
            if use_standard_syntax:
                # The standard syntax has four basic steps: request targets, schedule them, send them to positioners,
                # and execute the moves. See comments in petal.py for more detail. The requests are formatted as
                # dicts of dicts, where the primary keys are positioner ids, and then each subdictionary describes
                # the move you are requesting for that positioner.
                requests = {}
                if command == 'direct_dTdP':
                    # The 'direct_dTdP' is for 'expert' use.
                    # It instructs the theta and phis axes to simply rotate by some argued angular distances, with
                    # no regard for anticollision or travel range limits.

                    for pos_id in pos_ids:                
                        requests[pos_id] = {'target':target, 'log_note':log_note}
                    self.request_direct_dtdp(requests)
                else:

                    # Here is the request syntax for general usage.
                    # Any coordinate system can be requested, range limits are respected, and anticollision can be calculated.

                    for pos_id in pos_ids: 
                        requests[pos_id] = {'command':command, 'target':target, 'log_note':log_note}
                    self.request_targets(requests) # this is the general use function, where 

                self.schedule_moves()    # all the requests get scheduled, with anticollision calcs, generating a unique table of scheduled shaft rotations on theta and phi axes for every positioner 
                self.send_move_tables()  # the tables of scheduled shaft rotations are sent out to all the positioners over the CAN bus
                self.execute_moves()     # the synchronized start signal is sent, so all positioners start executing their scheduled rotations in sync
                # ptl.schedule_send_and_execute_moves() # alternative wrapper which just does the three things above in one line

            else:
                # This 'quick' syntax is mostly intended for manual operations, or simple operations on test stations.
                # You can send the command to multiple pos_ids simultaneously, but all the positioners receive the same command and target coordinates.
                # (So it generally would make no sense to use these in any global coordinate system, where all the positioners are in different places.)
                if command == 'direct_dTdP':
                    self.quick_direct_dtdp(pos_ids, target, log_note) # expert, no limits or anticollision
                else:
                    self.quick_move(pos_ids, command, target, log_note) # general, with limits and anticollision

        return self.SUCCESS
                
    def move(self, requests, *args, **kwargs):
        """
        Wrapper function to move positioners from receiving targets to actually moving.
        See request_targets method for description of allowed formats for the request object.
        """
        # add some code to validate that the requested posids are on this petal
        all_pos_on_ptl = pc.listify(self.get(key='POS_ID'),keep_flat=True)[0]
        for posid in requests.keys():
            if posid not in all_pos_on_ptl:
                rstring = 'move: positioner %s is not on Petal %d' % (repr(posid), self.petal_id)
                self.error(rstring)
                return 'FAILED: ' + rstring
            # Check format of request object
            if 'command' not in requests[posid]:
                rstring = 'move: invalid request format. command is missing'
                self.error(rstring)
                return 'FAILED: ' + rstring
            if 'target' not in requests[posid] and not isinstance(requests[posid]['target'], (tuple, list)):
                rstring= 'move: invalid request format. target missing or invalid type.'
                self.error(rstring)
                return 'FAILED: ' + rstring
        try:
            self.request_targets(requests)
        except Exception as e:
            rstring = 'move: Exception in request_targets call: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring
        try:
            self.schedule_send_and_execute_moves() # in future, may do this in a different thread for each petal
        except Exception as e:
            rstring = 'move: Exception in schedule_send_and_execute_move call: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring
        return self.SUCCESS
    
    def schedule_send_and_execute_moves(self, *args, **kwargs):
        """Convenience wrapper to schedule, send, and execute the pending requested
        moves, all in one shot.
        """
        self.info('scheduling moves')
        self.schedule_moves()
        self.info('excuting moves')
        try:
            self.send_and_execute_moves()
        except Exception as e:
            rstring = 'schedule_send_and_execute_moves: Exception: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring

    def send_and_execute_moves(self):
        """Convenience wrapper to send and execute the pending moves (that have already
        been scheduled).
        """
        self.send_move_tables()
        try:
            self.execute_moves()
        except Exception as e:
            rstring = 'send_execute_moves: Exception: %s' % str(e)
            self.error(rstring)
            return 'FAILED: ' + rstring

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
        return self.SUCCESS

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
        return self.SUCCESS
    
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
        self.petalbox_status['fiducials_state'] = True
        self.petalbox_status['fiducials_duty'] = self.fid_duty_percent
        self.petalbox_status['last_updated'] = datetime.datetime.utcnow().isoformat()
        self.petalbox_sv.write(self.petalbox_status)
        self.fiducials_sv.write({'fiducials_state' : True})
        self.info('fiducials_on: fiducials are turned on')
        return self.SUCCESS

    def fiducials_off(self):
        """Turn all the fiducials off.
        """
        duty_percents = [0]*len(self.fid_can_ids)
        duty_periods = [self.fid_duty_period]*len(self.fid_can_ids)
        self.comm.set_fiducials(self.fid_can_ids, duty_percents, duty_periods)
        self.petalbox_status['fiducials_state'] = False
        self.petalbox_status['fiducials_duty'] = self.fid_duty_percent
        self.petalbox_status['last_updated'] = datetime.datetime.utcnow().isoformat()
        self.petalbox_sv.write(self.petalbox_status)
        self.fiducials_sv.write({'fiducials_state' : False})
        self.info('fiducials_off: fiducials are turned off')
        return self.SUCCESS
    
# GETTERS, SETTERS, STATUS METHODS

    def get(self,*args, **kwargs):
        """
        Return configuration and positioner information.
        Options include
             status
             posid = < list of positioners>, key = < pos model keyword>
             petal_id
             telemetry
             logdir
             is_connected,
             positions
             petalbox
             status_update_rate
             anticollision_default
             anticollision_override
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
            if param == 'petalbox':
                self._update_petalbox()
                return self.petalbox_status
            elif param.startswith('petal'):
                return self.petal_id
            elif param == 'status':
                return self.status_sv._value
            elif param == 'anticollision_default':
                return self.anticollision_default
            elif param == 'anticollision_override':
                return self.anticollision_override
            elif param == 'posid':
                get_posid = True
            elif param in ['pos_ids', 'posids']:
                return self.posids
            elif param == 'logdir':
                return self.logdir
            elif param == 'status_update_rate':
                return self.status_update_rate
            elif param == 'positions':
                self._update_positions()
                return self.positions_sv._value
            elif param == 'is_connected':
                if self.comm == None:
                    return 'FAILED: No petalcomm object available'
                else:
                    return self.communicate('is_connected')
            elif param == 'telemetry':
                self._update_telemetry()
                return self.telemetry_sv._value
            elif param in ['fid_ids', 'fidids']:
                return self.fidids
            elif param in ['fid_can_ids', 'fidcanids']:
                return self.fid_can_ids
            elif param in self.config:
                return self.config[param]
            else:
                return 'FAILED: invalid argument for get command'
        if get_posid or 'posid' in kw or 'key' in kw:
            if get_posid or 'posid' not in kw:
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
        Configuration:
            fid_duty_percent, gfa_fan1, gfa_fan2, gfa_fan1_pwm, gfa_fan2_pwm
            fiducials, status_update_rate, anticollision_default, anticollision_override
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
                if k == 'fid_duty_percent':
                    self.fid_duty_percent = v
                elif 'fiducials' in kw:
                    if k == 'fiducials':
                        if v  in ('ON', 'on', True, 1):
                            return self.fiducials_on()
                        elif v in ('OFF', 'off', False, 0):
                            return self.fiducials_off()
                        else:
                            return 'FAILED: set: invalid option for set fiducials command.'
                elif k == 'gfa_fan1':
                    if 'gfa_fan1_pwm' in kw:
                        return self._set_gfafans('GFA_FAN1', state = kw['gfa_fan1'], pwm = kw['gfa_fan1_pwm'])
                    else:
                        return self._set_gfafans('GFA_FAN1', state = kw['gfa_fan1'])
                elif k == 'gfa_fan2':
                    if 'gfa_fan2_pwm' in kw:
                        return self._set_gfafans('GFA_FAN2', state = kw['gfa_fan2'], pwm = kw['gfa_fan2_pwm'])
                    else:
                        return self._set_gfafans('GFA_FAN2', state = kw['gfa_fan2'])
                elif k == 'status_update_rate':
                    self.status_update_rate = v
                elif k == 'anticollision_default':
                    self.anticollision_default = True if 'T' in str(v).upper() else False
                elif k == 'anticollision_override':
                    self.anticollision_override = True if 'T' in str(v).upper() else False
                elif k in self.config:
                    self.config[k] = v
            return self.SUCCESS

        # Set positioner value
        if key == None or value == None:
            rstring = 'set: either no key (or value) was specified or and invalid keyword was used.'
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
            elif key[i] == 'posXY':
                vals.append([this_val['posX'],this_val['posY']])
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
        while self.status_sv._value != 'READY' and not self.shutdown_event.is_set():
            # wait for configure
            self.sleep(1)
        self.info('main: starting telemetry update loop')
        
        while not self.shutdown_event.is_set():
            # update telemetry
            self._update_telemetry()
            if self.shutdown_event.is_set():
                break
            self._update_petalbox()
            for i in range(6):
                if self.shutdown_event.is_set():
                    break
                self._update_positions()
                self.sleep(self.status_update_rate/6.0)
        print('Petal appplication %s exiting' % self.role)
        return

# INTERNAL METHODS
    def _set_gfafans(self, fan, state = 'on', pwm = None):
        """
        turn GFA fans on/off and set pwm
        """
        if fan not in ['GFA_FAN1', 'GFA_FAN2']:
            return 'FAILED: invalid GFA fan'
        if state in ['on', 'ON', True, 1]:
            self.comm.switch_en_ptl(fan, 1)
            self.petalbox_status[fan] = 'on'
            self.info('_set_gfafans: %s is on' % fan)
        elif state in ['off', 'OFF', False, 0]:
            self.comm.switch_en_ptl(fan, 0)
            self.petalbox_status[fan] = 'off'
            self.info('_set_gfafans: %s is off' % fan)
        if pwm != None:
            self.comm.fan_pwm_ptl(fan,pwm)
            self.petalbox_status['%s_PWM' %fan] = float(pwm)            
            self.info('_set_gfafans: %s pwm is now %s' % (fan,str(pwm)))
        self.petalbox_status['last_updated'] = datetime.datetime.utcnow().isoformat()
        self.petalbox_sv.write(self.petalbox_status)
        return self.SUCCESS
    
    def _update_petalbox(self):
        """
        Update petalcontroller status
        """
        try:
            current = {}
            hrpg600 = self.communicate('read_HRPG600')
            if isinstance(hrpg600, dict):
                current.update(hrpg600)
            switches = self.communicate('read_switch_ptl')
            if isinstance(switches, dict):
#                for k in switches:
#                    if switches[k] == 1: switches[k] = True
#                    if switches[k] == 0: switches[k] = False
                current.update(switches)
            self.petalbox_status.update(current)
            self.petalbox_status['last_updated'] = datetime.datetime.utcnow().isoformat()
            self.petalbox_sv.write(self.petalbox_status)
        except Exception as e:
            self.error('_update_petalbox: Exception reading device status: %s' % str(e))
            
    def _update_telemetry(self):
        """
        Retrieve telemetry information from the petalcontroller
        """
        try:
            current = {}
            temps = self.communicate('read_temp_ptl')
            if isinstance(temps, dict):
                for k in temps:
                    if k.startswith('28-00'):
                        key = 'TEMP_' + k[-2:].upper()
                        current[key] = temps[k]
                    else:
                        current[k] = temps[k]
            pwms = self.communicate('read_fan_pwm')
            if isinstance(pwms, dict):
                for k in pwms:
                    current[str(k)+'_PWM'] = pwms[k]
            tach = self.communicate('read_fan_tach')
            if isinstance(tach, dict):
                for k in pwms:
                    current[str(k)+'_TACH'] = tach[k]
            fid_status = self.communicate('get_fid_status')
            if isinstance(fid_status, dict):
                for k in fid_status:
                    current['FID_'+str(k)] = fid_status[k]
            current['last_updated'] = datetime.datetime.utcnow().isoformat().replace('T',' ')
            self.telemetry_sv.write(current)
        except Exception as e:
            self.error('_update_telemetry: Exception reading telemetry: %s' % str(e))

    def _update_positions(self):
        """
        Retrieve expected position information
        """
        try:
            current = self.expected_current_position(self.posids, key='obsXY')
            p = zip(self.posids, current)
            self.positions_sv.write(list(p))
        except Exception as e:
            self.error('_update_positions: Exception reading expected positions: %s' % str(e))
                    
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
        try:
            for m in self.schedule.move_tables:
                m.posmodel.postmove_cleanup(m.for_cleanup)
        except Exception as e:
            self.error('_postmove_cleanup: Exception: %s' % str(e))
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
    """
    Many options to configure can be set on the command line. Some are processed here and the rest is passed on
    to the application framework.
    A configuration file (like protodesi_config.json in this directory) is required to provide the list of positioners
    and fiducials.
    logdir needs tobe set to tell the plate_control software where to write the log files.
    The convention for petal role names is PETALx where x is the petal number (from 0 through 9). The code extracts the
    petal number from the role name.
    For now we use the default service (DOStest) to advertise in device mode.
    device mode can be set on the command line with --device_mode True
    A typical command string to start a petal in device mode looks like this
    python3 petal_dos.py --role PETAL0 --device_mode True --logdir <your log directory --file protodesi_config.json
    """
    import argparse
    import json
    import sys, os
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--service',action='store',default='DOStest',type=str)
    parser.add_argument('--role', action='store', nargs = 1, required = True, help = 'Role name (required)', type=str)
    parser.add_argument('--logdir', action='store', help = 'Logfile directory (write access required)', type=str)
    parser.add_argument('--petal', action='store', nargs = 1, help = 'Petal Id [0-9]', type=int)
    parser.add_argument('--file', type=argparse.FileType('r'), required = True, help = 'file with pos_ids and fid_ids')                        
    args, unknown = parser.parse_known_args()

    # cleanup sys.args for application framework
    try:
        sys.argv.remove(args.file.name)
    except: 
        pass
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
        fid_can_ids = config[str(pid)]['fid_can_ids']
    else:
        print('Configuration file does not include pos and fid ids for petal %s' % str(pid))
        sys.exit()
        
    # Create application instance
    try:
        if args.logdir:
            myPetal = Petal(petal_id = pid, pos_ids = pos_ids, fid_ids = fid_ids, fid_can_ids = fid_can_ids, logdir = args.logdir, service='DOStest')
        else:
            myPetal = Petal(petal_id = pid, pos_ids = pos_ids, fid_ids = fid_ids, fid_can_ids = fid_can_ids, service='DOStest')
        # Enter run loop
        myPetal.run()
    except Exception as e:
        print('PETAL%d: Uncaught exception in run loop: %s' % (pid, str(e)))
        sys.exit()
