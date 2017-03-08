import posarraymaster
import legacypositionercomm

"""Demonstrator script for initializing / moving positioner.
"""

# Initialization
posids = ['6M01']
configs = ['DEFAULT']
m = posarraymaster.PosArrayMaster(posids,configs)

# Initialization of communications
# These commands are very specific to the hacked-together LegacyPositionerComm.
comm = legacypositionercomm.LegacyPositionerComm('COM5')
comm.master = m
m.comm = comm

# Demo script flags
should_home = False
should_move_QS_grid = False
should_move_abs_tp = False
should_move_rel_dtdp = True

# Moves
if should_home:
    m.expert_request_schedule_execute_moves(posids, ['homing']*len(posids), 0, 0)

if should_move_QS_grid:
    posX = [3,  0, -3,  0] # target x in positioner local coordinates
    posY = [0,  3,  0, -3] # target y in positioner local coordinates
    Qtargs = []
    Stargs = []
    for i in range(len(posids)):
        trans = m.get(posids[i]).trans # coordinate transformer for the positioner
        obsXY_targs = trans.posXY_to_obsXY([posX,posY]) # in observer global XY coordinate system
        QStargs = trans.obsXY_to_QS(obsXY_targs) # in QS global coordinate system
        Qtargs.append(QStargs[0])
        Stargs.append(QStargs[1])
        m.request_schedule_execute_moves([posids[i]]*len(Qtargs), Qtargs, Stargs)

if should_move_abs_tp:
    T = [-90,  0, 90,   0]
    P = [ 90, 90, 90, 180]
    for i in range(len(posids)):
        m.expert_request_moves([posids[i]]*len(T), ['tp']*len(T), T, P)
    m.schedule_moves()
    m.send_tables_and_execute_moves()

if should_move_rel_dtdp:
    dT = [-30, 30,   0,  0, -30, 30]
    dP = [  0,  0, -30, 30, -30, 30]
    for i in range(len(posids)):
        m.expert_request_moves([posids[i]]*len(dT), ['dtdp']*len(dT), dT, dP)
    m.schedule_moves()
    m.send_tables_and_execute_moves()
