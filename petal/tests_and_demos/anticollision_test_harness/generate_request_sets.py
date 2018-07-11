"""Creates a set of simulated targets for testing the anticollision code.
"""

import os
import sys
sys.path.append(os.path.abspath('../../../petal'))
import csv
import random
from read_nominal_pos_locations import locations
import poscollider
import posmodel
import posstate
import harness_constants as hc

# input parameters
num_sets_to_make = 2
nominal_patrol_radius = 6.0 # mm

# initialize a nominal poscollider instance (for reasonable target checking)
collider = poscollider.PosCollider()
posmodels = {}
for posid,data in locations.items():
    state = posstate.PosState(posid)
    state.store('DEVICE_ID',data['DEVICE_ID'])
    state.store('LENGTH_R1',3.0)
    state.store('LENGTH_R2',3.0)
    state.store('OFFSET_T',0.0)
    state.store('OFFSET_P',0.0)
    state.store('OFFSET_X',data['nomX'])
    state.store('OFFSET_Y',data['nomY'])
    state.store('PHYSICAL_RANGE_T',380.0)
    state.store('PHYSICAL_RANGE_P',200.0)    
    model = posmodel.PosModel(state)
    posmodels[posid] = model
collider.add_positioners(posmodels.values())

# generate random targets
all_targets = []
for i in range(num_sets_to_make):
    targets_obsTP = {}
    targets_posXY = {}
    for posid,model in posmodels.items():
        attempts_remaining = 50
        while posid not in targets_obsTP:
            rangeT = model.targetable_range_T
            rangeP = model.targetable_range_P
            this_posT = random.uniform(min(rangeT),max(rangeT))
            this_posP = random.uniform(min(rangeP),max(rangeP))
            this_posTP = [this_posT,this_posP]
            this_obsTP = model.trans.posTP_to_obsTP(this_posTP)
            target_interference = False
            for neighbor in collider.pos_neighbors[posid]:
                if neighbor in targets_obsTP:
                    if collider.spatial_collision_between_positioners(posid, neighbor, this_obsTP, targets_obsTP[neighbor]):
                        target_interference = True
                        break
            out_of_bounds = collider.spatial_collision_with_fixed(posid, this_obsTP)
            if not target_interference and not out_of_bounds:
                targets_obsTP[posid] = this_obsTP
                targets_posXY[posid] = model.trans.posTP_to_posXY(this_posTP)
            else:
                attempts_remaining -= 1
        if not attempts_remaining:
            v = state._val
            print('Warning: no valid target found for posid: ' + posid + ' at location ' + str(v['DEVICE_ID']) + ' (x,y) = (' + format(v['OFFSET_X'],'.3f') + ',' + format(v['OFFSET_Y'],'.3f') + ')')
    all_targets.append(targets_posXY)
    
# save set files
existing = os.listdir(hc.req_dir)
existing_filenumbers = [hc.filenumber(name,hc.req_prefix) for name in existing]
next_filenumber = max(existing_filenumbers) + 1 if existing_filenumbers else 0
for target in all_targets:
    save_path = hc.filepath(hc.req_dir, hc.req_prefix, next_filenumber)
    with open(save_path,'w',newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['DEVICE_ID','command','u','v'])
        for posid,uv in target.items():
            writer.writerow([posmodels[posid].state._val['DEVICE_ID'],'posXY',uv[0],uv[1]])
    next_filenumber += 1