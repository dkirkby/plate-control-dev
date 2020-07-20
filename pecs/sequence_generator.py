# -*- coding: utf-8 -*-
"""
Produces positioner move sequences, for any of several pre-cooked types of test.
"""

import sequence
import numpy as np

deg = '\u00B0'
tests = []

# HELPER FUNCTIONS

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

def describe(seq, axis):
    deltas = [move[f'target{axis}'] for move in seq.table]
    cumsum = np.cumsum(deltas).tolist()
    print('num test points: '  + str(len(deltas)))
    print('min and max excursions: [' + str(min(cumsum)) + deg + ', ' + str(max(cumsum)) + deg + ']')
    # print('delta sequence: ' + str(deltas))
    # print('running total: ' + str(cumsum))
    
def typ_motortest_sequence(prefix, short_suffix, long_suffix, details, forward_deltas, settings):
    new = sequence.Sequence(short_name = prefix.upper() + ' ' + short_suffix.upper(),
                            long_name = prefix + ' ' + long_suffix,
                            details = details)
    i = 0 if prefix.lower()[0] == 't' else 1
    deltas = wiggle(forward_deltas, case=i)
    for j in range(len(deltas)):
        target = [0,0]
        target[i] = deltas[j]
        note = 'motortest: ' + str(new.short_name) + ', move: ' + str(j)
        new.add_move(command='dTdP', target0=target[0], target1=target[1], log_note=note, pos_settings=settings)
    print(new)
    describe(new, i)
    print('')
    return new

# TEST DEFINITIONS

# Theta and phi performance at nominal settings
details = '''Settings: default
Moves: Several moves at cruise speed, each followed by the usual final creep moves for precision positioning and antibacklash.'
Purpose: Baseline tests for typical proper function.'''
options = {}
short_suffix = 'nominal'
long_suffix = 'performance at nominal settings'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi cruise-only at otherwise nominal settings
details = '''Settings: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON
Moves: Several moves at cruise speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in typical cruise mode.'''
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'] # smallest finite value
           }
short_suffix = 'cruise only'
long_suffix = 'cruise-only, at otherwise nominal settings'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi cruise-only, with spinup/down power disabled
# TEST 5 - Phi cruise-only, with spinup/down power disabled
details = '''Settings: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON. Set CURR_SPIN_UP_DOWN = 0.
Moves: Several moves at cruise speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in typical cruise mode.'''
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'], # smallest finite value
           'CURR_SPIN_UP_DOWN': 0,
           'SPINUPDOWN_PERIOD': 1 # smallest finite value
          }
short_suffix = 'cruise no spinupdown'
long_suffix = 'cruise-only, with spinup/down power disabled'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi creep-only at otherwise nominal settings
details = '''Settings: Turn on parameter ONLY_CREEP.
Moves: Several moves at creep speed. In each direction, at several step sizes.
Purpose: Measure the effective output ratio in creep mode.'''
options = {'ONLY_CREEP': True,
           'FINAL_CREEP_ON': False}
short_suffix = 'creep only'
long_suffix = 'creep-only, at otherwise nominal settings'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Theta and phi fast creep
details = '''Settings: Halve the creep period thereby doubling the creep speed.
Moves: Several moves at creep speed. In each direction, at several step sizes.
Purpose: Determine whether creep performance can be improved under existing firmware (v5.0) constraints.'''
options = {'ONLY_CREEP': True,
           'CREEP_PERIOD': 1,
           'FINAL_CREEP_ON': False}
short_suffix = 'fast creep'
long_suffix = 'with fastest available creep speed under firmware v5.0'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, details, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, details, forward_deltas, options))

# Debugging / code syntax tests
debug_note = lambda seq: f'move sequence code test, {seq.normalized_short_name}'
new = sequence.Sequence(short_name='debug dTdP', long_name='test the code with single tiny move')
new.add_move(command='dTdP', target0=0.01, target1=0.01, log_note=debug_note(new),
             pos_settings={'ANTIBACKLASH_ON': False})
print(new,'\n')
tests.append(new)

new = sequence.Sequence(short_name='debug dTdP full current',
                        long_name='test the code with single tiny move and motor current set to 100')
new.add_move(command='dTdP', target0=0.01, target1=0.01, log_note=debug_note(new),
             pos_settings={'ANTIBACKLASH_ON': False,
                           'CURR_SPIN_UP_DOWN': 100,
                           'CURR_CRUISE': 100,
                           'CURR_CREEP': 100})
print(new,'\n')
tests.append(new)

# Basic homing sequences
new = sequence.Sequence(short_name='home_and_debounce',
                        long_name='run a single rehome on both axes, followed by debounce moves')
new.add_move(command='home_and_debounce', target0=1, target1=1, log_note=debug_note(new))
print(new,'\n')
tests.append(new)

new = sequence.Sequence(short_name='home_no_debounce', 
                        long_name='run a single rehome on both axes, with no debounce moves')
new.add_move(command='home_no_debounce', target0=1, target1=1, log_note=debug_note(new))
print(new,'\n')
tests.append(new)

# Hardstop debounce measurements
details = '''Settings: default
Moves: Repeatedly strike hard-limit. After each, try a different debounce amount, then some test moves.
Purpose: Measure the debounce distance needed when coming off the hardstops.'''
debounce_vals = {'theta': [2.0, 3.0, 4.0],
                 'phi': [-2.0, -3.0, -4.0]}
test_step_away = {'theta': 30.0, 'phi': -30.0}
num_test_steps = {'theta': 2, 'phi': 2}
for axis in {'theta', 'phi'}:
    new = sequence.Sequence(short_name=f'{axis} hardstop test',
                            long_name=f'tests varying debounce distances, when coming off {axis} hard limit',
                            details=details)
    init_cmd = 'posintTP'
    init_pos = [0, 130]
    new.add_move(command=init_cmd, target0=init_pos[0], target1=init_pos[1],
                 log_note=f'{new.short_name}, going to initial {init_cmd}={init_pos} (away from stops)')
    n_debounce = len(debounce_vals[axis])
    for i in range(n_debounce):
        debounce = debounce_vals[axis][i]
        note = f'{new.short_name}, loop {i+1} of {n_debounce}'
        new.add_move(command='home_no_debounce',
                     target0=(axis=='theta'),
                     target1=(axis=='phi'),
                     log_note=note)
        new.add_move(command='dTdP',
                     target0=debounce_vals[axis][i] * (axis=='theta'),
                     target1=debounce_vals[axis][i] * (axis=='phi'),
                     log_note=f'{note}, debounce={debounce}')
        for j in range(num_test_steps[axis]):
            for direction in {'away from', 'toward'}:
                sign = 1 if direction == 'away from' else -1
                step = sign * test_step_away[axis]
                new.add_move(command='dTdP',
                             target0=step * (axis=='theta'),
                             target1=step * (axis=='phi'),
                             log_note=f'{note}, step {j+1} of {num_test_steps[axis]}, {direction} hardstop',
                             )
    print(new,'\n')
    tests.append(new)

# SAVE TO DISK
for test in tests:
    test.save()
    