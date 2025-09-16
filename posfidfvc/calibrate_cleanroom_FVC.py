#! /usr/bin/env python3

# Script to calibrate FVC using the DOSlib.proxies module
# This script assumes that  the FVC, PETAL and ILLUMINATOR are running (either devices or roles - if roles,
# join_instance <name> must be called before running this script.
import os,sys,time
sys.path.append(os.path.abspath('/home/msdos/focalplane/plate_control/trunk/petal/'))
sys.path.append(os.path.abspath('/home/msdos/focalplane/plate_control/trunk/posfidfvc/'))
sys.path.append(os.path.abspath('/home/msdos/focalplane/plate_control/trunk/xytest/'))

sys.path.remove('/software/products/plate_control-trunk/xytest')
sys.path.remove('/software/products/plate_control-trunk/posfidfvc')
sys.path.remove('/software/products/plate_control-trunk/petalbox')
sys.path.remove('/software/products/plate_control-trunk/petal')


from DOSlib.proxies import FVC, Illuminator, Petal
#import pdb
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import csv
import petal
import posconstants as pc


# start set of new and changed files
new_and_changed_files = set()
gui_root = tkinter.Tk()

#PULL IN HWSETUP FILE
# get the station config info
message = 'Pick hardware setup file.'
hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)

hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)
new_and_changed_files.add(hwsetup.filename)

# Select petal_id
pid = hwsetup['ptl_id'] #48

# FVC exposure time
exptime = hwsetup['exposure_time'] #2.0  exptime for fvchandler is hard-coded as 1.0s. Shoudl we change it?

sim = hwsetup['fvc_type'] == 'simulator'

#Set Petal
myPetal=Petal('2')
ptl = petal.Petal(petal_id = pid,posids=[],fidids=[],
                  simulator_on = sim,
                  user_interactions_enabled = True,
                  db_commit_on = False,
                  local_commit_on = True,
                  local_log_on = True,
                  printfunc = print,
                  verbose = False,
                  collider_file = None,
                  sched_stats_on = False,
                  anticollision = None)

# number of spots
posids = ptl.posids
fidids = ptl.fidids
nspots = len(posids)
print(nspots)
for fidid in fidids:
    nspots += int(ptl.get_posfid_val(fidid,'N_DOTS'))
print(hwsetup['num_extra_dots'])
nspots += hwsetup['num_extra_dots']
print(nspots)
text = '\n\n' + str(len(fidids)) + ' FIDUCIALS:'
for fidid in fidids:
    text += '\n  ' + format(fidid+':','11s') + 'busid = ' + format(str(ptl.get_posfid_val(fidid,'BUS_ID')),'5s') + '  canid = ' + format(str(ptl.get_posfid_val(fidid,'CAN_ID')),'5s') + '  ndots = ' + str(ptl.get_posfid_val(fidid,'N_DOTS'))
print(text)
print("The number of expected dots is %d" % nspots)

# Create the FVC proxy for the em PlateMaker instrument (which uses petal 48)
myFVC = FVC(hwsetup['pm_instrument'])

# Create Petal
petal_id = str(int(pid))


# Calibration sequence
#   fiducials, fiber backight off
#   FVC calibrate_bias dark_flag=False
#   fiducials, fiber backlight on
#   FVC calibrate_image

# TURN OFF ALL LIGHTS
print("Turning off the fiducials")
myPetal.set_fiducials(setting=0)
tkinter.messagebox.showwarning("TURN OFF THE LIGHTS","Make sure backlight LED is OFF and fiducials are OFF")

print('Fiducials: \n%r' % myPetal.get_fiducials())
print('Setting FVC exposure time to %f' % exptime)
myFVC.set(exptime=exptime)
print('calibrate bias')
myFVC.calibrate_bias(dark_flag=False)

#TURN LIGHTS BACK ON
print('lights back on')
myPetal.set_fiducials(setting=15.0)
tkinter.messagebox.showwarning("TURN ON THE LIGHTS", "Make sure backlight LED is ON and fiducials are ON")
print('Fiducials: \n%r' % myPetal.get_fiducials())
#nspots = len(myPetal.get_positioners()) + 4*len(myPetal.get_fiducials())
print('Petal has %d spots' % nspots)
myFVC.make_targets(num_spots=nspots)
print('calibrate image')
myFVC.calibrate_image()

print("That's All Folks!")
