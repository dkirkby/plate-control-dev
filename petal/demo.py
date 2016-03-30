import posarraymaster
import time
import posconstants as pc

"""Demonstrator script for initializing / moving positioner.
"""

# initialization
posids = ['UM00012']#,'UM00013']
petal_id=1
#
n = len(posids)
m = posarraymaster.PosArrayMaster(posids,petal_id)
m.anticollision_default = False # turn off anticollision algorithm for all scheduled moves

print('INITIAL POSITION')
for posid in posids:
    print(m.get(posid).expected_current_position_str)

# demo script flags
should_flash       = True
should_home        = True
should_direct_dtdp = True
should_move_qs     = False
should_move_dqds   = False
should_move_xy     = False
should_move_dxdy   = False
should_move_tp     = False
should_move_dtdp   = False

# flash the LEDs
if should_flash:
    for canid in pc.listify(m.get(key='CAN_ID')): # this usage of get method returns a list with that value for all the positioners
        m.comm.set_led(canid,'on')
    time.sleep(1)
    for canid in pc.listify(m.get(key='CAN_ID')):
        m.comm.set_led(canid,'off')

# run the various move types
if should_home:
    print('\nMOVE: homing')
    # m.set(key='CREEP_TO_LIMITS',value=True) # to force only creeping to hard stops
    m.request_homing(posids)
    m.schedule_send_and_execute_moves()
else:
    m.set(key=['POS_T','POS_P'],value=[-180,180]) # faking having just homed

# this is an 'expert' use function, which instructs the theta and phis axes to go some distances with no regard for anticollision or hardstops
if should_direct_dtdp:
    dt = [90]#[ 270,   0, -180]
    dp = [0]#[   0, -60,   30]
    for i in range(len(dt)):
        val1 = dt[i]
        val2 = dp[i]
        print('\nMOVE: direct dtdp (' + str(val1) + ',' + str(val2) + ')')
        m.request_direct_dtdp(posids, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

# the remainder below are for general usage
if should_move_qs:
    Q = [0, 90, -90, 0]
    S = [3,  3,   3, 0]
    command = 'QS'
    for i in range(len(Q)):
        val1 = Q[i]
        val2 = S[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

if should_move_dqds:
    dq = [ 0,  90, -180, 90]
    ds = [ 3,  -3,    6,  6]
    command = 'dQdS'
    for i in range(len(dq)):
        val1 = dq[i]
        val2 = ds[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

if should_move_xy:
    x = [2.5,   0, -5,  0, -5.99, 6, 0, 0]
    y = [  0, 2.5,  0, -5,     0, 0, 8, 0]
    command = 'posXY'
    for i in range(len(x)):
        val1 = x[i]
        val2 = y[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

if should_move_dxdy:
    dx = [ 2.5,  2.5, -10,  5, 0]
    dy = [   0,    0,   0, -5, 5]
    command = 'dXdY'
    for i in range(len(dx)):
        val1 = dx[i]
        val2 = dy[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

if should_move_tp:
    t = [-90,  0, 90,   0]
    p = [ 90, 90, 90, 180]
    command = 'posTP'
    for i in range(len(t)):
        val1 = t[i]
        val2 = p[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()

if should_move_dtdp:
    dt = [ 210, -30,   0,  0, -30, -150]
    dp = [   0,   0, -30, 30, -30, 30]
    command = 'dTdP'
    for i in range(len(dt)):
        val1 = dt[i]
        val2 = dp[i]
        print('\nMOVE: ' + command + ' (' + str(val1) + ',' + str(val2) + ')')
        m.request_targets(posids, [command]*n, [val1]*n, [val2]*n)
        m.schedule_send_and_execute_moves()
