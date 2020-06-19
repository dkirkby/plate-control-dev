# -*- coding: utf-8 -*-
"""
Perform a sequence of moves + FVC measurements on hardware.
"""

import os
script_name = os.path.basename(__file__)

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-i', '--infile', type=str, required=True, help='Path to sequence file, readable by sequence.py. For some common pre-cooked sequences, run sequence_generator.py.')
parser.add_argument('-d', '--debug', action='store_true', help='suppresses sending "SYNC" to positioners, so they will not actually move')
parser.add_argument('-m', '--match_radius', type=int, default=None, help='int, specify a particular match radius, other than default')
parser.add_argument('-c', '--check_unmatched', action='store_true', help='turns on auto-disabling of unmatched positioners')
parser.add_argument('-t', '--test_tp', action='store_true', help='turns on auto-updating of POS_T, POS_P based on measurements')
args = parser.parse_args()

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
log_name = pc.filename_timestamp_str() + '_set_calibrations.log'
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
    get_posids = lambda: sorted(set(pecs.posids))
except:
    # still a useful case, for testing some portion of the script offline
    logger.info(f'PECS initialization failed')
    pecs_on = False
    get_posids = lambda: [f'DUMMY{i:05d}' for i in range(10)]
logger.info(f'selected posids: {get_posids()}')

# helpers for generating move requests
import pandas as pd
import numpy as np

def is_number(x):
    '''Check type to see if it's a common number type.'''
    return isinstance(x, (int, float, np.int, np.float))

def is_boolean(x):
    '''Check type to see if it's a common boolean type.'''
    if isinstance(x, bool):
        return True
    if is_number(x) and (x == 0 or x == 1):
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
    return requests

# general settings for the move measure function
if args.match_radius == None and pecs_on:
    args.match_radius = pecs.match_radius
move_meas_settings = {key: args.__dict__[key] for key in ['match_radius', 'check_unmatched', 'test_tp']}
logger.info(f'move_measure() general settings: {move_meas_settings}')

# motor settings (must be made known to petal.py and FIPOS)
motor_settings = {'CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP', 'CREEP_PERIOD'}
other_settings = {key for key in sequence.pos_defaults if key not in motor_settings}

def apply_pos_settings(posids, settings):
    '''Push new settings values to the positioners in posids. The dict settings
    should have keys / value types like pos_defaults in the sequence module.'''
    for key, value in settings.items():
        assert2(key in sequence.pos_defaults.keys(), f'unexpected pos settings key {key}')
        default = sequence.pos_defaults[key]
        if is_number(default):
            test = is_number(value)
        elif is_boolean(default):
            test = is_boolean(value)
        else:
            test = isinstance(value, type(default))
        assert2(test, f'unexpected type {type(value)} for value {value}')
        value = settings[key]
        for posid in posids:
            role = pecs._pcid2role(pecs.posinfo.loc[posid, 'PETAL_LOC'])
            val_accepted = pecs.ptlm.set_posfid_val(posid, key, value, participating_petals=role)
            assert2(val_accepted, f'unable to set {key}={value} for {posid}')
    # TO BE IMPLEMENTED:
    # refresh the posmodels (may need some rework internally)
    # send out new motor values
    # pecs.ptlm.commit(mode='both', log_note='')
    # logger.info(f'Commit complete.')

# do the sequence
last_pos_settings = None
for row in seq.table:
    posids = get_posids()  # dynamically retrieved, just in case pecs changes something mid-sequence
    logger.info(f'Now doing move {row.index} of 0-{len(seq.table)-1} on {len(posids)} positioners.')
    kwargs1 = {key: row[key] for key in sequence.move_defaults}
    requests = make_requests(posids, **kwargs1)
    logger.info(f'General move command: {kwargs1}')
    kwargs2 = {'request': requests}
    kwargs2.update(move_meas_settings)
    settings = seq.pos_settings(row.index)
    if settings != last_pos_settings:
        if pecs_on:
            apply_pos_settings(posids, settings)
        logger.info(f'Positioner settings: {settings}')
        last_pos_settings = settings
    else:
        logger.info('Positioner settings: (no change)')
    if pecs_on:
        result = pecs.move_measure(**kwargs2)

logger.info('Sequence complete!')
logger.info(f'Log file: {log_path}')
