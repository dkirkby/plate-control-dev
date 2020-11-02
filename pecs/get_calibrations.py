#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Retrieves calibration parameters from online database. Can return them as
an astropy table (when run as an imported module) or save to disk as an ecsv.
"""

def assert2_no_log(test, message):
    assert test, message

import os, sys
try:
    import posconstants as pc
except:
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc

default_petal_ids = {'kpno': {2, 3, 4, 5, 6, 7, 8, 9, 10, 11},
                     'lbnl': {0, 1}}
possible_petal_ids = set()
for ids in default_petal_ids.values():
    possible_petal_ids |= ids

def validate_petal_ids(proposed_ids, assert2=None):
    '''Validates collection of petal ids. Also see comments in help docstr of
    "--petal-ids" command line arg for more detail. Returns a set.'''
    assert2 = assert2 if assert2 else assert2_no_log
    if pc.is_string(proposed_ids):
        use_all_ptls = proposed_ids in default_petal_ids.keys()
        if use_all_ptls:
            petal_ids = default_petal_ids[proposed_ids]
        else:
            petal_ids = proposed_ids.split(',')
            petal_ids = {int(i) for i in petal_ids}
    else:
        assert2(pc.is_collection(proposed_ids), 'proposed petal ids {proposed_ids} is not a collection')
        petal_ids = set(proposed_ids)
    assert2(len(petal_ids) > 0, 'no petal ids detected in {petal_ids}')
    for petal_id in petal_ids:
        assert2(petal_id in possible_petal_ids, f'petal id {petal_id} is unrecognized')
    return petal_ids

# keys and descriptions to retrieve
keys = {
        'POS_ID': 'unique serial id number of fiber positioner',
        'PETAL_ID': 'unique serial id number of petal',
        'DEVICE_LOC': 'location number on petal, c.f. DESI-0530',
        'LENGTH_R1': 'kinematic length between central axis and phi axis',
        'LENGTH_R2': 'kinematic length between phi axis and fiber',
        'OFFSET_T': 'mounting angle of positioner\'s x-axis (roughly halfway between theta hardstops) w.r.t. that of petal',
        'OFFSET_P': 'angle from hardstop at far clockwise position to phi=0',
        'OFFSET_X': 'x position of robot\'s central axis, in "flat" coordinate system',
        'OFFSET_Y': 'y position of robot\'s central axis, in "flat" coordinate system',
        'PHYSICAL_RANGE_T': 'angular distance between theta hardstops',
        'PHYSICAL_RANGE_P': 'angular distance between phi hardstops',
        'GEAR_CALIB_T': 'scale factor for theta shaft rotations, actual/nominal',
        'GEAR_CALIB_P': 'scale factor for phi shaft rotations, actual/nominal',
        'KEEPOUT_EXPANSION_PHI_RADIAL': 'radially expands phi keepout polygon by this amount',
        'KEEPOUT_EXPANSION_THETA_RADIAL': 'radially expands theta keepout polygon by this amount',
        'KEEPOUT_EXPANSION_PHI_ANGULAR': 'angularly expands phi keepout polygon by + and - this amount',
        'KEEPOUT_EXPANSION_THETA_ANGULAR': 'angularly expands theta keepout polygon by + and - this amount',
        'CLASSIFIED_AS_RETRACTED': 'identifies positioner for travel only within a restricted radius',
        'CTRL_ENABLED': 'if True, move tables are allowed to be sent to the positioner',
        'DEVICE_CLASSIFIED_NONFUNCTIONAL': 'if True, the focal plane team has determined this positioner cannot be operated',
        'FIBER_INTACT': 'if False, the focal plane team has determined the positioner\'s fiber cannot be measured',
        }
descriptions = {desc: key for key, desc in keys.items()}

# units (where applicable)
angular_keys = {'POS_T', 'POS_P', 'OFFSET_T', 'OFFSET_P', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P', 'KEEPOUT_EXPANSION_PHI_ANGULAR', 'KEEPOUT_EXPANSION_THETA_ANGULAR'}
mm_keys = {'LENGTH_R1', 'LENGTH_R2', 'OFFSET_X', 'OFFSET_Y', 'KEEPOUT_EXPANSION_PHI_RADIAL', 'KEEPOUT_EXPANSION_THETA_RADIAL'}
units = {key: 'deg' for key in angular_keys}
units.update({key: 'mm' for key in mm_keys})

def initialize_petals(petal_ids):
    '''Returns a dict with keys = petal_ids'''
roles = {}
apps = {}
ptls = {}
logger.info('Will attempt to get c')
try:
    from DOSlib.proxies import Petal
    import threading
    def run_petal(petal_id, role):
        os.system(f'python PetalApp.py --device_mode True --sim True --petal_id {petal_id} --role {role}')
    for petal_id in petal_ids:
        role = f'PETALSIM{petal_id}'
        ptl_app = threading.Thread(target=run_petal, name=f'PetalApp{petal_id}', args=(petal_id, role))
        ptl_app.daemon = False
        ptl_app.start()
        roles[petal_id] = role
        apps[petal_id] = ptl_app
    for petal_id, role in roles.items():
        ptl = Petal(petal_id, role=role)
        ptls[petal_id] = ptl
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    import petal
    for petal_id in petal_ids:
        ptl = petal.Petal(petal_id        = petal_id,
                      petal_loc       = 3,
                      posids          = pos_params.keys(),
                      fidids          = fidids,
                      simulator_on    = True,
                      db_commit_on    = False,
                      local_commit_on = False,
                      local_log_on    = False,
                      collider_file   = None,
                      sched_stats_on  = True, # minor speed-up if turn off
                      anticollision   = 'adjust',
                      verbose         = False,
                      phi_limit_on    = False)


# proceed with remainder of imports
from astropy.table import Table

# gather data
data = {key:[] for key in keys}
for ptl in ptls:
    this_data = {}
    available_keys_dict = ptl.quick_query()
    available_keys = set()
    for group_name, keys in available_keys_dict.items():
        if 'keys' in group_name:
            available_keys |= set(keys)
    missing = set(keys) - available_keys
    assert not any(missing), f'some keys are not available for petal {ptl.petal_id}: {missing}'
    posids_ordered = sorted(ptl.posids)
    for key in keys:
        this_dict = ptl.quick_query(key=key, mode='iterable')
        this_list = [this_dict[p] for p in posids_ordered]
        data[key].append(this_list)
        
t = Table(data)

# add some metadata
meta = {}
meta['DATE_RETRIEVED'] = pc.timestamp_str()
meta['EO_RADIUS_WITH_MARGIN'] = None
t.meta = meta

# add units and descriptions
for key in t.columns:
    if key in descriptions:
        t[key].description = descriptions[key]
    if key in units:
        t[key].unit = units[key]

# dependently-calculated information
states = {}
models = {}
for posid in t['POS_ID']:
    state = posstate.PosState()
    model = posmodel.PosModel()
    posmodels[posid] = model
    
# shut down the threads

# columns for desimodel
'PETAL', 'DEVICE', 'PETAL_ID', 'DEVICE_ID', 'DEVICE_TYPE',
'OFFSET_X_CS5', 'OFFSET_Y_CS5',
'OFFSET_X_PTL', 'OFFSET_Y_PTL',
'OFFSET_X_FLAT', 'OFFSET_Y_FLAT',
'MAX_T', 'MIN_T', 'MAX_P', 'MIN_P'
'KEEPOUT_T', 'KEEPOUT_P' # --> and have these each be in local coords (i.e. placed at x0,y0 = 0,0)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-ptl', '--petal_ids', type=str, default='kpno', help='Comma-separated integers, specifying one or more PETAL_ID number(s) for which to retrieve data. Defaults to all known petals at kpno database. Alternately argue "lbnl" for all known petals in lbnl (beyonce) database.')
    parser.add_argument('-o', '--outdir', type=str, default='.', help='Path to directory where to save output file. Defaults to current dir.')
    parser.add_argument('-m', '--comment', type=str, default='', help='Comment string which will be included in output file metadata.')
    uargs = parser.parse_args()

    # set up logger
    import simple_logger
    log_dir = pc.dirs['sequence_logs']
    log_timestamp = pc.filename_timestamp_str()
    log_name = log_timestamp + '_get_calibrations.log'
    log_path = os.path.join(log_dir, log_name)
    logger = simple_logger.start_logger(log_path)
    assert2 = simple_logger.assert2
    
    save_dir = os.path.realpath(uargs.outdir)
    petal_ids = validate_petal_ids(uargs.petal_ids, assert2)