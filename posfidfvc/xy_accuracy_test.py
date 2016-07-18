import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posmovemeasure
import posconstants as pc
import datetime
import numpy as np
import time
import pos_xytest_plot

# simulation mode
simulate = False

# start timer on the whole script
script_start_time = time.time()

# initialization
if simulate:
    fvc = fvchandler.FVCHandler('simulator')
else:
    fvc = fvchandler.FVCHandler('FLI')
fvc.scale = 0.0061 # mm/pixel (update um_scale below if not in mm)
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
pos_ids = ['UM00013','UM00014','UM00017','UM00022']
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.simulator_on = simulate
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.n_points_full_calib_T = 4#11#17
m.n_points_full_calib_P = 4#7#9
m.n_fiducial_dots = 3 # number of fiducial centroids the FVC should expect
num_corr_max = 3 # number of correction moves to do for each target

# test operations to do
should_initial_rehome     = True
should_identify_fiducials = True
should_identify_pos_loc   = False
should_calibrate_quick    = False
should_measure_ranges     = False
should_calibrate_grid     = True
should_calibrate_full     = False
should_do_accuracy_test   = True

# certain operations require particular preceding operations
if should_identify_pos_loc: should_initial_rehome = True
if should_measure_ranges: should_calibrate_quick = True

# log file setup
log_directory = pc.test_logs_directory
os.makedirs(log_directory, exist_ok=True)
log_suffix = '' # string gets appended to filenames -- useful for user to identify particular tests
log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
def log_timestamp_with_notes():
    return (log_timestamp + '_SIMULATED') if simulate else log_timestamp
def path_prefix(pos_id):
    return log_directory + os.path.sep + pos_id + '_' + log_timestamp_with_notes() + log_suffix
def move_log_name(pos_id):
    return path_prefix(pos_id) + '_movedata.csv'
def summary_log_name(pos_id):
    return path_prefix(pos_id) + '_summary.csv'
def summary_plot_name(pos_id):
    return path_prefix(pos_id) + '_xyplot'

# cycles configuration (for life testing)
# STILL TO BE IMPLEMENTED

# test grid configuration (local to any positioner, centered on it)
# this will get copied and transformed to each particular positioner's location below
grid_max_radius = 5.8 # mm
grid_min_radius = 0.2 # mm
n_pts_across = 7 # 7 --> 28 pts, 27 --> 528 pts
line = np.linspace(-grid_max_radius,grid_max_radius,n_pts_across)
local_targets = [[x,y] for x in line for y in line]
for i in range(len(local_targets)-1,-1,-1): # traverse list from end backward
    r = (local_targets[i][0]**2 + local_targets[i][1]**2)**0.5
    if r < grid_min_radius or r > grid_max_radius: local_targets.pop(i)

# initial homing
if should_initial_rehome:
    m.rehome(pos_ids='all')

# identify fiducials
if should_identify_fiducials:
    m.identify_fiducials()
    
# identification of which positioners are in which (x,y) locations on the petal
if should_identify_pos_loc:
    m.identify_positioner_locations()

# quick pre-calibration, especially because we need some reasonable values for theta offsets prior to measuring physical travel ranges (where phi arms get extended)
if should_calibrate_quick:
    m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes())

# measure the physical travel ranges of the theta and phi axes by ramming hard limits in both directions
if should_measure_ranges:
    m.measure_range(pos_ids='all', axis='theta')
    m.measure_range(pos_ids='all', axis='phi')
    m.rehome(pos_ids='all')
    if not(should_calibrate_full):
        mode = 'grid' if should_calibrate_grid else should_calibrate_quick
        m.calibrate(pos_ids='all', mode=mode, save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes()) # needed after having struck hard limits

if should_calibrate_grid:
    m.calibrate(pos_ids='all', mode='grid', save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes())

# full calibration
if should_calibrate_full:
    m.calibrate(pos_ids='all', mode='full', save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes())

# do the xy accuracy test
if should_do_accuracy_test:
    submove_idxs = [i for i in range(num_corr_max+1)]

    # write headers for move data log files
    move_log_header = 'timestamp,cycle,target_x,target_y'
    submove_fields = ['meas_obsXY','errXY','err2D','posTP']
    for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
    for i in submove_idxs: move_log_header += ',err_x'  + str(i) + ',err_y' + str(i)
    for i in submove_idxs: move_log_header += ',err_xy' + str(i)
    for i in submove_idxs: move_log_header += ',pos_t'  + str(i) + ',pos_p' + str(i)
    move_log_header += '\n'
    for pos_id in pos_ids:
        file = open(move_log_name(pos_id),'w')
        file.write(move_log_header)
        file.close()

    # transform test grid to each positioner's global position, and create all the move request dictionaries
    all_targets = []
    for local_target in local_targets:
        these_targets = {}
        for pos_id in pos_ids:
            posmodel = ptl.get(pos_id)
            these_targets[pos_id] = {'command':'obsXY', 'target':posmodel.trans.posXY_to_obsXY(local_target)}
        all_targets.append(these_targets)

    # initialize some data structures for storing test data
    targ_num = 0
    all_data_by_target = []
    all_data_by_pos_id = {}
    for pos_id in pos_ids:
        all_data_by_pos_id[pos_id] = {'targ_obsXY': []}
        for key in submove_fields:
            all_data_by_pos_id[pos_id][key] = [[] for i in submove_idxs]
    start_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
    start_cycles = ptl.get(pos_ids,'TOTAL_MOVE_SEQUENCES')
    
    # run the test
    for these_targets in all_targets:
        targ_num += 1
        print('\nMEASURING TARGET ' + str(targ_num) + ' OF ' + str(len(all_targets)))
        print('Local target (posX,posY)=(' + format(local_targets[targ_num-1][0],'.3f') + ',' + format(local_targets[targ_num-1][1],'.3f') + ') for each positioner.')
        this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
        these_meas_data = m.move_and_correct(these_targets, num_corr_max=num_corr_max)
        
        # store this set of measured data
        all_data_by_target.append(these_meas_data)
        for pos_id in these_targets.keys():
            all_data_by_pos_id[pos_id]['targ_obsXY'].append(these_meas_data[pos_id]['targ_obsXY'])
            for sub in submove_idxs:
                for key in submove_fields:
                    all_data_by_pos_id[pos_id][key][sub].append(these_meas_data[pos_id][key][sub])              
        
        # update summary data log
        for pos_id in pos_ids:
            summary_log_data =  'pos_id,' + str(pos_id) + '\n'
            summary_log_data += 'log_suffix,' + str(log_suffix) + '\n'
            summary_log_data += 'cycles at start,' + str(start_cycles[pos_ids.index(pos_id)]) + '\n'
            summary_log_data += 'cycles at finish,' + str(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES')) + '\n'
            summary_log_data += 'start time,' + start_timestamp + '\n'
            summary_log_data += 'finish time,' + this_timestamp + '\n'
            summary_log_data += 'num targets,' + str(len(all_targets)) + '\n'
            summary_log_data += 'num corrections max,' + str(num_corr_max) + '\n'
            summary_log_data += 'submove index -->'
            for i in submove_idxs: summary_log_data += ',' + str(i)
            summary_log_data += '\n'
            for calc in ['max','min','mean','rms']:
                summary_log_data += calc + '(um)'
                for i in submove_idxs:
                    this_submove_data = all_data_by_pos_id[pos_id]['err2D'][i]
                    if calc == 'max':    summary_log_data += ',' + str(np.max(this_submove_data) * um_scale)
                    elif calc == 'min':  summary_log_data += ',' + str(np.min(this_submove_data) * um_scale)
                    elif calc == 'mean': summary_log_data += ',' + str(np.mean(this_submove_data) * um_scale)
                    elif calc == 'rms':  summary_log_data += ',' + str(np.sqrt(np.mean(np.array(this_submove_data)**2)) * um_scale)
                    else: pass
                    if i == submove_idxs[-1]: summary_log_data += '\n'
            file = open(summary_log_name(pos_id),'w')
            file.write(summary_log_data)
            file.close()

        # update move data log
        for pos_id in these_targets.keys():
            row = this_timestamp
            row += ',' + str(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES'))
            row += ',' + str(these_targets[pos_id]['targ_obsXY'][0])
            row += ',' + str(these_targets[pos_id]['targ_obsXY'][1])
            for key in submove_fields:
                for submove_data in these_targets[pos_id][key]:
                    if isinstance(submove_data,list):
                        for j in range(len(submove_data)):
                            row += ',' + str(submove_data[j])
                    else:
                        row += ',' + str(submove_data)
            row += '\n'
            file = open(move_log_name(pos_id),'a')
            file.write(row)
            file.close()
    
    # make summary plots showing the targets and measured positions
    for pos_id in all_data_by_pos_id.keys():
        posmodel = ptl.get(pos_id)
        title = log_timestamp + log_suffix
        center = [ptl.get(pos_id,'OFFSET_X'),ptl.get(pos_id,'OFFSET_Y')]
        theta_min = posmodel.trans.posTP_to_obsTP([min(posmodel.targetable_range_T),0])[0]
        theta_max = posmodel.trans.posTP_to_obsTP([max(posmodel.targetable_range_T),0])[0]
        theta_range = [theta_min,theta_max]
        r1 = ptl.get(pos_id,'LENGTH_R1')
        r2 = ptl.get(pos_id,'LENGTH_R2')
        pos_xytest_plot.plot(summary_plot_name(pos_id),pos_id,all_data_by_pos_id[pos_id],center,theta_range,r1,r2,title)
            
script_exec_time = time.time() - script_start_time
print('Total test time: ' + format(script_exec_time/60/60,'.1f') + 'hrs')
