# THIS IS THE BEGINNINGS OF A NEW SCRIPT WHICH WE WILL RUN WHENEVER WE SET UP
# HARDWARE ON A TEST STAND. ALL THE INITIAL CALIBRATIONS AND CHECKS HAPPEN HERE.
# THEREAFTER, WE DON'T HAVE TO REPEAT THESE ALL THE TIME FOR EVERY XY ACCURACY
# TEST.

import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petal
import posmovemeasure
import fvchandler
import posconstants as pc

# software initialization and startup
sim = False
pos_ids = ['M00095','M00072']#,'M00077','M00078','M00094','M00098','M00112','M00105','M00084','M00095','M00072','M00036','M00037','M00047','M00048','M00107']
fid_ids = ['F017']
ptl_ids = [42]
petals = [petal.Petal(ptl_ids[0], pos_ids, fid_ids, simulator_on=sim)] # single-petal placeholder for generality of future implementations, where we could have a list of multiple petals, and need to correlate pos_ids and fid_ids to thier particular petals
for ptl in petals:
    ptl.anticollision_default = False
if sim:
    fvc = fvchandler.FVCHandler('simulator')
else:
    fvc = fvchandler.FVCHandler('SBIG')      
fvc.rotation = 0 # deg
fvc.scale = 0.2 # mm/pixel
m = posmovemeasure.PosMoveMeasure(petals,fvc)
start_timestamp = pc.timestamp_str_now()

# calibration routines
m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
m.identify_fiducials() 
m.identify_positioner_locations()
m.calibrate(mode='quick', save_file_dir=pc.test_logs_directory, save_file_timestamp=start_timestamp) # need to calibrate prior to measuring  physical travel ranges (where phi arms get extended, and need some reasonable values for theta offsets before doing such extensions)
m.measure_range(axis='theta')
m.measure_range(axis='phi')
m.rehome() # rehome again because range measurements intentionally ran against hardstops, messing up shaft angle counters
m.one_point_calibration() # do a measurement at one point with fvc after the blind rehome
m.park() # retract all positioners to their parked positions
           

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