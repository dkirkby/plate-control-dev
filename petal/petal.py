from posmodel import PosModel
import posschedule
import posmovetable
import posstate
try:
    import poscollider
except:
    import sys
    print('Error while importing poscollider. Make sure you have compiled the cython file ' +
          'poscollider.pyx. Use setup.py in the petal directory, see usage comments in there.')
    sys.exit(1)
import posconstants as pc
import posschedstats
from petaltransforms import PetalTransforms
import time
import os
import random
import numpy as np
from astropy.table import Table as AstropyTable
try:
    # DBSingleton in the code is a class inside the file DBSingleton
    from DBSingleton import DBSingleton
    DB_COMMIT_AVAILABLE = True
except ImportError:
    DB_COMMIT_AVAILABLE = False
# try:
#     from DOSlib.constants import ConstantsDB
#     CONSTANTSDB_AVAILABLE = True
# except ImportError:
#     CONSTANTSDB_AVAILABLE = False
try:
    from DOSlib.util import raise_error
except ImportError:
    def raise_error(*args, **kwargs):
        raise RuntimeError(*args, **kwargs)
try:
    # Perhaps force this to be a requirement in the future?
    from DOSlib.flags import POSITIONER_FLAGS_MASKS, REQUEST_RESET_MASK, ENABLED_RESET_MASK, NON_PETAL_MASK
    FLAGS_AVAILABLE = True
except ImportError:
    FLAGS_AVAILABLE = False
    

class Petal(object):
    """Controls a petal. Communicates with the PetalBox hardware via PetalComm.

    The general sequence to make postioners move is:
        1. request all the desired moves from all the desired positioners
        2. schedule the moves (anti-collision and anti-backlash are automatically calculated here)
        3. send the scheduled move tables out to the positioners
        4. execute the move tables (synchronized start on all the positioners at once.

    Convenience wrapper functions are provided to combine these steps when desirable.

    Required initialization inputs:
        petal_id        ... unique int id of the petal

    Optional initialization inputs:
        posids          ... list, positioner ids. If provided, validate against the ptl_setting file. If empty [], read from the ptl_setting file directly.
        fidids          ... list, fiducial ids. If provided, validate against the ptl_setting file. If empty [], read from the ptl_setting file directly.
        simulator_on    ... boolean, controls whether in software-only simulation mode
        db_commit_on    ... boolean, controls whether to commit state data to the online system database (can be done with or without local_commit_on (available only if DB_COMMIT_AVAILABLE == True))
        local_commit_on ... boolean, controls whether to commit state data to local .conf files (can be done with or without db_commit_on)
        local_log_on    ... boolean, controls whether to commit timestamped log of state data to local .csv files (can can be done with or without db_commit_on)
        printfunc       ... method, used for stdout style printing. we use this for logging during tests
        verbose         ... boolean, controls whether verbose printout to console is enabled
        collider_file   ... string, file name of collider configuration file, no directory loction. If left blank will use default.
        sched_stats_on  ... boolean, controls whether to log statistics about scheduling runs
        anticollision   ... string, default parameter on how to schedule moves. See posschedule.py for valid settings.
        petal_loc       ... integer, (option) location (0-9) of petal in FPA
        phi_limit_on    ... boolean, for experts only, controls whether to enable/disable a safety limit on maximum ra
        sync_mode       ... string, 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners

    Note that if petal.py is used within PetalApp.py, the code has direct access to variables defined in PetalApp. For example self.anticol_settings
    Eventually we could clean up the constructure (__init__) and pass viewer arguments.
    """

    def __init__(self, petal_id=None, petal_loc=None, posids=None, fidids=None,
                 simulator_on=False, petalbox_id=None, shape=None,
                 db_commit_on=False, local_commit_on=True, local_log_on=True,
                 printfunc=print, verbose=False,
                 user_interactions_enabled=False, anticollision='freeze',
                 collider_file=None, sched_stats_on=False,
                 phi_limit_on=True, sync_mode='hard'):
        # specify an alternate to print (useful for logging the output)
        self.printfunc = printfunc
        self.printfunc(f'Running plate_control version: {pc.code_version}')
        self.printfunc(f'poscollider used: {poscollider.__file__}')
        # petal setup
        if None in [petal_id, petalbox_id, fidids, posids, shape] or \
                not hasattr(self, 'alignment'):
            self.printfunc('Some parameters not provided to __init__, reading petal config.')
            self.petal_state = posstate.PosState(
                unit_id=petal_id, device_type='ptl', logging=True,
                printfunc=self.printfunc)
            if petal_id is None:
                self.printfunc('Reading Petal_ID from petal_state')
                petal_id = self.petal_state.conf['PETAL_ID'] # this is the string unique hardware id of the particular petal (not the integer id of the beaglebone in the petalbox)
            if petalbox_id is None:
                self.printfunc('Reading petalbox_ID from petal_state')
                petalbox_id = self.petal_state.conf['PETALBOX_ID'] # this is the integer software id of the petalbox (previously known as 'petal_id', before disambiguation)
            if posids is None:
                self.printfunc('posids not given, read from ptl_settings file')
                posids = self.petal_state.conf['POS_IDS']
            if fidids is None:
                self.printfunc('fidids not given, read from ptl_settings file')
                fidids = self.petal_state.conf['FID_IDS']
            if shape is None:
                self.printfunc('Reading shape from petal_state')
                shape = self.petal_state.conf['SHAPE']
            if not hasattr(self, 'alignment'):
                self.alignment = {'Tx': self.petal_state.conf['X_OFFSET'],
                                  'Ty': self.petal_state.conf['Y_OFFSET'],
                                  'Tz': 0,
                                  'alpha': 0,
                                  'beta': 0,
                                  'gamma': self.petal_state.conf['ROTATION']}

        self.petalbox_id = petalbox_id
        self.petal_id = int(petal_id)
        self.shape = shape
        self._last_state = None
        self._posids_where_tables_were_just_sent = set()
        self._set_exposure_info(exposure_id=None, exposure_iter=None)
        if fidids in ['',[''],{''}]: # check included to handle simulation cases, where no fidids argued
            fidids = {}

        self.verbose = verbose # whether to print verbose information at the terminal
        self.simulator_on = simulator_on
        # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners
        assert sync_mode.lower() in ['hard','soft'], f'Invalid sync mode: {sync_mode}'
        self.sync_mode = sync_mode
        
        # sim_fail_freq: injects some occasional simulated hardware failures. valid range [0.0, 1.0]
        self.sim_fail_freq = {'send_tables': 0.0} 
        
        if not(self.simulator_on):
            import petalcomm
            self.comm = petalcomm.PetalComm(self.petalbox_id, user_interactions_enabled=user_interactions_enabled)
            self.comm.pbset('non_responsives', 'clear') #reset petalcontroller's list of non-responsive canids
            # get ops_state from petalcontroller
            try:
                o = self.comm.ops_state()
                self.ops_state_sv.write(o)
            except Exception as e:
                self.printfunc('init: Exception calling petalcontroller ops_state: %s' % str(e))

        # database setup
        self.db_commit_on = db_commit_on if DB_COMMIT_AVAILABLE else False
        if self.db_commit_on:
            os.environ['DOS_POSMOVE_WRITE_TO_DB'] = 'True'
            self.posmoveDB = DBSingleton(petal_id=int(self.petal_id))
        self.local_commit_on = local_commit_on
        self.local_log_on = local_log_on
        self.altered_states = set()
        self.altered_calib_states = set()

        # schedule stats module
        self.schedule_stats = posschedstats.PosSchedStats(enabled=sched_stats_on)
        self.sched_stats_dir = os.path.join(pc.dirs['kpno'], pc.dir_date_str())
        sched_stats_filename = f'PTL{self.petal_id:02}-pos_schedule_stats.csv'
        self.sched_stats_path = os.path.join(self.sched_stats_dir, sched_stats_filename)

        # must call the following 3 methods whenever petal alingment changes
        self.init_ptltrans()
        self.init_posmodels(posids)
        self._init_collider(collider_file, anticollision)
        
        # extra limitations on addressable target area. limit is a minimum phi value (like a maximum radius)
        self.typical_phi_limit_angle = self.collider.Eo_phi
        if phi_limit_on:
            self.limit_angle = self.typical_phi_limit_angle  # [deg] minimum poslocP angle to reject targets. Set to False or None to skip check
        else:
            self.limit_angle = None
            
        # fiducials setup
        self.fidids = {fidids} if isinstance(fidids,str) else set(fidids)
        for fidid in self.fidids:
            self.states[fidid] = posstate.PosState(fidid,
                                   logging=self.local_log_on, device_type='fid',
                                   printfunc=self.printfunc, petal_id=self.petal_id,
                                   alt_move_adder=self._add_to_altered_states,
                                   alt_calib_adder=self._add_to_altered_calib_states)
            self.devices[self.states[fidid]._val['DEVICE_LOC']] = fidid

        # pos flags setup
        if FLAGS_AVAILABLE:
            self.flags = POSITIONER_FLAGS_MASKS
            self.reset_mask = REQUEST_RESET_MASK
            self.enabled_mask = ENABLED_RESET_MASK
            self.non_petal_mask = NON_PETAL_MASK
            self.missing_flag = 0
        else:
            self.printfunc('WARNING: DOSlib.flags not imported! Flags will not be set!')
            self.flags = {}
            self.reset_mask = 0
            self.enabled_mask = 0
            self.non_petal_mask = 0
            self.missing_flag = 0
        self.pos_flags = {} #Dictionary of flags by posid for the FVC, use get_pos_flags() rather than calling directly
        self.disabled_devids = [] #list of devids with DEVICE_CLASSIFIED_NONFUNCTIONAL = True or FIBER_INTACT = False
        self._initialize_pos_flags(initialize=True, enabled_only=False)
        self._apply_all_state_enable_settings()

        self.hw_states = {}

    def is_pc_connected(self):
        if self.simulator_on:
            return True
        elif not hasattr(self, 'comm'):
            return False
        else:
            try:
                return self.comm.is_connected()
            except:
                return False

    def init_ptltrans(self, alignment=None):
        '''
        initialise PetalTransforms class as a property of petal
        called upon petal instantiation inside __init__()
        must also be called whenever petal alignment changes in the focal plane
        input (self.)alignment is a dict of 6 items structured as follows:
        self.alignment = {'Tx': 0,  # x translation in mm
                          'Ty': 0,  # y translation in mm
                          'Tz': 0,  # z translation in mm
                          'alpha': 0,  # x rotation in rad from DB
                          'beta': 0,  # y rotation in rad from DB
                          'gamma': 0}  # z rotation in rad from DB
        '''
        if alignment is None:
            # no alingment supplied, try to find self.alingment attribute
            if hasattr(self, 'alignment'):  # attribute found, just re-use it
                if self.verbose:
                    self.printfunc('Using existing petal.alignment')
            else:
                self.printfunc('Initialization requires petal.alignment'
                               'attribute to be set, using zeros.')
                self.alignment = {'Tx': 0,  # x translation in mm
                                  'Ty': 0,  # y translation in mm
                                  'Tz': 0,  # z translation in mm
                                  'alpha': 0,  # x rotation in rad
                                  'beta': 0,  # y rotation in rad
                                  'gamma': 0}  # z rotation rad
        else:  # new alingment supplied, overwrite self.aglinment attribute
            self.alignment = alignment
        self.printfunc(f'Petal transform initialised with\n{self.alignment}')
        self.trans = PetalTransforms(Tx=self.alignment['Tx'],
                                     Ty=self.alignment['Ty'],
                                     Tz=self.alignment['Tz'],
                                     alpha=self.alignment['alpha'],
                                     beta=self.alignment['beta'],
                                     gamma=self.alignment['gamma'])

    def init_posmodels(self, posids=None):
        # positioners setup
        if posids is None:  # posids are not supplied, only alingment changed
            assert hasattr(self, 'posids')  # re-use self.posids
            posids = self.posids
        else:  # posids are supplied
            pass  # just use supplied posids, ignore self.posids that may exist
        self.posmodels = {}  # key posid, value posmodel instance
        self.states = {}  # key posid, value posstate instance
        self.devices = {}  # key device_location_id, value posid
        self.shape == 'petal'
        for posid in posids:
            self.states[posid] = posstate.PosState(
                posid, logging=self.local_log_on, device_type='pos',
                printfunc=self.printfunc, petal_id=self.petal_id,
                alt_move_adder=self._add_to_altered_states,
                alt_calib_adder=self._add_to_altered_calib_states)
            self.posmodels[posid] = PosModel(state=self.states[posid],
                                             petal_alignment=self.alignment)
            self.devices[self.states[posid]._val['DEVICE_LOC']] = posid
        self.posids = set(self.posmodels.keys())
        self.canids = {posid:self.posmodels[posid].canid for posid in self.posids}
        self.busids = {posid:self.posmodels[posid].busid for posid in self.posids}
        self.canids_to_posids = {canid:posid for posid,canid in self.canids.items()}
        self.buscan_to_posids = {(self.busids[posid], self.canids[posid]): posid for posid in self.posids}
        self.set_motor_parameters()
        self.power_supply_map = self._map_power_supplies_to_posids()  # used by posschedulestage for annealing

    def _init_collider(self, collider_file=None, anticollision='freeze'):
        '''collider, scheduler, and animator setup
        '''
        kwargs = {'printfunc': self.printfunc, 'use_neighbor_loc_dict': True}
        if hasattr(self, 'anticol_settings'):
            self.printfunc('Using provided anticollision settings')
            kwargs['config'] = self.anticol_settings
        else:
            kwargs['configfile'] = collider_file
        self.collider = poscollider.PosCollider(**kwargs)
        self.anticol_settings = self.collider.config  # for case where petal does not yet have anticol_settings
        self.printfunc(f'Collider setting: {self.collider.config}')
        self.collider.add_positioners(self.posmodels.values())
        self.animator = self.collider.animator
        # this should be turned on/off using the animation start/stop
        # control methods below
        self.animator_on = False
        # keeps track of total time of the current animation
        self.animator_total_time = 0
        self.previous_animator_total_time = 0
        self.schedule = self._new_schedule()
        self.anticollision_default = anticollision
        

    # METHODS FOR POSITIONER CONTROL

    def request_targets(self, requests, allow_initial_interference=False):
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
                                    ... valid values are 'QS', 'dQdS', 'obsXY', 'ptlXY',
                                        'poslocXY', 'obsdXdY', 'poslocdXdY', 'poslocTP',
                                        'posintTP', or 'dTdP'
                    target      pair of target coordinates or deltas, of the form [u,v]
                                    ... the elements u and v can be floats or integers
                                    ... 1st element (u) is the value for q, dq, x, dx, t, or dt
                                    ... 2nd element (v) is the value for s, ds, y, dy, p, or dp
                    log_note    optional string to store alongside in the log data for this move
                                    ... gets stored in the 'NOTE' field
                                    ... if the subdict contains no note field, then '' will be added automatically
                                    
            allow_initial_interference ... rarely used, only by experts, see comments in posschedule.py

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
        if self.verbose:
            self.printfunc(f'petal: requests received {len(requests)}')
        # self.info(requests)  # this breaks when petal is not prepared by petalApp
        marked_for_delete = set()
        for posid in requests:
            if posid not in self.posids:
                continue   # pass
            requests[posid]['posmodel'] = self.posmodels[posid]
            self._initialize_pos_flags(ids = {posid})
            if 'log_note' not in requests[posid]:
                requests[posid]['log_note'] = ''
            if not(self.get_posfid_val(posid,'CTRL_ENABLED')):
                self.pos_flags[posid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
                marked_for_delete.add(posid)
                if self.verbose:
                    self.printfunc(f'petal: {posid} CTRL_ENABLED=False, '
                                   f'{len(marked_for_delete)} to delete')
            elif self.schedule.already_requested(posid):
                self.pos_flags[posid] |= self.flags.get('MULTIPLEREQUESTS', self.missing_flag)
                marked_for_delete.add(posid)
                if self.verbose:
                    self.printfunc(f'petal: {posid} already requested, '
                                   f'{len(marked_for_delete)} to delete')
            else:
                accepted = self.schedule.request_target(posid=posid,
                                        uv_type=requests[posid]['command'],
                                        u=requests[posid]['target'][0],
                                        v=requests[posid]['target'][1],
                                        log_note=requests[posid]['log_note'],
                                        allow_initial_interference=allow_initial_interference)
                if not accepted:
                    marked_for_delete.add(posid)
                    if self.verbose:
                        self.printfunc(f'petal: {posid} request not accepted, '
                                       f'{len(marked_for_delete)} to delete')
        for posid in marked_for_delete:
            del requests[posid]
        if self.verbose:
            self.printfunc(f'petal: {len(requests)} requests approved, '
                           f'{len(marked_for_delete)} deleted')
        return requests

    def request_direct_dtdp(self, requests, cmd_prefix=''):
        """Put in requests to the scheduler for specific positioners to move by specific rotation
        amounts at their theta and phi shafts.

        This method is generally recommended only for expert usage.

            - Anticollision is limited to 'freeze' or None modes.
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
                    
                    postmove_cleanup_cmds
                                optional dict with posmodel commands to execute after the move
                                    ... keys are the axisids (i.e. pc.T and pc.P)
                                    ... values are the command string for each axis

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
            self.pos_flags[posid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
            del requests[posid]
        for posid, request in requests.items():
            if posid not in self.posids:
                pass
            request['posmodel'] = self.posmodels[posid]
            if 'log_note' not in requests[posid]:
                request['log_note'] = ''
            table = posmovetable.PosMoveTable(request['posmodel'])
            table.set_move(0, pc.T, request['target'][0])
            table.set_move(0, pc.P, request['target'][1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'direct_dtdp'
            table.store_orig_command(string=cmd_str, val1=request["target"][0], val2=request["target"][1])
            table.append_log_note(request['log_note'])
            table.allow_exceed_limits = True
            if 'postmove_cleanup_cmds' in request:
                for axisid, cmd_str in request['postmove_cleanup_cmds'].items():
                    table.append_postmove_cleanup_cmd(axisid=axisid, cmd_str=cmd_str)
            self.schedule.expert_add_table(table)
        return requests

    def request_limit_seek(self, posids, axisid, direction, cmd_prefix='', log_note=''):
        """Request hardstop seeking sequence for a single positioner or all positioners
        in iterable collection posids. This method is generally recommended only for
        expert usage. Requests to disabled positioners will be ignored.
        
        ** IMPORTANT **
        This is a very EXPERT function. There is no situation where a normal user would
        ever call it. If you're even sniffing in this direction, be assured you want the
        vastly safer rehome_pos wrapper function (defined in PetalApp.py) instead.
        
        INPUTS:
            posids ... single positioner id or iterable collection of ids
            axisid ... 0 for theta or 1 for phi axis
            direction ... +1 or -1
            cmd_prefix ... optional, allows adding a descriptive string to the log
        """
        self._initialize_pos_flags(ids = posids)
        posids = {posids} if isinstance(posids,str) else set(posids)
        enabled = self.enabled_posmodels(posids)
        for posid in posids:
            if posid not in enabled.keys():
                self.pos_flags[posid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
        for posid, posmodel in enabled.items():
            search_dist = pc.sign(direction)*posmodel.axis[axisid].limit_seeking_search_distance
            table = posmovetable.PosMoveTable(posmodel)
            table.should_antibacklash = False
            table.should_final_creep  = False
            table.allow_exceed_limits = True
            table.allow_cruise = not(posmodel.state._val['CREEP_TO_LIMITS'])
            dist = [0,0]
            dist[axisid] = search_dist
            table.set_move(0, pc.T, dist[0])
            table.set_move(0, pc.P, dist[1])
            cmd_str = (cmd_prefix + ' ' if cmd_prefix else '') + 'limit seek'
            table.store_orig_command(string=f'{cmd_str} dir={direction}')
            table.append_log_note(log_note)
            axis_cmd_prefix = f'self.axis[{axisid}]'
            table.append_postmove_cleanup_cmd(axisid=axisid, cmd_str=f'{axis_cmd_prefix}.total_limit_seeks += 1')
            if direction < 0:
                direction_cmd_suffix = 'minpos'
            else:
                direction_cmd_suffix = 'maxpos'
            table.append_postmove_cleanup_cmd(axisid=axisid, cmd_str=f'{axis_cmd_prefix}.pos = {axis_cmd_prefix}.{direction_cmd_suffix}')
            self.schedule.expert_add_table(table)

    def request_homing(self, posids, axis='both', debounce=True, log_note=''):
        """Request homing sequence for positioners in single posid or iterable
        collection of posids. Finds the primary hardstop, and sets values for
        the max position and min position. Requests to disabled positioners
        will be ignored.
        
        ** IMPORTANT **
        This is an EXPERT function. A user should call the rehome_pos wrapper
        function (defined in PetalApp.py) instead.

        INPUTS:
            axis ... string, 'both' (default), 'theta_only', or 'phi_only'. Optional
                     argument that allows for homing either theta or phi only.
            
            debounce ... boolean, if True the hard limit strike is followed by
                         a small move off the hardstop in the opposite direction
                         
            log_note ... optional string to append in the log. N.B.: 'homing', the 
                         axis, and whether debounce was done, will all automatically
                         be included in the log, so it's just redundant and noisy to
                         include such information here. So this log_note is intended
                         more for contextual info not known to the petal, like name
                         of a human operator, or whether the sky was blue that day, etc.
        """
        axis = 'phi_only' if axis == 'phi' else axis  # deal with common typo
        axis = 'theta_only' if axis == 'theta' else axis  # deal with common typo
        assert axis in {'both', 'phi_only', 'theta_only'}, f'Error in request_homing, unrecognized arg axis={axis}'
        posids = {posids} if isinstance(posids,str) else set(posids)
        self._initialize_pos_flags(ids = posids)
        enabled = self.enabled_posmodels(posids)
        for posid in posids:
            if posid not in enabled.keys():
                self.pos_flags[posid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
        for posid, posmodel in enabled.items():
            directions = {}
            phi_note = None
            if axis in {'both', 'phi_only'}:
                directions[pc.P] = +1 # force this, because anticollision logic depends on it
                phi_note = pc.join_notes(log_note, 'homing phi')
                self.request_limit_seek(posid, pc.P, directions[pc.P], cmd_prefix='P', log_note=phi_note)
            if axis in {'both', 'theta_only'}:
                directions[pc.T] = posmodel.axis[pc.T].principle_hardstop_direction
                theta_note = 'homing theta'
                if phi_note == None:
                    theta_note = pc.join_notes(log_note, theta_note)
                self.request_limit_seek(posid, pc.T, directions[pc.T], cmd_prefix='T', log_note=theta_note)
            hardstop_debounce = [0,0]
            postmove_cleanup_cmds = {pc.T: '', pc.P:''}
            for i, direction in directions.items():
                cmd_prefix = f'self.axis[{i}].last_primary_hardstop_dir ='
                if direction < 0:
                    hardstop_debounce[i] = posmodel.axis[i].hardstop_debounce[0]
                    postmove_cleanup_cmds[i] = f'{cmd_prefix} -1.0'
                else:
                    hardstop_debounce[i] = posmodel.axis[i].hardstop_debounce[1]
                    postmove_cleanup_cmds[i] = f'{cmd_prefix} +1.0'
            if debounce:
                request = {posid:{'target': hardstop_debounce,
                                  'postmove_cleanup_cmds': postmove_cleanup_cmds}}
                self.request_direct_dtdp(request, cmd_prefix='debounce')
                
    def schedule_moves(self, anticollision='default', should_anneal=True):
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
        if anticollision == 'None':
            anticollision = None  # because DOS Console casts None into 'None'
        self.printfunc(f'schedule_moves called with anticollision = {anticollision}')
        if anticollision not in {None,'freeze','adjust'}:
            anticollision = self.anticollision_default
            self.printfunc(f'using default anticollision mode --> {self.anticollision_default}')
            
        # This temporary stateful storage is an unfortunate necessity for error
        # handling, when we need to reschedule the move tables. Needed here
        # because the sequence of schedule_moves() --> send_move_tables()
        # is not always an unbroken chain, hence can't always pass along the
        # arguments directly from one to the next.
        self.__current_schedule_moves_anticollision = anticollision
        self.__current_schedule_moves_should_anneal = should_anneal
        
        self.schedule.schedule_moves(anticollision, should_anneal)

    def send_move_tables(self, n_retries=1):
        """Send move tables that have been scheduled out to the positioners.
        
        The argument n_retries is for internal usage when handling error
        cases, where move tables need to be rescheduled and resent.
        
        Returns a set containing any posids for which sending the table failed.
        """
        self.printfunc(f'send_move_tables called (n_retries={n_retries})')
        hw_tables = self._hardware_ready_move_tables()
        if not hw_tables:
            self.printfunc('send_move_tables: no tables to send')
            return set()
        for tbl in hw_tables:
            self._posids_where_tables_were_just_sent.add(tbl['posid'])
        if self.simulator_on:
            sim_fail = random.random() <= self.sim_fail_freq['send_tables']
            if sim_fail:
                commanded_posids = [table['posid'] for table in hw_tables]
                num_fail = random.randint(1, len(commanded_posids)) if commanded_posids else 0
                sim_fail_posids = set(random.choices(commanded_posids, k=num_fail))
                sim_fail_buscans = {}
                for posid in sim_fail_posids:
                    busid = self.busids[posid]
                    if busid not in sim_fail_buscans:
                        sim_fail_buscans[busid] = []
                    sim_fail_buscans[busid].append(self.canids[posid])
                response = 'FAILED', sim_fail_buscans
            else:
                response = 'SUCCESS'
            if self.verbose:
                self.printfunc('Simulator skips sending move tables to positioners.')
        else:
            self._wait_while_moving() # note how this needs to be preceded by adding positioners to _posids_where_tables_were_just_sent, so that the wait function can await the correct devices
            response = self.comm.send_tables(hw_tables)
        failed_posids = self._handle_any_failed_send_of_move_tables(response, n_retries)
        if n_retries == 0 or not failed_posids:
            frozen = self.schedule.get_frozen_posids()
            for posid in frozen:
                self.pos_flags[posid] |= self.flags.get('FROZEN', self.missing_flag) # Mark as frozen by anticollision
            if any(frozen):
                self.printfunc(f'frozen: {frozen}')
            times = {tbl['total_time'] for tbl in hw_tables}
            self.printfunc(f'max move table time = {max(times):.4f} sec')
            self.printfunc(f'min move table time = {min(times):.4f} sec')
            self.printfunc('send_move_tables: Done')
        return failed_posids      
            
    def set_motor_parameters(self):
        """Send the motor current and period settings to the positioners.
        
        INPUTS:  None
        """
        if self.simulator_on:
            if self.verbose:
                self.printfunc('Simulator skips sending motor parameters to positioners.')
            return
        parameter_keys = ['CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CURR_HOLD', 'CREEP_PERIOD','SPINUPDOWN_PERIOD']
        currents_by_busid = dict((p.busid,{}) for posid,p in self.posmodels.items())
        periods_by_busid =  dict((p.busid,{}) for posid,p in self.posmodels.items())
        enabled = self.enabled_posmodels(self.posids)
        for posid, posmodel in enabled.items():
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
        self.printfunc(f'Set motor parameters for {len(enabled)} positioners')

    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        
        INPUTS:  None
        """
        self.printfunc('execute_moves called')
        if self.simulator_on:
            if self.verbose:
                self.printfunc('Simulator skips sending execute moves command to positioners.')
            self._postmove_cleanup()
        else:
            self.comm.execute_sync(self.sync_mode)
            self._postmove_cleanup()
            self._wait_while_moving()
        self._remove_posid_from_sent_tables('all')
        self.printfunc('execute_moves: Done')

    def schedule_send_and_execute_moves(self, anticollision='default', should_anneal=True):
        """Convenience wrapper to schedule, send, and execute the pending requested
        moves, all in one shot.
        """
        self.schedule_moves(anticollision, should_anneal)
        failed_posids = self.send_and_execute_moves()
        return failed_posids

    def send_and_execute_moves(self):
        """Convenience wrapper to send and execute the pending moves (that have already
        been scheduled).
            
        INPUTS:  None
        """
        failed_posids = self.send_move_tables()
        self.execute_moves()
        return failed_posids

    def quick_move(self, posids='', cmd='', target=[None, None],
                   log_note='', anticollision='default', should_anneal=True,
                   disable_limit_angle=False):
        """Convenience wrapper to request, schedule, send, and execute a single move command, all in
        one shot. You can argue multiple posids if you want, though note they will all get the same
        command and target sent to them. So for something like a local (theta,phi) coordinate
        this often makes sense, but not for a global coordinate.

        INPUTS:     posids    ... either a single posid or an iterable collection of posids (note sets don't work at DOS Console interface)
                    cmd       ... command string like those usually put in the requests dictionary (see request_targets method)
                    target    ... [u,v] values, note that all positioners here get sent the same [u,v] here
                    log_note  ... optional string to include in the log file
                    anticollsion  ... 'default', 'adjust', 'freeze', or None. See comments in schedule_moves() function
                    should_anneal ... see comments in schedule_moves() function
                    disable_limit_angle ... boolean, when True will turn off any phi limit angle
        """
        old_limit = self.limit_angle
        if disable_limit_angle:
            self.limit_angle = None
        requests = {}
        posids = {posids} if isinstance(posids, str) else set(posids)
        err_prefix = 'quick_move: error,'
        assert len(posids) > 0, f'{err_prefix} empty posids argument'
        assert cmd in pc.valid_move_commands, f'{err_prefix} invalid move command {cmd}'
        assert len(target) == 2, f'{err_prefix} target arg len = {len(target)} != 2'
        assert all(np.isfinite(target)), f'{err_prefix} non-finite target {target}'
        for posid in posids:
            requests[posid] = {'command':cmd, 'target':target, 'log_note':log_note}
        allow_initial_interference = anticollision == None
        self.request_targets(requests, allow_initial_interference)
        self.schedule_send_and_execute_moves(anticollision, should_anneal)
        self.limit_angle = old_limit

    def quick_direct_dtdp(self, posids='', dtdp=[0,0], log_note='', should_anneal=True):
        """Convenience wrapper to request, schedule, send, and execute a single move command for a
        direct (delta theta, delta phi) relative move. There is NO anti-collision calculation. This
        method is intended for expert usage only. You can argue an iterable collection of posids if
        you want, though note they will all get the same (dt,dp) sent to them.

        INPUTS:     posids    ... either a single posid or a list of posids (note sets don't work at DOS Console interface)
                    dtdp      ... [dt,dp], note that all posids get sent the same [dt,dp] here. i.e. dt and dp are each just one number
                    log_note  ... optional string to include in the log file
                    should_anneal ... see comments in schedule_moves() function
        """
        requests = {}
        posids = {posids} if isinstance(posids, str) else set(posids)
        err_prefix = 'quick_direct_dtdp: error,'
        assert len(posids) > 0, f'{err_prefix} empty posids argument'
        assert len(dtdp) == 2, f'{err_prefix} dtdp arg len = {len(dtdp)} != 2'
        assert all(np.isfinite(dtdp)), f'{err_prefix} non-finite target {dtdp}'
        for posid in posids:
            requests[posid] = {'target':dtdp, 'log_note':log_note}
        self.request_direct_dtdp(requests)
        self.schedule_send_and_execute_moves(None, should_anneal)
        
    default_dance_sequence = [(3,0), (0,1), (-3,0), (0,-1)]
    def dance(self, posids='all', n_repeats=1, delay=60, targets=default_dance_sequence,
              anticollision='default', should_anneal=True, disable_limit_angle=False):
        '''Repeatedly moves positioners to a series of positions at argued radius.
        
        INPUTS:     posids ... either 'all', a single posid, or an iterable collection of posids (note sets don't work at DOS Console interface), defaults to 'all''
                    n_repeats ... integer number of repeats of the sequence, defaults to 1
                    delay ... minimum seconds from move to move, defaults to 60
                    targets ... sequence of tuples giving poslocXY targets, default is [(3,0), (0,1), (-3,0), (0,-1)]
                    anticollsion  ... 'default', 'adjust', 'freeze', or None. See comments in schedule_moves() function
                    should_anneal ... see comments in schedule_moves() function, defaults to True
                    disable_limit_angle ... boolean, when True will turn off any phi limit angle, defaults to False
        '''
        if posids == 'all':
            posids = self.all_enabled_posids()
        n_repeats = int(n_repeats)
        delay = float(delay)
        assert n_repeats > 0, f'dance: invalid arg {n_repeats} for n_repeats'
        assert delay > 0, f'dance: invalid arg {delay} for delay'
        count = 0
        next_allowed_move_time = time.time() - delay + 0.001
        for n in range(n_repeats):
            for target in targets:
                assert len(target) == 2 and all([isinstance(val, (int, float, np.integer, np.float)) for val in target]), f'dance: invalid target {target}'
                count += 1
                sleep_time = next_allowed_move_time - time.time()
                if sleep_time > 0:
                    self.printfunc(f'Pausing {sleep_time:.1f} seconds before next move.')
                    time.sleep(sleep_time)
                note = pc.join_notes('petal dance sequence', f'move {count}')
                self.printfunc(note + f' to poslocXY = {target}')
                next_allowed_move_time = time.time() + delay
                self.quick_move(posids=posids, cmd='poslocXY', target=target, log_note=note,
                                anticollision=anticollision, should_anneal=should_anneal,
                                disable_limit_angle=disable_limit_angle)
                
                
# METHODS FOR FIDUCIAL CONTROL
    def set_fiducials(self, fidids='all', setting='on', save_as_default=False):
        """Set specific fiducials on or off.

        fidids ... one fiducial id string, or an iterable collection of fiducial id strings, or 'all'
        [KH: note that the fidids list might include devices that are not on this petal. The code must ignore those]           
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
        error = False
        all_off = False
        if self.simulator_on:
            self.printfunc('Simulator skips sending out set_fiducials commands on petal ' + str(self.petal_id) + '.')
            return {}
        if fidids == 'all' and setting=='off':
            self.printfunc('set_fiducials: calling comm.all_fiducials_off')
            ret = self.comm.all_fiducials_off()
            if 'FAILED' in ret:
                self.printfunc('WARNING: set_fiducials: calliing comm.all_fiducials_off failed: %s' % str(ret))
            else:
                all_off = True
        if fidids == 'all':
            fidids = self.fidids
        else:
            fidids = {fidids} if isinstance(fidids,str) else set(fidids)
        # currently fiducials don't have an enable flag in pos state (bypass for now)
        enabled = [fidid for fidid in fidids if True or self.get_posfid_val(fidid,'CTRL_ENABLED')]
        busids = [self.get_posfid_val(fidid,'BUS_ID') for fidid in enabled]
        canids = [self.get_posfid_val(fidid,'CAN_ID') for fidid in enabled]
        if isinstance(setting,int) or isinstance(setting,float):
            if setting < 0:
                setting = 0
            if setting > 100:
                setting = 100
            duties = [setting]*len(enabled)
        elif isinstance(setting, (list, tuple)):
            duties = []
            for f in enabled:
                i = enabled.index(f)
                duties.append(setting[i])
        elif setting == 'on':
            duties = [self.get_posfid_val(fidid,'DUTY_DEFAULT_ON') for fidid in enabled]
        else:
            duties = [self.get_posfid_val(fidid,'DUTY_DEFAULT_OFF') for fidid in enabled]
        fiducial_settings_by_busid = {busid:{} for busid in set(busids)}
        for idx, busid in enumerate(busids):
            fiducial_settings_by_busid[busid][canids[idx]] = duties[idx]
        if all_off:
            ret = fiducial_settings_by_busid
        else:
            self.comm.pbset('fiducials', fiducial_settings_by_busid)
            ret = self.comm.pbget('FIDUCIALS')

        settings_done = {}
        for i in range(len(enabled)):
            set_duty = duties[i]
            # protect against missing fiducials in ret
            if busids[i] in ret.keys() and canids[i] in ret[busids[i]].keys():
                if ret[busids[i]][canids[i]] != duties[i]:
                    self.printfunc('WARNING: set_fiducials: disagreement in fiducial set duty and returned duty, ID: %s' % enabled[i])
                    set_duty = ret[busids[i]][canids[i]]
                    error = True
            elif not save_as_default:
                # Use remembered state, fid not responding but only if not saving defaults
                self.printfunc('WARNING: set_fiducials: fiducials %s not returned by petalcontroller, state not set.' % enabled[i])
                set_duty = self.get_posfid_val(enabled[i], 'DUTY_STATE')
                error = True
            self.set_posfid_val(enabled[i], 'DUTY_STATE', set_duty, check_existing=True)
            settings_done[enabled[i]] = set_duty
            if save_as_default:
                self.set_posfid_val(enabled[i], 'DUTY_DEFAULT_ON', set_duty, check_existing=True)
        self.commit(mode='both', log_note='set fiducial parameters')
        if error:
            return 'FAILED: not all fiducials set. Try moving to READY if trying to turn them off.'
        else:
            return settings_done

    @property
    def n_fiducial_dots(self):
        """Returns number of fixed fiducial dots this petal contributes
        in the field of view.
        """
        n_dots = [int(self.get_posfid_val(fidid, 'N_DOTS'))
                  for fidid in self.fidids]
        return sum(n_dots)

# METHODS FOR CONFIGURING THE PETALBOX

    def _set_hardware_state(self, hw_state):
        '''
        Sets the hardware state on the petal controller, scheme documented here:
        https://docs.google.com/document/d/1U9mxdTwgT6Bj5Sw_oTerU5wkiq9cXnN7I8QpMl_LT9E/edit#heading=h.ineqjw6t36ek

        Goes through and sets the parameters that defines the state. Checks
        the state at the end and returns the state that was actually set
        (either the one requested or 'ERROR') along with a list of strings
        explaining the reason for an error state.
        '''
        hw_state = hw_state.upper()
        state_list = ['STANDBY','READY','OBSERVING'] #INITIALIZED ops_state also exists but can only be reached when BBB reboots
        if not hasattr(self, '_last_state'):
            self._last_state = None
        assert hw_state in state_list, '_set_hardware_state: invalid state requested, possible states: %s' % state_list
        # Setup what values are expected when checking the state in the future
        # Notation: key (device name), tuple with value, max wait time for state change
        if hw_state in ['INITIALIZED', 'STANDBY', 'READY', 'OBSERVING']: 
            self._last_state = hw_state
        # Set petalbox State
        if self.simulator_on:
            if hasattr(self, 'ops_state_sv'):
                self.ops_state_sv.write('READY')
            return 'OBSERVING' # bypass everything below if in petal sim mode - sim should always be observing
        todo = list(pc.PETAL_OPS_STATES[self._last_state].keys())
        for key, value in pc.PETAL_OPS_STATES[self._last_state].items():
            old_state = self.comm.pbget(key)
            if old_state == pc.PETAL_OPS_STATES[self._last_state][key][0]:
                # Don't change state if it's where we want it
                todo.remove(key)
            # Ignore GFAFAN
            else:
                # Change state because it needs to be changed
                ret = self.comm.pbset(key, value[0])
                if 'FAILED' in ret:
                    #fail message, should only happen if petalcontroller changes - code will raise error later on
                    self.printfunc('_set_hardware_state: WARNING: key %s returned %s from pbset.' % (key,ret))
        # now check if all state changes are complete
        # wait for timeout, if still inconsistent raise exception
        failed = {}
        start = time.time()
        while len(todo) != 0:
            for key in pc.PETAL_OPS_STATES[self._last_state].keys():
                if key not in todo:
                    continue
                new_state = self.comm.pbget(key)
                if new_state == pc.PETAL_OPS_STATES[self._last_state][key][0]:
                    todo.remove(key)
                elif key == 'GFA_FAN': #GFA has different structure
                    req = pc.PETAL_OPS_STATES[self._last_state][key][0]['inlet'][0], pc.PETAL_OPS_STATES[self._last_state][key][0]['outlet'][0]
                    new = new_state['inlet'][0], new_state['outlet'][0]
                    if req == new:
                        todo.remove(key)
                else:   # check timeout
                    if time.time() > start + pc.PETAL_OPS_STATES[self._last_state][key][1]:
                        failed[key] = (new_state, pc.PETAL_OPS_STATES[self._last_state][key][0])
                        self.printfunc('_set_hardware_state: Timeout for %r' % key)
                        todo.remove(key)
            time.sleep(1)

        if len(failed) == 0:
            ret = self.comm.ops_state(hw_state)
            if 'FAILED' not in ret:
                self.printfunc('_set_hardware_state: all devices have changed state.')
                if hasattr(self, 'ops_state_sv'):
                    self.ops_state_sv.write(ret)
                if hw_state != 'OBSERVING':
                    # fids off
                    for fid in self.fidids:
                        self.set_posfid_val(fid, 'DUTY_STATE', 0, check_existing=True)
            else:
                self.printfunc('_set_hardware_state: FAILED: when calling comm.ops_state: %s' % ret)
                raise_error('_set_hardware_state: comm.ops_state returned %s' % ret)
        else:
            self.printfunc('_set_hardware_state: FAILED: some inconsistent device states (new/last): %r' % failed)
            raise_error('_set_hardware_state: Inconsistent device states: %r' % failed)
        return hw_state

    def _get_hardware_state(self, what = None):
        '''
        Loops through keys in pc.PETAL_OPS_STATES[self._last_state] to compare with what the
        PetalController thinks they are. Any differences are recorded and
        'ERROR' state is set if there are any discrepencies. Otherwise
        returns the state of the PetalController.

        Arguments:
        what =  list (returns list of current settings for variables in last_state)
             =  <key> (returns current value of key)
        '''
        err_strings = []
        if self.simulator_on: #Sim should always be observing
            return 'OBSERVING', err_strings
        if not hasattr(self, 'comm') or getattr(self, 'comm') is None:
            return 'ERROR', 'Petal controller is not connected'
        if self._last_state is None:
            self.printfunc('_get_hardware_state: No state yet set by petal. Trying to reconstruct from PC settings')
            for state in ['INITIALIZED', 'STANDBY', 'READY', 'OBSERVING']:
                errors = self._check_hardware_state(state)
                if errors == []:
                    self._last_state = state
                    break
            if self._last_state is None:
                return 'ERROR', 'petal hardware state unknown'
        # Look for different settings from what petal last set.
        errors = self._check_hardware_state(self._last_state, what = what)
        if what != None:
            return errors
        if isinstance(errors, list) and len(errors) == 0:
            # Check if petal and PC ops states match
            pc_ops = self.comm.ops_state()
            if pc_ops != self._last_state:
                self.printfunc('_get_hardware_state: PC ops state (%r) does not match device settings (%r). Corrected.' % (pc_ops, self._last_state))
                self.comm.ops_state(self._last_state)
            return self._last_state, errors
        else: #If errors were found, set 'ERROR' state and return 'ERROR' as well as strings explaining why.
            return 'ERROR', errors

    def _check_hardware_state(self, state, what = None):
        # Look for different settings from what petal last set.
        err_strings = []
        current = {}
        for key in pc.PETAL_OPS_STATES[state].keys():
            fbk = self.comm.pbget(key)
            if what == 'list' or what == key:
                current[key] = fbk
            if key == 'GFA_FAN' and isinstance(fbk,dict): #sadly GFA_FAN is a little weird.
                for k in fbk.keys(): #should be 'inlet' and 'outlet'
                    if fbk[k][0] != pc.PETAL_OPS_STATES[state][key][0][k][0]: #comparing only off/on, not worring about PWM or TACH
                        err_strings.append(key+' expected: '+str(pc.PETAL_OPS_STATES[state][key][0][k][0])+', got: '+str(fbk[k][0]))
            else:
                if pc.PETAL_OPS_STATES[state][key][0] != fbk:
                    err_strings.append(key+' expected: '+str(pc.PETAL_OPS_STATES[state][key][0])+', got: '+str(fbk))
        if what == None:
            return err_strings
        else:
            return current

    def reset_petalbox(self):
        """Reset all errors and turn all enables off.  This method
        returns the petalbox to its default safe state (how it comes up prior to
        communicating with the petal).
        """
        if not self.simulator_on:
            self.comm.configure()

# GETTERS, SETTERS, STATUS METHODS
    def get_information(self, what):
        """
        returns petalcontroller information
        """
        return self.comm.get(what)

    def get_posfid_val(self, uniqueid, key):
        """Retrieve the state value identified by string key, for positioner or fiducial uniqueid."""
        if uniqueid in self.posids.union(self.fidids):
            return self.states[uniqueid]._val[key]
        else:
            return 'Not in petal'

    def set_posfid_val(self, device_id, key, value, check_existing=False):
        """Sets a single value to a positioner or fiducial. In the case of a 
        fiducial, this call does NOT turn the fiducial physically on or off.
        It only saves a value.
        
        Returns a boolean whether the value was accepted.
        
        The boolean arg check_existing only changes things if the old value
        differs from new. A special return value of None is returned if the
        new value is the same.
        """
        if device_id not in self.posids | self.fidids:
            raise ValueError(f'{device_id} not in PTL{self.petal_id:02}')
        state = self.states[device_id]
        if check_existing:
            old = state._val[key] if key in state._val else None
            if old == value:
                return None
        accepted = state.store(key, value, register_if_altered=True)
        return accepted
    
    def get_posids_with_commit_pending(self):
        '''Returns set of all posids for which there is a commit to DB pending.
        '''
        states = self.altered_states | self.altered_calib_states
        unit_ids = {state.unit_id for state in states}
        posids = unit_ids & self.posids
        return posids
    
    def _add_to_altered_states(self, state):
        '''Wrapper function so that another module (posstate) can add itself
        to petal's cached set.'''
        self.altered_states.add(state)
    
    def _add_to_altered_calib_states(self, state):
        '''Wrapper function so that another module (posstate) can add itself
        to petal's cached set.'''
        self.altered_calib_states.add(state)
    
    def get_pbdata_val(self, key):
        """Requests data from petalbox using the pbget method.
        key ... string, corresponds to petalbox pbget method keys (eg 'TELEMETRY', 'CONF_FILE')
        """
        return self.comm.pbget(key)

    def commit(self, mode='move', log_note=''):
        '''Commit move data or calibration data to DB and/or local config and
        log files. A note string may optionally be included to go along with
        this entry. mode can be: 'move', 'calib', 'both'
        '''
        if mode == 'both':
            self._commit(mode='move', log_note=log_note)
            self._commit(mode='calib', log_note=log_note)
            return
        elif mode not in {'move', 'calib'}:
            self.printfunc(f'Error: mode {mode} not recognized in commit()')
            return
        self._commit(mode=mode, log_note=log_note)

    def _commit(self, mode, log_note):
        '''Underlying implemetation for commit().'''
        if not self._commit_pending(mode):
            return
        if mode == 'move':
            states = self.altered_states
            if log_note:
                for state in states:
                    state.append_log_note(log_note)
        elif mode == 'calib':
            states = self.altered_calib_states
            # As of 2020-06-04, no field exists in calib db for log_notes,
            # hence they are ignored in this case.
        self._send_to_db_as_necessary(states, mode)
        self._write_local_logs_as_necessary(states)
        if mode == 'move':
            self.altered_states = set()
            if self.schedule_stats.is_enabled():
                stats_path = self.sched_stats_path
                new_path = self.schedule_stats.save(path=stats_path)
                if new_path != stats_path:
                    self.sched_stats_path = new_path
                    self.printfunc(f'Updated schedule stats path from {stats_path} to {new_path}')
        elif mode == 'calib':
            self.altered_calib_states = set()
        
        # 2020-06-29 [JHS] This step is a simple way to guarantee freshness of
        # the collider cache. Executes in 6.3 ms on my desktop, for a simulated
        # petal of 502 positioners.
        self.collider.refresh_calibrations(verbose=False)

    def _send_to_db_as_necessary(self, states, mode):
        '''Saves state data to posmove database, if that behavior is currently
        turned on.
        '''
        if self.db_commit_on and not self.simulator_on:
            if mode == 'move':
                type1, type2 = 'pos_move', 'fid_data'
            elif mode == 'calib':
                type1, type2 = 'pos_calib', 'fid_calib'
            pos_commit_list = [st for st in states if st.type == 'pos']
            fid_commit_list = [st for st in states if st.type == 'fid']
            if len(pos_commit_list) > 0:
                for state in pos_commit_list:
                    state.store('EXPOSURE_ID', self._exposure_id, register_if_altered=False)
                    state.store('EXPOSURE_ITER', self._exposure_iter, register_if_altered=False)
                self.posmoveDB.WriteToDB(pos_commit_list, self.petal_id, type1)
            if len(fid_commit_list) > 0:
                self.posmoveDB.WriteToDB(fid_commit_list, self.petal_id, type2)
            if mode == 'move':
                if self._currently_in_an_exposure():
                    committed_posids = {state.unit_id for state in pos_commit_list}
                    overlapping_commits = committed_posids & self._devids_committed_this_exposure
                    if overlapping_commits:
                        self.printfunc(f'WARNING: device_ids {overlapping_commits} received multiple posDB ' +
                                       f'commit requests for expid {self._exposure_id}, iteration ' +
                                       f'{self._exposure_iter}. These have the potential to overwrite data.')
                    self._devids_committed_this_exposure |= committed_posids
        if mode == 'move':
            for state in self.altered_states:
                state.clear_log_notes() # known minor issue: if local_log_on simultaneously with DB, this may clear the note field
            
    def _write_local_logs_as_necessary(self, states):
        '''Saves state data to disk, if those behaviors are currently turned on.'''
        for state in states:
            if self.local_commit_on:
                state.write()
            if self.local_log_on:
                state.log_unit()
    
    def _commit_pending(self, mode):
        '''Returns boolean whether there is a pending commit for the argued
        mode. Argument mode can be either 'move' or 'calib'.'''
        if mode == 'move':
            return len(self.altered_states) > 0
        elif mode == 'calib':
            return len(self.altered_calib_states) > 0
        else:
            self.printfunc(f'Error: mode {mode} not recognized in _commit_pending()')
        
    def _late_commit(self, data):
        '''Commits "late" data to the posmovedb.
        
        There are several special fields for which this is possible, defined in
        posconstants.late_commit_defaults.
                
        If _set_exposure_info() has previously been called, while
        _clear_exposure_info() has not yet been called, then petal understands
        that we are currently in the middle of a known exposure. In this case
        the behavior can vary according to the particular posid:
            
         1. For a positioner which already had some data committed during this
            exposure, the new data argued here gets written to that same,
            existing row in the database.
               
         2. If no data yet committed for this positioner, then a new row is
            generated to hold the data.
        
        INPUTS:
            data ... dict with keys --> posids and values --> subdicts
                     subdicts --> key/value pairs
                     valid subdict keys are defined in first line of function
        
        OUTPUTS:
            No outputs
        '''
        if not self.db_commit_on or self.simulator_on:
            return
        allowed_keys = pc.late_commit_defaults.keys()
        valid_posids = {p for p in data.keys() if p in self.posids}
        data_for_existing_rows = []
        data_for_new_rows = {}
        for posid in valid_posids:
            this_data = {k:v for k,v in data[posid].items() if k in allowed_keys}
            if not this_data:
                continue
            if posid in self._devids_committed_this_exposure: 
                this_data['POS_ID'] = posid
                data_for_existing_rows.append(this_data)
            else:
                data_for_new_rows[posid] = this_data
        if data_for_existing_rows:
            kwargs = {'input_list': data_for_existing_rows,
                      'petal_id': self.petal_id,
                      'types': 'pos_move'}
            if self._exposure_id is not None:
                kwargs['expid'] = self._exposure_id
            if self._exposure_iter is not None:
                kwargs['iteration'] = self._exposure_iter
            self.posmoveDB.UpdateDB(**kwargs)
        if data_for_new_rows:
            for posid, subdict in data_for_new_rows.items():
                log_note = 'Stored new:'
                accepted = []
                for key, val in subdict.items():
                    accepted += [self.set_posfid_val(posid, key, val, check_existing=True)]
                    log_note += f' {key}'
                if any(accepted):
                    self.set_posfid_val(posid, 'LOG_NOTE', log_note)
            self._commit(mode='move', log_note='')  # no need for extra log note info
        self._clear_late_commit_data()
    
    def _clear_late_commit_data(self):
        '''Clears special data fields associated with the "_late_commit"
        function.
        '''
        for posid in self.posids:
            self.states[posid].clear_late_commit_entries()

    def _set_exposure_info(self, exposure_id, exposure_iter=None):
        '''Sets exposure identification values. These will be included in the
        posmovedb upon the next commit(). They will subsequently be cleared
        during _postmove_cleanup().
        '''
        self._exposure_id = exposure_id
        self._exposure_iter = exposure_iter
        self._devids_committed_this_exposure = set()
        
    def _clear_exposure_info(self):
        '''Clears exposure identification values. C.f. _set_exposure_info().
        '''
        self._set_exposure_info(exposure_id=None, exposure_iter=None)
    
    def _currently_in_an_exposure(self):
        '''Returns boolean whether the the petal understands that we are
        currently in the process of an exposure.
        '''
        return (self._exposure_id is not None) and (self._exposure_iter is not None)

    def expected_current_position(self, posid, key):
        """Retrieve the current position, for a positioner identied by posid,
        according to the internal tracking of its posmodel object.
        Returns a two element list.
        
        INPUTS:  posid ... id string for a single positioner
                 key ... coordinate system to return position in
        
        Valid keys are:
            'posintTP, 'poslocXY', 'poslocTP',
            'QS', 'flatXY', 'obsXY', 'ptlXY'
        See comments in posmodel.py for explanation of these values.
        """
        if key == 'posintTP':
            return self.posmodels[posid].expected_current_posintTP
        elif key == 'poslocTP':
            return self.posmodels[posid].expected_current_poslocTP
        pos = self.posmodels[posid].expected_current_position
        if key in pos.keys():
            return pos[key]
        else:
            self.printfunc(f'Unrecognized key {key} when requesting '
                           f'expected_current_position of posid {posid}')

    def all_enabled_posids(self):
        """Returns set of all posids of positioners with CTRL_ENABLED == True.
        """
        return {p for p in self.posids if self.posmodels[p].is_enabled}

    def all_disabled_posids(self):
        """Returns set of all posids of positioners with CTRL_ENABLED == False.
        """
        return set(self.posids) - set(self.all_enabled_posids())

    def enabled_posmodels(self, posids):
        """Returns dict with keys = posids, values = posmodels, but only for
        those positioners in the collection posids which are enabled.
        """
        pos = set(posids).intersection(self.posids)
        return {p: self.posmodels[p] for p in pos if self.posmodels[p].is_enabled}

    def get_pos_flags(self, posids='all', should_reset = False):
        '''Getter function for self.pos_flags that carries out a final is_enabled
        check before passing them off. Important in case the PC sets ctrl_enabled = False
        when a positioner is not responding.
        '''
        pos_flags = {}
        if posids == 'all':
            posids = self.posids
        for posid in posids:
            if posid not in self.posids:
                continue  # this posid does not belong to this petal
            self._apply_state_enable_settings(posid)
            if self.posmodels[posid].is_enabled:
                self.pos_flags[posid] = (self.pos_flags[posid] | self.enabled_mask) ^ self.enabled_mask
            pos_flags[posid] = self.pos_flags[posid]
        if should_reset:
            self._initialize_pos_flags()
        return pos_flags
    
    def set_keepouts(self, posids, radT=0.0, radP=0.0, angT=0.0, angP=0.0, classify_retracted=False):
        '''Convenience function to set parameters affecting positioner collision
        envelope(s). One or more posids may be argued. The other args will be
        uniformly applied to ALL argued posids.
        
        INPUTS:
            posids ... 'all', an id string, or an iterable
            angT ... new value for 'KEEPOUT_EXPANSION_THETA_RADIAL'
            radT ... new value for 'KEEPOUT_EXPANSION_PHI_RADIAL'
            angP ... new value for 'KEEPOUT_EXPANSION_THETA_ANGULAR'
            radP ... new value for 'KEEPOUT_EXPANSION_PHI_ANGULAR'
            classify_retracted ... new value for 'CLASSIFIED_AS_RETRACTED'
        '''
        if posids == 'all':
            posids = self.posids
        else:
            posids = {posids} if isinstance(posids, str) else set(posids)
        invalid_posids = {p for p in posids if p not in self.posids}
        posids -= invalid_posids
        if invalid_posids:
            self.printfunc(f'{len(invalid_posids)} positioner id(s) not found on petal id' +
                           f' {self.petal_id}. These will be skipped: {invalid_posids}')
            self.printfunc(f'{len(posids)} valid positioner(s) remaining')
        new = {'KEEPOUT_EXPANSION_THETA_RADIAL': radT,
               'KEEPOUT_EXPANSION_PHI_RADIAL': radP,
               'KEEPOUT_EXPANSION_THETA_ANGULAR': angT,
               'KEEPOUT_EXPANSION_PHI_ANGULAR': angP,
               'CLASSIFIED_AS_RETRACTED': classify_retracted}
        msg_prefix = 'set_keepouts:'
        err_prefix = f'{msg_prefix} error,'
        assert len(posids) > 0, f'{err_prefix} empty posids argument'
        for key, val in new.items():
            try:
                float(val)
            except:
                assert False, f'{err_prefix} non-numeric {key} {val}'
            assert np.isfinite(val), f'{err_prefix} non-finite {key} {val}'
        assert isinstance(classify_retracted, bool), f'{err_prefix} non-boolean classify_retracted {classify_retracted}'
        changed = set()
        for key, val in new.items():
            changed_this_key = set()
            for posid in posids:
                accepted = self.set_posfid_val(posid, key, val, check_existing=True)
                if accepted:
                    changed_this_key.add(posid)
            if changed_this_key:
                self.printfunc(f'{msg_prefix} Changed {key} to {val} for {len(changed_this_key)}' +
                               f' positioner(s): {changed_this_key}')
            changed |= changed_this_key
        if changed:
            self.printfunc(f'{msg_prefix} Committing new values for {len(changed)} positioner(s)')
            self.commit(mode='calib')  # as of 2020-06-29, all valid args here are stored in calib table of DB
        else:
            self.printfunc(f'{msg_prefix} No positioners found requiring parameter update(s)')
            
    def cache_keepouts(self):
        '''Cache keepout parameters to a temporary file on disk. Returns the path
        to the cache file.
        
        INPUTS:  None
        '''
        msg_prefix = 'cache_keepouts:'
        path = pc.get_keepouts_cache_path(self.petal_id)
        data = {key:[] for key in ['POS_ID'] + pc.keepout_keys}
        for posid in self.posids:
            data['POS_ID'] += [posid]
            for key in pc.keepout_keys:
                data[key] += [self.states[posid]._val[key]]
        table = AstropyTable(data)
        table.write(path, overwrite=True, delimiter=',')
        self.printfunc(f'{msg_prefix} Collision keepout settings for {len(table)} positioners cached to {path}')
        return path
        
    def restore_keepouts(self, path=None):
        '''Restores keepout parameters from cache file on disk. In typical usage
        no path needs to be provided, and the default file path will be used.
        
        INPUTS:  path ... string, optional file path where to find cached data
        '''
        msg_prefix = 'restore_keepouts:'
        argued_path = str(path)
        argued_ext = os.path.splitext(argued_path)[1]
        default_path = pc.get_keepouts_cache_path(self.petal_id)
        default_ext = os.path.splitext(default_path)[1]
        if os.path.exists(argued_path) and argued_ext == default_ext:
            path_to_use = argued_path
        else:
            path_to_use = default_path
        assert os.path.exists(path_to_use), f'{msg_prefix} error, no cache file found at {path_to_use}'
        self.printfunc(f'{msg_prefix} Restoring collision keepout settings from {path_to_use}')
        table = AstropyTable.read(path_to_use)
        changed = set()
        for row in table:
            posid = row['POS_ID']
            for key in pc.keepout_keys:
                accepted = self.set_posfid_val(posid, key, row[key], check_existing=True)
                if accepted:
                    changed.add(posid)
        self.printfunc(f'{msg_prefix} {len(changed)} of {len(table)} positioners found with keepout values needing change.')
        skipped = set(table['POS_ID']) - changed
        if any(skipped):
            self.printfunc(f'{msg_prefix} {len(skipped)} skipped. The skipped positioners are: {skipped}')
        if any(changed):
            self.printfunc(f'{msg_prefix} Committing restored values for {len(changed)} positioners.')
            self.commit(mode='calib')
            
    def get_collision_params(self, posid):
        '''Returns a formatted string describing the current parameters known to
        the collider module for a given positioner.
        
        INPUTS:
            posid ... string identifying the positioner
        '''
        if posid in self.posids:
            out = f'{posid}:'
            for dict_name in ['R1', 'R2', 'x0', 'y0', 't0', 'p0', 'keepout_expansions',
                              'pos_neighbors', 'fixed_neighbor_cases', 'keepouts_T',
                              'keepouts_P']:
                value = getattr(self.collider, dict_name)[posid]
                if dict_name == 'fixed_neighbor_cases':
                    value = {pc.case.names[x] for x in value}
                out += f'\n {dict_name}: {value}'
            out += f'\n classified_as_retracted: {posid in self.collider.classified_as_retracted}'
        else:
            out = f'No posid {posid} found'
        return out
    
    def get_posmodel_params(self, posid):
        '''Returns a formatted string describing the current parameters known to
        the posmodel instance for a given positioner.
        
        INPUTS:
            posid ... string identifying the positioner
        '''
        properties = ['canid', 'busid', 'deviceloc', 'is_enabled', 'expected_current_position',
                      'full_range_posintT', 'full_range_posintP',
                      'targetable_range_posintT', 'targetable_range_posintP',
                      'abs_shaft_speed_cruise_T', 'abs_shaft_speed_cruise_P']
        def formatter(key, value):
            return f'\n {key:12s} : {value}'
        if posid in self.posmodels:
            out = f'{posid}:'
            for name in properties:
                prop = getattr(self.posmodels[posid], name)
                if isinstance(prop, dict):
                    for k, v in prop.items():
                        out += formatter(k,v)
                else:
                    out += formatter(name, prop)
        else:
            out = f'No posid {posid} found'
        return out
    
    def quick_query(self, key=None, op='', value='', posids='all', mode='compact'):
        '''Returns a list of posids which have a parameter key with some
        relation op to value. Not all conceivable param keys and ops are
        necessarily supported. Can be applied to all posids on the petal, or
        an argued subset.
        
        INPUTS:
            key ... string like 'POS_P' or 'LENGTH_R1', etc
            op ... string like '>' or '==', etc. Can leave blank to simply retrieve all values.
                   assume '==' if a value is argued but no op
            value ... the operand to compare against, usually a number for most keys
            posids ... 'all' or iterator of positioner id strings
            mode ... 'compact', 'expanded', 'iterable' ... controls return type
            
        Call with no arguments, to get a list of valid keys and ops.
        
        Any position value (such as 'posintT' or 'Q' or 'flatX') is the current
        *expected* position (i.e. the internally-tracked value), based on latest
        POS_T, POS_P, and calibration params.
        '''
        import operator
        position_keys = {'posintT', 'posintP', 'poslocT', 'poslocP', 'poslocX',
                         'poslocY', 'flatX', 'flatY', 'ptlX', 'ptlY', 'obsX',
                         'obsY', 'Q', 'S'}
        state_keys = set(pc.calib_keys) | {'POS_P', 'POS_T', 'CTRL_ENABLED'}
        constants_keys = set(pc.constants_keys)
        id_keys = {'CAN_ID', 'BUS_ID', 'DEVICE_LOC', 'POS_ID'}
        valid_keys = position_keys | state_keys | constants_keys | id_keys
        valid_ops = {'>': operator.gt,
                     '>=': operator.ge,
                     '==': operator.eq,
                     '<': operator.lt,
                     '<=': operator.le,
                     '!=': operator.ne,
                     '': None}
        if not any([key, op, value]):
            valids = {'state_keys': sorted(state_keys),
                      'position_keys': sorted(position_keys),
                      'constants_keys': sorted(constants_keys),
                      'valid_ops': sorted(valid_ops)}
            return valids
        if value != '' and op == '':
            op == '=='
        msg_prefix = 'quick_query:'
        err_prefix = f'{msg_prefix} error,'
        assert key in valid_keys, f'{err_prefix} invalid key {key}'
        assert op in valid_ops, 'f{err_prefix} invalid op {op}'
        op_func = valid_ops[op]
        try:
            if key in {'POS_ID', 'BUS_ID'}:
                operand = str(value)
            else:
                if value == '':
                    value = 0  # case where user made no argument
                operand = float(value)
        except:
            assert False, f'{err_prefix} invalid type {type(value)} for value {value}'
        if posids == 'all':
            posids = self.posids
        else:
            posids = {posids} if isinstance(posids, str) else set(posids)
        assert len(posids) > 0, f'{err_prefix} empty posids argument'
        if key in position_keys:
            def getter(posid):
                expected = self.posmodels[posid].expected_current_position
                if key in {'Q', 'S'}:
                    return expected[key]
                prefix = key[:-1]
                suffix = key[-1]
                if suffix in {'T', 'P'}:
                    pair_key = prefix + 'TP'
                else:
                    pair_key = prefix + 'XY'
                pair = expected[pair_key]
                if suffix in {'T', 'X'}:
                    return pair[0]
                return pair[1]
        else:
            def getter(posid):
                return self.states[posid]._val[key]
        found = dict()
        posids = sorted(posids)
        for posid in posids:
            this_value = getter(posid)
            if op == '' or op_func(this_value, operand):
                found[posid] = this_value
        out = found if op == '' else sorted(found.keys())
        if mode == 'compact':
            out = str(out)
        elif mode == 'expanded':
            out = [f'{key}: {val}' for key, val in found.items()]
            out = '\n'.join(out)
        if isinstance(out, str):
            try:
                values = list(found.values()) if isinstance(found, dict) else found
                max_ = np.max(values)
                min_ = np.min(values)
                mean = np.mean(values)
                std = np.std(values)
                rms = np.sqrt(np.sum(np.array(values)**2) / len(values))
                out = f'stats: max={max_:.4f}, min={min_:.4f}, mean={mean:.4f}, std={std:.4f}, rms={rms:.4f}\n{out}'
            except:
                pass
            out = f'total entries found = {len(found)}\n{out}'
        return out

# MOVE SCHEDULING ANIMATOR CONTROLS

    def start_gathering_frames(self):
        """Frame data representing scheduled moves will begin to be collected as
        it is generated (during move scheduling) and will be retained for making
        an animation of it in the future. Old frame data from any previous animation
        is cleared out first.
        
        INPUTS:  None
        """
        self.animator.clear()
        self.animator_on = True
        self.animator_total_time = 0
        self.collider.add_fixed_to_animator(self.animator_total_time)

    def stop_gathering_frames(self):
        """Stop collecting frame data of scheduled moves for the animator.
        
        INPUTS:  None
        """
        self.animator_on = False

    def generate_animation(self):
        """Use the current collection of move frames in the animator to plot
        the animation. Returns path to the generated movie.
        
        INPUTS:  None
        """
        output_path = self.animator.animate()
        self.printfunc(f'Animation saved to {output_path}.')
        return output_path

# INTERNAL METHODS

    def _hardware_ready_move_tables(self):
        """Strips out information that isn't necessary to send to petalbox, and
        formats for sending. Any cases of multiple tables for one positioner are
        merged in sequence into a single table.

        Output format:
            List of dictionaries.

            Each dictionary is the move table for one positioner.

            The dictionary has the following fields:

                posid          ... string                    ... identifies the positioner by 'POS_ID'                
                canid          ... unsigned integer          ... identifies the positioner by 'CAN_ID'
                busid          ... string                    ... identified teh canbus the positioner is on
                nrows          ... unsigned integer          ... number of elements in each of the list fields (i.e. number of rows of the move table)
                motor_steps_T  ... list of signed integers   ... number of motor steps to rotate on theta axis
                                                                    ... motor_steps_T > 0 ... ccw rotation
                                                                    ... motor_steps_T < 0 ... cw rotation
                motor_steps_P  ... list of signed integers   ... number of motor steps to rotate on phi axis
                                                                    ... motor_steps_P > 0 ... ccw rotation
                                                                    ... motor_steps_P < 0 ... cw rotation
                speed_mode_T   ... list of strings           ... 'cruise' or 'creep' mode on theta axis
                speed_mode_P   ... list of strings           ... 'cruise' or 'creep' mode on phi axis
                move_time      ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
                postpause      ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
        """
        hw_tables = []
        for m in self.schedule.move_tables.values():
            hw_tbl = m.for_hardware()
            hw_tables.append(hw_tbl)
            err = m.error_str
            if err:
                self.printfunc(err)
                m.display(self.printfunc)
        return hw_tables

    def _postmove_cleanup(self):
        """This always gets called after performing a set of moves, so that
        PosModel instances can be informed that the move was physically done on
        the hardware.
        """
        if self.schedule_stats.is_enabled():
            for posid in self.posids:
                avoidance = self.schedule_stats.get_avoidances(posid)
                if avoidance:
                    self.set_posfid_val(posid, 'LOG_NOTE', f'collision avoidance: {avoidance}')
        for m in self.schedule.move_tables.values():
            if m.posmodel.posid in self._posids_where_tables_were_just_sent:
                m.posmodel.postmove_cleanup(m.for_cleanup())
                self.altered_states.add(m.posmodel.state)
            else:
                self.pos_flags[m.posid] |= self.flags.get('REJECTED', self.missing_flag)
        self.commit(mode='both')  # commit() determines whether anything actually needs pushing to db
        self._clear_temporary_state_values()
        self.schedule = self._new_schedule()
        if self.animator_on:
            self.previous_animator_total_time = self.animator_total_time
        
    def _cancel_move(self, reset_flags=True):
        '''Resets schedule and performs posmodel cleanup commands.
        
        INPUTS:            
            reset_flags ... True --> reset posflags (for enabled positioners only)
                            False --> do not reset any posflags
                            'all' --> reset posflags for both enabled and disabled
        '''
        self._clear_temporary_state_values()
        self.schedule = self._new_schedule()
        if reset_flags:
            enabled_only = reset_flags != 'all'
            self._initialize_pos_flags(ids='all', enabled_only=enabled_only)
        self._remove_posid_from_sent_tables('all')
        if self.animator_on:
            self.animator.clear_after(time=self.previous_animator_total_time)
            self.animator_total_time = self.previous_animator_total_time
    
    def _handle_any_failed_send_of_move_tables(self, response, n_retries):
        '''Inspects response from petalcontroller after attempt to send move
        tables to hardware.
        
        Based on that response, may trigger recursive recalculation of move
        schedule (limited by integer arg n_retries). This is necessary, when
        tables fail to be sent to positioners, for two reasons:
            
          1. Keep track of correct expected position of each robot.
          2. Ensure neighbors don't collide with those now effectively disabled.
          
        Returns set of posids that failed to send (empty if all succeeded).
        
        As of this writing (2020-04-28) this handler will NOT automatically set
        any CTRL_ENABLED flags to False. Doing so would save some time for the
        flag), by avoiding recalculation of the anticollision move schedules
        upon each retargeting. Consensus with the larger team would be wanted
        prior to including any such auto-disabling feature here.
        '''
        failed_send_posids = set()
        if isinstance(response, tuple):  # conditional here is to support earlier implementations of petalcontroller (pre v4.18)
            response_str = response[0]
            failed_send_buscanids = response[1]
            for busid, canids in failed_send_buscanids.items():
                buscan_combo_keys = {(busid, canid) for canid in canids}
                failed_send_posids |= {self.buscan_to_posids[key] for key in buscan_combo_keys}            
        else:
            response_str = response
        failed = response_str.upper().find('FAILED') == 0  # petalcomm.py interface specifies that this keyword would be found as first token of response string, in failure case
        failed |= len(failed_send_posids) > 0  # backup check, in case some formatting inconsistency in response string
        if failed:
            if len(failed_send_posids) > 0:
                buses_with_fails = {self.busids[posid] for posid in failed_send_posids}
                self.printfunc(f'WARNING: {response_str}. Could not send {len(failed_send_posids)} ' +
                               f'move tables to petalcontroller. Failed posids: {failed_send_posids}. ' +
                               f'CAN busids with failures: {buses_with_fails}.')
                posids_to_retry = self._posids_where_tables_were_just_sent - failed_send_posids
            else:
                self.printfunc(f'ERROR: {response_str}. Could not send move tables to some unknown number ' +
                               'of positioners. Most likely due petalcontroller not sending back information ' +
                               'about which positioners failed to communicate. Further downstream errors are ' +
                               'likely.')
                posids_to_retry = {}
                failed_send_posids = self._posids_where_tables_were_just_sent
            if self.schedule.expert_mode_is_on():
                expert_mode = True
                all_tables = self.schedule.get_orig_expert_tables_sequence()
                expert_tables_to_retry = [t for t in all_tables if t.posid in posids_to_retry]
            else:
                expert_mode = False
                all_requests = self.schedule.get_requests()
                posids_to_retry = {p for p in posids_to_retry if p in all_requests}
                requests_to_retry = {posid:all_requests[posid] for posid in posids_to_retry}
            self.printfunc('Canceling move. Tracking data in petal.py will be reset')
            self._cancel_move(reset_flags='all')
            # set flags and disable nonresponsiives after canceling to so that the moves will not be committed.
            self._handle_nonresponsive_positioners(failed_send_posids, auto_disabling_on=True)
            if n_retries > 0 and posids_to_retry:
                self.printfunc(f'Attempting to reschedule and resend move tables to {len(posids_to_retry)} ' +
                               f'positioners (num tries remaining = {n_retries})')
                if expert_mode:
                    for move_table in expert_tables_to_retry:
                        self.schedule.expert_add_table(move_table)
                else:
                    cleaned = {}
                    for posid, req in requests_to_retry.items():
                        cleaned[posid] = {'command': req['command'],
                                          'target': [req['cmd_val1'], req['cmd_val2']],
                                          'log_note': req['log_note']}
                    self.request_targets(cleaned) # 2020-04-30 [JHS] anything useful to be done with return value?
                anticollision = self.__current_schedule_moves_anticollision
                should_anneal = self.__current_schedule_moves_should_anneal
                self.schedule_moves(anticollision=anticollision, should_anneal=should_anneal)
                return self.send_move_tables(n_retries - 1)
            else:
                msg = 'WARNING: Due to failures when sending move tables to positioners, the entire move is canceled.'
                if n_retries <= 0:
                    msg += ' No scheduling retries remaining.'
                if len(posids_to_retry) == 0:
                    msg += ' No communicable positioners remaining to reschedule.'
                self.printfunc(msg)
        return failed_send_posids

    def _handle_nonresponsive_positioners(self, posids, auto_disabling_on=True):
        """Receives a list of positioners that the petalcontroller reports it
        could not send move tables to. Sets communication error flag.

        Optionally automatically disables positioners to remove them from
        future send_move_tables attempts.
        """
        disabled = set()
        for posid in posids:
            self.pos_flags[posid] |= self.flags.get('COMERROR', self.missing_flag)
            if auto_disabling_on and self.posmodels[posid].is_enabled:
                accepted = self.set_posfid_val(posid, 'CTRL_ENABLED', False, check_existing=True)
                if accepted:
                    self.set_posfid_val(posid, 'LOG_NOTE', 'Disabled due to communication error')
                    disabled.add(posid)
        if disabled:
            self.printfunc(f'{len(disabled)} positioners disabled due to communication error: {disabled}')

    def _clear_temporary_state_values(self):
        '''Clear out any existing values in the state objects that were only temporarily
        held until we could get the state committed to the log / db.
        '''
        resets = {'MOVE_CMD'  : '',
                  'MOVE_VAL1' : '',
                  'MOVE_VAL2' : '',
                  }
        for posid in self.posids:
            for key in resets:
                # Set directly with state.store + special arg, to avoid triggering another commit
                self.states[posid].store(key, resets[key], register_if_altered=False)

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
        min_timeout = 20.0 # seconds
        timeout = max(min_timeout, self.schedule.conservative_move_timeout_period())
        poll_period = 0.5 # seconds
        keep_waiting = True
        start_time = time.time()
        while keep_waiting:
            elapsed_time = time.time() - start_time
            if elapsed_time >= timeout:
                self.printfunc('Timed out at ' + str(timeout) + ' seconds waiting for positioners to be ready to receive next commands.')
                keep_waiting = False
            if self.comm.ready_for_tables():
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
        power_supply_map = {}
        already_mapped = set()
        for supply, these_buses in pc.power_supply_canbus_map.items():
            these_posids = {p for p in self.posids if self.busids[p] in these_buses}
            power_supply_map[supply] = these_posids
            already_mapped |= these_posids
        power_supply_map['other'] = self.posids - already_mapped
        return power_supply_map

    def _initialize_pos_flags(self, ids='all', initialize=False, enabled_only=True):
        '''
        Sets pos_flags to initial values: 4 for positioners and 8 for fiducials.

        FVC/Petal bit string (When bits are passed to FVC, petal bits are wiped out)
        
        See https://desi.lbl.gov/trac/wiki/FPS/PositionerFlags
        OR DOSlib.flags
        '''
        if ids == 'all':
            ids = self.posids.union(self.fidids)
        elif isinstance(ids, str): #strings that != 'all'
            ids = {ids}
        if initialize:
            for posfidid in ids:
                if posfidid not in self.posids.union(self.fidids): 
                    continue
                if posfidid.startswith('M') or posfidid.startswith('D') or posfidid.startswith('UM'):
                    if not(enabled_only) or self.posmodels[posfidid].is_enabled:
                        self.pos_flags[posfidid] = self.flags.get('POSITIONER', self.missing_flag)
                else:
                    self.pos_flags[posfidid] = self.flags.get('FIDUCIAL', self.missing_flag)
            if hasattr(self, 'disabled_fids') and ids == 'all':
                for fid in self.disabled_fids:
                    self.pos_flags[fid] = self.flags.get('FIDUCIAL', self.missing_flag) | self.flags.get('NOTCTLENABLED', self.missing_flag)
        else:
            for posfidid in ids:
                # Unsets flags in reset_mask
                if posfidid not in self.posids.union(self.fidids): 
                    continue
                self.pos_flags[posfidid] = (self.pos_flags[posfidid] | self.reset_mask) ^ self.reset_mask
        return

    def _apply_state_enable_settings(self, devid):
        """Read positioner/fiducial configuration settings and disable/set flags accordingly.
           KF - fids in DB might not have DEVICE_CLASSIFIED_NONFUNCTIONAL 6/27/19
        """
        if self.get_posfid_val(devid, 'DEVICE_CLASSIFIED_NONFUNCTIONAL'):
            self.set_posfid_val(devid, 'CTRL_ENABLED', False, check_existing=True)
            self.pos_flags[devid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
            self.pos_flags[devid] |= self.flags.get('NONFUNCTIONAL', self.missing_flag)
            self.disabled_devids.append(devid)
        if not self.get_posfid_val(devid, 'FIBER_INTACT'):
            self.set_posfid_val(devid, 'CTRL_ENABLED', False, check_existing=True)
            self.pos_flags[devid] |= self.flags.get('NOTCTLENABLED', self.missing_flag)
            self.pos_flags[devid] |= self.flags.get('BROKENFIBER', self.missing_flag)
            self.pos_flags[devid] |= self.flags.get('BADPOSFID', self.missing_flag)
            self.disabled_devids.append(devid)

    def _apply_all_state_enable_settings(self):
        """Read positioner/fiducial configuration settings and disable/set flags accordingly.
           KF - fids in DB might not have DEVICE_CLASSIFIED_NONFUNCTIONAL 6/27/19
        """
        for devid in self.posids: 
            self._apply_state_enable_settings(devid)

    def _petal_configure(self, constants = 'DEFAULT'):
        """
        petal.py internal configure function.
        calls petalcontroller configure
        calls get_ready to change ops_state to READY

        Resets posflags, schedule, clears temporary posstate values,
        commits uncommitted state changes to the DB
        """
        self.printfunc('_petal_configure: configuring Petalbox %r' % self.petalbox_id)
        if hasattr(self, 'comm'):
            #First configure, then worry about opsstate (don't trust PC code)
            try:
                retcode = self.comm.configure(constants = constants)
                self.printfunc('_petal_configure: petalbox returns %r' % retcode)
            except Exception as e:
                rstring = '_petal_configure: Exception configuring petalbox: %s' % str(e)
                self.printfunc(rstring)
                return 'FAILED: ' + rstring
            # Manually check opsstate for inconsistancies (will catch INITIALIZED)
            hwstate, err_strings = self._get_hardware_state()
            if hwstate == 'ERROR':
                # Someone mucked with the settings, just move to standby
                self._set_hardware_state('STANDBY')
                self.printfunc('_petal_configure: ops_state is now STANDBY')
                if self.verbose:
                    self.printfunc('_petal_configure: error strings from checking opsstate: %s' % err_strings)
            else:
                self.printfunc('_petal_configure: ops_state remains in %s' % hwstate)
            if hwstate != 'OBSERVING':
                # fids off
                for fid in self.fidids:
                    self.set_posfid_val(fid, 'DUTY_STATE', 0, check_existing=True)
        #Reset values
        self._remove_posid_from_sent_tables('all')
        self._initialize_pos_flags() # Reset posflags
        self._apply_all_state_enable_settings()
        self._clear_temporary_state_values()
        self._clear_exposure_info() #Get rid of lingering exposure details
        self.commit(mode='both', log_note='configuring') #commit uncommitted changes to DB
        self.schedule = self._new_schedule() # Refresh schedule so it has no tables
        return 'SUCCESS'

    def _remove_posid_from_sent_tables(self, posid):
        """There is an internal list in petal.py of which positioners have had
        move tables actually sent out to hardware. This function removes a
        positioner (identified by posid) from the list. You can also argue
        posid='all', in which case the whole list will get cleared.
        """
        if posid == 'all':
            self._posids_where_tables_were_just_sent = set()         
        elif posid in self._posids_where_tables_were_just_sent:
            self._posids_where_tables_were_just_sent.remove(posid)

if __name__ == '__main__':
    '''
    python -m cProfile -s cumtime petal.py
    '''
    from configobj import ConfigObj
    cfg = ConfigObj(  # posids and fidids
        "/home/msdos/focalplane/fp_settings/ptl_settings/unit_03.conf",
        unrepr=True, encoding='utf-8')
    ptl = Petal(petal_id=3, petal_loc=0,
                posids=cfg['POS_IDS'], fidids=cfg['FID_IDS'],
                db_commit_on=True, local_commit_on=False, local_log_on=False,
                simulator_on=True, printfunc=print, verbose=False,
                sched_stats_on=False)
    # print('Dumping initial positions in DB')
    # init_pos_dump = np.zeros((len(ptl.posids), 3))
    # for i, posid in enumerate(sorted(ptl.posids)):
    #     init_pos_dump[i, 0] = int(posid[1:])
    #     init_pos_dump[i, 1:] = ptl.posmodels[posid].expected_current_posTP
    # np.savetxt(os.path.join(pc.dirs['temp_files'], 'init_pos_dump.txt'), init_pos_dump)
    init_pos_dump = np.loadtxt(os.path.join(pc.dirs['temp_files'],
                                            'init_pos_dump.txt'))
    init_pos = np.zeros((len(ptl.posids), 3))
    for i, posid in enumerate(sorted(ptl.posids)):
        init_pos[i, 0] = int(posid[1:])
        init_pos[i, 1:] = ptl.posmodels[posid].expected_current_posTP
    np.savetxt(os.path.join(pc.dirs['temp_files'], 'init_pos_1.txt'), init_pos)
    print(f'Checking if posids and initial positions of all '
          f'{init_pos.shape[0]} positioners equal to dump: '
          f'{np.all(init_pos_dump == init_pos)}')
    posT = np.linspace(0, 360, 6)
    posP = np.linspace(90, 180, 6)
    for i in range(4):
        print(f'==== target {i}, posTP = ({posT[i]:.3f}, {posP[i]:.3f}) ====')
        request = {'command': 'posintTP',
                   'target': (posT[i], posP[i])}
        requests = {posid: request for posid in ptl.posids}
        ptl.request_targets(requests)
        ptl.schedule_moves(anticollision='adjust')
        ptl.send_and_execute_moves()
