import petal
import time
import numpy as np

"""Script for moving positioner in a fashion characteristic of actual operation.
Intent is to have a repeatable set of actions for measuring the max, idle, and average
power consumption values.
"""

# initialization
pos_ids = ['UM00013','UM00014','UM00017','UM00022']
fid_ids = []
petal_id = 0
ptl = petal.Petal(petal_id, pos_ids, fid_ids)
ptl.anticollision_default = False # turn off anticollision algorithm for all scheduled moves

# test settings
should_home = True
n_targets = 10
n_corrections = 2
fvc_pause = 5 # seconds to emulate waiting for an FVC image to be taken and processed

# generate target points set
grid_max_radius = 6.0 # mm
grid_min_radius = 0.0 # mm
r = np.random.uniform(-grid_max_radius,grid_max_radius,n_targets)
t = np.random.uniform(-180,180,n_targets)
x = r*np.cos(np.deg2rad(t))
y = r*np.sin(np.deg2rad(t))
targets = [[x[i],y[i]] for i in range(len(x))]

# generate simulated error values for correction moves
corrections = []
for move in range(len(targets)):
    corrections.append([])
    for submove in range(n_corrections):
        if submove == 0:
            max_corr = 0.100
        else:
            max_corr = 0.025
        dxdy = np.random.uniform(-max_corr,max_corr,2)
        corrections[move].append(dxdy.tolist())
        
# define in-between targets location (simulates anticollision extra moves)
between_TP = [0,90]

# homing of positioner, if necessary
if should_home:
    print('Homing...')
    ptl.request_homing(pos_ids)
    ptl.schedule_send_and_execute_moves()
    print('Homing complete.')

input('Press enter to begin move sequence...')
for move in range(len(targets)):
    target = targets[move]
    print('Simulated target ' + str(move + 1) + ' of ' + str(len(targets)) + ': moving to (x,y) = (' + str(target[0]) + ',' + str(target[1]) + ')')
    
    log_note = 'anticollision sim in-between move'
    requests = {}
    for pos_id in pos_ids: 
        requests[pos_id] = {'command':'posTP', 'target':between_TP, 'log_note':log_note}
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()    
    
    log_note = 'powertest target ' + str(move + 1)
    requests = {}
    for pos_id in pos_ids: 
        requests[pos_id] = {'command':'posXY', 'target':target, 'log_note':log_note}
    ptl.request_targets(requests)
    ptl.schedule_send_and_execute_moves()
    time.sleep(fvc_pause)

    correction = corrections[move]
    for corr in range(len(correction)):
        dxdy = correction[corr]
        print('  ... simulated correction move ' + str(corr + 1) + ' of ' + str(range(len(correction))) + ': moving by (dx,dy) = (' + str(dxdy[0]) + ',' + str(dxdy[1]) + ')')
        log_note = 'powertest target ' + str(move + 1) + ' corr ' + str(corr + 1)
        requests = {}
        for pos_id in pos_ids: 
            requests[pos_id] = {'command':'dXdY', 'target':dxdy, 'log_note':log_note}
        ptl.request_targets(requests)
        ptl.schedule_send_and_execute_moves()
        time.sleep(fvc_pause)
        