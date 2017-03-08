import petal
import time
import posconstants as pc
import sys

"""Demonstrator script for initializing / moving positioner.
"""

# initialization
pos_ids = ['UM00022']
#pos_ids = ['UM00011','UM00012','UM00013','UM00014','UM00015']
fid_ids = []
petal_id = 3
ptl = petal.Petal(petal_id, pos_ids, fid_ids)
ptl.anticollision_default = False # turn off anticollision algorithm for all scheduled moves

n = len(pos_ids)

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
    dtdp = [[270,0], [0,-60], [-180,30]]
    for i in range(len(dtdp)):
        values = dtdp[i]
        print('MOVE: direct dtdp (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_dtdp(pos_ids, [values]*n)

# the remainder below are for general usage
if should_move_qs:
    QS = [[0,3],[90,3],[-90,3],[60,6],[0,0]]
    command = 'QS'
    for i in range(len(QS)):
        values = QS[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, [command]*n, [values]*n)

if should_move_dqds:
    dQdS = [[0,3], [90,-3], [-180,6], [90,6]]
    command = 'dQdS'
    for i in range(len(dQdS)):
        values = dQdS[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, [command]*n, [values]*n)

if should_move_xy:
    #xy = [[2.5,0], [0,2.5], [-5,0], [0,-5], [-5.99,0], [6,0], [0,8], [0,0]]
    xy = [[-4,-4], [-4,0], [-4,4], [0,-4], [0,0], [0,4], [4,-4], [4,0], [4,4]]
    command = 'posXY'
    for i in range(len(xy)):
        values = xy[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, [command]*n, [values]*n)

if should_move_dxdy:
    dxdy = [[2.5,0], [2.5,0], [-10,0], [5,-5], [0,5]]
    command = 'dXdY'
    for i in range(len(dxdy)):
        values = dxdy[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, [command]*n, [values]*n)

if should_move_tp:
    tp = [[-90,90], [0,90], [90,90], [0,180]]
    command = 'posTP'
    for i in range(len(tp)):
        values = tp[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, [command]*n, [values]*n)

if should_move_dtdp:
    dtdp = [[180,0], [-90,-90],[180,60],[-90,30]]
    command = 'dTdP'
    for i in range(len(dtdp)):
        values = dtdp[i]
        print('MOVE: ' + command + ' (' + str(values[0]) + ',' + str(values[1]) + ')')
        ptl.quick_move(pos_ids, command, values)
