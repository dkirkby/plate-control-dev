# THIS IS THE BEGINNINGS OF A NEW SCRIPT WHICH WE WILL RUN WHENEVER WE SET UP
# HARDWARE ON A TEST STAND. ALL THE INITIAL CALIBRATIONS AND CHECKS HAPPEN HERE.
# THEREAFTER, WE DON'T HAVE TO REPEAT THESE ALL THE TIME FOR EVERY XY ACCURACY
# TEST.


# initial homing
m.rehome(pos_ids='all')

# identify fiducials
m.identify_fiducials()
    
# identification of which positioners are in which (x,y) locations on the petal
m.identify_positioner_locations()

# quick pre-calibration, especially because we need some reasonable values for theta offsets prior to measuring physical travel ranges (where phi arms get extended)
m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes())

# measure the physical travel ranges of the theta and phi axes by ramming hard limits in both directions
m.measure_range(pos_ids='all', axis='theta')
m.measure_range(pos_ids='all', axis='phi')
m.rehome(pos_ids='all')
m.calibrate(pos_ids='all', mode='quick', save_file_dir=log_directory, save_file_timestamp=log_timestamp_with_notes()) # needed after having struck hard limits

           


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