#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''Script to replay in simulation, a sequence of moves done on hardware.
'''

import os

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-i', '--infiles', type=str, required=True, nargs='*',
                    help='Path to input csv file(s), containing results from "get_posmoves --with-calib" ' +
                         '(see that function''s help for full syntax). Regex is ok (like M*.csv). Multiple ' +
                         'file args are also ok (like M00001.csv M00002.csv M01*.csv), as is a directory ' +
                         'that contains the files.')
parser.add_argument('-a', '--anticollision', type=str, default='adjust', help='anticollision mode, can be "adjust", "freeze" or None. Default is "adjust"')
parser.add_argument('-p', '--enable_phi_limit', action='store_true', help='turns on minimum phi limit for move targets, default is False')
parser.add_argument('-ms', '--start_move', type=int, default=0, help='start the simulation at this move index, default is 0')
parser.add_argument('-mf', '--final_move', type=int, default=None, help='end the simulation at this move index, defaults to final move in data')
parser.add_argument('-anim', '--animate', action='store_true', help='plot an animation of simulated moves (can be slow), defaults to False')
parser.add_argument('-f', '--focus', type=str, default=None, help='focus the animation in on a particular positioner and its neighbors. Identify it either by device location integer or POS_ID')
parser.add_argument('-f2', '--second_order_focus', action='store_true', help='when focus option is specified, this causes not just neighbors, but also neighbors-of-neighbors to be animated')
parser.add_argument('-v', '--verbose', action='store_true', help='turn on additional verbosity at console, may be helpful for debugging')

uargs = parser.parse_args()
if uargs.anticollision == 'None':
    uargs.anticollision = None
assert uargs.anticollision in {'adjust', 'freeze', None}, f'bad argument {uargs.anticollision} for anticollision parameter'

import glob
import sys
sys.path.append(os.path.abspath('../../petal/'))
import petal
import posconstants as pc
import posstate
from astropy.table import Table, vstack
import numpy as np

# paths
infiles = []
for s in uargs.infiles:
    these = glob.glob(s)
    for this in these:
        if os.path.isdir(this):
            contents = os.listdir(this)
            contents = [os.path.join(this, file) for file in contents]
            infiles.extend(contents)
        else:
            infiles.append(this)
infiles = [os.path.realpath(p) for p in infiles]

# data types / definitions
nulls = {'--', None, 'none', 'None', '', 0, False, 'False', 'FALSE', 'false'}
boolean = lambda x: x not in nulls
required = {'DATE': str, 'EXPOSURE_ID': int, 'EXPOSURE_ITER': int, 'POS_MOVE_INDEX': int,
            'POS_ID': str, 'PETAL_ID': int, 'DEVICE_LOC': int,
            'MOVE_CMD': str, 'MOVE_VAL1': str, 'MOVE_VAL2': str, 'LOG_NOTE': str,
            'POS_T': float, 'POS_P': float, 'PTL_X': float, 'PTL_Y': float,
            }
param_keys = {'LENGTH_R1': float, 'LENGTH_R2': float, 'OFFSET_X': float, 'OFFSET_Y': float,
              'OFFSET_T': float, 'OFFSET_P': float, 'PHYSICAL_RANGE_T': float, 'PHYSICAL_RANGE_P': float,
              'KEEPOUT_EXPANSION_PHI_RADIAL': float, 'KEEPOUT_EXPANSION_PHI_ANGULAR': float,
              'KEEPOUT_EXPANSION_THETA_RADIAL': float, 'KEEPOUT_EXPANSION_THETA_ANGULAR': float,
              'CLASSIFIED_AS_RETRACTED': boolean, 'CTRL_ENABLED': boolean,
             }
required.update(param_keys)

# read in the move data
input_tables = []
for path in infiles:
    if 'csv' not in path:
        continue  # i.e. skip non-data files
    table = Table.read(path)
    missing = set(required) - set(table.columns)
    if any(missing):
        print(f'Skipped data at {path} due to missing columns {missing}')
        continue
    new = {}
    for key, typefunc in required.items():
        new[key] = [typefunc(x) for x in table[key]]
    input_tables.append(Table(new))
t = vstack(input_tables)
t.sort(keys=['EXPOSURE_ID', 'EXPOSURE_ITER', 'POS_ID'])

# confirm only one petal
petal_ids = set(t['PETAL_ID'])
assert len(petal_ids) == 1, f'replay script does not support {len(petal_ids)} petals'
petal_id = petal_ids.pop()

# identify moving positioners and their neighbors
no_cmd = [x in nulls for x in t['MOVE_CMD']]
has_cmd = [not(x) for x in no_cmd]
t['HAS_MOVE_CMD'] = has_cmd
moving = set(t['POS_ID'][has_cmd])
nonmoving = set(t['POS_ID']) - moving
assert any(moving), 'no moving positioners found in data'
nonmoving_neighbors = set()
known_device_locs = set(t['DEVICE_LOC'])
for posid in moving:
    this_loc = t['DEVICE_LOC'][t['POS_ID'] == posid][0]
    neighbor_locs = pc.generic_pos_neighbor_locs[this_loc]
    for loc in neighbor_locs:
        if loc not in known_device_locs:
            continue
        neighbor_posid = t['POS_ID'][t['DEVICE_LOC'] == loc][0]
        if neighbor_posid in nonmoving:
            nonmoving_neighbors.add(neighbor_posid)
all_posids = moving | nonmoving_neighbors

# identify / define move indexes
move_idxs = [0]
for i in range(1, len(t)):
    this = move_idxs[-1]
    plus_one = this + 1
    if t['EXPOSURE_ID'][i] != t['EXPOSURE_ID'][i-1]:
        move_idxs.append(plus_one)
    elif t['EXPOSURE_ITER'][i] != t['EXPOSURE_ITER'][i-1]:
        move_idxs.append(plus_one)
    else:
        move_idxs.append(this)
t['MOVE_IDX'] = move_idxs
start_move = uargs.start_move
final_move = uargs.final_move
if final_move == None:
    final_move = max(move_idxs)
assert min(move_idxs) <= start_move <= max(move_idxs), f'cannot start at move index {start_move}'
assert min(move_idxs) <= final_move <= max(move_idxs), f'cannot finish at move index {final_move}'
assert start_move <= final_move, f'final move index {final_move} must be >= than start {start_move}'
move_idxs_to_run = sorted(set([i for i in move_idxs if start_move <= i <= final_move]))

# helper functions
def get_row(move_idx, posid):
    '''Get matching row in table for a given move index and posid.'''
    row_match = np.logical_and(t['POS_ID'] == posid, t['MOVE_IDX'] == move_idx)
    rows = t[row_match]
    assert len(rows) == 1, f'unexpected match of {len(row)} > 1 rows'
    return rows[0]

def set_params(move_idx, ptl=None, include_posintTP=False):
    '''Set state parameters for all positioners at a given move index.
    INPUTS:  move_idx ... in the general astropy table "t"
             ptl ... Petal instance
             include_posintTP ... set POS_T, POS_P using values from CSV data file
    '''
    posids = ptl.posids if ptl else all_posids
    keys = set(param_keys)
    if include_posintTP:
        keys |= {'POS_T', 'POS_P'}
    for posid in posids:
        if ptl:
            state = ptl.states[posid]
        else:
            state = posstate.PosState(unit_id=posid, device_type='pos', petal_id=petal_id)
        row = get_row(move_idx, posid)

        for key in keys:
            state.store(key, row[key], register_if_altered=False)
        state.write()
        
def make_request(move_cmd_str):
    '''Generate a move request, by parsing a MOVE_CMD string.'''
    a = move_cmd_str.split('=')
    command = a[0]
    b = a[1].split(';')
    targ_strs = b[0].strip('[').strip(']').split(',')
    target = [float(x) for x in targ_strs]
    request = {'command':command, 'target':target, 'log_note':''}
    return request

# initialize petal
set_params(0, ptl=None, include_posintTP=True)
ptl = petal.Petal(petal_id        = petal_id,
                  petal_loc       = 3,
                  posids          = all_posids,
                  fidids          = {},
                  simulator_on    = True,
                  db_commit_on    = False,
                  local_commit_on = False,
                  local_log_on    = False,
                  collider_file   = None,
                  sched_stats_on  = True,
                  anticollision   = uargs.anticollision,
                  verbose         = uargs.verbose,
                  phi_limit_on    = uargs.enable_phi_limit,
                  )

# initialize animator
anim_label_size = 'medium' # size in points, 'xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large'
anim_cropping_on = True # crops the plot window to just contain the animation
if uargs.animate:
    ptl.animator.cropping_on = True
    ptl.animator.label_size = anim_label_size
    if uargs.focus != None:
        try:
            focus_loc = int(uargs.focus)
            focus_posid = ptl.devices[focus_loc]
        except:
            focus_posid = uargs.focus
        assert focus_posid in all_posids, f'cannot focus video on missing posid {focus_posid}'
        neighbors = pc.generic_pos_neighbor_locs[focus_posid]
        if uargs.second_order_focus:  # include neighbors of neighbors
            for n in neighbors.copy():
                neighbors |= pc.generic_pos_neighbor_locs[n]
        all_foci = set(focus_posid) | neighbors
        ptl.collider.posids_to_animate = all_foci
        ptl.collider.fixed_items_to_animate = set()
    ptl.start_gathering_frames()

# run the sequence
for m in move_idxs_to_run:
    force_tp = m == move_idxs_to_run[0]
    rows = t[t['MOVE_IDX'] == m]
    set_params(m, ptl=ptl, include_posintTP=force_tp)
    move_id_str = pc.join_notes(*[f'{key}: {rows[key][0]}' for key in ['MOVE_IDX', 'DATE', 'EXPOSURE_ID', 'EXPOSURE_ITER']])
    print('\n\n', move_id_str, '\n')
    if ptl.schedule_stats.is_enabled():
        ptl.schedule_stats.add_note(move_id_str)
    requests = {}
    for row in rows:
        if row['HAS_MOVE_CMD']:
            posid = row['POS_ID']
            requests[posid] = make_request(row['MOVE_CMD'])
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()    
    if uargs.verbose:
        coords = {'posintTP': ['POS_T', 'POS_P'], 'ptlXY': ['PTL_X', 'PTL_Y']}
        tab = '  '
        for posid in set(requests):
            s = f'{posid:<7s} ... {"SIMULATED":<20}{tab}{"FROM_FILE":<20}'
            expected = ptl.posmodels[posid].expected_current_position
            for ptl_coord, data_coord in coords.items():
                exp = expected[ptl_coord]
                dat = list(get_row(m, posid)[data_coord])
                exp_str = f'({exp[0]:8.3f}, {exp[1]:8.3f})'
                dat_str = f'({dat[0]:8.3f}, {dat:8.3f})'
                s += f'\n{ptl_coord:>12s}{exp_str:<20}{tab}{dat_str:<20}'
            print(s)   
if ptl.schedule_stats.is_enabled():
    ptl.schedule_stats.save(path=ptl.sched_stats_path, footers=True)
    print(f'Stats saved to {ptl.sched_stats_path}')
if uargs.animate and not ptl.animator.is_empty():
    ptl.stop_gathering_frames()
    print('Generating animation (this can be quite slow)...')
    ptl.animator.filename_suffix = pc.filename_timestamp_str()
    ptl.animator.add_timestamp_prefix_to_filename = False
    ptl.generate_animation()
