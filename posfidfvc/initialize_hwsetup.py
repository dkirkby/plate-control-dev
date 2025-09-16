import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
	sys.path.append(os.path.abspath(basepath+'/posfidfvc/'))
	sys.path.append(os.path.abspath(basepath+'/xytest/'))
else:
	sys.path.append(os.path.abspath('../petal/'))
	sys.path.append(os.path.abspath('../posfidfvc/'))
	sys.path.append(os.path.abspath('../xytest/'))

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import xytest
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import scipy
import astropy
import csv
import numpy as np
from lmfit import minimize, Parameters
import matplotlib.pyplot as plt
import getpass
import time
import svn.local

class _read_key:
	def __init__(self):
		import tty, sys

	def __call__(self):
		import sys, tty, termios
		fd = sys.stdin.fileno()
		old_settings = termios.tcgetattr(fd)
		try:
			tty.setraw(sys.stdin.fileno())
			ch = sys.stdin.read(1)
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
		return ch

# added optional use of local presets
USE_LOCAL_PRESETS=False
arguments = sys.argv[1:]
try:
	if len(arguments) > 0:
		if arguments[0].lower()=='uselocal': USE_LOCAL_PRESETS=True
except:
	pass

# unique timestamp and fire up the gui
start_filename_timestamp = pc.filename_timestamp_str()

# start set of new and changed files
new_and_changed_files = set()

if USE_LOCAL_PRESETS:
	try:
		presets_file=os.environ['TEST_PRESETS_CONFIG']
		test_base_path=os.environ['TEST_BASE_PATH']
		presets = configobj.ConfigObj(presets_file,unrepr=True)
		hwsetup_conf=presets['hwsetup_conf']
		should_update_from_svn=presets['should_update_from_svn']
		should_commit_to_svn=presets['should_commit_to_svn']
		should_identify_fiducials = presets['should_identify_fiducials']
		should_identify_positioners = presets['should_identify_positioners']
	except:
		print("Can not use local presets.")
		USE_LOCAL_PRESETS=False
if USE_LOCAL_PRESETS:
	print("")
	print("  Using code tag: "+os.environ['TEST_TAG'])
	print("")
	print("The following presets will be used:")
	print("")
	print("  Hardware setup file: "+str(hwsetup_conf))
	print("  Should update from SVN: "+str(should_update_from_svn))
	print("  Should commit to SVN: "+str(should_commit_to_svn))
	print("  Should identify positioners: "+str(should_identify_positioners))
	print("  Should identify fiducials: "+str(should_identify_fiducials))
	print("")
	print("  Is this correct? (hit 'y' for yes or any key otherwise)")
	sel=_read_key().__call__()
	if sel.lower() !='y':
		USE_LOCAL_PRESETS=False
	else:
		print("Local presets will be used")
		hwsetup_conf=test_base_path+'/fp_settings/hwsetups/'+hwsetup_conf

# present settings from preset file and check if okay

# if not okay set USE_LOCAL_PRESETS to False
if not USE_LOCAL_PRESETS:
	gui_root = tkinter.Tk()

# get the station config info
if not USE_LOCAL_PRESETS:
	message = 'Pick hardware setup file.'
	hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)

hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# ask user whether to auto-generate a platemaker instrument file

# are we in simulation mode?
sim = hwsetup['fvc_type'] == 'simulator'

# update log and settings files from the SVN
if not(sim):
	if not USE_LOCAL_PRESETS:
		svn_user, svn_pass, svn_auth_err = xytest.XYTest.ask_user_for_creds(should_simulate=sim)
	else:
		try:
			print("")
			svn_user=input("Please enter your SVN username: ")
			svn_pass=getpass.getpass("Please enter your SVN password: ")
			svn_auth_err=False
		except:
			svn_auth_err=True

	svn_update_dirs = [pc.dirs[key] for key in ['pos_logs','pos_settings','xytest_logs','xytest_summaries']]

	if not USE_LOCAL_PRESETS:
		should_update_from_svn = tkinter.messagebox.askyesno(title='Update from SVN?',message='Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
	if should_update_from_svn:
		if svn_auth_err:
			print('Could not validate svn user/password.')
		else:
			for d in svn_update_dirs:
				os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
				os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')


# software initialization and startup
if hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in hwsetup:
    fvc=fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'],platemaker_instrument=hwsetup['pm_instrument'])
else:
    fvc=fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'])
#fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'])
fvc.rotation = hwsetup['rotation']
fvc.scale = hwsetup['scale']
posids = hwsetup['pos_ids']
fidids = hwsetup['fid_ids']
shape = 'asphere' if hwsetup['plate_type'] == 'petal' else 'flat'
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
m = posmovemeasure.PosMoveMeasure([ptl],fvc)
m.make_plots_during_calib = True
print('Automatic generation of calibration plots is turned ' + ('ON' if m.make_plots_during_calib else 'OFF') + '.')
for ptl in m.petals:
	for posmodel in ptl.posmodels:
		new_and_changed_files.add(posmodel.state.conf.filename)
		new_and_changed_files.add(posmodel.state.log_path)
	for fidstate in ptl.fidstates.values():
		new_and_changed_files.add(fidstate.conf.filename)
		new_and_changed_files.add(fidstate.log_path)
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
if not USE_LOCAL_PRESETS:
	if not tkinter.messagebox.askyesno(title='IDs correct?',message=message):
		tkinter.messagebox.showinfo(title='Quitting',message='Ok, will quit now so the IDs can be fixed.')
		gui_root.withdraw()
		sys.exit(0)
else:
	print("")
	print(message_local)
	print("  Hit 'y' for yes or any key otherwise)")
	sel=_read_key().__call__()
	if sel.lower() !='y':
		print('Ok, will quit now so the IDs can be fixed.')
		sys.exit()


# check if auto-svn commit is desired
if not sim and not svn_auth_err:
	if not USE_LOCAL_PRESETS:
		should_commit_to_svn = tkinter.messagebox.askyesno(title='Commit to SVN?',message='Auto-commit files to SVN after script is complete?\n\n(Typically answer "Yes")')
else:
	should_commit_to_svn = False

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
	if not USE_LOCAL_PRESETS:
		response = tkinter.messagebox.askyesno(title='Identify fid and pos?',message='Identify fiducial and positioner locations?\n\n(Say "NO" only if you are confident of their stored locations from a previous run.)')
		should_identify_fiducials = response
		should_identify_positioners = response

# close the gui
if not USE_LOCAL_PRESETS:
	gui_root.withdraw()

# fire up the fiducials
fid_settings_done = m.set_fiducials('on')
print('Fiducials turned on: ' + str(fid_settings_done))

# make sure control is enabled for all positioners
for ptl in m.petals:
	for posid in ptl.posids:
		ptl.set_posfid_val(posid, 'CTRL_ENABLED', True)

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
m.calibrate(mode='rough')
if not should_limit_range:
	m.measure_range(axis='theta')
	m.measure_range(axis='phi')
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=start_filename_timestamp)
new_and_changed_files.update(plotfiles)
m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN

xtime0=time.time()
if should_commit_to_svn:
	if not USE_LOCAL_PRESETS:
		n_total = len(new_and_changed_files)
		n = 0
		for file in new_and_changed_files:
			n += 1
			err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
			err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
			print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')
	else:
		commit_message="autocommit from initialize_hwsetup script"
		n_total = len(new_and_changed_files)
		flist=list(new_and_changed_files)
		n_add = 0
		loc_repo=svn.local.LocalClient('/home/msdos/focalplane/plate_control/trunk',username=svn_user,password=svn_pass)
		for file in flist:
			try:
				loc_repo.add(file)
				n_add=n_add+1
			except:
				pass
		print("Added "+str(n_add)+' files out of '+str(n_total))
		try:
			loc_repo.commit(commit_message,flist)
		except:
			import datetime
			now = datetime.datetime.now()
			datestr= now.strftime('%y%m%d:%H:%M')
			xfer_file=	'svnxfer_'+datestr+'.lst'
			print("Automated SVN commit failed - please transfer files manually.")
			print("The list of files to be transferred was written out to ('"+xfer_file+"').lst')")
			with open(xfer_file,'w') as f:
				f.write(str(flist))
print("SVN upload took "+str(time.time()-xtime0)+" seconds")
print("")
print("Ready to run XYtest")

# COMMENTS ON FUTURE WORK BELOW...
# --------------------------------
# VERIFICATIONS AND CALIBRATIONS SEQUENCE:
# (TO IMPLEMENT IN FULLY AUTOMATED FASHION (IN THIS ORDER)
#   [note, not doing focus here -- too difficult to automate with our astronomy cameras' lack of control over lenses]
#   - look up the canids for all the positioners, and validate that the number of unique canids matches the number of positioners
#   - calibrate each fiducial
#       - get relative brightness at a standard setting
#   - calibrate fiber illumination
#       - get relative brightness at a standard setting
#   - select new optimal combination of settings for:
#       - fiducial brightness
#       - fiber brightness
#           - if manual setting, tell user:
#               - how much to change power level
#               - or if there is too much variation, which spots look dim (make a plot where the point labels are the relative brightness)
#       - camera exposure time (may prefer to leave this fixed, for test timing issues)
#   (rehome)
#   - verify each positioner moves
#   - verify number of extra ref dots
#   - verify positioner motor directions are correct:
#       - theta, by moving a few degrees with phi arm a little extended
#           - use this to set first rough fvc scale
#       - phi, by moving 180 degress with phi arm retracted, and dot shouldn't move much
#   (quick calibration)
#   - using plate_type, which defines the possible device locations:
#       - which devices are in which holes
#       - calculate fvc rotation, offset, and scale
#       - calculate precise xy offsets for each positioner, and for fiducial dots, and record these to their calib files
#       - make a platemaker instrument file if needed
#   - phi bearing bond integrity
#       - we can detect if phi bearing bond is broken by ramming ferrule holder hard against stop and looking for lateral prying motion
#       - this will be a great one to generally automate, and perhaps incor
#       1. ram hard stop with no back-off and measure
#       2. back off a few degrees and re-measure
#       3. do a few more points on the phi arc
#       4. calculate: if there is any significant radial component w.r.t. phi arc center when you rammed hard stop, then there was prying / broken bond
