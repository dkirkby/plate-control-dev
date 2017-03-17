'''fiberlife.py
This script is for life-testing a bunch of fibers that are installed in positioners.
'''

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
sys.path.append(os.path.abspath('../../xytest/'))
import petal
import xytest
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import collections
import time

# hardware configurations
ptl_id = 10 # pc number of the petal controller
pos_ids = ['fakepos1','fakepos2'] # list of positioners being tested
time_between_exposures = 20.0 # seconds between camera exposures
camera_expose_and_readout_time = 1.0 # seconds it takes to do a camera exposure and readout

# target lists
targets = collections.OrderedDict()
targets['full']    = [[t,p] for t in [-180,-90,0,90,180] for p in [180,135,90,45,0]]
targets['reduced'] = [[t,p] for t in [0] for p in [180]]

# configure the log writer
timestamp_str = pc.timestamp_str_now()
filename_timestamp_str = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()
logfile = tkinter.filedialog.asksaveasfilename(title='Save test log as...',initialdir='~',initialfile=filename_timestamp_str + '_fiberlife_log.txt',filetypes='.txt')
if not(logfile):
    tkinter.messagebox.showwarning(title='Quitting.',message='No log file was defined.')
    gui_root.withdraw()
    sys.exit(0)
with open(logfile,'w') as file:
    file.write('Test log from a run of fiberlife.py\n\n')
def logwrite(string):
    timestamp_str = pc.timestamp_str_now()
    stamped = timestamp_str + ': ' + string
    print(stamped)
    with open(logfile,'a'):
        file.write(stamped + '\n')

# log configuration info
pos_ids.sort()
logwrite('POSITIONERS: ' + str(pos_ids))

# configure the test
should_simulate = True
logwrite('SIMULATION MODE: ' + 'on' if should_simulate else 'off')

# retrieve latest log files and settings from svn
svn_update_dirs = [pc.pos_logs_directory, pc.pos_settings_directory]
if not(should_simulate):
    svn_user, svn_pass, err = xytest.XYTest.ask_user_for_creds(should_simulate=False)
    if err:
        logwrite('Could not validate svn user/password.')
    else:
        for d in svn_update_dirs:
            logwrite('Updating SVN directory ' + d)
            os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
new_and_changed_files = set()

# initialize the "petal" of positioners
ptl = petal.Petal(ptl_id, pos_ids, fid_ids=[], simulator_on=should_simulate, printfunc=logwrite)
ptl.anticollision_default = False
logwrite('Petal ' + str(ptl_id) + ' initialized.')

# configure some specific positioner parameters
pos_params_during_test = {'FINAL_CREEP_ON':False, 'CURR_CRUISE':100, 'CURR_CREEP':100, 'PRINCIPLE_HARDSTOP_CLEARANCE_P':5.0}
pos_params_before_test = collections.OrderedDict()
for pos_id in pos_ids:
    pos_params_before_test[pos_id] = {}
    for param in pos_params_during_test.keys():
        pos_params_before_test[pos_id][param] = ptl.get(pos_id, param)
        ptl.set(pos_id, param, pos_params_during_test[param])
        logwrite(pos_id + ': Set ' + param + ' = ' + str(ptl.get(pos_id, param)))

# home and center the positioners
logwrite('Re-homing all positioners to hard stops.')
ptl.request_homing(pos_ids)
ptl.schedule_send_and_execute_moves()
logwrite('Moving all positioners to center positions.')
ptl.quick_move('all','posTP',[0,180])

# do some functional tests to make sure all the positioners are working
def functional_tests(pos_ids):
    for pos_id in pos_ids:
        keep_asking = True
        title = 'Functional test: ' + pos_id
        message = 'Ready to try moving positioner ' + pos_id + '?'
        while keep_asking:
            should_move = tkinter.messagebox.askyesno(title, message)
            if should_move:
                ptl.quick_move(pos_id,'posTP',[90,0])
                ptl.quick_move(pos_id,'posTP',[-90,0])
                ptl.quick_move(pos_id,'posTP',[0,180])
                moved = tkinter.messagebox.askyesno(title,'Did you see ' + pos_id + ' move?')
                if moved:
                    keep_asking = False
                    logwrite(pos_id + ': PASSED functional test')
                else:
                    message = 'Try moving positioner ' + pos_id + ' again?'
            else:
                keep_asking = False
                failed_pos.add(pos_id)
    return failed_pos
failed_pos = functional_tests(pos_ids)
keep_asking = True
while failed_pos and keep_asking:
    message = 'The following positioners apparently failed the functional test:\n'
    for pos in failed_pos:
        message += '\n' + pos
    message += 'Do you want to retry these positoners?\n'
    message += 'YES --> retry\n'
    message += 'NO --> accept these results'
    should_retry = tkinter.messagebox.askyesno('Retry functional tests?',message)
    if should_retry:
        failed_pos = functional_tests(list(failed_pos))
    else:
        keep_asking = False
        for pos_id in failed_pos:
            ptl.posmodels.pop(ptl.posids.index(pos_id))
            ptl.posids.pop(ptl.posids.index(pos_id))
            pos_ids.pop(pos_ids.index(pos_id))
            logwrite(pos_id + ': FAILED functional test and was disabled for this test run')

# run the test points
options_msg = 'Select which positioner to do the next FRD test on.\n'
i = 0
options_msg += '\n   ' + str(i) + ': Quit this round of testing.'
for pos_id in pos_ids:
    i += 1
    options_msg += '\n   ' + str(i) + ': ' + pos_id
keep_testing = True
while keep_testing:
    selection = tkinter.simpledialog('Pick next pos...', options_msg)
    if selection == 0:
        keep_testing = False
    elif selection > 0 and selection <= len(pos_ids):
        pos_id = pos_ids[selection-1]
        title = 'Ready to test ' + pos_id + '?'
        message = 'Ready to start FRD test on positioner ' + pos_id + '?'
        message += '\n\n(Camera delay should be set to ' + format(time_between_exposures,'.1f') + ' seconds, and ' + str(len(targets)) + ' number of exposures. Be ready to activate the camera at roughly the same time as you press OK below.)'
        tkinter.messagebox.showwarning(title,message)
        for target in targets:
    else:
        tkinter.messagebox.showerror('Invalid selection','Option ' + str(selection) + ' was not recognized.')

# ask user how many random moves to do now
# give opportunity to review what is about to happen
#  - expected time it will take (1000 moves per hour)
#  - how many moves each positioner has on it now, and how many it will have on it at end, and the delta

# initialize the random positions table

# run the random moves

# restore old positioner parameters (good housekeeping)
for pos_id in pos_params_before_test.keys():
    for param in pos_params_before_test[pos_id]:
        ptl.set(pos_id, param, pos_params_before_test[pos_id][param])
        logwrite(pos_id + ': Restored ' + param + ' to ' + str(ptl.get(pos_id, param)))

# post log files and settings to svn


# close out the gui
gui_root.withdraw()