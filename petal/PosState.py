# imports here

class PosState(object):
    """State variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object. Data structure is kept to a straightforward single
    key / single value scheme.
    """
    
    def __init__(self):
        pass

# Parker, as I've been working the code into shape I've modified / removed
# some of the state variables. These are the changes I've tracked:

    # keep these    
    'SERIAL_ID'
    'BUS_ID'
    'LENGTH_R1', 'LENGTH_R2'
    'POLYN_T0', 'POLYN_T1', 'POLYN_T2'
    'POLYN_P0', 'POLYN_P1', 'POLYN_P2'
    'POLYN_X0', 'POLYN_X1'
    'POLYN_Y0', 'POLYN_Y1'
    'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P'
    'BACKLASH'
    'PRINCIPLE_HARDSTOP_DIR_T', 'PRINCIPLE_HARDSTOP_DIR_P'
    'ALLOW_EXCEED_LIMITS'
    'LIMIT_SEEK_EXCEED_RANGE_FACTOR'
    'SHOULD_DEBOUNCE_HARDSTOPS'
    'BACKLASH_REMOVAL_BACKUP_FRACTION'
    'CURR_SPIN_UP_DOWN', 'CURR_CRUISE', 'CURR_CREEP'
    'GEAR_T', 'GEAR_P'
    
    # rename these
    'MOTOR_CW_DIR_T' --> 'MOTOR_CCW_DIR_T' # ... and change comments to 'counter-clockwise'
    'MOTOR_CW_DIR_P' --> 'MOTOR_CCW_DIR_P' # ... and change comments to 'counter-clockwise'
    'BACKLASH_REMOVAL_DIR_T' --> 'ANTIBACKLASH_FINAL_MOVE_DIR_T' # +1 or -1 ... remove cw / ccw statements in old comment
    'BACKLASH_REMOVAL_DIR_P' --> 'ANTIBACKLASH_FINAL_MOVE_DIR_P' # +1 or -1 ... remove cw / ccw statements in old comment
    'ONLY_CREEP_TO_LIMITS' --> 'CREEP_TO_LIMITS'
    'CURR_HOLD_AFTER_CREEP' --> 'HOLD_CURRENT'
    
    # new ones
    'DEVICE_ID'           = 'test' # string, id number of location on the petal or plate
    'PETAL_ID'            = 'test' # string, id of the petal or plate it is mounted on
    'MOTOR_ID_T'          = 1      # 0 or 1, which motor number in firmware commands corresponds to theta
    'MOTOR_ID_P'          = 0      # 0 or 1, which motor number in firmware commands corresponds to phi
    'SPINUPDOWN_DISTANCE' = 628.2  # float, distance at the motor shaft in deg over which to spin up to cruise speed or down from cruise speed
    'CREEP_PERIOD'        = 2      # int, number of timer intervals corresponding to a creep step
    'ONLY_CREEP'          = 0      # boolean, if true disable cruising speed
    'FINAL_CREEP_ON'      = 1      # boolean, if true do a finishing creep move after a cruise
    'BACKLASH_REMOVAL_ON' = 1      # boolean, if true do an antibacklash sequence at end of a move
    'FINAL_CREEP_DIST'    = 180.0  # float, distance in deg to creep after a cruise
    'PRINCIPLE_HARDSTOP_CLEARANCE_T' = 10.0 # float, minimum distance in deg to stay clear of theta principle hardstop
    'SECONDARY_HARDSTOP_CLEARANCE_T' =  5.0 # float, minimum distance in deg to stay clear of theta secondary hardstop
    'PRINCIPLE_HARDSTOP_CLEARANCE_P' =  5.0 # float, minimum distance in deg to stay clear of phi principle hardstop
    'SECONDARY_HARDSTOP_CLEARANCE_P' =  5.0 # float, minimum distance in deg to stay clear of phi secondary hardstop
    
    # remove these
    'HARDSTOP_CLEARANCE'
    'BACKLASH_REMOVAL_ON_CW_MOVES'    
    'BACKLASH_REMOVAL_ON_CCW_MOVES'
    'FIRST_CMD_AXIS'