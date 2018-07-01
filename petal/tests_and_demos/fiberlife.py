'''fiberlife.py
This script is for life-testing a bunch of fibers that are installed in positioners.
'''

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
sys.path.append(os.path.abspath('../../xytest/'))
sys.path.append(os.path.abspath('../../posfidfvc/'))
import petal
import xytest
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import collections
import time
import csv
import numpy as np

# set up the hardware configurations
ptlid = 12 # pc number of the petal controller
posids = ['M00082','M00063','M00524','M00047','M00084','M00078','M00528','M00118','M00048','M00077','M00049','M00153','M00214','M00037','M00390','M00162','M00157'] # list of positioners being tested

# set up the timing of the automated FRD tests
time_between_exposures = 10.0 # seconds to wait between camera exposures
camera_expose_time = 0.4 # seconds
camera_expose_and_readout_time = 1.1 + camera_expose_time # approximate # of seconds it takes to do a camera exposure and readout
positioner_max_move_time = 5.0 # seconds, generous maximum time to wait for positioner moves to happen

# define the target positions (theta,phi) at which to measure FRD
# note that phi = 180 is centered, while phi = 0 is fully extended
targets = [[t,p] for t in [-180,-90,0,90,180] for p in [180,135,90,45,0]]

# fire up the gui
gui_root = tkinter.Tk()

# ask whether it's a simulation run
should_simulate = tkinter.messagebox.askyesno('Simulate test?','Is this a simulation run?')
if should_simulate:
    time_between_exposures = 0.1
    camera_expose_and_readout_time = 0.01
    positioner_max_move_time = 0.05

# configure the log writer
filename_timestamp_str = pc.filename_timestamp_str_now()
logfile = tkinter.filedialog.asksaveasfilename(title='Save test log as...', initialdir='~', initialfile=filename_timestamp_str + '_fiberlife_log.txt', filetypes=(('Text','.txt'),('All files','.*')))
if not(logfile):
    tkinter.messagebox.showwarning(title='Quitting.',message='No log file was definedup.')
    gui_root.withdraw()
    sys.exit(0)
with open(logfile,'w') as file:
    file.write('Test log from a run of fiberlife.py\n\n')
def logwrite(string):
    timestamp_str = pc.timestamp_str_now()
    stamped = timestamp_str + ': ' + string
    print(stamped)
    with open(logfile,'a') as file:
        file.write(stamped + '\n')
    return timestamp_str

# get a little info
operator = tkinter.simpledialog.askstring('Test operator?','Who is doing this test run?\n\nTest operator:')
logwrite('Test operator: ' + operator)
notes = tkinter.simpledialog.askstring('General notes?','Enter any general notes you want to record about this test run here:')
logwrite('Test notes: ' + notes)

# configure the exposure table writer
expstampfile = tkinter.filedialog.asksaveasfilename(title='Save exposure timestamps to...', initialdir=os.path.dirname(logfile), initialfile=filename_timestamp_str + '_fiberlife_timestamps.csv', filetypes=(('CSV','.csv'),('All files','.*')))
fieldnames = ['POS_ID','TIMESTAMP','TARGET THETA','TARGET PHI','NUM LIFE MOVES','NOTES']
with open(expstampfile,'w',newline='') as file:
    writer = csv.DictWriter(file,fieldnames)
    writer.writeheader()
def log_exposure(posid, state, note=''):
    n_moves = str(state._val['TOTAL_MOVE_SEQUENCES'])
    posT = format(state._val['POS_T'],'.1f')
    posP = format(state._val['POS_P'],'.1f')
    timestamp_str = logwrite(posid + ': Approx time of camera exposure for target [' + posT + ',' + posP + ']  (life=' + n_moves + ')')
    row = {'POS_ID'         : posid,
           'TIMESTAMP'      : timestamp_str,
           'TARGET THETA'   : posT,
           'TARGET PHI'     : posP,
           'NUM LIFE MOVES' : n_moves,
           'NOTES'          : note}
    with open(expstampfile,'a',newline='') as file:
        writer = csv.DictWriter(file,fieldnames)
        writer.writerow(row)
    
# log configuration info
posids.sort()
logwrite('POSITIONERS: ' + str(posids))
logwrite('SIMULATION MODE: ' + 'on' if should_simulate else 'off')

# retrieve latest log files and settings from svn
svn_update_dirs = [pc.dirs['pos_logs'], pc.dirs['pos_settings']]
svn_user, svn_pass, err = xytest.XYTest.ask_user_for_creds(should_simulate=should_simulate)
if not(should_simulate):
    if err:
        logwrite('Could not validate svn user/password.')
    else:
        should_update = tkinter.messagebox.askyesno('Update from SVN?','Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
        if should_update:
            for d in svn_update_dirs:
                logwrite('Updating SVN directory ' + d)
                os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
                os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')
new_and_changed_files = set()

# initialize the "petal" of positioners
ptl = petal.Petal(ptlid, posids, fidids=[], simulator_on=should_simulate, printfunc=logwrite)
ptl.anticollision_default = False
states = collections.OrderedDict()
for posid in posids:
    states[posid] = ptl.posmodel(posid).state
    new_and_changed_files.add(states[posid].log_path)
    new_and_changed_files.add(states[posid].conf.filename)
logwrite('Petal ' + str(ptlid) + ' initialized.')

# configure some specific positioner parameters
pos_params_during_test = {'FINAL_CREEP_ON':False, 'CURR_CRUISE':100, 'CURR_CREEP':100, 'PRINCIPLE_HARDSTOP_CLEARANCE_P':5.0}
pos_params_before_test = collections.OrderedDict()
for posid in posids:
    pos_params_before_test[posid] = {}
    for param in pos_params_during_test.keys():
        pos_params_before_test[posid][param] = ptl.get_posfid_val(posid, param)
        ptl.set_posfid_val(posid, param, pos_params_during_test[param])
        logwrite(posid + ': Set ' + param + ' = ' + str(ptl.get_posfid_val(posid, param)))

# home and center the positioners
logwrite('Re-homing all positioners to hard stops.')
ptl.request_homing(posids)
ptl.schedule_send_and_execute_moves()
logwrite('Moving all positioners to center positions.')
ptl.quick_move(posids,'posTP',[0,180])

# do some functional tests to make sure all the positioners are working
def functional_tests(posids):
    failed_pos = set()
    for posid in posids:
        keep_asking = True
        title = 'Functional test'
        message = 'Ready to try moving positioner ' + posid + '?'
        while keep_asking:
            should_move = tkinter.messagebox.askyesno(title, message)
            if should_move:
                ptl.quick_move(posid,'posTP',[90,90])
                ptl.quick_move(posid,'posTP',[0,180])
                moved = tkinter.messagebox.askyesno(title,'Did you see ' + posid + ' move?')
                if moved:
                    keep_asking = False
                    logwrite(posid + ': PASSED functional test')
                else:
                    message = 'Try moving positioner ' + posid + ' again?'
            else:
                keep_asking = False
                failed_pos.add(posid)
    return failed_pos
failed_pos = functional_tests(posids)
keep_asking = True
while failed_pos and keep_asking:
    message = 'The following positioners apparently failed the functional test:\n'
    for pos in failed_pos:
        message += '\n   ' + pos
    message += '\n\nDo you want to retry these positoners?\n\n'
    message += 'YES --> retry\n'
    message += 'NO --> accept these results'
    should_retry = tkinter.messagebox.askyesno('Retry functional tests?',message)
    if should_retry:
        failed_pos = functional_tests(list(failed_pos))
    else:
        keep_asking = False
        for posid in failed_pos:
            ptl.posmodels.pop(ptl.posids.index(posid))
            ptl.posids.pop(ptl.posids.index(posid))
            posids.pop(posids.index(posid))
            logwrite(posid + ': FAILED functional test and was disabled for this test run')

# run the test points
options_msg = 'Select which positioner to do the next FRD test on.\n'
i = 0
options_msg += '\n   ' + str(i) + ': Quit this round of FRD testing.'
for posid in posids:
    i += 1
    options_msg += '\n   ' + str(i) + ': ' + posid
keep_testing = True
initial_sleep_time = time_between_exposures - positioner_max_move_time
while keep_testing:
    pos_selection = tkinter.simpledialog.askinteger(title='Pick next pos...',prompt=options_msg,minvalue=0,maxvalue=len(posids))
    if pos_selection == 0:
        keep_testing = False
    else:
        posid = posids[pos_selection-1]
        usernote = tkinter.simpledialog.askstring(title='Enter user note...',prompt='Optional user note can be typed here and will be included in the log.')
        logwrite(posid + ': user note: ' + usernote)
        ptl.quick_move(posid,'posTP',targets[0],'Initial FRD test point for this sequence')
        logwrite(posid + ': placed at first target ' + str(targets[0]) + ' and ready to start FRD test')
        title = 'Ready to start?'
        message = 'Ready to start FRD test on positioner ' + posid + '?'
        message += '\n\nMake sure camera software is set to:\n\n'
        message += '   delay = ' + format(time_between_exposures,'.1f') + ' seconds\n'
        message += '   exp = ' + format(camera_expose_time,'.1f') + ' seconds\n'
        message += '\n\nTo time things out right, start the Artemis camera software in autosave mode, and then hit OK here at the same time as a new image happens.'
        tkinter.messagebox.showwarning(title,message)
        start_time = time.time()
        logwrite(posid + ': Beginning timed FRD test sequence')
        time.sleep(camera_expose_and_readout_time)
        log_exposure(posid, states[posid], usernote)
        for i in range(1,len(targets)):
            time.sleep(initial_sleep_time)
            ptl.quick_move(posid,'posTP',targets[i],log_note='FRD test point')
            logwrite(posid + ': placed at ' + str(targets[i]) + ' target ' + str(i + 1) + ' of ' + str(len(targets)))
            previous_loop_end_time = start_time + i * (time_between_exposures + camera_expose_and_readout_time)
            previous_loop_remaining_sleep_time = previous_loop_end_time - time.time()
            if previous_loop_remaining_sleep_time > 0:
                time.sleep(previous_loop_remaining_sleep_time)
            time.sleep(camera_expose_and_readout_time)
            log_exposure(posid, states[posid], usernote)
        logwrite(posid + ': Timed FRD test sequence complete')
logwrite('All FRD test sequences complete')

# ask user how many random moves to do now
keep_asking = True
seconds_per_move = 3.6
while keep_asking:
    n_rand_moves = tkinter.simpledialog.askinteger(title='Specify num of moves',prompt='Enter the number of uninterrupted random moves to do now:', minvalue=0, maxvalue=1000000)
    hours_estimate = seconds_per_move * n_rand_moves / 60 / 60
    if n_rand_moves != 0:
        message = 'You requested a sequence of\n\n   ' + str(n_rand_moves) + '\n\nuninterrupted random moves to now be done.'
        message += ' This will take about\n\n   ' + format(hours_estimate,'.1f') + ' hours\n\nafter which the total number of lifetime moves on each positioner will be:\n'
        for posid in posids:
            message += '\n   ' + posid + ': ' + str(states[posid]._val['TOTAL_MOVE_SEQUENCES'] + n_rand_moves)
        message += '\n\nBegin move sequence now?\n\nYes --> begin sequence\nNo --> enter different number'
        begin_now = tkinter.messagebox.askyesno('Begin random moves?',message)
        if begin_now:
            keep_asking = False
    else:
        message = 'You requested no random moves be done now. Is this right?\n\nYes --> proceed\nNo --> enter different number'
        just_proceed = tkinter.messagebox.askyesno('No random moves?',message)
        if just_proceed:
            keep_asking = False

# initialize the random positions table
if n_rand_moves > 0:
    rand_xy_targs_idx = 0 # where we are in the random targets list
    rand_xy_targs_list = []
    rand_targs_basename = 'xytargs_n10000_seed1486847599.csv'
    rand_targs_file = pc.dirs['test_settings'] + rand_targs_basename
    with open(rand_targs_file, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        header_rows_remaining = 1
        for row in reader:
            if header_rows_remaining:
                header_rows_remaining -= 1
            else:
                rand_xy_targs_list.append([float(row[0]),float(row[1])])
    logwrite('Random targets file: ' + rand_targs_file)
    logwrite('Random targets file length: ' + str(len(rand_xy_targs_list)) + ' targets')

# run the unmeasured random moves
if n_rand_moves > 0:
    start_time = time.time()
    max_log_length = states[posids[0]].max_log_length
    logwrite('Starting unmeasured move sequence')
    status_str = lambda j : '... now at move ' + str(j) + ' of ' + str(n_rand_moves)
    def target_within_limits(xytarg):
        r_min = 0.001
        r_max = 5.999
        x = xytarg[0]
        y = xytarg[1]
        r = np.sqrt(x**2 + y**2)
        if r > r_min and r < r_max:
            return True
        return False
    for j in range(n_rand_moves):
        if j % max_log_length == 0:
            for posid in states.keys():
                new_and_changed_files.add(states[posid].log_path)
        if j % 1000 == 0:
            logwrite(status_str(j))
        elif j % 50 == 0:
            print(status_str(j))
        targ_xy = [np.Inf,np.Inf]
        while not(target_within_limits(targ_xy)):
            targ_xy = rand_xy_targs_list[rand_xy_targs_idx]
            rand_xy_targs_idx += 1
            if rand_xy_targs_idx >= len(rand_xy_targs_list):
                rand_xy_targs_idx = 0
        ptl.quick_move(posids,'posXY',targ_xy,log_note='unmeasured move during fiber life test')
    elapsed_hours = (time.time() - start_time)/60/60
    logwrite(str(n_rand_moves) + ' moves completed in ' + format(elapsed_hours,'.1f') + ' hours')
    
# restore old positioner parameters (good housekeeping)
for posid in pos_params_before_test.keys():
    for param in pos_params_before_test[posid]:
        ptl.set_posfid_val(posid, param, pos_params_before_test[posid][param])
        logwrite(posid + ': Restored ' + param + ' to ' + str(states[posid]._val[param]))

# post log files and settings to svn
logwrite('Files changed or modified during test: ' + str(new_and_changed_files))
start_time = time.time()
print('Will attempt to commit the logs automatically now. This may take a long time. In the messages printed to the screen for each file, a return value of 0 means it was committed to the SVN ok.')
err1 = []
err2 = []
files_attempted = []
n = 0
n_total = len(new_and_changed_files)
for file in new_and_changed_files:
    n += 1
    if should_simulate:
        err1.append(0)
        err2.append(0)
    else:
        err1.append(os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file))
        err2.append(os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + file))
        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1[-1]) + ' (add) and ' + str(err2[-1]) + ' (commit)')
        files_attempted.append(os.path.basename(file))
add_and_commit_errs = [err1[i] and err2[i] for i in range(len(err1))]
if any(add_and_commit_errs):
    print('Warning: it appears that not all the log or plot files committed ok to SVN. Check through carefully and do this manually. The files that failed were:')
    for i in range(len(add_and_commit_errs)):
        if add_and_commit_errs(i):
            print(files_attempted[i])
del svn_user
del svn_pass
elapsed_hours = (time.time() - start_time)/60/60
print('SVN uploads completed in ' + format(elapsed_hours,'.1f') + ' hours')

# close out the gui
gui_root.withdraw()