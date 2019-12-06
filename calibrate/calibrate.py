import os
import sys
import posmovemeasure
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))

import petal
import fvchandler
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj

logfile = pc.dirs['xytest_logs'] + pc.filename_timestamp_str() + '_calib.log'

def logwrite(text,stdout=True):
    """Standard logging function for writing to the test traveler log file.
    """
    global logfile
    line = '# ' + pc.timestamp_str() + ': ' + text
    with open(logfile,'a',encoding='utf8') as fh:
        fh.write(line + '\n')
    if stdout:
        print(line)

#Selects whether to use calibration method that reduces contact with hard stops (currently under development/test)
should_avoid_hardstop_strikes = False

# start set of new and changed files
new_and_changed_files = set()

# unique timestamp and fire up the gui
start_filename_timestamp = pc.filename_timestamp_str()
gui_root = tkinter.Tk()

# get the station config info
message = 'Pick hardware setup file.'
hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# are we in simulation mode?
sim = hwsetup['fvc_type'] == 'simulator'

# automated SVN setup (will remove this)
svn_user = ''
svn_pass = ''
if not sim:
    should_update_from_svn = tkinter.messagebox.askyesno(title='Update from SVN?',message='Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
    should_commit_to_svn = tkinter.messagebox.askyesno(title='Commit to SVN?',message='Auto-commit files to SVN after script is complete?\n\n(Typically answer "Yes")')
    if should_update_from_svn or should_commit_to_svn:
        import xytest
        svn_user, svn_pass, err = xytest.XYTest.ask_user_for_creds()
        svn_userpass_valid = err == 0
    if should_update_from_svn and svn_userpass_valid:
        svn_update_dirs = [pc.dirs[key] for key in ['pos_logs','pos_settings','xytest_logs','xytest_summaries']]
        for d in svn_update_dirs:
            os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
            os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')
else:
    should_update_from_svn = False
    should_commit_to_svn = False

# software initialization and startup
if hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in hwsetup:
    fvc=fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'],printfunc=logwrite,platemaker_instrument=hwsetup['pm_instrument'])
else:
    fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],printfunc=logwrite,save_sbig_fits=hwsetup['save_sbig_fits'])    
fvc.rotation = hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
fvc.scale = hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
fvc.translation = hwsetup['translation']
fvc.exposure_time = hwsetup['exposure_time']

#This will be expanded to intialize multiple petals (all enabled)
ptl = petal.Petal(petal_id = hwsetup['ptl_id'],posids=[],fidids=[], 
                  simulator_on = sim,
                  user_interactions_enabled = True,
                  db_commit_on = False,
                  local_commit_on = True,
                  local_log_on = True,
                  printfunc = logwrite,
                  verbose = False,
                  collider_file = None,
                  sched_stats_on = False,
                  anticollision = None) # valid options for anticollision arg: None, 'freeze', 'adjust'
m = posmovemeasure.PosMoveMeasure([ptl],fvc,printfunc=logwrite)
m.make_plots_during_calib = True
print('Automatic generation of calibration plots is turned ' + ('ON' if m.make_plots_during_calib else 'OFF') + '.')

for ptl in m.petals:
    for posid_this,posmodel in ptl.posmodels.items():
        new_and_changed_files.add(posmodel.state.conf.filename)
        new_and_changed_files.add(posmodel.state.log_path)
    for id_this,state in ptl.states.items():
        print(id_this)
        if id_this.startswith('P') or id_this.startswith('F'):
            new_and_changed_files.add(state.conf.filename)
            new_and_changed_files.add(state.log_path)

# fire up the fiducials
fid_settings_done = m.set_fiducials('on')
print('Fiducials turned on: ' + str(fid_settings_done))

# disable certain features if anticollision is turned off yet it is also a true petal (with close-packed positioenrs)
if ptl.shape == 'petal' and not ptl.anticollision_default:
    should_limit_range = True
else:
    should_limit_range = False

# calibration routines
if should_avoid_hardstop_strikes:
    m.calibrate(mode='rough_avoid_strikes') #testing of this method is in progress, not yet added to new posmovemeasure
else:
    m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
    m.calibrate(mode='rough')
if not should_limit_range:
    m.measure_range(axis='theta')
    m.measure_range(axis='phi')
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=start_filename_timestamp, keep_phi_within_Eo=True)
new_and_changed_files.update(plotfiles)
if not(should_avoid_hardstop_strikes):
    m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN (will be removed)
if should_commit_to_svn and svn_userpass_valid:
    n_total = len(new_and_changed_files)
    n = 0
    for file in new_and_changed_files:
        n += 1
        err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
        err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')

    n_total=0
    these_files_to_commit = ''
    for file in new_and_changed_files:
        these_files_to_commit += ' ' + file
        n_total += 1
    print("these_files_to_commit")
    print(these_files_to_commit)
    print("")
    logwrite('Beginning add + commit of ' + str(n_total) + ' data files to SVN.')
    err_add = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + these_files_to_commit)
    err_commit = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + these_files_to_commit)

# clean up any svn credentials
if svn_user:
    del svn_user
if svn_pass:
    del svn_pass

