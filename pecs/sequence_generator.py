# -*- coding: utf-8 -*-
"""
Produces positioner move sequences, for any of several pre-cooked types of test.
"""

import sequence
import numpy as np
import itertools
import math
import os

seqs = []
make_sparse_csv = []

# DEBUGGING / CODE SYNTAX seqs
# -----------------------------

seq = sequence.Sequence(short_name='debug dTdP', long_name='test the code with single tiny move')
move = sequence.Move(command='dTdP', target0=0.01, target1=0.01, log_note='', allow_corr=False,
                     pos_settings={'ANTIBACKLASH_ON': False})
seq.append(move)
seqs.append(seq)

seq = sequence.Sequence(short_name='debug dTdP full current',
                        long_name='test the code with single tiny move and motor current set to 100')
move = sequence.Move(command='dTdP', target0=0.01, target1=0.01, log_note='', allow_corr=False,
                     pos_settings={'ANTIBACKLASH_ON': False,
                                   'CURR_SPIN_UP_DOWN': 100,
                                   'CURR_CRUISE': 100,
                                   'CURR_CREEP': 100})
seq.append(move)
seqs.append(seq)

x = 1.0
y = 1.0
seq = sequence.Sequence(short_name='debug poslocXY with corr',
                        long_name=f'single move to poslocXY = ({x}, {y}) and a followup correction move')
move = sequence.Move(command='poslocXY', target0=x, target1=y, log_note='', allow_corr=True)
seq.append(move)
seqs.append(seq)

t = 0.0
p = 150.0
seq = sequence.Sequence(short_name='debug posintTP with corr',
                        long_name=f'single move to posintTP = ({t}, {p}) and a followup correction move')
move = sequence.Move(command='posintTP', target0=t, target1=p, log_note='', allow_corr=True)
seq.append(move)
seqs.append(seq)


seq = sequence.Sequence(short_name='debug multitarget',
                        long_name='test the code with differing simultaneous targets on several positioners')
locs = sequence.possible_device_locs
targ_val_options = [i*.5-2.0 for i in range(9)]
targ_val_unique_combos = list(itertools.combinations(targ_val_options,2))
fill_repeats = math.ceil(len(locs) / len(targ_val_unique_combos))
targ_val_combos = []
for i in range(fill_repeats):
    targ_val_combos += targ_val_unique_combos
targets = [[], []]
for axis in [0,1]:
    targets[axis] = [targ_val_combos[k][axis] for k in range(len(locs))]
n_moves = 2
shift = lambda X: X[1:] + [X[0]]
for i in range(n_moves):
    for axis in range(len(targets)):
        targets[axis] = shift(targets[axis])
    move = sequence.Move(command='poslocXY',
                         target0=targets[0],
                         target1=targets[1],
                         device_loc=locs,
                         log_note='',
                         allow_corr=True,
                         )
    seq.append(move)
seqs.append(seq)
make_sparse_csv.append(seq)


# GENERIC XY TESTS
# ----------------
import xy_targets_generator
n_targs = 24
for limited in [True]:  # [JHS] as of 2020-08-27 I'm not yet releasing the unlimited version into the wild, until anticollision is well-tested
    seq = sequence.Sequence(short_name=f'xytest uniform{" limited" if limited else ""}',
                            long_name=f'rectilinear grid of test points, same local xy for all pos{", limited patrol" if limited else ""}')
    targs = xy_targets_generator.filled_annulus(n_points=n_targs,
                                                r_min=0.0,
                                                r_max=3.3 if limited else 6.0,
                                                random=False)
    for targ in targs:
        move = sequence.Move(command='poslocXY', target0=targ[0], target1=targ[1], allow_corr=True)
        seq.append(move)
    seqs.append(seq)


# BASIC HOMING SEQUENCES
# ----------------------

seq = sequence.Sequence(short_name='home_and_debounce',
                        long_name='run a single rehome on both axes, followed by debounce moves')
move = sequence.Move(command='home_and_debounce', target0=1, target1=1, log_note='', allow_corr=False)
seq.append(move)
seqs.append(seq)

seq = sequence.Sequence(short_name='home_no_debounce', 
                        long_name='run a single rehome on both axes, with no debounce moves')
move = sequence.Move(command='home_no_debounce', target0=1, target1=1, log_note='', allow_corr=False)
seq.append(move)
seqs.append(seq)


# SIMPLE ARC SEQUENCES
# --------------------

cmd = 'posintTP'
settings = {'ALLOW_EXCEED_LIMITS': True}
name_note = ', travel limits OFF'
for axis in ['theta', 'phi']:
    seq = sequence.Sequence(short_name=f'arc {axis}', long_name=f'rotate {axis} repeatedly, for use in circle fits{name_note}')
    if axis == 'theta':
        thetas = [-170+i*20 for i in range(18)]
        phi = 130
        targets = [[theta, phi] for theta in thetas]
    else:
        theta = 0
        phis = [120+i*3 for i in range(18)]
        targets = [[theta, phi] for phi in phis]
    for i in range(len(targets)):
        target = targets[i]
        move = sequence.Move(command=cmd, target0=target[0], target1=target[1], log_note='', pos_settings=settings, allow_corr=False)
        seq.append(move)
    seqs.append(seq)
    
cmd = 'dTdP'
deltas = [1.0 for i in range(10)]
for axis in ['theta', 'phi']:
    seq = sequence.Sequence(short_name=f'shortdeltas {axis}', long_name=f'rotate {axis} small delta amounts, over a short distance{name_note}')
    if axis == 'theta':
        targets = [[delta, 0] for delta in deltas]
    else:
        targets = [[0, delta] for delta in deltas]
    for i in range(len(targets)):
        target = targets[i]
        move = sequence.Move(command=cmd, target0=target[0], target1=target[1], log_note='', pos_settings=settings, allow_corr=False)
        seq.append(move)
    seqs.append(seq)


# HARDSTOP DEBOUNCE MEASUREMENTS
# ------------------------------

details = '''Settings: default
Moves: Repeatedly strike hard-limit. After each, try a different debounce amount, then some test moves.
Purpose: Measure the debounce distance needed when coming off the hardstops.'''
clearance_vals = {'theta': [3.0, 4.0, 5.0, 6.0],
                 'phi': [3.0, 4.0, 5.0, 6.0]}
test_step_away = {'theta': 30.0, 'phi': -30.0}
num_test_steps = {'theta': 3, 'phi': 3}
for axis in ['theta', 'phi']:
    seq = sequence.Sequence(short_name=f'hardstoptest {axis}',
                            long_name=f'seqs varying debounce distances, when coming off {axis} hard limit',
                            details=details)
    init_cmd = 'posintTP'
    init_pos = [0, 130]
    move = sequence.Move(command=init_cmd, target0=init_pos[0], target1=init_pos[1], allow_corr=False,
                         log_note=f'{seq.short_name}, going to initial {init_cmd}={init_pos} (away from stops)')
    seq.append(move)
    n_loops = len(clearance_vals[axis])
    for i in range(n_loops):
        clearance_val = clearance_vals[axis][i]
        clearance_key = f'PRINCIPLE_HARDSTOP_CLEARANCE_{"T" if axis=="theta" else "P"}'
        settings = {clearance_key: clearance_val}
        note = f'loop {i+1} of {n_loops}, {clearance_key}={clearance_val}'
        move = sequence.Move(command='home_and_debounce',
                             target0=(axis=='theta'),
                             target1=(axis=='phi'),
                             log_note=note,
                             allow_corr=False,
                             pos_settings=settings,
                             )
        for j in range(num_test_steps[axis]):
            for direction in ['away from', 'toward']:
                sign = 1 if direction == 'away from' else -1
                step = sign * test_step_away[axis]
                move = sequence.Move(command='dTdP',
                                     target0=step * (axis=='theta'),
                                     target1=step * (axis=='phi'),
                                     log_note=f'{note}, step {j+1} of {num_test_steps[axis]}, {direction} hardstop',
                                     allow_corr=False,
                                     pos_settings=settings,
                                     )
                seq.append(move)
    seqs.append(seq)


# MOTOR TESTS
# -----------

# Helper functions
def wiggle(forward, case=0):
    '''Generates a wiggly sequence with lots of back and forth, using a starting list
    of forward direction deltas. Several pre-cooked cases are provided.'''
    backward = [-x for x in forward]
    forward_reversed = [x for x in reversed(forward)]
    backward_reversed = [x for x in reversed(backward)]
    backandforth = [x for t in zip(forward, backward) for x in t]
    if case == 0:
        deltas = forward + backward + backward_reversed + forward_reversed + backandforth
    if case == 1:
        deltas = backward + backandforth + forward + backward_reversed + forward_reversed
    return deltas
    
def typ_motortest_sequence(prefix, short_suffix, long_suffix, details, forward_deltas, settings):
    seq = sequence.Sequence(short_name = f'motortest {prefix} {short_suffix}',
                            long_name = f'{prefix} motor test, {long_suffix}',
                            details = details)
    i = 0 if prefix.lower()[0] == 't' else 1
    deltas = wiggle(forward_deltas, case=i)
    for j in range(len(deltas)):
        target = [0,0]
        target[i] = deltas[j]
        move = sequence.Move(command='dTdP', target0=target[0], target1=target[1], log_note='', pos_settings=settings, allow_corr=False)
        seq.append(move)
    return seq

# Theta and phi performance at nominal settings
details = '''Settings: default
Moves: Several moves at cruise speed, each followed by the usual final creep moves for precision positioning and antibacklash.'
Purpose: Baseline tests for typical proper function.'''
options = {}
short_suffix = 'nominal'
long_suffix = 'performance at nominal settings'
forward_deltas = [1, 5, 15, 30]
seqs.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
seqs.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi cruise-only at otherwise nominal settings
details = '''Settings: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON
Moves: Several moves at cruise speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in typical cruise mode.'''
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'] # smallest finite value
           }
short_suffix = 'cruiseonly'
long_suffix = 'cruise-only, at otherwise nominal settings'
forward_deltas = [1, 5, 15, 30]
seqs.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
seqs.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi cruise-only, with spinup/down power disabled
details = '''Settings: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON. Set CURR_SPIN_UP_DOWN = 0.
Moves: Several moves at cruise speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in typical cruise mode.'''
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'], # smallest finite value
           'CURR_SPIN_UP_DOWN': 0,
           'SPINUPDOWN_PERIOD': 1 # smallest finite value
          }
short_suffix = 'cruise nospinupdown'
long_suffix = 'cruise-only, with spinup/down power disabled'
forward_deltas = [1, 5, 15, 30]
seqs.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
seqs.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi creep-only at otherwise nominal settings
details = '''Settings: Turn on parameter ONLY_CREEP.
Moves: Several moves at creep speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in creep mode.'''
options = {'ONLY_CREEP': True,
           'FINAL_CREEP_ON': False}
short_suffix = 'creeponly'
long_suffix = 'creep-only, at otherwise nominal settings'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
seqs.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
seqs.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi fast creep
details = '''Settings: Halve the creep period thereby doubling the creep speed.
Moves: Several moves at creep speed. In each direction, at several step sizes.
Purpose: Determine whether creep performance can be improved under existing firmware (v5.0) constraints.'''
options = {'ONLY_CREEP': True,
           'CREEP_PERIOD': 1,
           'FINAL_CREEP_ON': False}
short_suffix = 'fastcreep'
long_suffix = 'with fastest available creep speed under firmware v5.0'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
seqs.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
seqs.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))


# SAVE ALL TO DISK
# ----------------
paths = []
sparse_paths = []
for seq in seqs:
    path = seq.save()
    paths.append(path)
    if seq in make_sparse_csv:
        table = seq.to_table()
        all_cols = set(table.columns)
        keep_cols = {sequence.move_idx_key, 'command', 'target0', 'target1', 'device_loc'}
        for col in all_cols - keep_cols:
            del table[col]
        sparse_path = os.path.splitext(path)[0] + '_sparse.csv'
        table.write(sparse_path, overwrite=True, delimiter=',')
        sparse_paths.append(sparse_path)
    paths.extend(sparse_paths)
    
# READ FROM DISK AND PRINT TO STDOUT
# ----------------------------------
for path in paths:
    if 'XYTEST' in path:
        print(f'Now reading: {path}')  # debug breakpoint
    seq = sequence.Sequence.read(path)
    print(seq,'\n')
    if 'motortest' in seq[0].log_note:
        axis = 0 if 'THETA' in seq.normalized_short_name else 1
        deltas = [getattr(move, f'target{axis}') for move in seq]
        cumsum = np.cumsum(deltas).tolist()
        print('num test points: '  + str(len(deltas)))
        print(f'min and max excursions: [{min(cumsum)} deg, {max(cumsum)} deg]')
        # print('delta sequence: ' + str(deltas))
        # print('running total: ' + str(cumsum))
    
    
