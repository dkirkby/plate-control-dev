#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Retrieves calibration parameters from online database. Can return them as
an astropy table (when run as an imported module) or save to disk as an ecsv.
"""

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-ptl', '--petal_ids', type=str, default='kpno', help='Comma-separated integers, specifying one or more PETAL_ID number(s) for which to retrieve data. Defaults to all known petals at kpno database. Alternately argue "lbnl" for all known petals in lbnl (beyonce) database.')
parser.add_argument('-o', '--outdir', type=str, default='.', help='Path to directory where to save output file. Defaults to current dir.')
parser.add_argument('-m', '--comment', type=str, default='', help='Comment string which will be included in output file metadata.')
parser.add_argument('-dl', '--disable_logger', action='store_true', help='Disable logging to disk.')
uargs = parser.parse_args()

# general imports
import os
import sys
from astropy.table import Table
try:
    import posconstants as pc
except:
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
import poscollider

# set up logger
import simple_logger
import traceback
if uargs.disable_logger:
    log_path = None
else:
    log_dir = pc.dirs['calib_logs']
    log_timestamp = pc.filename_timestamp_str()
    log_name = log_timestamp + '_get_calibrations.log'
    log_path = os.path.join(log_dir, log_name)
logger = simple_logger.start_logger(log_path)
assert2 = simple_logger.assert2

# validate petal ids
default_petal_ids = {'kpno': {2, 3, 4, 5, 6, 7, 8, 9, 10, 11},
                     'lbnl': {0, 1}}
possible_petal_ids = set()
for ids in default_petal_ids.values():
    possible_petal_ids |= ids
use_all_ptls = uargs.petal_ids in default_petal_ids.keys()
if use_all_ptls:
    petal_ids = default_petal_ids[uargs.petal_ids]
else:
    petal_ids = uargs.petal_ids.split(',')
    petal_ids = {int(i) for i in petal_ids}
assert2(len(petal_ids) > 0, 'no petal ids detected in {petal_ids}')
for petal_id in petal_ids:
    assert2(petal_id in possible_petal_ids, f'petal id {petal_id} is unrecognized')

# data keys retreivable from quick_query(), along with human-readable descriptions
query_keys = {'POS_ID': 'unique serial id number of fiber positioner',
              'DEVICE_LOC': 'location number of device on petal (c.f. DESI-0530)',
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
              'CTRL_ENABLED': 'if True, move tables are allowed to be sent to the positioner (may vary from night to night)',
              'DEVICE_CLASSIFIED_NONFUNCTIONAL': 'if True, the focal plane team has determined this positioner cannot be operated (stable from night to night)',
              'FIBER_INTACT': 'if False, the focal plane team has determined the positioner\'s fiber cannot be measured (stable from night to night)',
              'POS_T': 'current value of internally-tracked theta angle, a.k.a. "posintT" or t_int',
              'POS_P': 'current value of internally-tracked phi angle, a.k.a. "posintP" or p_int',
              'PTL_X': 'current x position in petal coordinates, as transformed from (POS_T, POS_P)',
              'PTL_Y': 'current y position in petal coordinates, as transformed from (POS_T, POS_P)',
              'OBS_X': 'current x position in global coordinates (a.k.a. "CS5" or "x_fp") as transformed from (POS_T, POS_P)',
              'OBS_Y': 'current y position in global coordinates (a.k.a. "CS5" or "y_fp") as transformed from (POS_T, POS_P)',
              }
query_keys_map = {'PTL_X': 'ptlX',
                  'PTL_Y': 'ptlY',
                  'OBS_X': 'obsX',
                  'OBS_Y': 'obsY'}

# petal-wide keys for storage in positioner data rows
pos_petal_keys = {'PETAL_ID': 'unique serial id number of petal',
                  'PETAL_LOC': 'location number of petal on focal plane (c.f. DESI-3596)'}
pos_petal_attr_map = {'PETAL_ID': 'petal_id',
                      'PETAL_LOC': 'petal_loc'}

# petal-wide keys for storage in meta-data
other_petal_keys = {'PETAL_ALIGNMENTS': '6 DOF transformation parameters from "PTL" local coordinates to "OBS" a.k.a. "CS5" a.k.a. "FP" global coordinates'}

# general and positioner-specific data keys from the collider
flat_note = '["flat" coordinates]'
keepout_T_note = f'central body (theta) polygon {flat_note}'
keepout_P_note = f'eccentric body (phi) keepout polygon {flat_note}'
general_collider_keys = {'timestep': '[sec] quantization when sweeping polygons through rotation schedules, to check for collisions',
                         'Eo_phi': '[deg] poslocP angle (poslocP = POS_P + OFFSET_P) above which phi is defined to be within envelope "Eo" (i.e. retracted)',
                         'Eo_radius_with_margin': '[mm] when a positioner is CLASSIFED_AS_RETRACTED, neighbor polygons not allowed to enter this circle',
                         'general_keepout_T': f'basic {keepout_T_note}',
                         'general_keepout_P': f'basic {keepout_P_note}',
                         'keepout_PTL': f'petal boundary keepout polygon {flat_note}',
                         'keepout_GFA': f'GFA boundary keepout polygon {flat_note}', 
                         }
pos_collider_keys = {'KEEPOUT_T': keepout_T_note,
                     'KEEPOUT_P': keepout_P_note,
                     'POS_NEIGHBORS': 'neighboring positioners',
                     'FIXED_NEIGHBORS': 'neighboring fixed boundaries'}
pos_collider_attr_map = {'KEEPOUT_T': 'keepouts_T',
                         'KEEPOUT_P': 'keepouts_P',
                         'POS_NEIGHBORS': 'pos_neighbors',
                         'FIXED_NEIGHBORS': 'fixed_neighbor_cases'}

# dependently-calculated fields
offset_variants = {'PTL': 'ptlXY', 'CS5': 'obsXY'}
offset_variant_keys = {f'{coord}_{var}': f'{coord} transformed into {system}' for coord in ['OFFSET_X', 'OFFSET_Y'] for var, system in offset_variants.items()}
range_desc = lambda func, c: f'{func} targetable internally-tracked {"theta" if c == "T" else "phi"} angle (i.e. "POS_{c}" or "posint{c}" or "{c.lower()}_int"'
range_keys = {f'{func.upper()}_{c}': range_desc(func, c) for func in ['max', 'min'] for c in ['T', 'P']}

# summarize all keys and units (where applicable)
all_pos_keys = {}
all_pos_keys.update(pos_petal_keys)
all_pos_keys.update(query_keys)
all_pos_keys.update(pos_collider_keys)
all_pos_keys.update(offset_variant_keys)
all_pos_keys.update(range_keys)
angular_keys = {'POS_T', 'POS_P', 'OFFSET_T', 'OFFSET_P', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
                'KEEPOUT_EXPANSION_PHI_ANGULAR', 'KEEPOUT_EXPANSION_THETA_ANGULAR'}
angular_keys |= set(range_keys)
mm_keys = {'LENGTH_R1', 'LENGTH_R2', 'OFFSET_X', 'OFFSET_Y', 'OBS_X', 'OBS_Y', 'PTL_X', 'PTL_Y',
           'KEEPOUT_EXPANSION_PHI_RADIAL', 'KEEPOUT_EXPANSION_THETA_RADIAL'}
mm_keys |= set(offset_variant_keys)
units = {key: 'deg' for key in angular_keys}
units.update({key: 'mm' for key in mm_keys})

# identifying fields with polygon data
polygons = 'KEEPOUT_T', 'KEEPOUT_P', 'general_keepout_T', 'general_keepout_P'

# initialize petals
roles = {}
apps = {}
ptls = {}
logger.info(f'Attempting to retrieve data for {len(petal_ids)} petals: {petal_ids}')
try:
    import PetalApp
    from DOSlib.proxies import Petal
    ptlapp_dir = PetalApp.__path__._path[0]
    ptlapp_path = os.path.join(ptlapp_dir, 'PetalApp.py')
    assert2(os.path.exists(ptlapp_path), f'No PetalApp found at path {ptlapp_path}', show_quit_msg=False)
    logger.info('Online system is available, will use PetalApp')
    online = True
except:
    import petal
    logger.warning('Online system is not available. Falling back to dummy data + petal.py instances (may be useful for other debugging).')
    online = False
if online:
    import threading
    def run_petal(petal_id, role):
        os.system(f'python {ptlapp_path} --device_mode True --sim True --petal_id {petal_id} --role {role}')
    for petal_id in petal_ids:
        name = f'PetalApp{petal_id}'
        role = f'PETALSIM{petal_id}'
        logger.info(f'Initializing threaded PetalApp with name {name} and role {role}...')
        ptl_app = threading.Thread(target=run_petal, name=name, args=(petal_id, role))
        ptl_app.daemon = False
        ptl_app.start()
        roles[petal_id] = role
        apps[petal_id] = ptl_app
    for petal_id, role in roles.items():
        ptl = Petal(petal_id, role=role)
        ptls[petal_id] = ptl
else:
    for petal_id in petal_ids:
        logger.info(f'Initializing petal instance for petal id {petal_id}...')
        ptl = petal.Petal(petal_id=petal_id,
                          simulator_on=True,
                          db_commit_on=False,
                          local_commit_on=False,
                          local_log_on=False,
                          collider_file=None,
                          sched_stats_on=False,
                          printfunc=logger.info,
                          )
        ptls[petal_id] = ptl
logger.info(f'{len(ptls)} petals initialized')

# Most of the remainder is enclosed in a try so that we can shut down PetalApps
# at the end, even if a crash occurs before that.
exception_during_run = None
try:
    # gather data
    data = {key:[] for key in all_pos_keys}
    meta = {}
    meta['DATE_RETRIEVED'] = pc.timestamp_str()
    meta['COMMENT'] = uargs.comment
    for key in ['DATE_RETRIEVED', 'COMMENT']:        
        logger.info(f'metadata {key} = {meta[key]}')
    meta['PETAL_ATTRIBUTES'] = other_petal_keys
    meta['PETAL_ALIGNMENTS'] = {}
    for petal_id, ptl in ptls.items():
        this_data = {}
        valid_keys = ptl.quick_query()['valid_keys']
        mapped_query_keys = {query_keys_map[key] if key in query_keys_map else key for key in query_keys}
        missing = set(mapped_query_keys) - set(valid_keys)
        assert2(not(any(missing)), f'some keys are not available for petal {ptl.petal_id}: {missing}')
        posids_ordered = sorted(ptl.posids)
        logger.info(f'Now gathering data for {len(posids_ordered)} positioners on petal id {petal_id}...')
        
        # queryable values
        for key in set(query_keys) | set(pos_collider_keys):
            if key in query_keys:
                query_key = query_keys_map[key] if key in query_keys_map else key
                this_dict = ptl.quick_query(key=query_key, mode='iterable')
            else:
                attr_key = pos_collider_attr_map[key]
                this_dict = getattr(ptl.collider, attr_key)
                if 'fixed' in attr_key.lower():
                    this_dict = {posid: {pc.case.names[enum] for enum in neighbors} for posid, neighbors in this_dict.items()}
                sample = this_dict[posids_ordered[0]]
                if isinstance(sample, poscollider.PosPoly):
                    this_dict = {posid: str(poly.points) for posid, poly in this_dict.items()}
            this_list = [this_dict[p] for p in posids_ordered]
            data[key].extend(this_list)
    
        # dependent values
        for posid in posids_ordered:
            model = ptl.posmodels[posid]
            flat_offset_xy = (ptl.collider.x0[posid], ptl.collider.y0[posid])
            for suffix, coord in offset_variants.items():
                if coord == 'obsXY':   
                    xy_new = model.trans.flatXY_to_obsXY(flat_offset_xy, cast=True)
                elif coord == 'ptlXY':
                    xy_new = model.trans.flatXY_to_ptlXY(flat_offset_xy)
                else:
                    assert2(False, f'unexpected destination coordinates {coord}')
                data[f'OFFSET_X_{suffix}'].append(float(xy_new[0]))
                data[f'OFFSET_Y_{suffix}'].append(float(xy_new[1]))
            for key in range_keys:
                func = max if 'MAX' in key else min
                rng = model.targetable_range_posintT if 'T' in key else model.targetable_range_posintP
                data[key].append(func(rng))
        
        # petal-wide values
        for key, attr in pos_petal_attr_map.items():
            value = getattr(ptl, attr)
            data[key].extend([value] * len(posids_ordered))
        meta['PETAL_ALIGNMENTS'][petal_id] = ptl.trans.petal_alignment
            
    # [JHS] As of 2020-11-02, these general collider parameters should be equivalent for
    # any petal. Here, I simply use the last ptl instance from the for loop above.
    meta['COLLIDER_ATTRIBUTES'] = general_collider_keys
    for key in general_collider_keys:
        meta[key] = getattr(ptl.collider, key)
        if isinstance(meta[key], poscollider.PosPoly):
            meta[key] = str(meta[key].points)
        
    logger.info('All data gathered, generating table format...')
    t = Table(data)
    t.meta = meta
    
    # add units and descriptions
    for key in t.columns:
        t[key].description = all_pos_keys[key]
        if key in units:
            t[key].unit = units[key]
        
    # save data to disk
    save_dir = os.path.realpath(uargs.outdir)
    save_name = pc.filename_timestamp_str() + '_fp_calibs.ecsv'
    save_path = os.path.join(save_dir, save_name)
    t.write(save_path)
    logger.info(f'Data saved to: {save_path}')
    
    # save a reference to this file in a standard place
    ref_dir = pc.dirs['temp_files']
    ref_path = os.path.join(ref_dir, 'latest_fp_calibs.txt')
    with open(ref_path, mode='w') as file:
        file.write(save_path)
    logger.info(f'File path cached at standard location: {ref_path}')
    
except Exception as e:
    exception_during_run = e
    logger.error('get_calibrations crashed! See traceback below:')
    logger.critical(traceback.format_exc())
    logger.info('Attempting to clean up lingering PetalApp instances prior to exiting...')

# shut down the threads
for petal_id in apps.keys():
    logger.info(f'Sending shutdown command for petal {petal_id}...')
    ptl = ptls[petal_id]
    ptl.kill()

# re-raise exception from above if we have one
if exception_during_run:
    raise(exception_during_run)
