import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import instrmaker
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import csv
import getpass

# start set of new and changed files
new_and_changed_files = set()

# unique timestamp and fire up the gui
start_filename_timestamp = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()

# get the station config info
message = 'Pick hardware setup file.'
hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# ask user whether to auto-generate a platemaker instrument file
message = 'Should we auto-generate a platemaker instrument file?'
should_make_instrfile = tkinter.messagebox.askyesno(title='Make PM file?',message=message)

# are we in simulation mode?
sim = hwsetup['fvc_type'] == 'simulator'

# update log and settings files from the SVN
if not(sim):
    print("")
    svn_user=input("Please enter your SVN username: ")
    svn_pass=getpass.getpass("Please enter your SVN password: ")      
    svn_auth_err=False
    svn_update_dirs = [pc.dirs[key] for key in ['pos_logs','pos_settings','xytest_logs','xytest_summaries']]
    should_update_from_svn = tkinter.messagebox.askyesno(title='Update from SVN?',message='Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
    if should_update_from_svn:
        if svn_auth_err:
            print('Could not validate svn user/password.')
        else:
            for d in svn_update_dirs:
                os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
                os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')

# software initialization and startup
fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'])    
fvc.rotation = hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
fvc.scale = hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
posids = hwsetup['pos_ids']
fidids = hwsetup['fid_ids']
ptl = petal.Petal(petal_id = hwsetup['ptl_id'],
                  posids = posids,
                  fidids = fidids,
                  simulator_on = sim,
                  user_interactions_enabled = True,
                  db_commit_on = False,
                  local_commit_on = True,
                  local_log_on = True,
                  printfunc = print,
                  verbose = False,
                  collider_file = None,
                  sched_stats_on = False,
                  anticollision = None) # valid options for anticollision arg: None, 'freeze', 'adjust'
m = posmovemeasure.PosMoveMeasure([ptl],fvc)
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
instr = instrmaker.InstrMaker(hwsetup['plate_type'],ptl,m,fvc,hwsetup)

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

# check if auto-svn commit is desired
if not sim and not svn_auth_err:
    should_commit_to_svn = tkinter.messagebox.askyesno(title='Commit to SVN?',message='Auto-commit files to SVN after script is complete?\n\n(Typically answer "Yes")')

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
    response = tkinter.messagebox.askyesno(title='Identify fid and pos?',message='Identify fiducial and positioner locations?\n\n(Say "NO" only if you are confident of their stored locations from a previous run.)')
    should_identify_fiducials = response
    should_identify_positioners = response

# close the gui
gui_root.withdraw()

# fire up the fiducials
fid_settings_done = m.set_fiducials('on')
print('Fiducials turned on: ' + str(fid_settings_done))

# disable certain features if anticollision is turned off yet it is also a true petal (with close-packed positioenrs)
if hwsetup['plate_type'] == 'petal' and not ptl.anticollision_default:
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
else:
    m.extradots_fvcXY = extradots_existing_data
if should_identify_positioners:
    m.identify_positioner_locations()
if should_make_instrfile:
    instr.make_instrfile()
    instr.push_to_db()
if not should_limit_range:
    m.measure_range(axis='theta')
    m.measure_range(axis='phi')
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=start_filename_timestamp)
new_and_changed_files.update(plotfiles)
m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN
if should_commit_to_svn:
    n_total = len(new_and_changed_files)
    n = 0
    for file in new_and_changed_files:
        n += 1
        err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
        err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')
