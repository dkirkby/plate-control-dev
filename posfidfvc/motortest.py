'''
motortest.py

Moves motor with ferrule holder attached and measures position with fvc.
Moves repeatedly in one direction. This code should be used for test #6 -
cold phi test and what was formerly test #7 - motor test.

WARNING: when using on on an assembled positioner be careful to first
the positioner is against one hardstop then preform the test for a maximum of
360 degrees. DO NOT drive it against the hardstop.
'''

import motormovemeasure
import matplotlib.pyplot as plt
import datetime
import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
import numpy as np

direction = 'cw'
pos_id = 'M00004' #name for plots only
can_id = 1004
petal_id = 4
m = motormovemeasure.MotorMoveMeasure(petal_id)
m.n_fiducial_dots = 0
is_assembled = True #Bool - whether just motor or assembed positioner
axis = 'phi' 
condition = 180 #How far to go
stepsize = 10 #degrees each move
m.fvc.scale = 0.0274 # mm/pixel (update um_scale below if not in mm)
m.fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
title = pos_id + '_' + log_timestamp + '_motor_test' #For filenames
direction = 'cw'

if direction == 'cw':
    direction_sign = -1
else:
    direction_sign = 1

motor_max_angle = 360
if axis == 'phi':
    motor_max_angle = 180

# write headers for move data log files
move_log_name = pc.test_logs_directory + title + '_move_data.csv'
move_log_header = 'timestamp,target_angle,target_x,target_y,meas_angle,meas_x,meas_y,err_angle,err_x,err_y,err_2D'
move_log_header += '\n'
file = open(move_log_name,'w')
file.write(move_log_header)
file.close()

#Initialize test and calibration
total_move_angle = 0
meas_xy = []
target_angles = [0]
target_xy = []
err_2D = []
err_angle = []
data = m.calibrate(can_id, axis, mode = 'full')

#WRITE SUMMARY
summary_name = pc.test_logs_directory + title + '_summary.csv'
file = open(summary_name,'w')
summary = 'radius,' + str(data['radius']) + '\naxis,' + str(axis)
summary += '\noffset_angle,' + str(np.rad2deg(data['angle_offset']))
summary += '\noffset_x,' + str(data['offset_x']) + '\noffset_y,' + str(data['offset_y']) + '\n'
file.write(summary)
file.close()

#Take data (first point is rehome)
this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
target_xy.append(m.posPolar_to_obsXY(total_move_angle))
print('Measuring position at', axis, ' angle', str(total_move_angle), 'degrees.')
m.rehome(can_id, axis)
meas_obsXY = m.move_measure(can_id, direction, axis, 0)
meas_xy.append(meas_obsXY)  
meas_angle = m.obsXY_to_posPolar(meas_obsXY)
err_x = target_xy[-1][0] - meas_obsXY[0]
err_y = target_xy[-1][1] - meas_obsXY[1]
# update move data log
row = this_timestamp
row += ',' + str(total_move_angle)
row += ',' + str(target_xy[-1][0])
row += ',' + str(target_xy[-1][1])
row += ',' + str(meas_angle)
row += ',' + str(meas_obsXY[0])
row += ',' + str(meas_obsXY[1])
row += ',' + str((total_move_angle - meas_angle))
row += ',' + str(err_x)
row += ',' + str(err_y)
row += ',' + str(np.sqrt(err_x**2 + err_y**2))
row += '\n'
file = open(move_log_name,'a')
file.write(row)
file.close()
err_angle.append((total_move_angle - meas_angle))
err_2D.append(np.sqrt(err_x**2 + err_y**2))
 
while total_move_angle < condition:
    this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
    total_move_angle += stepsize
    if (total_move_angle >= motor_max_angle) and is_assembled: #safety net - at least prevents too much hardstop ramming
        break
    target_angles.append(total_move_angle)
    target_xy.append(m.posPolar_to_obsXY(direction_sign*total_move_angle))
    print('Measuring position at', axis, ' angle', str(total_move_angle), 'degrees.')
    meas_obsXY = m.move_measure(can_id, direction, axis, stepsize)
    meas_xy.append(meas_obsXY)  
    meas_angle = m.obsXY_to_posPolar(meas_obsXY)
    err_x = target_xy[-1][0] - meas_obsXY[0]
    err_y = target_xy[-1][1] - meas_obsXY[1]
    # update move data log
    row = this_timestamp
    row += ',' + str(direction_sign*total_move_angle)
    row += ',' + str(target_xy[-1][0])
    row += ',' + str(target_xy[-1][1])
    row += ',' + str(meas_angle)
    row += ',' + str(meas_obsXY[0])
    row += ',' + str(meas_obsXY[1])
    row += ',' + str((direction_sign*total_move_angle - meas_angle))
    row += ',' + str(err_x)
    row += ',' + str(err_y)
    row += ',' + str(np.sqrt(err_x**2 + err_y**2))
    row += '\n'
    file = open(move_log_name,'a')
    file.write(row)
    file.close()
    err_angle.append((total_move_angle - meas_angle))
    err_2D.append(np.sqrt(err_x**2 + err_y**2))


#Extract data
target_x = []; target_y = []; meas_x = []; meas_y = []
for i in range(len(target_angles)):
    target_x.append(target_xy[i][0])
    target_y.append(target_xy[i][1])
    meas_x.append(meas_xy[i][0])
    meas_y.append(meas_xy[i][1])

#Complete summary
file = open(summary_name,'a')
summary = 'min_err2D_(um),' + str(np.min(err_2D)*1000) + '\n'
summary += 'max_err2D_(um),' + str(np.max(err_2D)*1000) + '\n'
summary += 'mean_err2D_(um),' + str(np.mean(err_2D)*1000) + '\n'
summary += 'rms_err2D_(um),' + str(np.sqrt(np.mean(np.array(err_2D)**2))*1000) + '\n'
summary += 'min_err_angle,' + str(np.min(err_angle)) + '\n'
summary += 'max_err_angle,' + str(np.max(err_angle)) + '\n'
summary += 'mean_err_angle,' + str(np.mean(err_angle)) + '\n'
summary += 'rms_err_angle,' + str(np.sqrt(np.mean(np.array(err_angle)**2))) + '\n'
file.write(summary)
file.close()
           
#Plot Positions
figure = plt.figure(figsize=(10, 8), dpi=150)
plt.title(title + '_plot')
plt.ylabel('obsY (mm)')
plt.xlabel('obsX (mm)')
plt.plot(target_x, target_y,'ro',label='target points',markersize=4,markeredgecolor='r',markerfacecolor='None')
plt.plot(meas_x, meas_y,'k+',label='measured data',markersize=6,markeredgewidth='1')
plt.grid(True)
plt.axis('equal')
plt.savefig(pc.test_logs_directory + title + '_plot.png',dpi=150)
plt.close(figure)
    
