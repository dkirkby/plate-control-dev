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
    
def typ_motortest_sequence(prefix, short_suffix, long_suffix, forward_deltas, settings):
    new = sequence.Sequence(short_name = prefix.upper() + ' ' + short_suffix.upper(),
                            long_name = prefix + ' ' + long_suffix)
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

# TEST 0 - Theta performance at nominal settings
# TEST 1 - Phi performance at nominal settings
#
# Options: default
#
# Moves:   Several moves at cruise speed, each followed by the usual final
#          creep moves for precision positioning and antibacklash.
#
# Purpose: Baseline tests for typical proper function.
options = {}
short_suffix = 'nominal'
long_suffix = 'performance at nominal settings'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, forward_deltas, options))

# TEST 2 - Theta cruise-only at otherwise nominal settings
# TEST 3 - Phi cruise-only at otherwise nominal settings
#
# Options: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON
#
# Moves:   Several moves at cruise speed.
#          In each direction, at several step sizes.
#          
# Purpose: Measure the effective output ratio in typical cruise mode.
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'] # smallest finite value
           }
short_suffix = 'cruise only'
long_suffix = 'cruise-only, at otherwise nominal settings'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, forward_deltas, options))

# TEST 4 - Theta cruise-only, with spinup/down power disabled
# TEST 5 - Phi cruise-only, with spinup/down power disabled
#
# Options: Turn off parameters FINAL_CREEP_ON and ANTIBACKLASH_ON.
#          Set CURR_SPIN_UP_DOWN = 0.
#
# Moves:   Several moves at cruise speed.
#          In each direction, at several step sizes.
#          
# Purpose: Measure the effective output ratio in typical cruise mode.
options = {'FINAL_CREEP_ON': False,
           'ANTIBACKLASH_ON': False,
           'MIN_DIST_AT_CRUISE_SPEED': sequence.nominals['stepsize_cruise'], # smallest finite value
           'CURR_SPIN_UP_DOWN': 0,
           'SPINUPDOWN_PERIOD': 1 # smallest finite value
          }
short_suffix = 'cruise no spinupdown'
long_suffix = 'cruise-only, with spinup/down power disabled'
forward_deltas = [1, 5, 15, 30]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, forward_deltas, options))

# TEST 6 - Theta creep-only at otherwise nominal settings
# TEST 7 - Phi creep-only at otherwise nominal settings
#
# Options: Turn on parameter ONLY_CREEP
#
# Purpose: Measure the effective output ratio in creep mode.
options = {'ONLY_CREEP': True}
short_suffix = 'creep only'
long_suffix = 'creep-only, at otherwise nominal settings'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, forward_deltas, options))

# TEST 8 - Theta fast creep
# TEST 9 - Phi fast creep
#
# Options: Halve the creep period thereby doubling the creep speed.
#
# Purpose: Determine whether creep performance can be improved under
#          existing firmware (v5.0) constraints.
options = {'ONLY_CREEP': True,
           'CREEP_PERIOD': 1}
short_suffix = 'fast creep'
long_suffix = 'with fastest available creep speed under firmware v5.0'
forward_deltas = [0.5, 1.0, 1.5, 2.0]
tests.append(typ_motortest_sequence('Theta', short_suffix, long_suffix, forward_deltas, options))
tests.append(typ_motortest_sequence('Phi',   short_suffix, long_suffix, forward_deltas, options))

# SAVE TO DISK
for test in tests:
    test.save(basename='test' + str(tests.index(test)))
    