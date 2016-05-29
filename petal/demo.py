import petal
import time
import posconstants as pc

"""Demonstrator script for initializing / moving positioner.
"""

# initialization
pos_ids = ['UM00022']
#pos_ids = ['UM00011','UM00012','UM00013','UM00014','UM00015']
fid_ids = []
petal_id = 3
ptl = petal.Petal(petal_id, pos_ids, fid_ids)
ptl.anticollision_default = False # turn off anticollision algorithm for all scheduled moves

print('INITIAL POSITION')
for pos_id in pos_ids:
    print(ptl.get(pos_id).expected_current_position_str)

# demo script flags
should_flash       = True
should_home        = True
should_direct_dtdp = True
should_move_qs     = True
should_move_dqds   = True
should_move_xy     = False
should_move_dxdy   = False
should_move_tp     = False
should_move_dtdp   = False

# flash the LEDs
if should_flash:
    canids = pc.listify(ptl.get(key='CAN_ID'),True)[0]
    for canid in canids: # this usage of get method returns a list with that value for all the positioners
        ptl.comm.set_led(canid,'on')
    time.sleep(1)
    for canid in canids:
        ptl.comm.set_led(canid,'off')

# run the various move types
if should_home:
    print('MOVE: homing')
    # ptl.set(key='CREEP_TO_LIMITS',value=True) # to force only creeping to hard stops
    ptl.request_homing(pos_ids)
    ptl.schedule_send_and_execute_moves()
else:
    ptl.set(key=['POS_T','POS_P'],value=[-180,180]) # faking having just homed

# this is an 'expert' use function, which instructs the theta and phis axes to go some distances with no regard for anticollision or hardstops
if should_direct_dtdp:
    targets = [[270,0], [0,-60], [-180,30]]
    for t in targets:
        print('MOVE: direct dtdp (' + str(t[0]) + ',' + str(t[1]) + ')')
        requests = {}
        for pos_id in pos_ids:
            requests[pos_id] = {'target':t, 'log_note':'demo direct_dtdp point ' + str(targets.index(t))}
        ptl.quick_dtdp(requests)

# the remainder below are for general usage
# first I defined here a little common wrapper function for generating the request argument dictionary that gets sent to petal
def general_move(command,targets):
    for t in targets:
        print('MOVE: ' + command + ' (' + str(t[0]) + ',' + str(t[1]) + ')')
        requests = {}
        for pos_id in pos_ids:
            requests[pos_id] = {'command':command, 'target':t, 'log_note':'demo ' + command + ' point ' + str(targets.index(t))}
        ptl.quick_move(requests)

if should_move_qs:
    general_move('QS',[[0,3],[90,3],[-90,3],[60,6],[0,0]])

if should_move_dqds:
    general_move('dQdS',[[0,3], [90,-3], [-180,6], [90,6]])

if should_move_xy:
    general_move('posXY',[[-4,-4], [-4,0], [-4,4], [0,-4], [0,0], [0,4], [4,-4], [4,0], [4,4]])

if should_move_dxdy:
    general_move('dXdY',[[2.5,0], [2.5,0], [-10,0], [5,-5], [0,5]])

if should_move_tp:
    general_move('posTP',[[-90,90], [0,90], [90,90], [0,180]])

if should_move_dtdp:
    general_move('dTdP',[[180,0], [-90,-90],[180,60],[-90,30]]) # this is different from 'direct' dTdP. here, the dtdp is treated like any other general move, and anticollision calculations are allowed
