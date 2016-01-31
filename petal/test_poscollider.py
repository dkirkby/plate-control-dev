import poscollider
import posmodel
import posstate
import numpy as np
import configobj
import posconstants as pc

# generate an array of positioners
nx = 5
ny = 5
pitch = 10.4
xy0 = [[],[]]
tp0 = [[],[]]
for j in range(ny):
    if j == 0:
        y = -pitch*(ny-1)/2*np.sin(np.deg2rad(60))
    else:
        y += pitch*np.sin(np.deg2rad(60))
    for i in range(nx):
        if i == 0:
            x = -pitch*(nx-1)/2 + (j % 2) * pitch*np.cos(np.deg2rad(60))
        else:
            x += pitch
        xy0[0].append(x)
        xy0[1].append(y)
        tp0[0].append(0)
        tp0[1].append(0)
npos = len(xy0[0])
posmodels = []
for i in range(npos):
    state = posstate.PosState(unit_id='temp'+str(i).zfill(4), logging=False)
    state.write('OFFSET_X',xy0[0][i],write_to_disk=False)
    state.write('OFFSET_Y',xy0[1][i],write_to_disk=False)
    state.write('OFFSET_T',tp0[0][i],write_to_disk=False)
    state.write('OFFSET_P',tp0[1][i],write_to_disk=False)
    posmodels.append(posmodel.PosModel(state))
config = configobj.ConfigObj(pc.settings_directory + '_collision_settings_DEFAULT.conf',unrepr=True)
config.initial_comment = ['Temporary settings file for software test purposes, not associated with a real focal plate arrangement.','']
filename = 'collision_settings_test.conf'
config.filename = pc.settings_directory + filename
minX = min(xy0[0])-pitch/2
maxX = max(xy0[0])+pitch/2
minY = min(xy0[1])-pitch/2
maxY = max(xy0[1])+pitch/2
config['KEEPOUT_PTL'] = [[minX,maxX,maxX,minX],[minY,minY,maxY,maxY]]
config['KEEPOUT_GFA_X0'] = maxX + 40
config['KEEPOUT_GFA_Y0'] = maxY + 40
config['KEEPOUT_GFA_ROT'] = 0
config.write()

# set up a collider and put in some synthetic move tables
collider = poscollider.PosCollider(filename)
collider.add_positioners(posmodels)
tables =  [[] for i in range(len(collider.posmodels))]
for i in range(len(collider.posmodels)):
    dT = [180, -360, 270, -90,   0,   0,  0,    0]
    dP = [  0,    0,   0,   0, 180, -90, 45, -135]
    nrows = len(dT)
    Tdot = [180 for i in range(nrows)]
    Pdot = [180 for i in range(nrows)]
    prepause = [0 for i in range(nrows)]
    postpause = [0 for i in range(nrows)]
    prepause[1] = 0.5
    postpause[1] = 0.5
    move_time = [max(dT[i]/Tdot[i],dP[i]/Pdot[i]) for i in range(nrows)]
    tables[i] = {'nrows':nrows, 'dT':dT, 'dP':dP, 'Tdot':Tdot, 'Pdot':Pdot, 'prepause':prepause, 'move_time':move_time, 'postpause':postpause}

# calculate the move sweeps, checking for collisions
sweeps = [[] for i in range(len(collider.posmodels))]
earliest_collision = [np.inf for i in range(len(collider.posmodels))]
for k in range(len(collider.collidable_relations['A'])):
    A = collider.collidable_relations['A'][k]
    B = collider.collidable_relations['B'][k]
    B_is_fixed = collider.collidable_relations['B_is_fixed'][k]
    if B_is_fixed and A in range(len(tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
        these_sweeps = collider.spactime_collision_with_fixed(A, collider.tp0[:,A], tables[A])
    elif A in range(len(tables)) and B in range(len(tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
        these_sweeps = collider.spactime_collision_between_positioners(A, collider.tp0[:,A], tables[A], B, collider.tp0[:,B], tables[B])
    for i in range(len(these_sweeps)):
        AorB = A if i == 0 else B
        if these_sweeps[i].collision_time <= earliest_collision[AorB]:
            sweeps[AorB] = these_sweeps[i]
            earliest_collision[AorB] = these_sweeps[i].collision_time

# animate
collider.animate(sweeps)