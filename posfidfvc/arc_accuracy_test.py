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
import collections

# start timer on the whole script
script_start_time = time.time()

# test configuration
pos_ids = ['UM00013']
pos_id_suffixes = ['titanium']
def forward_back_sequence(start,step,nsteps,nrepeats):
    '''total number of entries in sequence = 1 + 2*nsteps*nrepeats'''
    sequence = [start]
    for i in range(nrepeats):
        for j in range(nsteps):
            sequence += [sequence[-1] + step]
        for j in range(nsteps):
            sequence += [sequence[-1] - step]
    return sequence
tests = []
tests.append({'axis':'phi', 'title':'big move', 'target_angle':forward_back_sequence(start=15, step=150, nsteps=1, nrepeats=15)})
tests.append({'axis':'phi', 'title':'medium move', 'target_angle':forward_back_sequence(start=15, step=50, nsteps=3, nrepeats=8)})
tests.append({'axis':'phi', 'title':'small no creep', 'target_angle':forward_back_sequence(start=15, step=15, nsteps=10, nrepeats=3)})
small = forward_back_sequence(     start=15,  step=+1, nsteps=10, nrepeats=3)
small.append(forward_back_sequence(start=90,  step=+1, nsteps=10, nrepeats=3))
small.append(forward_back_sequence(start=150, step=-1, nsteps=10, nrepeats=3))
tests.append({'axis':'phi', 'title':'small creep', 'target_angle':small})
verysmall = forward_back_sequence(     start=15,  step=+0.1, nsteps=10, nrepeats=3)
verysmall.append(forward_back_sequence(start=90,  step=+0.1, nsteps=10, nrepeats=3))
verysmall.append(forward_back_sequence(start=150, step=-0.1, nsteps=10, nrepeats=3))
tests.append({'axis':'phi', 'title':'very small creep', 'target_angle':verysmall})
for test in tests:
    test['n_pts'] = len(test['target_angle'])
    print(test['title'] + ': ' + str(test['n_pts']) + ' points')
total_pts = sum([test['n_pts'] for test in tests])
time_per_move_guess = 9 # seconds
print('   total all tests: ' + str(total_pts) + ' points, roughly ' + format(total_pts*time_per_move_guess/60,'0.1f') + ' minutes to complete test')

# initialization
fvc = fvchandler.FVCHandler('SBIG')
fvc.scale = 0.0061 # mm/pixel (update um_scale below if not in mm)
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
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

# general log file setup
log_directory = pc.test_logs_directory
os.makedirs(log_directory, exist_ok=True)
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
log_suffix = ('_' + 'log_suffix') if log_suffix else ''
def path_prefix(pos_id):
    pos_id_suffix = pos_id_suffixes[pos_ids.index(pos_id)]
    pos_id_suffix = ('_') + pos_id_suffix if pos_id_suffix else ''
    return log_directory + os.path.sep + pos_id + pos_id_suffix + '_' + log_timestamp + log_suffix
def move_log_name(pos_id):
    return path_prefix(pos_id) + '_movedata.csv'
def summary_log_name(pos_id):
    return path_prefix(pos_id) + '_summary.csv'
def summary_plot_name(pos_id):
    return path_prefix(pos_id) + '_xyplot'  


# initial homing, fiducial identification, positioner location and range-finding
m.rehome(pos_ids='all')
m.identify_fiducials()
m.identify_positioner_locations()

# begin tests sequence
is_first_test_in_sequence = True
pt = 0
data_keys = ['meas_obsX','meas_obsY','targ_angle']
for test in tests:
    pt += 1
    test['data'] = {}
    for pos_id in pos_ids:
        for key in data_keys:
            test['data'][pos_id][key] = []
    
    # measure physical travel range of axis and rehome
    if is_first_test_in_sequence:  
        if 'theta' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='theta')
        if 'phi' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='phi')
        m.rehome(pos_ids='all')
        is_first_test_in_sequence = False
        
    # do the test
    for angle in test['target_angles']:
        tp =  [0,angle] if test['axis'] == 'phi' else [angle,120]
        requests = {}
        for pos_id in pos_ids:
            requests[pos_id] = {'command':'posTP', 'target':tp, 'log_note':test['axis'] + ' ' + test['title']}
            test['data'][pos_id]['targ_angle'].append(angle)
        print('Measuring target ' + str(pt) + ' of ' + str(total_pts) + ' at angle ' + str(angle) + ' on ' + test['axis'] + ' (' + test['title'] + ' sequence)')
        this_timestamp = str(datetime.datetime.now().strftime(pc.timestamp_format))
        this_meas_data = m.move_measure(requests)
        for pos_id in this_meas_data.keys():
            test['data'][pos_id]['meas_obsX'].append(this_meas_data[pos_id][0])
            test['data'][pos_id]['meas_obsY'].append(this_meas_data[pos_id][1])
            
# useful alternate arrangements of data
data = {}
for pos_id in pos_ids:
    data[pos_id] = {}
    data[pos_id]['combined'] = {} # useful for fitting
    for key in data_keys:
        data[pos_id]['combined'][key] = []
for test in tests:
    data[pos_id][test] = {}
    for key in data_keys:
        data[pos_id][test][key] = test['data'][pos_id][key]
        data[pos_id]['combined'][key].append(test['data'][pos_id][key])

# fits on measured data
for pos_id in pos_ids:
    data['meas_obsXY'] = [[data[pos_id]['combined']['meas_obsX'][i],data[pos_id]['combined']['meas_obsY'][i]] for i in range(len(data[pos_id]['combined']['meas_obsX']))]

    # best fit circle
    (xy_ctr,radius) = fitcircle.FitCircle().fit(data['meas_obsXY'])
    data[pos_id]['xy_ctr'] = xy_ctr
    data[pos_id]['radius'] = radius
    
    # best fit angle offset (calibration of this offset is not what we're testing here)

--> CONTINUE WORK HERE




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
