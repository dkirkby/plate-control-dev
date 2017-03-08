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

pos_id = 'M00013' #name for plots only
can_id = 101
petal_id = 4
m = motormovemeasure.MotorMoveMeasure(petal_id)
m.n_fiducial_dots = 0
is_assembled = True #Bool - whether just motor or assembed positioner
axis = 'theta' 
condition = 360 #How far to go
stepsize = 10 #degrees each move
num_arcs = 6 #Number of arcs to do, total moves is (condition/stepsize)*num_arcs
m.fvc.scale = 0.0274 # mm/pixel (update um_scale below if not in mm)
m.fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
title = pos_id + '_' + log_timestamp + '_motor_test' #For filenames
direction = 'cw'
direction_prev = 'ccw'

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
meas_angles = []
target_xy = []
err_2D = []
err_angle = []
#Lists for error location plot to know cw and ccw
err_2D_ccw = []
target_angles_ccw = []
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
print('Measuring position with', axis, 'angle', str(total_move_angle), 'degrees.')
m.rehome(can_id, axis)
meas_obsXY = m.measure()#m.move_measure(can_id, direction, axis, 0)
meas_xy.append(meas_obsXY)  
meas_angle = m.obsXY_to_posPolar(meas_obsXY)
meas_angles.append(meas_angle)
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
err_angle.append((meas_angle - total_move_angle))
err_2D.append(np.sqrt(err_x**2 + err_y**2))
print('xy_error:', err_2D[-1], '\n')

#Begin test
for i in range(num_arcs):
    if direction_prev == 'ccw':
        direction = 'cw'
        direction_sign = -1
    else:
        direction = 'ccw'
        direction_sign = 1
    for j in range(0,motor_max_angle,stepsize):
        this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
        total_move_angle += direction_sign*stepsize
        local_angle = total_move_angle
        #if (total_move_angle > motor_max_angle) and is_assembled: #safety net - at least prevents too much hardstop ramming
        #    break
        target_angles.append(local_angle)
        target_xy.append(m.posPolar_to_obsXY(local_angle))
        print('Measuring position at', axis, 'angle', str(total_move_angle), 'degrees.')
        #Camera adjustment, turn around moves IE first move of new arcs after arc 1 need the opposite adjustment
        if (j == 1) and (i != 0):
            move_amount = stepsize + direction_sign*err_angle[-1]
        else:
            move_amount = stepsize - direction_sign*err_angle[-1]
        #Choosing the correct angle
        if abs(move_amount) > 360:
            move_amount = move_amount % 360
        if move_amount < 0:
            move_amount += 360
        #Measure
        meas_obsXY = m.move_measure(can_id, direction, axis, move_amount)
        meas_xy.append(meas_obsXY)  
        meas_angle = m.obsXY_to_posPolar(meas_obsXY)
        #Choosing correct measured angle
        if (abs(meas_angle - meas_angles[-1]) > 350):
            meas_angle = meas_angle - 360
        meas_angles.append(meas_angle)
        err_x = target_xy[-1][0] - meas_obsXY[0]
        err_y = target_xy[-1][1] - meas_obsXY[1]
        # update move data log
        row = this_timestamp
        row += ',' + str(local_angle)
        row += ',' + str(target_xy[-1][0])
        row += ',' + str(target_xy[-1][1])
        row += ',' + str(meas_angle)
        row += ',' + str(meas_obsXY[0])
        row += ',' + str(meas_obsXY[1])
        row += ',' + str((meas_angle - local_angle))
        row += ',' + str(err_x)
        row += ',' + str(err_y)
        row += ',' + str(np.sqrt(err_x**2 + err_y**2))
        row += '\n'
        file = open(move_log_name,'a')
        file.write(row)
        file.close()
        err_angle.append((meas_angle - local_angle))
        err_2D.append(np.sqrt(err_x**2 + err_y**2))
        if direction == 'ccw':
            err_2D_ccw.append(np.sqrt(err_x**2 + err_y**2))
            target_angles_ccw.append(local_angle)
        print('xy_error:', err_2D[-1], '\n')
    direction_prev = direction


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
circle_angles = np.arange(0,365,5)*np.pi/180
circle_x = m.offset_x + m.radius * np.cos(circle_angles)
circle_y = m.offset_y + m.radius * np.sin(circle_angles)
offset_line_angles = np.array([m.angle_offset-np.pi,m.angle_offset])
offset_line_x = m.offset_x + m.radius * np.cos(offset_line_angles)
offset_line_y = m.offset_y + m.radius * np.sin(offset_line_angles)
plt.ylabel('obsY (mm)')
plt.xlabel('obsX (mm)')
plt.plot(target_x, target_y,'ro',label='target points',markersize=4,markeredgecolor='r',markerfacecolor='None')
plt.plot(meas_x, meas_y,'k+',label='measured data',markersize=6,markeredgewidth='1')
#plt.plot(circle_x, circle_y, 'b')
#plt.plot(offset_line_x, offset_line_y, 'r')
plt.grid(True)
plt.axis('equal')
plt.savefig(pc.test_logs_directory + title + '_plot.png',dpi=150)
plt.close(figure)

figure = plt.figure(figsize=(10,8), dpi=150)
plt.hist(err_2D,20)
plt.title(title + '_xy_error')
plt.ylabel('frequency')
plt.xlabel('xy error (mm)')
plt.grid(True)
plt.savefig(pc.test_logs_directory + title + '_hist.png', dpi=150)

figure = plt.figure(figsize=(10, 8), dpi=150)
plt.title(title + '_Error Location')
plt.ylabel('error XY (mm)')
plt.xlabel('Target Angle (degrees)')
plt.plot(target_angles, err_2D, 'bo')
plt.plot(target_angles_ccw, err_2D_ccw, 'ro')
plt.grid(True)
plt.savefig(pc.test_logs_directory + title + '_err_location.png',dpi=150)
plt.close(figure)

summary_txt = 'error max: ' + format(np.max(err_2D)*1000,'6.1f') + ' um\n'
summary_txt += '      rms: ' + format(np.sqrt(np.mean(np.array(err_2D)**2))*1000,'6.1f') + ' um\n'
summary_txt += '      avg: ' + format(np.mean(err_2D)*1000,'6.1f') + ' um\n'
summary_txt += '      min: ' + format(np.min(err_2D)*1000,'6.1f') + ' um\n'
print(summary_txt)