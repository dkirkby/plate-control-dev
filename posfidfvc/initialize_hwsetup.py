import os
import sys
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
import configobj

# unique timestamp and fire up the gui
start_filename_timestamp = pc.filename_timestamp_str_now()
gui_root = tkinter.Tk()

# update log and settings files from the SVN
svn_user, svn_pass, svn_auth_err = xytest.XYTest.ask_user_for_creds(should_simulate=False)
svn_update_dirs = [pc.pos_logs_directory, pc.pos_settings_directory, pc.xytest_logs_directory, pc.xytest_summaries_directory]
should_update_from_svn = tkinter.messagebox.askyesno(title='Update from SVN?',message='Overwrite any existing local positioner log and settings files to match what is currently in the SVN?')
if should_update_from_svn:
    if svn_auth_err:
        print('Could not validate svn user/password.')
    else:
        for d in svn_update_dirs:
            os.system('svn update --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d)
            os.system('svn revert --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + d + '*')
new_and_changed_files = set()

# get the station config info
message = 'Pick hardware setup file.'
hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.hwsetups_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# software initialization and startup
fvc = fvchandler.FVCHandler(hwsetup['fvc_type'])    
fvc.rotation = hwsetup['rotation']
fvc.scale = hwsetup['scale']
sim = fvc.fvc_type == 'simulator'
pos_ids = hwsetup['pos_ids']
fid_ids = hwsetup['fid_ids']
ptl = petal.Petal(hwsetup['ptl_id'], pos_ids, fid_ids, simulator_on=sim)
ptl.anticollision_default = False
m = posmovemeasure.PosMoveMeasure([ptl],fvc)
m.make_plots_during_calib = True
print('Automatic generation of calibration plots is turned ' + ('ON' if m.make_plots_during_calib else 'OFF') + '.')
for ptl in m.petals:
    for posmodel in ptl.posmodels:
        new_and_changed_files.add(posmodel.state.unit.filename)
        new_and_changed_files.add(posmodel.state.log_path)
    for fidstate in ptl.fidstates.values():
        new_and_changed_files.add(fidstate.unit.filename)
        new_and_changed_files.add(fidstate.log_path)

# TEMPORARY HACK until individual fiducial dot locations tracking is properly handled
m.extradots_fid_state = ptl.fidstates[hwsetup['extradots_id']]

# check ids with user
print('\n\nHere are the known positioners and fiducials:\n')
print(str(len(pos_ids)) + ' POSITIONERS:')
for pos_id in pos_ids:
    print('  ' + format(pos_id+':','11s') + 'busid = ' + format(str(ptl.get(pos_id,'BUS_ID')),'5s') + '  canid = ' + format(str(ptl.get(pos_id,'CAN_ID')),'5s'))
print('\n' + str(len(fid_ids)) + ' FIDUCIALS:')
for fid_id in fid_ids:
    print('  ' + format(fid_id+':','11s') + 'busid = ' + format(str(ptl.get_fids_val(fid_id,'BUS_ID')[0]),'5s') + '  canid = ' + format(str(ptl.get_fids_val(fid_id,'CAN_ID')[0]),'5s') + '  ndots = ' + str(ptl.get_fids_val(fid_id,'N_DOTS')[0]))
print('\nPlease check each of these carefully.',end=' ')
ids_unchecked = True
while ids_unchecked:
    response = input('Are these all correct (yes/no): ')
    if 'n' in response.lower():
        print('Exiting, to give user a chance to fix the problem(s).\n\n')
        sys.exit(0)
    elif 'y' in response.lower():
        ids_unchecked = False
    else:
        print('Respond yes or no.')

# check if auto-svn commit is desired
if not svn_auth_err:
    should_commit_to_svn = tkinter.messagebox.askyesno(title='Commit to SVN?',message='Auto-commit files to SVN after script is complete?\n\n(Typically answer "Yes")')

# make sure control is enabled for all positioners
for ptl in m.petals:
    for pos_id in ptl.posids:
        ptl.set(pos_id, 'CTRL_ENABLED', True)
	
# calibration routines
m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
m.identify_fiducials()
m.identify_positioner_locations()
m.measure_range(axis='theta')
m.measure_range(axis='phi')
plotfiles = m.calibrate(mode='arc', save_file_dir=pc.xytest_plots_directory, save_file_timestamp=start_filename_timestamp)
new_and_changed_files.update(plotfiles)
m.park() # retract all positioners to their parked positions

# commit logs and settings files to the SVN
if should_commit_to_svn and not svn_auth_err:
    n_total = len(new_and_changed_files)
    n = 0
    for file in new_and_changed_files:
        n += 1
        err1 = os.system('svn add --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive ' + file)
        err2 = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from initialize_hwsetup script" ' + file)
        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1) + ' (add) and ' + str(err2) + ' (commit)')

# close the gui
gui_root.withdraw()

# COMMENTS ON FUTURE WORK BELOW...
# --------------------------------
# VERIFICATIONS AND CALIBRATIONS SEQUENCE:
# (TO IMPLEMENT IN FULLY AUTOMATED FASHION (IN THIS ORDER)
#   [note, not doing focus here -- too difficult to automate with our astronomy cameras' lack of control over lenses]
#   - look up the can_ids for all the positioners, and validate that the number of unique can_ids matches the number of positioners
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

"""EMAIL FROM STEVE ON STARTING POINT FOR INSTRUMENT PARAMETERS CONFIG FILE
All,

Here is a sample configuration file for an "instrument".  Let us call the instrument "em" for engineering model (or whatever you want).
Pound sign (#) is a comment line.  Blank lines are OK.  I will need to write up the meaning of fvcrot, fvcxoff, fvcyoff, and fvcflip, since the operations are not commutative.  None of the parameters is mandatory.

Steve

File is called em.par

#First 3 parameters are appropriate for protoDESI FLI camera.
fvcnrow 6000
fvcncol 6000
fvcpixmm .006

#Scale and orientation of FVC camera - these are appropriate for protoDESI
#fvcmag is demagnification from focal plane to FVC ccd.
fvcmag 21.842
fvcrot  0.
fvcxoff 0.
fvcyoff 0.
fvcflip 1

#Flat or aspheric focal plane?
asphere 1
"""



"""HOW TO READ AN FVC IMAGE AND GIVE PLATEMAKER THE RIGHT ORIENTATION / VALUES FOR INSTRUMENT FILE:
See picture that steve made.
I posted it at:
https://desi.lbl.gov/trac/wiki/DOS/PositionerLoop    
"""

           
"""COMMENTS FROM ERIC ON FORMAT OF FIDUCIALS DATA FILE FOR PLATEMAKER
PER EMAIL 2017-02-10, THIS STUFF DOES GO INTO THE .par INSTRUMENT FILE

Internally to Steve, it’s the same format as the files he uses for positioners and positioner_calib. There is an example in $PLATEMAKER_DIR/test/data/testinst1/fiducial-testinst1.dat, which is just a copy of the defualt file in dervishtools, trunk/desi/etc/default/fiducial-default.dat.

It looks like this:

#ProtoDESI - actual Fiducial positions
#serial   q        s     flags
1100  201.29864  57.62478  0
1118  158.65941  57.62944  0
1102  223.32243  61.13366  0
1103  136.73378  61.23237  0
1117  194.16599  37.48592  0
1106  163.62382  37.03236  0
1107  247.73668  45.35403  0
1108  179.81027  17.21309  0
1116  112.26703  45.38117  0
1115  270.01638  55.98100  0
1111  89.97447  56.10901  0
1112  293.97813  61.37240  0
1113  57.94744  66.04711  0
1114  9.49977  60.87482  0
1101  16.43042  37.25640  0
1109  263.43168  37.11059  0

(but actually use flag 8 indicating it is a fiducial)
"""
