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
config['KEEPOUT_GFA_X0'] = maxX + 100
config['KEEPOUT_GFA_Y0'] = maxY + 100
config['KEEPOUT_GFA_ROT'] = 0
config.write()
collider = poscollider.PosCollider(filename)
collider.add_positioners(posmodels)