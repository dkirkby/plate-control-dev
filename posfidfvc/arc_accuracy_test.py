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
simulate = False

# start timer on the whole script
script_start_time = time.time()

# test configuration
pos_ids = ['SS01','TI01','M00003']
pos_id_suffixes = ['416SS','Ti6Al4V','6061T6']
approx_thetaphi_offsets = [[-179,None],[-179,None],[-179,None]] # manual entry of rough estimate of as-installed offsets, enter None where not applicable
log_suffix = '25C_5V_100curr_RH38'
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
tests.append({'axis':'phi', 'title':'150 deg cruise', 'targ_angle':forward_back_sequence(start=15, step=150, nsteps=1, nrepeats=10)})
tests.append({'axis':'phi', 'title':'30 deg cruise', 'targ_angle':forward_back_sequence(start=15, step=50, nsteps=3, nrepeats=3)})
temp = forward_back_sequence(     start=15,  step=1, nsteps=3, nrepeats=1)
temp.extend(forward_back_sequence(start=65,  step=1, nsteps=3, nrepeats=1))
temp.extend(forward_back_sequence(start=115, step=1, nsteps=3, nrepeats=1))
temp.extend(forward_back_sequence(start=165, step=1, nsteps=3, nrepeats=1))
tests.append({'axis':'phi', 'title':'1 deg creep', 'targ_angle':temp})
temp = forward_back_sequence(     start=15,  step=0.2, nsteps=3, nrepeats=1)
temp.extend(forward_back_sequence(start=65,  step=0.2, nsteps=3, nrepeats=1))
temp.extend(forward_back_sequence(start=115, step=0.2, nsteps=3, nrepeats=1))
temp.extend(forward_back_sequence(start=165, step=0.2, nsteps=3, nrepeats=1))
tests.append({'axis':'phi', 'title':'0.2 deg creep', 'targ_angle':temp})
for test in tests:
    test['n_pts'] = len(test['targ_angle'])
    print(test['title'] + ': ' + str(test['n_pts']) + ' points')
calib_pts = 1 + 2 + len(pos_ids)*2 + 5 + 1
test_pts = sum([test['n_pts'] for test in tests])
total_pts = calib_pts + test_pts
time_per_move_guess = 14 # seconds
print('   total all tests: ' + str(test_pts) + ' points, expect roughly ' + format(total_pts*time_per_move_guess/60,'0.1f') + ' minutes to complete test')

# initialization
if simulate:
    fvc = fvchandler.FVCHandler('simulator')
else:
    fvc = fvchandler.FVCHandler('SBIG')
fvc.scale = 0.018670 # mm/pixel (update um_scale below if not in mm)
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
fid_can_ids = []
petal_id = 1
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.simulator_on = simulate
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.use_current_theta_during_phi_range_meas = True
m.n_fiducial_dots = 1 # number of fiducial centroids the FVC should expect

# function for setting arbitrary theta offsets after rehoming
def set_rough_theta_offsets():
    for pos_id in pos_ids:
        approx_offsets = approx_thetaphi_offsets[pos_ids.index(pos_id)]
        if approx_offsets[pc.T] != None:
            ptl.set(pos_id,'OFFSET_T',approx_offsets[pc.T])
        if approx_offsets[pc.P] != None:
            ptl.set(pos_id,'OFFSET_P',approx_offsets[pc.P]) 

# general log file setup
log_directory = pc.test_logs_directory
os.makedirs(log_directory, exist_ok=True)
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
def log_timestamp_with_notes():
    return (log_timestamp + '_SIMULATED') if simulate else log_timestamp
def summary_name(pos_id):
    pos_id_suffix = pos_id_suffixes[pos_ids.index(pos_id)]
    pos_id_suffix = ('_') + pos_id_suffix if pos_id_suffix else ''
    mod_log_suffix = ('_' + log_suffix) if log_suffix else ''
    return pos_id + pos_id_suffix + '_' + log_timestamp_with_notes() + mod_log_suffix
def multiline_summary_name(pos_id):
    pos_id_suffix = pos_id_suffixes[pos_ids.index(pos_id)]
    pos_id_suffix = (' ') + pos_id_suffix if pos_id_suffix else ''
    mod_log_suffix = ('\n' + log_suffix) if log_suffix else ''
    s = pos_id + pos_id_suffix + mod_log_suffix + '\n' + log_timestamp_with_notes()
    s = s.replace('_',' ')
    return s
def path_prefix(pos_id):
    return log_directory + summary_name(pos_id)
def log_path(pos_id):
    return path_prefix(pos_id) + '.csv'
def plot_path(pos_id):
    return path_prefix(pos_id) + '.png'

# initial homing, fiducial identification, positioner location and range-finding
m.rehome(pos_ids='all')
set_rough_theta_offsets()
m.identify_fiducials()
#m.identify_positioner_locations() # needs to be run at least once after initial hardware setup

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
    test['meas_refXY'] = []
    
    # measure physical travel range of axis and rehome
    if is_first_test_in_sequence:  
        if 'theta' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='theta')
        if 'phi' in [t['axis'] for t in tests]:
            m.measure_range(pos_ids='all', axis='phi')
        m.rehome(pos_ids='all')
        set_rough_theta_offsets()
        is_first_test_in_sequence = False
        
    # do the test
    for angle in test['targ_angle']:
        tp =  [0,angle] if test['axis'] == 'phi' else [angle,120]
        requests = {}
        for pos_id in pos_ids:
            requests[pos_id] = {'command':'posTP', 'target':tp, 'log_note':test['axis'] + ' ' + test['title']}
        pt += 1
        print('Measuring target ' + str(pt) + ' of ' + str(test_pts) + ' at angle ' + format(angle,'.2f') + ' on ' + test['axis'] + ' (' + test['title'] + ' sequence)')
        test['timestamps'].append(str(datetime.datetime.now().strftime(pc.timestamp_format)))
        this_meas_data = m.move_measure(requests)
        for pos_id in this_meas_data.keys():
            test[pos_id]['meas_obsX'].append(this_meas_data[pos_id][0])
            test[pos_id]['meas_obsY'].append(this_meas_data[pos_id][1])
            test[pos_id]['cycle'].append(ptl.get(pos_id,'TOTAL_MOVE_SEQUENCES'))
            test['meas_refXY'].append(m.last_meas_fiducials_xy)
            
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
    x = np.subtract(x,combined[pos_id]['x_center'])
    y = np.subtract(y,combined[pos_id]['y_center'])
    meas_angle = np.degrees(np.arctan2(y,x))
    targ_angle = np.array(combined['targ_angle'])
    def wrap_err(meas,targ):
        diff = meas_angle - targ_angle
        err = diff - np.mean(diff)
        return err
    meas_angle_wrapped = meas_angle
    err = wrap_err(meas_angle_wrapped,targ_angle)
    while (np.max(err) - np.min(err)) >= 360:
        meas_angle_wrapped[err < -180] += 360
        err = wrap_err(meas_angle_wrapped,targ_angle)
    #meas_angle[err > +180] -= 360 # wrapping about +/-180 so comparable to targ_angle
    meas_angle_wrapped = meas_angle
    meas_angle_wrapped[err < -180] += 360 # wrapping about +/-180 so comparable to targ_angle
    combined[pos_id]['offset_angle'] = np.mean(meas_angle_wrapped - targ_angle) 
    
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
        x_targ = r0*cos + x0
        y_targ = r0*sin + y0
        err_x = x_meas - x_targ
        err_y = y_meas - y_targ
        err_xy = np.array([err_x,err_y])
        radial_unit_vec = np.array([cos,sin])
        tangen_unit_vec = np.dot([[0,-1],[1,0]],radial_unit_vec)
        err_radial = np.sum(np.multiply(err_xy,radial_unit_vec),axis=0) # one-liner to dot each by its own unit vec
        err_tangen = np.sum(np.multiply(err_xy,tangen_unit_vec),axis=0) # one-liner to dot each by its own unit vec
        err_total = np.sqrt(err_radial**2 + err_tangen**2)        
        test[pos_id]['err_total'] = err_total.tolist()
        test[pos_id]['err_radial'] = err_radial.tolist()
        test[pos_id]['err_tangen'] = err_tangen.tolist()

# write logs
move_log_header = 'timestamp,cycle,test_title,axis,targ_angle,meas_obsX,meas_obsY'
for i in range(m.n_fiducial_dots):
    move_log_header += ',meas_refX' + str(i) + ',meas_refY' + str(i)
move_log_header += ',err_radial,err_tangen,err_total\n'
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
            for j in range(m.n_fiducial_dots):
                row += ',' + str(test['meas_refXY'][i][j][0])
                row += ',' + str(test['meas_refXY'][i][j][1])
            row += ',' + str(test[pos_id]['err_radial'][i])
            row += ',' + str(test[pos_id]['err_tangen'][i])
            row += ',' + str(test[pos_id]['err_total'][i])
            row += '\n'
            file.write(row)
        file.close()            

# make summary plots
for pos_id in pos_ids:
    pos_arctest_plot.plot(plot_path(pos_id), pos_id, tests, multiline_summary_name(pos_id))
                
script_exec_time = time.time() - script_start_time
print('Total test time: ' + format(script_exec_time/60/60,'.1f') + 'hrs')
