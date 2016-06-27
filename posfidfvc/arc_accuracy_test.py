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
import pos_arctest_plot
import fitcircle

# simulation mode
simulate = True

# start timer on the whole script
script_start_time = time.time()

# test configuration
pos_ids = ['UM00013']
pos_id_suffixes = ['titanium']
log_suffix = '20C'
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
tests.append({'axis':'phi', 'title':'150 deg cruise', 'targ_angle':forward_back_sequence(start=15, step=150, nsteps=1, nrepeats=15)})
tests.append({'axis':'phi', 'title':'30 deg cruise', 'targ_angle':forward_back_sequence(start=15, step=30, nsteps=5, nrepeats=6)})
temp = forward_back_sequence(     start=15,  step=1, nsteps=5, nrepeats=1)
temp.extend(forward_back_sequence(start=45,  step=1, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=75,  step=1, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=105, step=1, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=135, step=1, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=165, step=1, nsteps=5, nrepeats=1))
tests.append({'axis':'phi', 'title':'1 deg creep', 'targ_angle':temp})
temp = forward_back_sequence(     start=15,  step=0.2, nsteps=5, nrepeats=1)
temp.extend(forward_back_sequence(start=45,  step=0.2, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=75,  step=0.2, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=105, step=0.2, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=135, step=0.2, nsteps=5, nrepeats=1))
temp.extend(forward_back_sequence(start=165, step=0.2, nsteps=5, nrepeats=1))
tests.append({'axis':'phi', 'title':'0.2 deg creep', 'targ_angle':temp})
for test in tests:
    test['n_pts'] = len(test['targ_angle'])
    print(test['title'] + ': ' + str(test['n_pts']) + ' points')
total_pts = sum([test['n_pts'] for test in tests])
time_per_move_guess = 9 # seconds
print('   total all tests: ' + str(total_pts) + ' points, roughly ' + format(total_pts*time_per_move_guess/60,'0.1f') + ' minutes to complete test')

# initialization
if simulate:
    fvc = fvchandler.FVCHandler('simulator')
else:
    fvc = fvchandler.FVCHandler('SBIG')
fvc.scale = 0.0061 # mm/pixel (update um_scale below if not in mm)
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.simulator_on = simulate
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
if simulate: log_timestamp += '_SIMULATED'
log_suffix = ('_' + 'log_suffix') if log_suffix else ''
def summary_name(pos_id):
    pos_id_suffix = pos_id_suffixes[pos_ids.index(pos_id)]
    pos_id_suffix = ('_') + pos_id_suffix if pos_id_suffix else ''
    return pos_id + pos_id_suffix + '_' + log_timestamp + log_suffix
def path_prefix(pos_id):
    return log_directory + os.path.sep + summary_name(pos_id)
def log_path(pos_id):
    return path_prefix(pos_id) + '.csv'
def plot_path(pos_id):
    return path_prefix(pos_id) + '.png'  


# initial homing, fiducial identification, positioner location and range-finding
m.rehome(pos_ids='all')
m.identify_fiducials()
m.identify_positioner_locations()

# begin tests sequence
is_first_test_in_sequence = True
pt = 0
data_keys = ['meas_obsX','meas_obsY','cycle']
for test in tests:
    for pos_id in pos_ids:
        test[pos_id] = {} # will store measured data in here for each positioner
        for key in data_keys:
            test[pos_id][key] = []
    test['timestamps'] = []
    
    # measure physical travel range of axis and rehome
    if is_first_test_in_sequence:  
        if 'theta' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='theta')
        if 'phi' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='phi')
        m.rehome(pos_ids='all')
        is_first_test_in_sequence = False
        
    # do the test
    for angle in test['targ_angle']:
        tp =  [0,angle] if test['axis'] == 'phi' else [angle,120]
        requests = {}
        for pos_id in pos_ids:
            requests[pos_id] = {'command':'posTP', 'target':tp, 'log_note':test['axis'] + ' ' + test['title']}
        pt += 1
        print('Measuring target ' + str(pt) + ' of ' + str(total_pts) + ' at angle ' + str(angle) + ' on ' + test['axis'] + ' (' + test['title'] + ' sequence)')
        test['timestamps'].append(str(datetime.datetime.now().strftime(pc.timestamp_format)))
        this_meas_data = m.move_measure(requests)
        for pos_id in this_meas_data.keys():
            test[pos_id]['meas_obsX'].append(this_meas_data[pos_id][0])
            test[pos_id]['meas_obsY'].append(this_meas_data[pos_id][1])
            test[pos_id]['cycle'].append(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES'))
            
# combined data, for use in fitting
combined = {}
for pos_id in pos_ids:
    combined[pos_id] = {}
    for key in data_keys:
        combined[pos_id][key] = []
    for test in tests:
        for key in data_keys:
            combined[pos_id][key].extend(test[pos_id][key])
combined['targ_angle'] = []
for test in tests:
    combined['targ_angle'].extend(test['targ_angle'])

# best circle fits on measured data
for pos_id in pos_ids:
    x = combined[pos_id]['meas_obsX']
    y = combined[pos_id]['meas_obsY']
    meas_obsXY = [[x[i],y[i]] for i in range(len(x))]
    (xy_ctr,radius) = fitcircle.FitCircle().fit(meas_obsXY)
    combined[pos_id]['x_center'] = xy_ctr[0]
    combined[pos_id]['y_center'] = xy_ctr[1]
    combined[pos_id]['radius'] = radius
    
    # best angle offset (calibration of this offset is not what we're testing here)
    meas_angle = np.degrees(np.arctan2(y,x))
    combined[pos_id]['offset_angle'] = np.mean(meas_angle - combined['targ_angle'])
    
# collect log data
for pos_id in pos_ids:
    for test in tests:
        x_meas = test[pos_id]['meas_obsX']
        y_meas = test[pos_id]['meas_obsY']
        a_targ = np.radians(test['targ_angle']) + np.radians(combined[pos_id]['offset_angle'])
        r0 = combined[pos_id]['radius']
        x0 = combined[pos_id]['x_center']
        y0 = combined[pos_id]['y_center']
        sin = np.sin(a_targ)
        cos = np.cos(a_targ)
        tan = np.tan(a_targ)
        x_targ = r0*cos
        y_targ = r0*sin
        err_x = x_meas - x_targ
        err_y = y_meas - y_targ
        err_tangential = (err_y - err_x*tan)/(sin*tan + cos)
        err_radial = (err_x + sin*err_tangential)/cos
        err_total = np.sqrt(err_radial**2 + err_tangential**2)        
        test[pos_id]['err_total'] = err_total.tolist()
        test[pos_id]['err_radial'] = err_radial.tolist()
        test[pos_id]['err_tangential'] = err_tangential.tolist()

# write logs
move_log_header = 'timestamp,cycle,test_title,axis,targ_angle,meas_obsX,meas_obsY,err_radial,err_tangential,err_total\n'
for pos_id in pos_ids:
    file = open(log_path(pos_id),'w')
    file.write(move_log_header)
    file.close()
    for test in tests:
        file = open(log_path(pos_id),'a')
        for i in range(len(test['timestamps'])):
            row = test['timestamps'][i]
            row += ',' + str(test[pos_id]['cycle'][i])
            row += ',' + str(test['title'])
            row += ',' + str(test['axis'])
            row += ',' + str(test['targ_angle'][i])
            row += ',' + str(test[pos_id]['meas_obsX'][i])
            row += ',' + str(test[pos_id]['meas_obsY'][i])
            row += ',' + str(test[pos_id]['err_radial'][i])
            row += ',' + str(test[pos_id]['err_tangential'][i])
            row += ',' + str(test[pos_id]['err_total'][i])
            row += '\n'
            file.write(row)
        file.close()            

# make summary plots
for pos_id in pos_ids:
    pos_arctest_plot.plot(plot_path(pos_id), pos_id, tests, summary_name(pos_id))
                
script_exec_time = time.time() - script_start_time
print('Total test time: ' + format(script_exec_time/60/60,'.1f') + 'hrs')
