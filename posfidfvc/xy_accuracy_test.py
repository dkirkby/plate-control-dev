import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posmovemeasure
import posconstants as pc
import datetime
import numpy as np

# initialization
fvc = fvchandler.FVCHandler('SBIG')
fvc.scale = 0.019 # mm/pixel (update um_scale below if not in mm)
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
pos_ids = ['UM00012','UM00011','UM00014']
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.n_points_full_calib_T = 5#17
m.n_points_full_calib_P = 5#9
m.n_fiducial_dots = 3 # number of centroids the FVC should expect
num_corr_max = 2 # number of correction moves to do for each target

# test operations to do
should_identify_fiducials = True
should_initial_rehome     = True
should_identify_pos_loc   = True
should_calibrate_quick    = True
should_measure_ranges     = True
should_calibrate_full     = True
should_do_accuracy_test   = True

# log file setup
log_directory = pc.test_logs_directory
os.makedirs(log_directory, exist_ok=True)
log_suffix = '' # string gets appended to filenames -- useful for user to identify particular tests
log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
def move_log_name(pos_id):
    return log_directory + os.path.sep + pos_id + '_' + log_timestamp + log_suffix + '_movedata.csv'
def summary_log_name(pos_id):
    return log_directory + os.path.sep + pos_id + '_' + log_timestamp + log_suffix + '_summary.csv'

# cycles configuration (for life testing)
# STILL TO BE IMPLEMENTED

# test grid configuration (local to any positioner)
grid_max_radius = 5.8 # mm
grid_min_radius = 0.2 # mm
n_pts_across = 7
line = np.linspace(-grid_max_radius,grid_max_radius,n_pts_across)
local_targets = [[x,y] for x in line for y in line]
for i in range(len(local_targets)-1,-1,-1): # traverse list from end backward
    r = (local_targets[i][0]**2 + local_targets[i][1]**2)**0.5
    if r < grid_min_radius or r > grid_max_radius: local_targets.pop(i)

# identify fiducials
if should_identify_fiducials:
    m.identify_fiducials()
    
# identification of which positioners are in which (x,y) locations on the petal
if should_identify_pos_loc:
    # do a rehome here, then get the positioners a bit off the phi hardstops
    m.identify_positioner_locations()
    
# initial homing
if should_initial_rehome:
    m.rehome(pos_ids='all')

# quick pre-calibration, especially because we need some reasonable values for theta offsets prior to measuring physical travel ranges (where phi arms get extended)
if should_calibrate_quick:
    m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp)

# measure the physical travel ranges of the theta and phi axes by ramming hard limits in both directions
if should_measure_ranges:
    m.measure_range(pos_ids='all', axis='theta')
    m.measure_range(pos_ids='all', axis='phi')
    m.rehome(pos_ids='all')

# full calibration
if should_calibrate_full:
    m.calibrate(pos_ids='all', mode='full', save_file_dir=log_directory, save_file_timestamp=log_timestamp)

# do the xy accuracy test
if should_do_accuracy_test:
    submove_idxs = [i for i in range(num_corr_max+1)]

    # write headers for move data log files
    move_log_header = 'timestamp,cycle,target_x,target_y'
    for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
    for i in submove_idxs: move_log_header += ',err_x' + str(i) + ',err_y' + str(i)
    for i in submove_idxs: move_log_header += ',err_xy' + str(i)
    move_log_header += '\n'
    for pos_id in pos_ids:
        file = open(move_log_name(pos_id),'w')
        file.write(move_log_header)
        file.close()

    # transform test grid to each positioner's global position
    posmodels = ptl.get(pos_ids)
    all_global_targets = []
    for local_target in local_targets:
        these_global_targets = []
        for posmodel in posmodels:
            these_global_targets = pc.concat_lists_of_lists(these_global_targets, posmodel.trans.posXY_to_obsXY(local_target))
        all_global_targets.append(these_global_targets)

    # initialize some data structures for storing test data
    targ_num = 0
    all_meas_data_by_target = []
    all_meas_data_by_pos_id = {}
    for pos_id in pos_ids:
        all_meas_data_by_pos_id[pos_id] = {'targ_obsXY': [],
                                           'meas_obsXY': [[] for i in submove_idxs],
                                           'errXY':      [[] for i in submove_idxs],
                                           'err2D':      [[] for i in submove_idxs]}
    start_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
    start_cycles = ptl.get(pos_ids,'TOTAL_MOVE_SEQUENCES')
    
    # run the test
    for these_targets in all_global_targets:
        targ_num += 1
        print('\nMEASURING TARGET ' + str(targ_num) + ' OF ' + str(len(all_global_targets)))
        this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
        these_meas_data = m.move_and_correct(pos_ids, these_targets, coordinates='obsXY', num_corr_max=num_corr_max)
        
        # store this set of measured data
        all_meas_data_by_target.append(these_meas_data)
        for pos_id in these_meas_data.keys():
            all_meas_data_by_pos_id[pos_id]['targ_obsXY'].append(these_meas_data[pos_id]['targ_obsXY'])
            for i in submove_idxs:
                all_meas_data_by_pos_id[pos_id]['meas_obsXY'][i].append(these_meas_data[pos_id]['meas_obsXY'][i])
                all_meas_data_by_pos_id[pos_id]['errXY'][i].append(     these_meas_data[pos_id]['errXY'][i])
                all_meas_data_by_pos_id[pos_id]['err2D'][i].append(     these_meas_data[pos_id]['err2D'][i])                    
        
        # update summary data log
        for p in pos_ids:
            summary_log_data =  'pos_id,' + str(p) + '\n'
            summary_log_data += 'cycles at start,' + str(start_cycles[pos_ids.index(p)]) + '\n'
            summary_log_data += 'cycles at finish,' + str(ptl.get(p,'TOTAL_MOVE_SEQUENCES')) + '\n'
            summary_log_data += 'start time,' + start_timestamp + '\n'
            summary_log_data += 'finish time,' + this_timestamp + '\n'
            summary_log_data += 'num targets,' + str(len(all_meas_data_by_target)) + '\n'
            summary_log_data += 'num corrections max,' + str(num_corr_max) + '\n'
            summary_log_data += 'submove index -->'
            for i in submove_idxs: summary_log_data += ',' + str(i)
            summary_log_data += '\n'
            for calc in ['max','min','mean','rms']:
                summary_log_data += calc + '(um)'
                for i in submove_idxs:
                    this_submove_data = all_meas_data_by_pos_id[p]['err2D'][i]
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
        for p in these_meas_data.keys():
            row = this_timestamp
            row += ',' + str(ptl.get(p,'TOTAL_MOVE_SEQUENCES'))
            row += ',' + str(these_meas_data[p]['targ_obsXY'][0])
            row += ',' + str(these_meas_data[p]['targ_obsXY'][1])
            for submove_data in these_meas_data[p]['meas_obsXY']:
                row += ',' + str(submove_data[0]) + ',' + str(submove_data[1])
            for submove_data in these_meas_data[p]['errXY']:
                row += ',' + str(submove_data[0]) + ',' + str(submove_data[1])
            for submove_data in these_meas_data[p]['err2D']:
                row += ',' + str(submove_data)
            row += '\n'
            file = open(move_log_name(p),'a')
            file.write(row)
            file.close()
