# -*- coding: utf-8 -*-
"""
Perform a sequence of moves + FVC measurements on hardware. (Note that any positioner
calibration parameters or motor settings altered during the sequence are stored only
in memory, so a re-initialization of the petal software should restore you to the
original state, as defined by the posmove and constants databases.)
"""

import os
script_name = os.path.basename(__file__)

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-i', '--infile', type=str, required=True, help='Path to sequence file, readable by sequence.py. For some common pre-cooked sequences, run sequence_generator.py.')
parser.add_argument('-a', '--anticollision', type=str, default='adjust', help='anticollision mode, can be "adjust", "freeze" or None. Default is "adjust"')
parser.add_argument('-p', '--enable_phi_limit', action='store_true', help='turns on minimum phi limit for move targets, default is False')
parser.add_argument('-m', '--match_radius', type=int, default=None, help='int, specify a particular match radius, other than default')
parser.add_argument('-u', '--check_unmatched', action='store_true', help='turns on auto-disabling of unmatched positioners, default is False')
parser.add_argument('-t', '--test_tp', action='store_true', help='turns on auto-updating of POS_T, POS_P based on measurements, default is False')
parser.add_argument('-n', '--no_movement', action='store_true', help='for debugging purposes, this option suppresses sending move tables to positioners, so they will not physically move')
default_cycle_time = 60.0 # sec
parser.add_argument('-c', '--cycle_time', type=float, default=default_cycle_time, help=f'min period of time (seconds) for successive moves (default={default_cycle_time})')

args = parser.parse_args()
if args.anticollision == 'None':
    args.anticollision = None
assert args.anticollision in {'adjust', 'freeze', None}, f'bad argument {args.anticollision} for anticollision parameter'

# read sequence file
import sequence
seq = sequence.read(args.infile)

# set up a log file
import logging
import time
try:
    import posconstants as pc
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
log_dir = pc.dirs['sequence_logs']
log_timestamp = pc.filename_timestamp_str()
log_name = log_timestamp + '_run_sequence.log'
log_path = os.path.join(log_dir, log_name)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
[logger.removeHandler(h) for h in logger.handlers]
fh = logging.FileHandler(filename=log_path, mode='a', encoding='utf-8')
sh = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S %z')
formatter.converter = time.gmtime
fh.setFormatter(formatter)
sh.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(sh)
logger.info(f'Running {script_name} to perform a positioner move + measure sequence.')
logger.info(f'Log file: {log_path}')
logger.info(f'Input file: {args.infile}')
logger.info(f'Contents:\n{seq}')
response = input('\nDoes the sequence look correct? (y/n) >> ')
if 'n' in response.lower():
    logger.info('User rejected the sequence prior to running. Now quitting.')
    import sys
    sys.exit(0)

def assert2(test, message):
    '''Like an assert, but cleaner handling of logging.'''
    if not test:
        logger.error(message)
        logger.warning('Now quitting, so user can check inputs.')
        assert False  # for ease of jumping back into the error state in ipython debugger

# set up PECS (online control system)
try:
    from pecs import PECS
    pecs = PECS(interactive=True)
    pecs.logger = logger
    logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
    pecs_on = True
    get_posids = lambda: pecs.get_enabled_posids('sub')
except:
    # still a useful case, for testing some portion of the script offline
    logger.info('PECS initialization failed')
    pecs_on = False
    get_posids = lambda: [f'DUMMY{i:05d}' for i in range(10)]
logger.info(f'selected posids: {get_posids()}')

# helpers for generating move requests
import pandas as pd
import numpy as np

def is_number(x):
    '''Check type to see if it's a common number type.'''
    return isinstance(x, (int, float, np.integer, np.floating))

def is_boolean(x, include01=True):
    '''Check type to see if it's a common boolean type.'''
    if isinstance(x, (bool, np.bool_)):
        return True
    if include01 and is_number(x) and (x == 0 or x == 1):
        return True
    return False

def make_requests(posids, command, target0, target1, log_note):
    '''Make a structure with identical requests for all positioners in posids.
    '''
    if isinstance(posids, str):
        posids = [posids]
    else:
        posids = list(posids)
    assert2(command in sequence.valid_commands, f'unexpected command {command}')
    for arg in [target0, target1]:
        assert2(is_number(arg), f'unexpected type {type(arg)}')
    request_data = {'DEVICE_ID': posids,
                    'COMMAND': command,
                    'X1': target0,
                    'X2': target1,
                    'LOG_NOTE': log_note,
                    }
    requests = pd.DataFrame(request_data)
    requests = requests.merge(pecs.posinfo, on='DEVICE_ID')
    return requests

# general settings for the move measure function
if args.match_radius == None and pecs_on:
    args.match_radius = pecs.match_radius
move_meas_settings = {key: args.__dict__[key] for key in ['match_radius', 'check_unmatched', 'test_tp', 'anticollision']}
logger.info(f'move_measure() general settings: {move_meas_settings}')

# motor settings (must be made known to petal.py and FIPOS)
motor_settings = {'CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CREEP_PERIOD', 'SPINUPDOWN_PERIOD'}
other_settings = {key for key in sequence.pos_defaults if key not in motor_settings}

# caching / retrieval / application of positioner settings
def cache_current_pos_settings(posids):
    '''Gathers current positioner settings and caches them to disk. Returns a
    file path.
    '''
    cache_name = f'{log_timestamp}_pos_settings_cache.ecsv'
    cache_path = os.path.join(log_dir, cache_name)
    settings = []
    for posid in posids:
        role = pecs.ptl_role_lookup(posid)
        these_settings = {'POS_ID': posid}
        these_settings.update(sequence.pos_defaults.copy())
        for key in sequence.pos_defaults:
            value = pecs.ptlm.get_posfid_val(posid, key, participating_petals=role)
            these_settings[key] = value
        settings.append(these_settings)
    frame = pd.DataFrame(data=settings)
    frame.to_csv(cache_path, index=False)
    return cache_path

def retrieve_cached_pos_settings(path):
    '''Retrieves positioner settings from file cached to disk. Returns a dict with
    keys = posids and values = settings subdicts. This can be directly used in the
    apply_pos_settings function.'''
    frame = pd.read_csv(path)
    settings = {}
    for idx, row in frame.iterrows():
        posid = row['POS_ID']
        these_settings = {key: row[key] for key in sequence.pos_defaults}
        settings[posid] = these_settings
    return settings

def apply_pos_settings(settings):
    '''Push new settings values to the positioners in posids. The dict settings
    should have keys = posids, and values = sub-dictionaries. Each sub-dict
    should have keys / value types like pos_defaults in the sequence module.
    
    Nothing will be committed to the posmoves database (settings will be stored
    only in memory, and can be reset by reinitializing the petal software.
    '''
    if not settings:
        logger.warning(f'apply_pos_settings: called with null arg settings={settings}')
        return
    motor_update_petals = set()
    for posid, these_settings in settings.items():
        role = pecs.ptl_role_lookup(posid)
        for key, value in these_settings.items():
            assert2(key in sequence.pos_defaults, f'unexpected pos settings key {key} for posid {posid}')
            default = sequence.pos_defaults[key]
            if is_boolean(default, include01=False):
                test = is_boolean(value, include01=True)
            elif is_number(default):
                test = is_number(value)
            else:
                test = isinstance(value, type(default))
            assert2(test, f'unexpected type {type(value)} for value {value} for posid {posid}')
            value = these_settings[key]                
            val_accepted = pecs.ptlm.set_posfid_val(posid, key, value,
                                                    check_existing=True,
                                                    participating_petals=role)
            if val_accepted == False:  # val_accepted == None is in fact is ok --- just means no change needed
                assert2(False, f'unable to set {key}={value} for {posid}')
            elif val_accepted == True:  # again, distinct from the None case
                if key in motor_settings:
                    motor_update_petals.add(role)
    logger.info('apply_pos_settings: Positioner settings updated in memory')
    if motor_update_petals:
        logger.info('apply_pos_settings: Positioner settings include change(s) to motor' +
                    ' parameters. Now pushing new settings to petal controllers on petals' +
                    f' {motor_update_petals}')
        pecs.ptlm.set_motor_parameters(participating_petals=list(motor_update_petals))

# cache the pos settings
cache_path = cache_current_pos_settings(get_posids())
logger.info('Initial settings of positioner(s) cached to: {cache_path}')

# set phi limit angle for the test
old_phi_limits = pecs.ptlm.get_phi_limit_angle()
if args.enable_phi_limit:
    some_petal = pecs.ptl_roles[0]
    typical_phi_limit = pecs.ptlm.app_get('typical_phi_limit_angle', participating_petals=some_petal)
    uniform_phi_limit = typical_phi_limit
else:
    uniform_phi_limit = None
pecs.ptlm.set_phi_limit_angle(uniform_phi_limit)
new_phi_limits = pecs.ptlm.get_phi_limit_angle()
if new_phi_limits == old_phi_limits:
    logger.info(f'Phi limits unchanged: {old_phi_limits}')
else:
    logger.info(f'Phi limits changed. Old phi limits: {old_phi_limits}, ' +
                f'new phi limits: {new_phi_limits}')

# do the sequence
last_pos_settings = None
last_move_time = time.time() - args.cycle_time
for move in seq:
    sec_since_last_move = time.time() - last_move_time
    need_to_wait = args.cycle_time - sec_since_last_move
    if need_to_wait > 0:
        logger.info(f'Pausing {need_to_wait:.1f} sec for positioner cool down. ' +
                    'It is safe to CTRL-C abort the test during this wait period.')
        try:
            dt = 0.2  # sec
            for i in range(int(np.ceil(need_to_wait/dt))):
                time.sleep(dt)
        except KeyboardInterrupt:
            logger.info('Safely aborting the sequence.')
            break
    last_move_time = time.time()
    index = move.index
    posids = get_posids()  # dynamically retrieved, in case some positioner gets disabled mid-sequence
    dict_repr = dict(zip(move.columns, move))
    logger.info(f'Now doing move {index+1} of {len(seq)} (row idx {index}) on {len(posids)} positioner(s).')
    logger.info(f'Move settings are {dict_repr}')
    command = move['command']
    target0 = move['target0']
    target1 = move['target1']
    log_note = move['log_note']
    if command in sequence.general_commands:
        move_measure_func = pecs.move_measure
        requests = make_requests(posids, command, target0, target1, log_note)
        kwargs = {'request': requests}
    elif command in sequence.homing_commands:
        move_measure_func = pecs.rehome_and_measure
        if not target0 and not target1:
            logger.warning(f'Skipping move {index} because home request had neither'
                           f' axis specified. (Need to set target0 to 1 for theta homing'
                           f', target1 to 1 for phi homing, or both simultaneously.')
            continue
        should_debounce = command == 'home_and_debounce'
        axis = 'theta_only' if not target1 else 'phi_only' if not target0 else 'both'
        kwargs = {'posids': posids,
                  'axis': axis,
                  'debounce': should_debounce,
                  'log_note': log_note,
                  }
    else:
        logger.warning(f'Skipping move {index} due to unexpected command {command}')
        continue
    kwargs.update(move_meas_settings)
    new_settings = seq.pos_settings(index)
    if new_settings != last_pos_settings:
        all_settings = {posid:new_settings for posid in posids}  # this extra work improves generality of apply_pos_settings, and I expect not too costly
        if pecs_on:
            apply_pos_settings(all_settings)
        logger.info(f'Positioner settings: {new_settings}')
        last_pos_settings = new_settings
    else:
        logger.info('Positioner settings: (no change)')
    if pecs_on and not args.no_movement:
        result = move_measure_func(**kwargs)  # nothing is done here with result, data retrieval is a separate step, from the online DB
logger.info(f'Sequence "{seq.short_name}" complete!')

# restore the original pos settings
orig_settings = retrieve_cached_pos_settings(cache_path)
logger.info(f'Retrieved original positioner settings from {cache_path}')
new_cache_path = cache_current_pos_settings(posids)
new_settings = retrieve_cached_pos_settings(new_cache_path)
if orig_settings == new_settings:
    logger.info('No net change of positioner settings detected between start and finish' +
                ' of sequence. No further modifications to postioner state required.')
else:
    logger.info('Some net change(s) of positioner settings detected between start and' +
                ' finish of sequence. Now restoring system to original state.')
    apply_pos_settings(orig_settings)
    logger.info('Restoration of original positioner settings complete.')
    
# restore old phi limit angles
if new_phi_limits != old_phi_limits:
    if isinstance(old_phi_limits, dict):
        # 2020-07-13 [JHS] I'm unclear if the keys here are supposed to be role or
        # pcid. Might be a bug, but hard for me to test at LBNL because only one petal.
        # Frankly I'm not even 100% sure if it's a dict in the case of multiple petals.
        roles_angles = [(role, angle) for role, angle in old_phi_limits.items()]
    else:
        roles_angles = [(None, old_phi_limits)]
    for ra in roles_angles:
        pecs.ptlm.set_phi_limit_angle(ra[1], participating_petals=ra[0])
    restored_phi_limits = pecs.ptlm.get_phi_limit_angle()
    if restored_phi_limits == old_phi_limits:
        logger.info(f'Phi limits restored to: {restored_phi_limits}')
    else:
        logger.warning('Some error when restoring phi limits. Old limits were' +
                       f' {old_phi_limits} but restored values are different:' +
                       f' {restored_phi_limits}')

# final thoughts...
logger.info(f'Log file: {log_path}')
