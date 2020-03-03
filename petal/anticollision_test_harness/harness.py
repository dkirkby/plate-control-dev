"""Script to run the anticollision test harness.
"""

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
import petal
import harness_constants as hc
import posconstants as pc
import sequences
import posstate
import random
import csv

# Some pre-cooked device location selections (can be used below)
locations_all = 'all'
locations_near_gfa = {309,328,348,368,389,410,432,454,474,492,508,521,329,349,369,390,411,433,455,475,493,509,522,532,330,350,370,391,412,434,456,476,494,510,523,533,351,371,392,413,435,457,477,495,511,524,372,393,414,436,458,512,525,415,437,459,526}
subset7a = {89,79,78,99,87,98,88}

# Selection of which device location ids to send move requests to
# (i.e. which positioners on petal to directly command)
device_loc_to_operate = subset7a

# Whether to include any untargeted neighbors in the calculations
include_neighbors = True

# Selection of which pre-cooked sequences to run. See "sequences.py" for more detail.
runstamp = hc.compact_timestamp()
pos_param_sequence_id = 'PTL03_20200211'
move_request_sequence_id = '03000-03001' #'04000-04999' #'04108-04110'
note = ''
filename_suffix = str(runstamp) + '_' + str(move_request_sequence_id) + ('_' + str(note) if note else '')

# Other ids
fidids = {}
petal_id = 3

# Other options
should_animate = True
anim_label_size = 'medium' # size in points, 'xx-small', 'x-small', 'small', 'medium', 'large', 'x-large', 'xx-large'
animation_foci =  'commanded' # argue {} or 'all' to animate everything, including PTL and GFA.
                             # 'colliding' to only animate colliding bots.
                             # 'all but fixed' to animate all robots, but no PTL or GFA
                             # 'commanded' to animate the robots that receive move requests
                             # otherwise, give a specific set of posids (plus their surrounding neighbors) to animate. Can include 'GFA' or 'PTL' as desired.
anim_cropping_on = True # crops the plot window to just contain the animation
n_corrections = 0 # number of correction moves to simulate after each target
max_correction_move = 0.050/1.414 # mm
should_profile = False

# saving of target sets for later use on hardware
# formatted for direct input to xytest
should_export_targets = True
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

# Include any neighbors in the scheduling calculations as necessary.
all_device_loc = device_loc_to_operate
if include_neighbors and device_loc_to_operate != 'all':
    all_device_loc = 'all' # could do more elaborate search for specific neighbors, but this works for most use cases

# Run the sequences.
pos_param_sequence = sequences.get_positioner_param_sequence(pos_param_sequence_id, all_device_loc)
move_request_sequence = sequences.get_move_request_sequence(move_request_sequence_id, device_loc_to_operate)
exportable_targets = []
for pos_param_id, pos_params in pos_param_sequence.items():
    for posid,params in pos_params.items():
        state = posstate.PosState(unit_id=posid, device_type='pos', petal_id=petal_id)
        state.store('POS_T',0.0)
        state.store('POS_P',180.0)
        for key,val in params.items():
            state.store(key,val)
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
    ptl.limit_radius = None
    if ptl.schedule_stats:
        ptl.schedule_stats.filename_suffix = filename_suffix
        ptl.schedule_stats.clear_cache_after_save_by_append = False
        ptl.schedule_stats.add_note('POS_PARAMS_ID: ' + str(pos_param_id))
    if should_animate:
        ptl.animator.cropping_on = True
        ptl.animator.label_size = anim_label_size
        if animation_foci == 'colliding':
            ptl.collider.animate_colliding_only = True  
        elif animation_foci == 'all but fixed':
            ptl.collider.posids_to_animate = ptl.posids
            ptl.collider.fixed_items_to_animate = set()
        elif animation_foci == 'commanded':
            ptl.collider.posids_to_animate = {ptl.devices[loc] for loc in device_loc_to_operate}
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
        if ptl.schedule_stats:
            ptl.schedule_stats.add_note('MOVE_REQUESTS_ID: ' + str(move_requests_id))
        for n in range(n_corrections + 1):
            print(' move: ' + str(m) + ' of ' + str(mtot) + ', submove: ' + str(n))
            requests = {}
            for loc_id,data in move_request_data.items():
                if data['command'] == 'posXY': # handles older file format
                    data['command'] = 'poslocXY'
                if loc_id in ptl.devices:
                    requests[ptl.devices[loc_id]] = {'command':data['command'], 'target': [data['u'], data['v']]}
                    u_header, v_header = make_xytest_column_headers(data['command'], loc_id)
                    exportable_targets[-1][u_header] = data['u']
                    exportable_targets[-1][v_header] = data['v']
            anticollision = 'adjust'
            if n > 0:
                for request in requests.values():
                    request['command'] = 'obsdXdY'
                    request['target'][0] = random.uniform(-max_correction_move,max_correction_move)
                    request['target'][1] = random.uniform(-max_correction_move,max_correction_move)
                anticollision = 'freeze'
            if should_profile:
                hc.profile('ptl.request_targets(requests)')
            else:
                ptl.request_targets(requests)
            if should_profile:
                hc.profile('ptl.schedule_send_and_execute_moves(anticollision="'+anticollision+'")')
            else:
                ptl.schedule_send_and_execute_moves(anticollision=anticollision)
    if ptl.schedule_stats:
        ptl.schedule_stats.save()
    if should_export_targets and exportable_targets:
        filename = 'xytest_targets_' + runstamp + '.csv'
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
        ptl.animator.filename_suffix = runstamp
        ptl.generate_animation()