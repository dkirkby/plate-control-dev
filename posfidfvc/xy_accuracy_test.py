import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posmovemeasure
import posconstants as pc
import datetime

# initialization
fvc = fvchandler.FVCHandler('SBIG')
fvc.scale = 0.02 # mm/pixel
fvc.rotation = 0  # deg
pos_ids = ['UM00012']
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.n_fiducial_dots = 2 # number of centroids the FVC should expect
num_corr_max = 2 # number of correction moves to do for each target

# log file setup
log_directory = os.path.abspath('../test_logs')
os.makedirs(log_directory, exist_ok=True)
log_suffix = '' # string gets appended to filenames -- useful for user to identify particular tests
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
def main_log_name(pos_id):
    suffix = ('_' + log_suffix) if log_suffix else ''
    return log_directory + os.path.sep + pos_id + '_' + log_timestamp + suffix + '.csv'
main_log_header = 'timestamp,cycle,target_x,target_y'
for i in range(num_corr_max + 1):
    main_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
for i in range(num_corr_max + 1):
    main_log_header += ',err_x' + str(i) + ',err_y' + str(i)
for i in range(num_corr_max + 1):
    main_log_header += ',err_xy' + str(i)
for pos_id in pos_ids:
    file = open(main_log_name(pos_id),'w')
    file.write(main_log_header)
    file.close()

# cycles configuration (for life testing)

# test grid configuration (local to any positioner)
local_targets = [[2,0], [-2,0]] # rebrand to targets_posXY

# identify fiducials and initial homing
m.identify_fiducials()
m.rehome(pos_ids='all')

# quick pre-calibration, especially because we need some reasonable values for theta offsets prior to measuring physical travel ranges (where phi arms get extended)
m.calibrate(pos_ids='all', mode='quick')

# measure the physical travel ranges of the theta and phi axes by ramming hard limits in both directions
m.measure_range(pos_ids='all', axis='theta')
m.measure_range(pos_ids='all', axis='phi')
m.rehome(pos_ids='all')

# full calibration
m.calibrate(pos_ids='all', mode='full')

# transform test grid to each positioner's global position
posmodels = ptl.get(pos_ids)
all_global_targets = []
for local_target in local_targets:
    these_global_targets = []
    for posmodel in posmodels:
        these_global_targets = pc.concat_lists_of_lists(these_global_targets, posmodel.trans.posXY_to_obsXY(local_target))
    all_global_targets = pc.concat_lists_of_lists(all_global_targets, these_global_targets)

# run the test
for these_targets in all_global_targets:
    (sorted_pos_ids, sorted_targets, obsXY, errXY, err2D) = m.move_and_correct(pos_ids, these_targets, coordinates='obsXY', num_corr_max=num_corr_max)
    # data logging
    sorted_cycles = ptl.get(sorted_pos_ids,'TOTAL_MOVE_SEQUENCES')
    for i in range(len(sorted_pos_ids)):
        row = str(datetime.datetime.now().strftime(pc.timestamp_format))
        row += ',' + str(sorted_cycles[i])
        row += ',' + str(sorted_targets[i][0])
        row += ',' + str(sorted_targets[i][1])
        for submove in obsXY:
            row += ',' + submove[i][0] + ',' + submove[i][1]
        for submove in errXY:
            row += ',' + submove[i][0] + ',' + submove[i][1]
        for submove in err2D:
            row += ',' + submove[i]
        file = open(main_log_name(sorted_pos_ids[i]),'a')
        file.write(row + '\n')
        file.close()