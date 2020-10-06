#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Produces move request sequence. In particular for testing a specific group
of positioners, using their particular calibration parameters to do some intelligent
target selection. As of 2020-10-05, only works on one petal worth of positioners
at a time.
"""

# To retrieve real-world parameters from online DB, use desimeter/get_posmoves, or web tools at e.g.:
#     "calib" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/DESIPositioners/Positioner_calibration.html
#     "moves" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/DESIPositioners/Positioner_moves.html


# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-i', '--infile', type=str, required=True, help='path to input csv file, containing positioner calibration parameters')
parser.add_argument('-o', '--outdir', type=str, required=True, help='path to directory where to save output file')
parser.add_argument('-n', '--num_moves', type=int, required=True, help='integer number of moves to generate')
parser.add_argument('-pos', '--posids', type=str, default='all', help='comma-separated POS_IDs, saying which positioners to generate targets for (defaults to "all")')
parser.add_argument('-ptl', '--petal_id', type=int, default=0, help='specify which petal to use (if PETAL_ID field exists, and has multiple different values)')
parser.add_argument('-ai', '--allow_interference', action='store_true', help='boolean, allow targets to interfere with one another')
parser.add_argument('-s', '--num_stress_select', type=int, default=1, help='integer, for every selected move, code will internally test this many moves and pick the one with the most opportunities for collision.')
parser.add_argument('-lim', '--enable_phi_limit', action='store_true', help='turns on minimum phi limit for move targets, default is False')
parser.add_argument('-p', '--profile', action='store_true', help='turns on timing profiler for move scheduling')
uargs = parser.parse_args()

import os
save_dir = os.path.realpath(uargs.outdir)
assert uargs.num_moves > 0
assert uargs.num_stress_select > 0

# proceed with bulk of imports
from astropy.table import Table
import sys
path_to_petal = '../petal'
sys.path.append(os.path.abspath(path_to_petal))
import posconstants as pc
import petal
import sequence
import random

# read positioner parameter data
required = {'POS_ID', 'DEVICE_LOC', 'LENGTH_R1', 'LENGTH_R2', 'OFFSET_T',
            'OFFSET_P', 'OFFSET_X', 'OFFSET_Y', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
            'KEEPOUT_EXPANSION_PHI_RADIAL', 'KEEPOUT_EXPANSION_PHI_ANGULAR',
            'KEEPOUT_EXPANSION_THETA_RADIAL', 'KEEPOUT_EXPANSION_THETA_ANGULAR',
            'CLASSIFIED_AS_RETRACTED', 'CTRL_ENABLED'}
booleans = {'CLASSIFIED_AS_RETRACTED', 'CTRL_ENABLED'}
nulls = {'--', None, 'none', 'None', '', 0, False, 'False', 'FALSE', 'false'}
boolean = lambda x: x not in nulls
input_table = Table.read(uargs.infile)
missing = required - set(input_table.columns)
assert not any(missing), f'input positioner parameters file is missing columns {missing}'
for col in booleans:
    input_table[col] = [boolean(x) for x in input_table[col].tolist()]

# select petal id
petal_id = uargs.petal_id
if 'PETAL_ID' in input_table.columns:
    all_petal_ids = set(input_table['PETAL_ID'])
    assert petal_id in uargs.petal_id, f'argued petal_id {petal_id} not found in input file'
    undesired = input_table['PETAL_ID'] != petal_id
    input_table.remove_rows(undesired)
    
# ensure single, unique set of parameters per positioner
all_posids = set(input_table['POS_ID'])
params_dict = {key:[] for key in required}
if 'DATE' in input_table.columns:
    input_table.sort('DATE', reverse=True)
for posid in all_posids:
    row = input_table[input_table['POS_ID'] == posid][0]
    for key in params_dict:
        params_dict[key].append(row[key])
params = Table(params_dict)

# ensure single, unique positioner in any given device locations per petal
possible_locs = set(pc.generic_pos_neighbor_locs)
device_locs = params['DEVICE_LOC']
invalid_locs = set(params['DEVICE_LOC']) - possible_locs
assert not any(invalid_locs), f'invalid device locations in input file: {invalid_locs}'
assert len(device_locs) == len(set(device_locs)), f'found repeated device location(s) in input file for petal {petal_id}'

# select which positioners get move commands
if uargs.posids == 'all':
    movers = all_posids
else:
    movers = set(uargs.posids.split(','))
    missing = movers - all_posids
    assert not any(missing), f'argued posids {missing} were not found in parameters file'
disabled = set(params['POS_ID'][params['CTRL_ENABLED'] == False])
movers -= disabled
movers = sorted(movers)  # code lower down assumes consistent order of these

# initialize a simulated petal instance
ptl = petal.Petal(petal_id        = petal_id,
                  petal_loc       = 3,
                  posids          = params['POS_ID'].tolist(),
                  fidids          = set(),
                  simulator_on    = True,
                  db_commit_on    = False,
                  local_commit_on = False,
                  local_log_on    = False,
                  collider_file   = None,
                  sched_stats_on  = True,
                  anticollision   = 'adjust',
                  verbose         = False,
                  phi_limit_on    = uargs.enable_phi_limit,
                  )

# set up calibration parameters
keys_to_store = set(params.columns) - {'POS_ID'}
for posid, state in ptl.states.items():
    row = params[params['POS_ID'] == posid][0]
    for key in keys_to_store:
        state.store(key, row[key])
ptl.collider.refresh_calibrations()

# helper functions
def generate_target_set(posids):
    '''Produces one target set, for the argued collection of posids. Returns a
    dict with keys = posids and values = target locations (poslocXY coordinates).
    '''
    targets_obsTP = {}
    targets_posXY = {}
    for posid in posids:
        attempts_remaining = 10000 # just to prevent infinite loop if there's a bug somewhere
        model = ptl.posmodels[posid]
        min_patrol = abs(ptl.collider.R1[posid] - ptl.collider.R2[posid])
        max_patrol = ptl.collider.R1[posid] + ptl.collider.R2[posid]
        if uargs.enable_phi_limit:
            max_patrol = min(max_patrol, ptl.typical_phi_limit_angle)
        while posid not in targets_obsTP and attempts_remaining:
            bad_target = False
            rangeT = model.targetable_range_posintT
            rangeP = model.targetable_range_posintP
            x = random.uniform(-max_patrol, max_patrol)
            y = random.uniform(-max_patrol, max_patrol)
            this_radius = (x**2 + y**2)**0.5
            if min_patrol > this_radius or this_radius > max_patrol:
                bad_target = True
            else:
                this_posXY = [x,y]
                this_posTP = model.trans.poslocXY_to_posintTP(this_posXY)[0]
                this_obsTP = model.trans.posintTP_to_poslocTP(this_posTP)
                if not uargs.allow_interference:
                    target_interference = False
                    for neighbor in ptl.collider.pos_neighbors[posid]:
                        if neighbor in targets_obsTP:
                            if ptl.collider.spatial_collision_between_positioners(posid, neighbor, this_obsTP, targets_obsTP[neighbor]):
                                target_interference = True
                                break
                    out_of_bounds = ptl.collider.spatial_collision_with_fixed(posid, this_obsTP)
                    out_of_range_T = min(rangeT) > this_posTP[0] or max(rangeT) < this_posTP[0]
                    out_of_range_P = min(rangeP) > this_posTP[1] or max(rangeP) < this_posTP[1]
                    if target_interference or out_of_bounds or out_of_range_T or out_of_range_P:
                        bad_target = True
            if bad_target:
                attempts_remaining -= 1
            else:
                targets_obsTP[posid] = this_obsTP
                targets_posXY[posid] = this_posXY
        if attempts_remaining < 0:
            v = model.state._val
            print(f'Warning: no valid target found for posid: {posid} at location {v["DEVICE_LOC"]}' +
                  f' (x0, y0) = ({v["OFFSET_X"]:.3f}, {v["OFFSET_Y"]:.3f})!')
    return targets_posXY

def generate_request_set(targets):
    '''Produces a dict of requests, ready for petal, from a dict with keys = posids
    and values = target locations (poslocXY coordinates).
    '''
    requests = {}
    for posid, target in targets.items():
        requests[posid] = {'command': 'poslocXY', 'target':target, 'log_note':''}
    return requests

def get_current_posTP():
    '''Returns dict with keys=posid, values=posintTP for all positioners.
    '''
    return {posid: model.expected_current_posintTP for posid, model in ptl.posmodels.items()}

def set_posTP(tp):
    '''Set system with POS_T, POS_P values. Input is a dict with keys = posid,
    values=posintTP.
    '''
    for posid, values in tp.items():
        state = ptl.states[posid]
        state.store('POS_T', values[0])
        state.store('POS_P', values[1])
        
n_stats_lines = 20
statsfile = os.path.join(pc.dirs['temp_files'], 'stats_make_sequence')
import cProfile, pstats
def profile(evaluatable_string):
    print(f'\nProfiling {evaluatable_string}:')
    cProfile.run(evaluatable_string,statsfile)
    p = pstats.Stats(statsfile)
    p.strip_dirs()
    p.sort_stats('cumtime')
    p.print_stats(n_stats_lines)

# generate sequence
timestamp = pc.compact_timestamp()
seq = sequence.Sequence(short_name=f'ptl{petal_id:02}_npos{len(movers)}_ntarg{uargs.num_moves:03}_{timestamp}',
                        long_name='Test move sequence generated by make_sequence.py',
                        details=f'Generated with settings: {uargs}')
set_posTP({posid: (0, 150) for posid in ptl.posids})  # inital values like typical "parked" position
n_collisions_resolved = []
for m in range(uargs.num_moves):
    initial_posTP = get_current_posTP()
    candidates = {key: [] for key in ['targets', 'requests', 'final_posTP', 'n_resolved']}
    for s in range(uargs.num_stress_select):
        print(f'Move {m}: Generating candidate target set {s}.')
        candidates['targets'] += [generate_target_set(movers)]
        candidates['requests'] += [generate_request_set(candidates['targets'][-1])]
        ptl.request_targets(candidates['requests'][-1])
        schedule_command = "ptl.schedule_moves(anticollision='default', should_anneal=True)"
        if uargs.profile:
            profile(schedule_command)
        else:
            eval(schedule_command)
        ptl.send_and_execute_moves()
        candidates['final_posTP'] += [get_current_posTP()]
        num_unresolved_collisions = ptl.schedule_stats.total_unresolved
        assert num_unresolved_collisions == 0, f'{num_unresolved_collisions} collisions were NOT resolved! this indicates a bug that needs to be fixed'
        candidates['n_resolved'] += [ptl.schedule_stats.total_resolved]
        set_posTP(initial_posTP)
    selection = candidates['n_resolved'].index(max(candidates['n_resolved']))
    sel = {k:v[selection] for k,v in candidates.items()}
    n_collisions_resolved += [sel['n_resolved']]
    print(f'Move {m}: Targets selected. Num collisions avoided = {n_collisions_resolved[-1]}')
    set_posTP(sel['final_posTP'])
    move = sequence.Move(command='poslocXY',
                         target0=[sel['targets'][posid][0] for posid in movers],
                         target1=[sel['targets'][posid][0] for posid in movers],
                         device_loc=[ptl.posmodels[posid].deviceloc for posid in movers],
                         log_note='',
                         pos_settings={},
                         allow_corr=True,
                         )
    seq.append(move)

# output
seq.n_collisions_resolved = n_collisions_resolved  # hack, sneaks this value into the sequence meta data
if not os.path.isdir(save_dir):
    os.path.os.makedirs(save_dir)
seq.save(save_dir)