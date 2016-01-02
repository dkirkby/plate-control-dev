import posarraymaster
import legacypositionercomm
import numpy as np

"""Demonstrator script for initializing / moving positioner.
"""

# Initialization
posids = ['6M01']
m = posarraymaster.PosArrayMaster(posids)

# Initialization of communications
# These commands are very specific to the hacked-together LegacyPositionerComm.
comm = legacypositionercomm.LegacyPositionerComm('COM6')
comm.master = m
m.comm = comm

# Demo script flags
should_home      = False
should_move_qs   = False
should_move_dqds = False
should_move_xy   = False
should_move_dxdy = True
should_move_tp   = False
should_move_dtdp = False

# Moves
if should_home:
    m.expert_request_schedule_execute_moves(posids, ['homing']*len(posids), 0, 0)

# command formats below are for standard operation
if should_move_qs:
    # starting with targets in (x,y) space, just to illustrate some transformatons, too
    posX = [3,  0, -3,  0] # target x in positioner local coordinates
    posY = [0,  3,  0, -3] # target y in positioner local coordinates
    Qtargs = []
    Stargs = []
    for posid in posids:
        trans = m.get(posid).trans # coordinate transformer for the positioner
        obsXY_targs = trans.posXY_to_obsXY([posX,posY]) # in observer global XY coordinate system
        QStargs = trans.obsXY_to_QS(obsXY_targs) # in QS global coordinate system
        Qtargs.append(QStargs[0])
        Stargs.append(QStargs[1])
        m.request_schedule_execute_moves([posid]*len(Qtargs), Qtargs, Stargs) # immediate execution on this positioner

if should_move_dqds:
    dq = [ 0,  90, -180, 90]
    ds = [ 3,  -3,    6,  6]
    for posid in posids:
        Qstart = m.expected_current_position(posid,'Q')
        Sstart = m.expected_current_position(posid,'S')
        Qtargs = (Qstart + np.cumsum(dq)).tolist()
        Stargs = (Sstart + np.cumsum(ds)).tolist()
        m.request_moves([posid]*(len(Qtargs)), Qtargs, Stargs) # delay execution until all positioners have been loaded with targets
    self.schedule_moves() # could have an optional anticollision on/off flag as an argument
    self.send_tables_and_execute_moves()

# command formats below are for 'expert' user
if should_move_xy:
    x = [3, 0, -6,  0, 0]
    y = [0, 3,  0, -6, 0]
    for posid in posids:
        m.expert_request_schedule_execute_moves([posid]*len(x), ['xy']*len(x), x, y)

if should_move_dxdy:
    dx = [ 3,  3, -12,  6, 0]
    dy = [ 0,  0,   0, -6, 6]
    for posid in posids:
        m.expert_request_moves([posid]*len(dx), ['dxdy']*len(dx), dx, dy)
    m.schedule_moves()
    m.send_tables_and_execute_moves()

if should_move_tp:
    T = [-90,  0, 90,   0]
    P = [ 90, 90, 90, 180]
    for posid in posids:
        m.expert_request_moves([posid]*len(T), ['tp']*len(T), T, P)
    m.schedule_moves()
    m.send_tables_and_execute_moves()

if should_move_dtdp:
    dT = [-30, 30,   0,  0, -30, 30]
    dP = [  0,  0, -30, 30, -30, 30]
    for posid in posids:
        m.expert_request_moves([posid]*len(dT), ['dtdp']*len(dT), dT, dP)
    m.schedule_moves()
    m.send_tables_and_execute_moves()
