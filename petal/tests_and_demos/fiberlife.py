'''fiberlife.py
This script is for life-testing a bunch of fibers that are installed in positioners.
'''

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
import petal

# configure the test hardware
pos_ids = [] # list of positioners being tested
ptl_id = 10 # pc number of the petal controller

# configure the test
should_simulate = True

# configure the log writer
def logwrite(string):
    print(string)
    # and save to some log file?

# retrieve latest log files and settings from svn

# initialize the "petal" of positioners
ptl = petal.Petal(ptl_id, pos_ids, fid_ids=[], simulator_on=should_simulate, printfunc=logwrite)
ptl.anticollision_default = False

# define some convenience move functions
def rehome_all_to_hardstops():
    ptl.request_homing(pos_ids)
    ptl.schedule_send_and_execute_moves()



# ask questions


# ask user how many random moves to do now
# give opportunity to review what is about to happen
#  - expected time it will take (1000 moves per hour)
#  - how many moves each positioner has on it now, and how many it will have on it at end, and the delta

# initialize the random positions table

# run the random moves

# post log files and settings to svn