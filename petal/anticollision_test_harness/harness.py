"""Script to run the anticollision test harness.
"""

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
import petal
import posconstants as pc
import harness_constants as hc
import sequences
import posstate
import random
import csv

# Some pre-cooked device location selections (can be used below)
locations_all = 'all'
locations_near_gfa = {309,328,348,368,389,410,432,454,474,492,508,521,329,349,369,390,411,433,455,475,493,509,522,532,330,350,370,391,412,434,456,476,494,510,523,533,351,371,392,413,435,457,477,495,511,524,372,393,414,436,458,512,525,415,437,459,526}
subset7a = {78, 79, 87, 88, 89, 98, 99}

# Selection of which device location ids to send move requests to
# (i.e. which positioners on petal to directly command)
# either a set of device locations, or the keyword 'all' or 'near_gfa'
device_loc_to_command = subset7a # note pre-cooked options above

# Select devices to CLASSIFY_AS_RETRACTED and disable
retract_and_disable = {87,88} # enter device locations to simulate those positioners as retracted and disabled
retracted_TP = [0, 110]

# Whether to include any untargeted neighbors in the calculations
include_neighbors = True

# Whether to test some "expert" mode commands
test_direct_dTdP = False
test_homing = False  # note that this one will look a bit weird, since there are no hardstops in simulation. So the results take a bit of extra inspection, but still quite useful esp. to check syntax / basic function

# Override for petal simulated hardware failure rates
sim_fail_freq = {'send_tables': 0.0,
                 'clear_move_tables': 0.0} 

# Selection of which pre-cooked sequences to run. See "sequences.py" for more detail.
runstamp = hc.compact_timestamp()
pos_param_sequence_id = 'PTL03_30001' # 'cmds_unit_test'
move_request_sequence_id = '03000-03001' # 'cmds_unit_test'
note = ''
filename_suffix = str(runstamp) + '_' + str(move_request_sequence_id) + ('_' + str(note) if note else '')

# Other ids
fidids = {}
petal_id = 3

# Animation on/off options
should_animate = False
anim_label_size = 'medium' # size in points, 'xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large'
anim_cropping_on = True # crops the plot window to just contain the animation

# Animation foci
#   {} or 'all' to animate everything, including PTL and GFA.
#   'colliding' to only animate colliding bots.
#   'commanded' to only animate the robots that receive move requests
#   Otherwise, give a specific set of posids to animate. Can include 'GFA' or 'PTL' as desired.
animation_foci = 'all'

# other options
n_corrections = 0 # number of correction moves to simulate after each target
max_correction_move = 0.1/1.414 # mm
should_profile = False
should_inspect_some_TP = False # some *very* verbose printouts of POS_T, OFFSET_T, etc, sometimes helpful for debugging

# saving of target sets for later use on hardware
# formatted for direct input to xytest
should_export_targets = False
def make_xytest_column_headers(command, device_loc):
    '''For making the funky column headers of xytest target files. Returns
    a pair of headers, e.g. for the x and y coordinates or the like.'''
    u_cmd = command[:-1] + '_' + str(device_loc)
    v_cmd = command[:-2] + command[-1] + '_' + str(device_loc)
    return u_cmd, v_cmd
def make_xytest_header_sortable_key(s):
    '''Another utility for generating the funky column headers of xytest target
    files. Returns a key that can be used by sorted() function on a list of
    headers.'''
    target_no_1st = s[1]
    device_loc_2nd = s.split('_')[1].rjust(5,'0')
    uv_coord_3rd = s.split('_')[0][-1]
    return target_no_1st + device_loc_2nd + uv_coord_3rd

# randomizer for correction moves
randomizer_seed = 0
random.seed(randomizer_seed)

# resolve which device locations to operate on
if device_loc_to_command == 'all':
    device_loc_to_command = set(pc.generic_pos_neighbor_locs.keys())
all_device_loc = set(device_loc_to_command)
if include_neighbors:
    for loc in device_loc_to_command:
        neighbors = pc.generic_pos_neighbor_locs[loc]
        all_device_loc = all_device_loc.union(neighbors)

# Run the sequences.
pos_param_sequence = sequences.get_positioner_param_sequence(pos_param_sequence_id, all_device_loc)
move_request_sequence = sequences.get_move_request_sequence(move_request_sequence_id, device_loc_to_command)
exportable_targets = []
orig_params = {}
for pos_param_id, pos_params in pos_param_sequence.items():         
    for posid,params in pos_params.items():
        state = posstate.PosState(unit_id=posid, device_type='pos', petal_id=petal_id)
        state.store('POS_T',0.0)
        state.store('POS_P',180.0)
        for key,val in params.items():
            state.store(key,val)
        if params['DEVICE_LOC'] in retract_and_disable:
            orig_params[posid] = {key:state._val[key] for key in ['CTRL_ENABLED', 'CLASSIFIED_AS_RETRACTED']}
            state.store('POS_T', retracted_TP[0])
            state.store('POS_P', retracted_TP[1])
            state.store('CTRL_ENABLED', False)
            state.store('CLASSIFIED_AS_RETRACTED', True)
        state.write()
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
    for key, val in sim_fail_freq.items():
        ptl.sim_fail_freq[key] = val
    ptl.limit_radius = None
    if ptl.schedule_stats.is_enabled():
        ptl.schedule_stats.filename_suffix = filename_suffix
        ptl.schedule_stats.clear_cache_after_save_by_append = False
        ptl.schedule_stats.add_note('POS_PARAMS_ID: ' + str(pos_param_id))
    if should_animate:
        ptl.animator.cropping_on = True
        ptl.animator.label_size = anim_label_size
        if animation_foci == 'colliding':
            ptl.collider.animate_colliding_only = True  
        elif animation_foci == 'commanded':
            ptl.collider.posids_to_animate = {ptl.devices[loc] for loc in device_loc_to_command}
            ptl.collider.fixed_items_to_animate = set()
        elif animation_foci != 'all' and len(animation_foci) > 0:
            posids_to_animate = set()
            fixed_items_to_animate = set()
            for identifier in animation_foci:
                if identifier in ptl.posids:
                    posids_to_animate.add(identifier)
                    posids_to_animate.update(ptl.collider.pos_neighbors[identifier])
                elif identifier in ['PTL','GFA']:
                    fixed_items_to_animate.add(identifier)
                else:
                    print('Warning: ' + str(identifier) + ', requested as an animation focus, is not a known item on this petal, therefore was ignored.')
                ptl.collider.posids_to_animate = posids_to_animate
                ptl.collider.fixed_items_to_animate = fixed_items_to_animate
        ptl.start_gathering_frames()
    m = 0
    mtot = len(move_request_sequence)
    for move_requests_id, move_request_data in move_request_sequence.items():
        m += 1
        exportable_targets.append({'target_no':m-1})
        if ptl.schedule_stats.is_enabled():
            ptl.schedule_stats.add_note('MOVE_REQUESTS_ID: ' + str(move_requests_id))
        for n in range(n_corrections + 1):
            print(' move: ' + str(m) + ' of ' + str(mtot) + ', submove: ' + str(n))
            log_note = f'harness move {m} submove {n}'
            requests = {}
            for loc_id,data in move_request_data.items():
                if data['command'] == 'posXY': # handles older file format
                    data['command'] = 'poslocXY'
                if loc_id in ptl.devices:
                    requests[ptl.devices[loc_id]] = {'command':data['command'], 'target': [data['u'], data['v']], 'log_note':log_note}
                    u_header, v_header = make_xytest_column_headers(data['command'], loc_id)
                    exportable_targets[-1][u_header] = data['u']
                    exportable_targets[-1][v_header] = data['v']
            anticollision = 'adjust'
            if n > 0:
                for request in requests.values():
                    request['command'] = 'poslocdXdY'
                    request['target'][0] = random.uniform(-max_correction_move,max_correction_move)
                    request['target'][1] = random.uniform(-max_correction_move,max_correction_move)
                    request['log_note'] = log_note
                anticollision = 'freeze'
            if should_profile:
                hc.profile('ptl.request_targets(requests)')
            else:
                ptl.request_targets(requests)
            if should_profile:
                hc.profile('ptl.schedule_send_and_execute_moves(anticollision="'+anticollision+'")')
            else:
                ptl.schedule_send_and_execute_moves(anticollision=anticollision)
            if should_inspect_some_TP:
                for dev in device_loc_to_command:
                    posid = ptl.devices[dev]
                    print('---------------')
                    print(f'posid {posid}, device {dev}')
                    vals = ptl.states[posid]._val
                    print(f'POS_T = {vals["POS_T"]}')
                    print(f'POS_P = {vals["POS_P"]}')
                    print(f'OFFSET_T = {vals["OFFSET_T"]}')
                    print(f'OFFSET_P = {vals["OFFSET_P"]}')
                    print(f'POS_T + OFFSET_T = {vals["POS_T"] + vals["OFFSET_T"]}')
                    print(f'POS_P + OFFSET_P = {vals["POS_P"] + vals["OFFSET_P"]}')
                print('---------------')
        if test_direct_dTdP:
            posids_to_test = list(requests.keys())
            for dtdp in [[30,0], [-30,0], [0,-30], [0,30], [30,-30], [-30,30]]:
                direct_requests = {posid: {'target': dtdp, 'log_note':''} for posid in posids_to_test}
                ptl.request_direct_dtdp(direct_requests)
                ptl.schedule_send_and_execute_moves(anticollision='adjust') # 'adjust' here *should* internally be ignored in favor of 'freeze'
        if test_homing:
            posids_to_test = list(requests.keys())
            for axis in ['phi', 'theta', 'both']:
                ptl.request_homing(posids_to_test, axis=axis)
                ptl.schedule_send_and_execute_moves(anticollision='adjust') # 'adjust' here *should* internally be ignored in favor of 'freeze'
    if ptl.schedule_stats.is_enabled():
        stats_path = os.path.join(pc.dirs['temp_files'], 'schedstats_' + filename_suffix + '.csv')
        ptl.schedule_stats.save(path=stats_path)
    if should_export_targets and exportable_targets:
        filename = 'xytest_targets_' + filename_suffix + '.csv'
        path = os.path.join(pc.dirs['temp_files'], filename)
        headers = exportable_targets[0].keys()
        headers = sorted(headers, key=make_xytest_header_sortable_key)
        headers = [''] + headers # to match weird extra index column in the table format we're trying to match...
        with open(path, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            for row in exportable_targets:
                row[''] = row['target_no']
                writer.writerow(row)
    if should_animate and not ptl.animator.is_empty():
        ptl.stop_gathering_frames()
        print('Generating animation (this can be quite slow)...')
        ptl.animator.filename_suffix = filename_suffix
        ptl.animator.add_timestamp_prefix_to_filename = False
        ptl.generate_animation()
    for posid, params in orig_params.items():
        for key,value in params.items():
            ptl.states[posid].store(key, value)
        ptl.states[posid].write()