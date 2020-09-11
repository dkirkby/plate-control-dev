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
parser.add_argument('-r', '--match_radius', type=int, default=None, help='int, specify a particular match radius, other than default')
parser.add_argument('-u', '--check_unmatched', action='store_true', help='turns on auto-disabling of unmatched positioners, default is False')
parser.add_argument('-t', '--test_tp', action='store_true', help='turns on auto-updating of POS_T, POS_P based on measurements, default is False')
parser.add_argument('-x', '--no_movement', action='store_true', help='for debugging purposes, this option suppresses sending move tables to positioners, so they will not physically move')
default_cycle_time = 60.0 # sec
parser.add_argument('-c', '--cycle_time', type=float, default=default_cycle_time, help=f'min period of time (seconds) for successive moves (default={default_cycle_time})')
max_fvc_iter = 10
parser.add_argument('-nm', '--num_meas', type=int, default=1, help=f'int, number of measurements by the FVC per move (default is 1, max is {max_fvc_iter})')
max_corr = 5
parser.add_argument('-nc', '--num_corr', type=int, default=0, help=f'int, number of correction moves, for those rows where allowed in sequence definition (default is 0, max is {max_corr})')
default_n_best = 5
default_n_worst = 5
parser.add_argument('-nb', '--num_best', type=int, default=default_n_best, help=f'int, number of best performers to display in log messages for each measurement (default is {default_n_best})')
parser.add_argument('-nw', '--num_worst', type=int, default=default_n_worst, help=f'int, number of worst performers to display in log messages for each measurement (default is {default_n_worst})')
park_options = ['posintTP', 'poslocTP', 'None', 'False']
default_park = park_options[0]
parser.add_argument('-prep', '--prepark', type=str, default=default_park, help=f'str, if argued, then an initial parking move will be performed prior to running the sequence. Parking will be done for all selected positioners and (where possible) neighbors. Valid options are: {park_options}, default is {default_park}')
parser.add_argument('-post', '--postpark', type=str, default=default_park, help=f'str, if argued, then an final parking move will be performed after running the sequence. Parking will be done for all selected positioners and (where possible) neighbors. Valid options are: {park_options}, default is {default_park}')

args = parser.parse_args()
if args.anticollision == 'None':
    args.anticollision = None
assert args.anticollision in {'adjust', 'freeze', None}, f'bad argument {args.anticollision} for anticollision parameter'
assert 1 <= args.num_meas <= max_fvc_iter, f'out of range argument {args.num_meas} for num_meas parameter'
assert 0 <= args.num_corr <= max_corr, f'out of range argument {args.num_corr} for num_corr parameter'
assert args.prepark in park_options, f'invalid park option, must be one of {park_options}'
assert args.postpark in park_options, f'invalid park option, must be one of {park_options}'
args.prepark = None if args.prepark in ['None', 'False'] else args.prepark
args.postpark = None if args.postpark in ['None', 'False'] else args.postpark

# read sequence file
import sequence
seq = sequence.Sequence.read(args.infile)

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
def clear_loggers():
    '''Mysteriously (to me) this doesn't seem to work on the second run of script in
    the same ipython/debugger session, but does seem to work on the third... Weird,
    not gonna bother trying to track it down --- just adds duplicate printouts.'''
    for h in logger.handlers:
        logger.removeHandler(h)
clear_loggers()
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
logger.info(f'Contents:\n\n{seq}')

def quit_query(question):
    response = input(f'\n{question} (y/n) >> ')
    if 'n' in response.lower():
        logger.info('User rejected the sequence prior to running. Now quitting.')
        import sys
        sys.exit(0)

quit_query('Does the sequence look correct?')
logger.info(f'Number of correction submoves: {args.num_corr}')
logger.info(f'Number of fvc images per measurement: {args.num_meas}')
logger.info(f'Minimum move cycle time: {args.cycle_time} sec')

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
    get_posids = lambda: list(pecs.get_enabled_posids('sub', include_posinfo=False))
    get_all_enabled_posids = lambda: list(pecs.get_enabled_posids('all', include_posinfo=False))
    _, all_posinfo = pecs.get_enabled_posids(posids='all', include_posinfo=True)
    all_posinfo = all_posinfo.reset_index()
    temp = all_posinfo[['DEVICE_LOC','DEVICE_ID']].to_dict(orient='list')
    all_loc2id = {temp['DEVICE_LOC'][i]: temp['DEVICE_ID'][i] for i in range(len(all_posinfo))}
except:
    # still a useful case, for testing some portion of the script offline
    logger.info('PECS initialization failed')
    pecs_on = False
    get_posids = lambda: [f'DUMMY{i:05d}' for i in range(10)]
    temp = sorted(get_posids())
    all_loc2id = {i: temp[i] for i in range(len(temp))}
all_id2loc = {val: key for key, val in all_loc2id.items()}
logger.info(f'selected posids: {get_posids()}')

_loc2id_cache = {}  # reduces overhead for function below
_id2loc_cache = {}  # reduces overhead for function below
def get_map(key='loc', posids=[]):
    '''Returns dict with containing positioner locations and corresponding ids.
    By default, positioners will be only those delivered dynamically by get_posids().
    
    INPUTS:  key ... 'loc' --> output has keys = locations, values = posids
                     'ids' --> output has keys = posids, values = locations
             posids ... (optional) collection of posids, to skip get_posids() call
    
    OUTPUT:  dict, with keys/values as determined by key arg above
    '''
    posids = posids if posids else get_posids()
    if key == 'loc':
        global _loc2id_cache
        if set(_loc2id_cache.values()) != set(posids):
            _loc2id_cache = {k:v for k,v in all_loc2id.items() if v in posids}
        return _loc2id_cache
    else:
        global _id2loc_cache
        if set(_id2loc_cache.values()) != set(posids):
            _id2loc_cache = {k:v for k,v in all_id2loc.items() if k in posids}
        return _id2loc_cache

if pecs_on:
    these = len(get_posids())
    allofthem = len(pecs.get_enabled_posids('all'))
    if these == allofthem:
        quit_query(f'Are you sure you want to be running ALL {allofthem} positioners?')

# helpers for generating move requests
import pandas as pd
import numpy as np
import math

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

def ptlcall(funcname, posid, *args, **kwargs):
    '''Passes function calls off to the petal instance. Works exclusively for
    functions whose first argument accepts a single positioner id.'''
    role = pecs.ptl_role_lookup(posid)
    extra_kwargs = {'participating_petals': role}
    if kwargs:
        kwargs.update(extra_kwargs)
    else:
        kwargs = extra_kwargs
    function = getattr(pecs.ptlm, funcname)
    result = function(posid, *args, **kwargs)
    if isinstance(result, dict) and len(result) == 1 and list(result.keys())[0] == role:
        # 2020-09-10 [JHS] I don't know how to predict why / when this happens, but some
        # calls through petalman return a single element dict that needs to be decomposed.
        result = list(result.values())[0]
    return result

def trans(posid, method, *args, **kwargs):
    '''Passes calls off to the petal instance to do postransforms conversions.
    The argument "method" is the name of the function in postransforms that
    you want to call.
    '''
    result = ptlcall('postrans', posid, method, *args, **kwargs) 
    return result


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
        these_settings = {'POS_ID': posid}
        these_settings.update(sequence.pos_defaults.copy())
        for key in sequence.pos_defaults:
            value = ptlcall('get_posfid_val', posid, key)
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
            val_accepted = ptlcall('set_posfid_val', posid, key, value, check_existing=True)
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

def calc_poslocXY_errors(requests, results):
    '''Calculates positioning errors based on initial requested targets and
    FVC measured results. Error values are calculated and returned in poslocXY
    coordinates. Only works for initial requests that were given in absolute
    coordinates.
    
    INPUT:   requests ... dataframe as generated by make_requests()
             results ... dataframe as generated by pecs.move_measure()
                         assumed to contain 'obsX', 'obsY', and index 'DEVICE_ID'
             
    OUTPUT:  dict with keys = posids and values = [err_locX, err_locY]
    '''
    if results.index.name == 'DEVICE_ID':
        results = results.reset_index()
    useful_results = results[['DEVICE_ID', 'obsX', 'obsY']]
    combo = requests.merge(useful_results, on='DEVICE_ID')
    err = {}
    for row in combo.iterrows():
        data = row[1]
        posid = data['DEVICE_ID']
        xy_meas = trans(posid, 'obsXY_to_poslocXY', (data['obsX'], data['obsY']))
        command = data['COMMAND']
        uv_targ = [data['X1'], data['X2']]
        assert2(command in sequence.abs_commands, 'error calc when initial request was a delta ' +
                                                  f'move ({command}) is not currently supported')
        if command == 'poslocXY':
            xy_targ = uv_targ
        else:
            conversion = f'{command}_to_poslocXY'
            xy_targ = trans(posid, conversion, uv_targ)
        err_x = xy_meas[0] - xy_targ[0]
        err_y = xy_meas[1] - xy_targ[1]
        err[posid] = [err_x, err_y]
    return err        

def summarize_errors(errs, move_num, submove_num, n_best=3, n_worst=3):
    '''Produces a string summarizing errors for a set of positioners.
    
    INPUT:   errs ... same format as output by calc_poslocXY_errors, a dict with
                      keys = posids and values = [err_locX, err_locY]
             move_num ... int, which move of the sequence this is
             submove_num ... int, which submove of the move this is
             n_best ... int, number of "best" performers to display
             n_worst ... int, number of "worst" performers to display
             
    OUTPUT:  string
    '''
    posids = sorted(errs.keys())
    vec_errs = [math.hypot(errs[posid][0], errs[posid][1]) for posid in posids]
    vec_errs_um = [err*1000 for err in vec_errs]
    err_str = f'Results for move {move_num}, submove {submove_num}, n_pos={len(posids)}, errors given in um:\n '
    first = True
    for name, func in {'max': max, 'min': min, 'mean': np.mean,
                       'median': np.median, 'std': np.std,
                       'rms': lambda X: (sum(x**2 for x in X)/len(X))**0.5,
                       }.items():
        if not first:
            err_str += ', '
        err_str += f'{name}: {func(vec_errs_um):5.1f}'
        first = False
    sorted_err_idxs = np.argsort(vec_errs_um)
    for desc, count in {'best': args.num_best, 'worst': args.num_worst}.items():
        n = len(vec_errs_um)
        if n == 0:
            break
        count_mod = min(count, int(n/2)) if n > 1 else 1
        err_str += f'\n {desc:<5} {count_mod}:'
        this_sort = list(sorted_err_idxs) if desc == 'best' else list(reversed(sorted_err_idxs))
        these_idxs = [this_sort[i] for i in range(count_mod)]
        for i in these_idxs:
            err_str += f' {posids[i]}: {vec_errs_um[i]:5.1f},'
        err_str = err_str[:-1]  # remove dangling comma
    return err_str

def pause_between_moves(last_move_time, cycle_time):
    '''Pauses the sequence between moves. User is given the option to safely
    CTRL-C exit the sequence during this period.
    
    INPUT:  last_move_time ... seconds since epoch, defining when the previous
                               move was done. last_move_time=None will wait the
                               full cycle_time
            cycle_time ... seconds to wait after last_move_time
    
    OUTPUT: Returns the time now, if the pause was succesfully completed.
            Returns KeyboardInterrupt if user did CTRL-C.
    '''
    if last_move_time == None:
        last_move_time = time.time()
    sec_since_last_move = time.time() - last_move_time
    need_to_wait = cycle_time - sec_since_last_move
    if need_to_wait > 0:
        logger.info(f'Pausing {need_to_wait:.1f} sec for positioner cool down. ' +
                    'It is safe to CTRL-C abort the test during this wait period.\n')
        try:
            dt = 0.2  # sec
            for i in range(int(np.ceil(need_to_wait/dt))):
                time.sleep(dt)
        except KeyboardInterrupt:
            return KeyboardInterrupt
    return time.time()

def get_parkable_neighbors(posids):
    '''Return set of neighbors of posids which can be "parked".
    '''
    parkable_neighbors = set()
    all_enabled = get_all_enabled_posids()
    for posid in posids:
        neighbors = ptlcall('get_positioner_neighbors', posid)
        enabled_neighbors = set(neighbors) & set(all_enabled)
        parkable_neighbors |= enabled_neighbors
    
    # 2020-09-10 [JHS] Unfortunately, PECS seems not quite set up to move neighbors
    # unless they were also in the selected set of commanded positioners at the
    # beginning. So for now I am simply removing such neighbors --- rendering this
    # function right now a functionally useless placeholder.
    all_known_as_commandable_to_pecs = set(pecs.posids)
    parkable_neighbors &= all_known_as_commandable_to_pecs
    
    return parkable_neighbors

# setup prior to running sequence
if pecs_on:
    # cache the pos settings
    cache_path = cache_current_pos_settings(get_posids())
    logger.info(f'Initial settings of positioner(s) cached to: {cache_path}')
    
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
last_pos_settings = None
real_moves = pecs_on and not args.no_movement
cycle_time = args.cycle_time if real_moves else 4.0
last_move_time = 'no moves done yet'

def do_pause():
    '''Convenience wrapper for pause_between_moves(), utilizing a global to
    track the timing.'''
    global last_move_time
    if last_move_time == 'no moves done yet':
        last_move_time = time.time()
    else:
        last_move_time = pause_between_moves(last_move_time, cycle_time)
    if last_move_time == KeyboardInterrupt:
        raise StopIteration
        
def park(park_option, is_prepark=True):
    '''Perform (or skip if appropriate) parking based on argued park_option.'''
    global last_move_time
    assert park_option in park_options
    if not park_option:
        return
    posids = get_posids()
    if pecs_on:
        neighbors = get_parkable_neighbors(posids)
    else:
        neighbors = set()
    extras = set(neighbors) - set(posids)
    neighbor_text = '' if not extras else f' specified for this test, as well as {len(extras)} of their unspecificed neighbors: {sorted(extras)}'
    logger.info(f'Doing {"initial" if is_prepark else "final"} parking move (coords={park_option}) on {len(posids)} positioners' + neighbor_text)
    all_to_park = sorted(set(posids) | set(neighbors))
    extra_note = sequence.sequence_note_prefix + seq.normalized_short_name
    if is_prepark:
        last_move_time = time.time()
    if real_moves:
        pecs.park_and_measure(posids=all_to_park, mode='normal', coords=park_option, log_note=extra_note,
                              match_radius=None, check_unmatched=False, test_tp=False)
    if any(seq) and is_prepark:
        do_pause()
    logger.info('Parking complete\n')
        
# do the sequence
logger.info('Beginning the move sequence\n')
try:
    if args.prepark:
        park(park_option=args.prepark, is_prepark=True)
    for m in range(len(seq)):
        move = seq[m]
        posids = get_posids()  # dynamically retrieved, in case some positioner gets disabled mid-sequence
        device_loc_unordered = set(get_map(key='loc', posids=posids))
        move_num = m + 1
        move_num_text = f'target {move_num} of {len(seq)}'
        if not move.is_defined_for_locations(device_loc_unordered):
            logger.warning(f'Skipping {move_num_text}, because targets not defined for some positioner locations.\n')
            continue
        logger.info(f'Preparing {move_num_text} on {len(posids)} positioner(s).')
        descriptive_dict = move.to_dict(sparse=True, device_loc=device_loc_unordered)
        logger.info(f'Move settings are {descriptive_dict}\n')
        correctable = move.command in sequence.general_commands and move.allow_corr
        n_corr = args.num_corr if correctable else 0
        errs = None
        calc_errors = True
        for submove_num in range(1 + n_corr):
            extra_log_note = f'move {move_num}'
            if n_corr > 0:
                extra_log_note = pc.join_notes(extra_log_note, f'submove {submove_num}')
            if move.command in sequence.general_commands:
                if pecs_on:
                    move_measure_func = pecs.move_measure
                if submove_num == 0:
                    submove = move
                else:
                    posids = get_posids()   # dynamically retrieved, in case some positioner gets disabled mid-sequence
                    device_loc_map = get_map(key='ids', posids=posids)
                    # note below how order is preserved for target0, target1, and device_loc
                    # lists, on the assumption that get_posids() returns a list
                    submove = sequence.Move(command='poslocdXdY',
                                            target0=[-errs[posid][0] for posid in posids],
                                            target1=[-errs[posid][1] for posid in posids],
                                            device_loc=[device_loc_map[posid] for posid in posids],
                                            log_note=move.log_note,
                                            pos_settings=move.pos_settings,
                                            allow_corr=move.allow_corr)
                request = submove.make_request(loc2id_map=get_map('loc'),log_note=extra_log_note)
                if submove_num == 0:
                    initial_request = request
                if pecs_on:
                    request = request.merge(pecs.posinfo, on='DEVICE_ID')
                kwargs = {'request': request, 'num_meas': args.num_meas}
            elif move.command in sequence.homing_commands:
                calc_errors = False
                if pecs_on:
                    move_measure_func = pecs.rehome_and_measure
                kwargs = move.make_homing_kwargs(posids=posids, log_note=extra_log_note)
            else:
                logger.warning(f'Skipping move {move_num} submove {submove_num} due to unexpected command {move.command}\n')
                continue
            kwargs.update(move_meas_settings)
            new_settings = move.pos_settings
            if new_settings != last_pos_settings:
                all_settings = {posid:new_settings for posid in posids}  # this extra work improves generality of apply_pos_settings, and I expect not too costly
                if pecs_on:
                    apply_pos_settings(all_settings)
                last_pos_settings = new_settings
            logger.info(f'Doing move {move_num}, submove {submove_num}')
            if real_moves:
                results = move_measure_func(**kwargs)
                
                # To be implemented: Some method of storing the submeas strings to
                # the online DB. Can replace the verbose printout below. For now,
                # I just want to be sure that the sub-measurements are logged *somewhere*.
                if args.num_meas > 1:
                    submeas = pecs.summarize_submeasurements(results)
                    logger.info(f'sub-measurements: {submeas}') 
    
                prev_posids = posids
                posids = get_posids()  # dynamically retrieved, in case some positioner gets disabled mid-sequence
                if len(prev_posids) != len(posids):
                    logger.info(f'Num posids changed from {len(prev_posids)} to {len(posids)}. ' +
                                'Check for auto-disabling after comm error. Lost positioners: ' +
                                f'{set(prev_posids) - set(posids)}')
            if calc_errors:
                if real_moves:
                    errs = calc_poslocXY_errors(initial_request, results)
                else:
                    dummy_err_x = np.random.normal(loc=0, scale=0.1, size=len(posids))
                    dummy_err_y = np.random.normal(loc=0, scale=0.1, size=len(posids))
                    errs = {posids[i]: [dummy_err_x[i], dummy_err_y[i]] for i in range(len(posids))}
                err_str = summarize_errors(errs, move_num, submove_num)
                logger.info(err_str + '\n')
            more_moves_to_do = submove_num < n_corr or move_num < len(seq) or args.postpark
            if more_moves_to_do:
                do_pause()
    if args.postpark:
        park(park_option=args.postpark, is_prepark=False)
except StopIteration:
    logger.info('Safely aborting the sequence.')
logger.info(f'Sequence "{seq.short_name}" complete!')

# cleanup after running sequence
if pecs_on:
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
clear_loggers()
