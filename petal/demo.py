import posarraymaster
import legacypositionercomm
import numpy as np

"""Demonstrator script for initializing / moving positioner.
"""

# initialization
posids = ['6M01']
n = len(posids)
m = posarraymaster.PosArrayMaster(posids)

# initialization of communications
# these commands are very specific to the hacked-together LegacyPositionerComm
comm = legacypositionercomm.LegacyPositionerComm('COM7')
comm.send_cmd_off = True # used to speed up software debugging / not actually send commands out over hardware
comm.master = m
m.comm = comm

print(m.get('6M01').expected_current_position_str)

# demo script flags
should_home        = False
should_direct_dtdp = False
should_move_qs     = False
should_move_dqds   = False
should_move_xy     = False
should_move_dxdy   = False
should_move_tp     = False
should_move_dtdp   = True

# run the various move types
if should_home:
    m.request_homing(posids)
    m.schedule_send_and_execute_moves()
else:
    m.set(key=['SHAFT_T','SHAFT_P'],value=[0,180]) # faking having just homed

# this is an 'expert' use function, which instructs the theta and phis axes to go some distances with no regard for anticollision or hardstops
if should_direct_dtdp:
    dt = [ 90, -180, 90]
    dp = [-60,    0, 60]
    for i in range(len(dt)):
        m.request_direct_dtdp(posids, dt[i], dp[i])
    m.schedule_send_and_execute_moves

# the remainder below are for general usage
if should_move_qs:
    Q = [0, 90, -90, 0]
    S = [3,  3,   3, 0]
    for i in range(len(Q)):
        m.request_targets(posids, ['qs']*n, [Q[i]]*n, [S[i]]*n)
    m.schedule_send_and_execute_moves()

if should_move_dqds:
    dq = [ 0,  90, -180, 90]
    ds = [ 3,  -3,    6,  6]
    for i in range(len(dq)):
        m.request_targets(posids, ['dqds']*n, [dq[i]]*n, [ds[i]]*n)
    m.schedule_send_and_execute_moves()

if should_move_xy:
    x = [3, 0, -5,  0, -5.99, 6, 0, 0]
    y = [0, 3,  0, -5,     0, 0, 8, 0]
    for i in range(len(x)):
        m.request_targets(posids, ['xy']*n, [x[i]]*n, [y[i]]*n)
    m.schedule_send_and_execute_moves()

if should_move_dxdy:
    dx = [ 2.5,  2.5, -10,  5, 0]
    dy = [   0,    0,   0, -5, 5]
    for i in range(len(dx)):
        m.request_targets(posids, ['dxdy']*n, [dx[i]]*n, [dy[i]]*n)
    m.schedule_send_and_execute_moves()

if should_move_tp:
    t = [-90,  0, 90,   0]
    p = [ 90, 90, 90, 180]
    for i in range(len(t)):
        m.request_targets(posids, ['tp']*n, [t[i]]*n, [p[i]]*n)
    m.schedule_send_and_execute_moves()

if should_move_dtdp:
    dt = [-30, 30,   0,  0, -30, 30]
    dp = [  0,  0, -30, 30, -30, 30]
    for i in range(len(x)):
        m.request_targets(posids, ['dtdp']*n, [dt[i]]*n, [dp[i]]*n)
    m.schedule_send_and_execute_moves()
