"""Creates a set of simulated move requests for testing the anticollision code.
"""

import os
import sys
sys.path.append(os.path.abspath('../../petal'))
import csv
import random
import poscollider
import posmodel
import posstate
import harness_constants as hc
import sequences

# input parameters
num_sets_to_make = 1000
posparams_id = 30001
posparams = sequences._read_data(data_id=posparams_id)
posids =  'all' # 'all' for all posids in posparams, otherwise a set of selected ones

# initialize a poscollider instance (for fair target checking)
collider = poscollider.PosCollider()
posmodels = {}
keys_to_copy = ['POS_ID','DEVICE_LOC','CTRL_ENABLED',
                'LENGTH_R1','LENGTH_R2',
                'OFFSET_T','OFFSET_P','OFFSET_X','OFFSET_Y',
                'PHYSICAL_RANGE_T','PHYSICAL_RANGE_P']
for posid,data in posparams.items():
    if posid in posids or posids == 'all':
        state = posstate.PosState(posid)
        for key in keys_to_copy:
            state.store(key,data[key])  
        model = posmodel.PosModel(state)
        posmodels[posid] = model
collider.add_positioners(posmodels.values())

# generate random targets
all_targets = []
for i in range(num_sets_to_make):
    targets_obsTP = {}
    targets_posXY = {}
    for posid,model in posmodels.items():
        attempts_remaining = 10000 # just to prevent infinite loop if there's a bug somewhere
        while posid not in targets_obsTP and attempts_remaining:
            rangeT = model.targetable_range_T
            rangeP = model.targetable_range_P
            max_patrol = posparams[posid]['LENGTH_R1'] + posparams[posid]['LENGTH_R2']
            min_patrol = abs(posparams[posid]['LENGTH_R1'] - posparams[posid]['LENGTH_R2'])
            x = random.uniform(-max_patrol,max_patrol)
            y = random.uniform(-max_patrol,max_patrol)
            this_radius = (x**2 + y**2)**0.5
            if min_patrol > this_radius or this_radius > max_patrol:
                attempts_remaining = max(attempts_remaining - 1, 0)
            else:
                this_posXY = [x,y]
                this_posTP = model.trans.poslocXY_to_posintTP(this_posXY)[0]
                this_obsTP = model.trans.posintTP_to_poslocTP(this_posTP)
                target_interference = False
                for neighbor in collider.pos_neighbors[posid]:
                    if neighbor in targets_obsTP:
                        if collider.spatial_collision_between_positioners(posid, neighbor, this_obsTP, targets_obsTP[neighbor]):
                            target_interference = True
                            break
                out_of_bounds = collider.spatial_collision_with_fixed(posid, this_obsTP)
                if not target_interference and not out_of_bounds:
                    targets_obsTP[posid] = this_obsTP
                    targets_posXY[posid] = this_posXY
                else:
                    attempts_remaining = max(attempts_remaining - 1, 0)
        if not attempts_remaining:
            v = model.state._val
            print('Warning: no valid target found for posid: ' + posid + ' at location ' + str(v['DEVICE_LOC']) + ' (x,y) = (' + format(v['OFFSET_X'],'.3f') + ',' + format(v['OFFSET_Y'],'.3f') + ')')
    all_targets.append(targets_posXY)
    
# save set files
petal_id = 3 #posparams_id - 10000 # quick hack, assuming the "add 10000" to id rule from "generate_request_sets_for_posparams.py" applies
start_number = input('Enter starting file number (or nothing, to start at \'000\'). The petal id number will be prefixed. start = ')
start_number = 0 if not start_number else int(start_number)
next_filenumber = petal_id * 1000 + start_number # more id number hackery
for target in all_targets:
    save_path = hc.filepath(hc.req_dir, hc.req_prefix, next_filenumber)
    with open(save_path,'w',newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['DEVICE_LOC','command','u','v'])
        for posid,uv in target.items():
            writer.writerow([posmodels[posid].state._val['DEVICE_LOC'],'poslocXY',uv[0],uv[1]])
    next_filenumber += 1