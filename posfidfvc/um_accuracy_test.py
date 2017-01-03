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
import um_test_report as test_report
import traceback

import petalcomm
import posmodel
import configobj


# read the configuration file
if len(sys.argv) ==1:
    configfile=os.environ['POSFIDFVC_PATH']+'/accuracy_test.conf'
else:
    configfile=sys.argv[1]
print("configfile:",configfile,flush=True)

config = configobj.ConfigObj(configfile,unrepr=True)

# start timer on the whole script
script_start_time = time.time()

# initialization
fvc = fvchandler.FVCHandler('SBIG')
fvc.scale =  config['local']['scale'] # mm/pixel (update um_scale below if not in mm) #Test2 = .0274 Test1 = .0282
fvc.rotation = 0  # deg
um_scale = 1000 # um/mm
bcast_id = config['positioners']['bcast_id'] # 20000
pos_ids = config['positioners']['ids']
pos_notes = config['positioners']['notes'] #notes for report to add about positioner (reported with positioner in same slot as pos_ids list)
while len(pos_notes) < len(pos_ids):
    pos_notes.append('')
fid_can_ids = []
petal_id = config['petal']['petal_id']
ptl = petal.Petal(petal_id, pos_ids, fid_can_ids)
ptl.anticollision_default = config['petal']['anticollision']
m = posmovemeasure.PosMoveMeasure(ptl,fvc)
m.n_points_full_calib_T = config['calib']['n_points_full_calib_T']
m.n_points_full_calib_P = config['calib']['n_points_full_calib_P']
m.n_fiducial_dots = config['calib']['n_fiducial_dots'] # number of fiducial centroids the FVC should expect
num_corr_max = config['mode']['num_corr_max'] # number of correction moves to do for each target

#get general configuration parameters and send them to positioners
pcomm = petalcomm.PetalComm(petal_id)
pm = posmodel.PosModel()

creep_p = pm.state.read('CREEP_PERIOD')
spin_p = pm.state.read('SPINUPDOWN_PERIOD')

curr_spin = pm.state.read('CURR_SPIN_UP_DOWN')
curr_creep = pm.state.read('CURR_CREEP')
curr_cruise = pm.state.read('CURR_CRUISE')
curr_hold = pm.state.read('CURR_HOLD')

pcomm.set_currents(bcast_id, [curr_spin, curr_cruise, curr_creep, curr_hold], [curr_spin, curr_cruise, curr_creep, curr_hold])
pcomm.set_periods(bcast_id, creep_p, creep_p, spin_p)
print('CURRENTS AND PERIODS: ', creep_p, spin_p, curr_spin, curr_cruise, curr_creep, curr_hold,flush=True) 

#select mode
#pcomm.select_mode(bcast_id, 'normal_old')  # MS Dec29, 2016: commented out per advice from Irena


# test operations to do
should_initial_rehome     = config['mode']['should_initial_rehome']
should_identify_fiducials = config['mode']['should_identify_fiducials']
should_identify_pos_loc   = config['mode']['should_identify_pos_loc']
should_calibrate_quick    = config['mode']['should_calibrate_quick']
should_measure_ranges     = config['mode']['should_measure_ranges']
should_calibrate_grid     = config['mode']['should_calibrate_grid']
should_calibrate_full     = config['mode']['should_calibrate_full']
should_do_accuracy_test   = config['mode']['should_do_accuracy_test']
should_auto_commit_logs   = config['mode']['should_auto_commit_logs']
should_report             = config['mode']['should_report']
should_email              = config['mode']['should_email']
should_final_position     = config['mode']['should_final_position']

email_list = config['email']['email_list'] #full or limited

# certain operations require particular preceding operations
if should_identify_pos_loc: should_initial_rehome = True
if should_measure_ranges: should_calibrate_quick = True

# log file setup
log_directory = pc.test_logs_directory
os.makedirs(log_directory, exist_ok=True)
log_suffix = config['mode']['log_suffix'] # string gets appended to filenames -- useful for user to identify particular tests
log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)
def path_prefix(pos_id):
    return log_directory + os.path.sep + pos_id + '_' + log_timestamp + log_suffix
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
grid_max_radius = config['grid']['grid_max_radius'] # mm
grid_min_radius =  config['grid']['grid_min_radius'] # mm
n_pts_across = config['grid']['n_pts_across']  # 7 --> 28 pts, 27 --> 528 pts
line = np.linspace(-grid_max_radius,grid_max_radius,n_pts_across)
local_targets = [[x,y] for x in line for y in line]
for i in range(len(local_targets)-1,-1,-1): # traverse list from end backward
    r = (local_targets[i][0]**2 + local_targets[i][1]**2)**0.5
    if r < grid_min_radius or r > grid_max_radius: local_targets.pop(i)
'''
select_targets=[]
select_targets.extend(local_targets[1:5])
select_targets.extend(local_targets[12:18])
select_targets.extend(local_targets[25:33])
select_targets.extend(local_targets[42:51])
select_targets.extend(local_targets[61:71])
select_targets.extend(local_targets[82:92])
select_targets.extend(local_targets[103:114])
select_targets.extend(local_targets[126:138])
select_targets.extend(local_targets[151:163])
select_targets.extend(local_targets[176:188])
select_targets.extend(local_targets[201:213])
select_targets.extend(local_targets[226:238])
local_targets =select_targets
'''

try:
    # initial homing
    if should_initial_rehome:
        print("REHOME")
        m.rehome(pos_ids='all')

    # identify fiducials
    if should_identify_fiducials:
        print("ID FIDUCIALS")
        m.identify_fiducials()
    
    # identification of which positioners are in which (x,y) locations on the petal
    if should_identify_pos_loc:
        print("ID POS")
        m.identify_positioner_locations()
        
    # quick pre-calibration, especially because we need some reasonable values for theta offsets prior to measuring physical travel ranges (where phi arms get extended)
    if should_calibrate_quick:
        print("CALIBRATE QUICK")
        m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp)
    
    # measure the physical travel ranges of the theta and phi axes by ramming hard limits in both directions
    if should_measure_ranges:
        print("MEASURE RANGES") 
        m.measure_range(pos_ids='all', axis='theta')
        m.measure_range(pos_ids='all', axis='phi')
        m.rehome(pos_ids='all')
        if not(should_calibrate_full):
            m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp) # needed after having struck hard limits
    
    if should_calibrate_grid:
        m.calibrate(pos_ids='all', mode='grid', save_file_dir=log_directory, save_file_timestamp=log_timestamp)
           
    # full calibration
    if should_calibrate_full:
        m.calibrate(pos_ids='all', mode='full', save_file_dir=log_directory, save_file_timestamp=log_timestamp)
    
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
        test_time = format(script_exec_time/60/60,'.1f')        
        
        #Test report and email only on certain tests
        if should_report and num_corr_max == 3 and n_pts_across == 27:
            test_report.do_test_report(pos_ids, all_data_by_pos_id, log_timestamp, pos_notes, should_email, email_list)
         
        #Commit logs through SVN
        if should_auto_commit_logs:
            filetypes = ['xyplot_submove0.png','xyplot_submove1.png','xyplot_submove2.png','xyplot_submove3.png',
                         'calib_full.png','calib_quick.png','summary.csv','movedata.csv']
            for pos_id in pos_ids:
                for file in filetypes:
                    command = 'svn add ' + pc.test_logs_directory + pos_id + '_' + log_timestamp + '_' + file
                    try:
                        os.system(command)
                    except:
                        print('Failed run command: ' + command)
            try:
                os.system('svn commit ' + pc.test_logs_directory + ' -m "' + log_timestamp + ' test logs"')
            except:
                print('Failed to commit files.')
                    

except (KeyboardInterrupt, SystemExit):
    raise
except:
    #Email traceback to alert that test failed and why
    if should_email:
        test_report.email_error(traceback.format_exc(),log_timestamp)
    raise
    
script_exec_time = time.time() - script_start_time
print('Total test time: ' + format(script_exec_time/60/60,'.1f') + 'hrs')
