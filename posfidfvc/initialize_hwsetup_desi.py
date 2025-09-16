import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))
#sys.path.remove('/software/products/plate_control-trunk/xytest')
#sys.path.remove('/software/products/plate_control-trunk/posfidfvc')
#sys.path.remove('/software/products/plate_control-trunk/petalbox')
#sys.path.remove('/software/products/plate_control-trunk/petal')
#sys.path.remove('/home/msdos/focalplane/plate_control/branches/production/xytest')
#sys.path.remove('/home/msdos/focalplane/plate_control/branches/production/posfidfvc')
#sys.path.remove('/home/msdos/focalplane/plate_control/branches/production/petalbox')
#sys.path.remove('/home/msdos/focalplane/plate_control/branches/production/petal')

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import csv


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


# automated SVN setup
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
# software initialization and startup
if hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in hwsetup:
    fvc=fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'],printfunc=logwrite,platemaker_instrument=hwsetup['pm_instrument'],fvc_role=hwsetup['fvc_role'])
else:
    fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],printfunc=logwrite,save_sbig_fits=hwsetup['save_sbig_fits'])
fvc.rotation = hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
fvc.scale = hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
fvc.translation = hwsetup['translation']
fvc.exposure_time = hwsetup['exposure_time']
try:
    db_commit_on = hwsetup['db_commit_on']
except:
    db_commit_on = False

try:
    petal_proxy = hwsetup['use_petal_proxy']
    from DOSlib.proxies import Petal
except:
    petal_proxy = False

if petal_proxy:
    ptl = Petal(hwsetup['ptl_id'])
else:
    #shape = 'asphere' if hwsetup['plate_type'] == 'petal' else 'flat'
    ptl = petal.Petal(petal_id = hwsetup['ptl_id'],posids=[],fidids=[],
                      simulator_on = sim,
                      user_interactions_enabled = True,
                      db_commit_on = db_commit_on,
                      local_commit_on = not(db_commit_on),
                      local_log_on = True,
                      printfunc = logwrite,
                      verbose = False,
                      collider_file = None,
                      sched_stats_on = False,
                      anticollision = None) # valid options for anticollision arg: None, 'freeze', 'adjust'
posids=ptl.posids
fidids=ptl.fidids
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

m.n_extradots_expected = hwsetup['num_extra_dots']

# check ids with user
text = '\n\nHere are the known positioners and fiducials:\n\n'
text += str(len(posids)) + ' POSITIONERS:'
for posid in posids:
    text += '\n  ' + format(posid+':','11s') + 'busid = ' + format(str(ptl.get_posfid_val(posid,'BUS_ID')),'5s') + '  canid = ' + format(str(ptl.get_posfid_val(posid,'CAN_ID')),'5s')
text += '\n\n' + str(len(fidids)) + ' FIDUCIALS:'
for fidid in fidids:
    text += '\n  ' + format(fidid+':','11s') + 'busid = ' + format(str(ptl.get_posfid_val(fidid,'BUS_ID')),'5s') + '  canid = ' + format(str(ptl.get_posfid_val(fidid,'CAN_ID')),'5s') + '  ndots = ' + str(ptl.get_posfid_val(fidid,'N_DOTS'))
text += '\n  num extra dots = ' + str(m.n_extradots_expected) + '\n'
print(text)
message='A list of all the positioner and fiducials has been printed to the stdout text console.\n\nPlease check each of these carefully.\n\nAre they all correct?'
message_local='Please check the above list of all the positioners and fiducials carefully.\nAre they all correct?\n'
if not tkinter.messagebox.askyesno(title='IDs correct?',message=message):
    tkinter.messagebox.showinfo(title='Quitting',message='Ok, will quit now so the IDs can be fixed.')
    gui_root.withdraw()
    sys.exit(0)

# determine if we need to identify fiducials and positioners this run
should_identify_fiducials = True
should_identify_positioners = True
extradots_filename = pc.dirs['temp_files'] + os.path.sep + 'extradots.csv'
extradots_existing_data = []
if m.n_extradots_expected > 0 and os.path.isfile(extradots_filename):
    if tkinter.messagebox.askyesno(title='Load extra dots data?',message='An existing extra dots data file was found at ' + extradots_filename + '. Load it and skip re-identification of fiducials?'):
        should_identify_fiducials = False
        with open(extradots_filename,'r',newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                extradots_existing_data.append([row['x_pix'],row['y_pix']])
        should_identify_positioners = tkinter.messagebox.askyesno(title='Identify positioners?',message='Identify positioner locations?\n\n(Say "NO" only if you are confident of their stored locations from a previous run.)')
else:
    response1 = tkinter.messagebox.askyesno(title='Identify fid ?',message='Identify fiducial locations?\n\n(Say "NO" only if you are confident of their stored locations from a previous run.)')
    response2 = tkinter.messagebox.askyesno(title='Identify pos?',message='Identify positioner locations?\n\n(Say "NO" only if you are confident of their stored locations from a previous run.)')
    should_identify_fiducials = response1
    should_identify_positioners = response2

# close the gui
gui_root.withdraw()

# fire up the fiducials
fid_settings_done = m.set_fiducials('on')
print('Fiducials turned on: ' + str(fid_settings_done))

# disable certain features if anticollision is turned off yet it is also a true petal (with close-packed positioenrs)
if ptl.shape == 'petal' and not ptl.anticollision_default:
    should_limit_range = True
else:
    should_limit_range = False

# calibration routines
m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
if should_identify_fiducials:
    m.identify_fiducials()
    with open(extradots_filename,'w',newline='') as file:
        writer = csv.DictWriter(file,fieldnames=['x_pix','y_pix'])
        writer.writeheader()
        for xy in m.extradots_fvcXY:
            writer.writerow({'x_pix':xy[0],'y_pix':xy[1]})
        if m.fvc.fvcproxy: #Remind FVC that it needs to look for all dots, not all dots without a fiducial
            m.fvc.fvcproxy.send_fvc_command('make_targets',len(posids) + m.n_ref_dots)
else:
    m.extradots_fvcXY = extradots_existing_data
if should_identify_positioners:
    m.identify_positioners_2images()
    if m.fvc.fvcproxy: #Remind FVC that it needs to look for all dots, not all dots without a fiducial
        m.fvc.fvcproxy.send_fvc_command('make_targets',len(posids) + m.n_ref_dots)

    #m.identify_many_enabled_positioners(list(m.all_posids))
    #m.identify_disabled_positioners()

#print("Positioners are identified")
#m.rehome()
m.calibrate(mode='rough')
if not should_limit_range:
    m.measure_range(axis='theta')
    m.measure_range(axis='phi')
m.rehome() #REMOVE put in as test
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=start_filename_timestamp, keep_phi_within_Eo=True)
new_and_changed_files.update(plotfiles)
m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN
if should_commit_to_svn and svn_userpass_valid:
    #n_total = len(new_and_changed_files)
    #n = 0
    #for file in new_and_changed_files:
    #    n += 1
    #    err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
    #    err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
    #    print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')

    n_total=0
    these_files_to_commit = ''
    for file in new_and_changed_files:
        these_files_to_commit += ' ' + file
        n_total += 1
    print("these_files_to_commit")
    print(these_files_to_commit)
    print("")
    logwrite('Beginning add + commit of ' + str(n_total) + ' data files to SVN.')
    err_add = os.system('svn add --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive ' + these_files_to_commit)
    err_commit = os.system('svn commit --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + these_files_to_commit)

# clean up any svn credentials
if svn_user:
    del svn_user
if svn_pass:
    del svn_pass

