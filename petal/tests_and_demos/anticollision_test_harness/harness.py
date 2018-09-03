"""Script to run the anticollision test harness.
"""

import os
import sys
sys.path.append(os.path.abspath('../../../petal/'))
import petal
import harness_constants as hc
import sequences
import posstate

# Selection of device location ids (which positioners on petal).
locations_all = 'all'
locations_near_gfa = {309,328,348,368,389,410,432,454,474,492,508,521,329,349,369,390,411,433,455,475,493,509,522,532,330,350,370,391,412,434,456,476,494,510,523,533,351,371,392,413,435,457,477,495,511,524,372,393,414,436,458,512,525,415,437,459,526}
device_loc_ids = locations_near_gfa # make the selection here

# Selection of which pre-cooked sequences to run. See "sequences.py" for more detail.
pos_param_sequence_id = 0
move_request_sequence_id = 0

# Other ids
fidids = {}
petal_id = 666

# Other options
should_animate = True

# Run the sequences.
pos_param_sequence = sequences.get_positioner_param_sequence(pos_param_sequence_id, device_loc_ids)
move_request_sequence = sequences.get_move_request_sequence(move_request_sequence_id, device_loc_ids)
for pos_params in pos_param_sequence:
    for posid,params in pos_params.items():
        state = posstate.PosState(posid)
        state.store('POS_T',0.0)
        state.store('POS_P',180.0)
        for key,val in params.items():
            state.store(key,val)
        state.write()
    ptl = petal.Petal(petal_id, pos_params, fidids,
                      simulator_on    = True,
                      db_commit_on    = False,
                      local_commit_on = False,
                      local_log_on    = False,
                      collider_file   = None,
                      sched_stats_on  = True,
                      anticollision   = 'adjust',
                      petal_shape     = 'asphere')
    if should_animate:
        ptl.start_gathering_frames()
    for move_request_data in move_request_sequence:
        requests = {ptl.devices[loc_id]:{'command':data['command'], 'target':[data['u'],data['v']]} for loc_id,data in move_request_data.items()}
        hc.profile('ptl.request_targets(requests)')
        hc.profile('ptl.schedule_send_and_execute_moves()')
    if ptl.schedule_stats:
        ptl.schedule_stats.save()
    if should_animate:
        ptl.stop_gathering_frames()
        hc.profile('ptl.generate_animation()')