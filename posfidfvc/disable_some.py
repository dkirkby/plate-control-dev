import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import configobj
import csv

sim=False
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


# software initialization and startup
# software initialization and startup
ptl = petal.Petal(petal_id = hwsetup['ptl_id'],
                  posids=[],fidids=[],  
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
posids_all=list(ptl.posids)
posids_all.sort()

for posid in posids_all:
    print(posid+'')
t=input('Enter the posids list you want to disable')
cmd='posid_list='+t
a=exec(cmd)

for posid in posid_list:
    print(posid+'')
    ptl.set_posfid_val(posid, 'CTRL_ENABLED', False)
    
ptl.commit(log_note='Disable Some Positioners')
print('Have Disabled',posid_list)

