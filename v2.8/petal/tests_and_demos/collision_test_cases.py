"""
Kevin Fanning fanning.59@osu.edu

collision_test_cases


"""
import sys
import os
import test_not_overlapping_targets
sys.path.append(os.path.abspath('../'))
import posstate
import posmodel


position_index = {'right': 0, 'upper right': 1, 'upper left': 2, 'left': 3,
                  'lower left': 4, 'lower right': 5}

collision_cases = {'TypeIII_easy':{'posidA':[[-60,0],[60,0]], 'posidB':[[180,180],[180,180]]},
                   'TypeIII_hard': {'posidA':[[-25,0],[25,0]], 'posidB': [[155,180],[205,180]]},
                   'TypeII_easy': {'posidA':[[-60,60],[0,180]],'posidB':[[180,0],[180,180]]},
                   'TypeII_hard': {'posidA':[[-60,60],[0,0]],'posidB':[[180,0],[120,60]]},
                   'both': {'posidA':[[-25,0],[25,0]],'posidB':[[155,0],[205,0]]}}

def shift_obsTP(targetA, targetB, B_location):
    '''
    Shifts obsTP of targets between base positioner, A, and neighbor positioner, B,
    from assuming B is to the right of A, to any general neighbor around A. Useful
    for adapting collision test cases (imagined in left-right case) to any general
    neighboring case.

    Input:
        targetA    - The original [obsT, obsP] pair of positioner A
        targetB    - the original [obsT, obsP] pair of positioner B,
                         the neighbor of positioner A
        B_location - The loaction of B relative to A, any one of 'right',
                         'upper right', 'upper left', 'left', 'lower left',
                         'lower right', corresponding to the six verticies
                         of a regular hexagon about positioner A
    '''
    if B_location not in position_index.keys():
        return False
    targetA[0] += position_index[B_location]*60
    targetB[0] -= position_index[B_location]*60
    return targetA, targetB

def generate_targets_from_collision_cases(posidA, posidB, B_location, collision_case, coord = 'obsXY'):
    """
    Generates requests in the form used by xytest to use the anticollision test cases.

    Input:
        posidA, posidB
        B_location - see above
        collision_case - must be a key of the defined collision cases above.
        coord - NOT YET SUPPORTED -does nothing right now, hopefully allows you to choose output coordinates in the future.

    IMPORTANT: For this to actually test anticollision the positioners must be well calibrated before running.
    """
    if (B_location not in position_index.keys()) or (collision_case not in collision_cases.keys()):
        return False
    stateA = posstate.PosState(unitid = posidA)
    posmodelA = posmodel.PosModel(state = stateA)
    stateB = posstate.PosState(unitid = posidB)
    posmodelB = posmodel.PosModel(state = stateB)
    targetA1 = collision_cases[collision_case]['posidA'][0]
    targetB1 = collision_cases[collision_case]['posidB'][0]
    test = test_not_overlapping_targets.OverlappingTargets(posid1 = posidA, posid2 = posidB)
    targetA1, targetB1 = shift_obsTP(targetA1, targetB1, B_location)
    collision_type = test.test_targets(left_target = targetA1, right_target = targetB1)
    if collision_type != 'Type I':
        print('Collision', collision_type, 'occured when trying to set the initial request, these must be some eccentric positioners and will not move to the first target.')
    if coord == 'obsXY':
        targetA1 = posmodelA.trans.obsTP_to_obsXY(targetA1)
        targetB1 = posmodelB.trans.obsTP_to_obsXY(targetB1)
    else:
        return False
    request1 = {posidA:{'command':coord,'target':targetA1}, posidB:{'command':coord,'target':targetB1}}

    targetA2 = collision_cases[collision_case]['posidA'][1]
    targetB2 = collision_cases[collision_case]['posidB'][1]
    targetA2, targetB2 = shift_obsTP(targetA2,targetB2, B_location)
    collision_type = test.test_targets(left_target = targetA2, right_target = targetB2)
    if collision_type != 'Type I':
        print('Collision', collision_type, 'occured when trying to set the second request, these must be some eccentric positioners and will not move to the second target.')
    if coord == 'obsXY':
        targetA2 = posmodelA.trans.obsTP_to_obsXY(targetA2)
        targetB2 = posmodelB.trans.obsTP_to_obsXY(targetB2)
    else:
        return False
    request2 = {posidA:{'command':coord,'target':targetA2}, posidB:{'command':coord,'target':targetB2}}
    
    return request1, request2
