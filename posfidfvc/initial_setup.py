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
