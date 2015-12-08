

from __future__ import print_function
import os, sys
import datetime
#import newdict
from configobj import ConfigObj
import PosConstants


class PosState(object):
    """
    Class : PosState
    Called by BUS_ID = pos_id
    State variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner in this
    single object.
    Values are stored in a config file.
    """

    def __init__(self,pos_id):
        self.verbose = PosConstants.verbose
        configfile = os.getcwd()+'/configfile.conf' #Need to decide where to put this
        #configfile = os.environ.get('CONFPATH')+'configfile.conf'
        self.config = ConfigObj(configfile)
        self.pos_id = str(pos_id)
    
    def read(self,*args):
        """
        Returns current values of state variables as an array
        """
        self.conf = []
        try:
            for arg in args:
                self.conf.append(self.config[self.pos_id][arg])
            return self.conf
        except:
            print('\n Error in reading Config file \n')
            return False

    def write(self,arg,val):
        """
        Change the values of the configuration file
        """
        try:
            self.config[self.pos_id][arg] = val
            return True
        except:
            print('\n Could not write to Config file \n')
            return False

    def log_config(self):
        "Not sure if need to create a log file"
        pass




    ## def __init__(self):

    ##     # proprieties
    ##     self.log_dir = './'          # folder where logs/ascii communication files go
    ##     self.kv = newdict.newdict()  # kv is a dictionary
    ##     self.log_table = dict()
    ##     self.log_filename_note = ''       # optional text string will be appended to log_file_basename
    ##     self.enable_logging = True        # boolean to turn on/off the automated logger
    ##     self.com_port = 'COM12'           # set PosConstants enumeration
    ##     self.tiny_dxdy_tol = 1E-3         # don't bother to move of sqrt(dx^2+dy^2) < tol
    ##     self.tiny_dt_tol = 1E-3           # don't bother to move t axis if |du| < tol
    ##     self.tiny_dp_tol = 1E-3           # don't bother to move p axis if |dv| < tol
    ##     self.last_known = {'x': 0, 'y': 0, 't': 0, 'p': 0}  # position of end effector (x,y) and of axis shafts (t,p)

    ##     # positioner identifiers
    ##     self.kv['SERIAL_ID'] = '6.M.02'  # serial id string of mechanical hardware
    ##     self.kv['BUS_ID'] = 4321         # electronics id number on the communication bus

    ##     # default for the positioner kinematics
    ##     self.kv['LENGTH_R1'] = 3.0  # mm       arm lenght of theta axis
    ##     self.kv['LENGTH_R2'] = 3.0  # mm       arm lenght of phi axis
    ##     self.kv['POLYN_T0'] = 0.0   # deg      Tobserver = T0 + T1*Tshaft + T2*Tshaft^2
    ##     self.kv['POLYN_T1'] = 1.0   # deg
    ##     self.kv['POLYN_T2'] = 0.0   # deg/deg^2
    ##     self.kv['POLYN_P0'] = 0.0   # deg      Pobserver = P0 + P1*Pshaft + P2*Pshaft^2
    ##     self.kv['POLYN_P1'] = 1.0   # deg
    ##     self.kv['POLYN_P2'] = 0.0   # deg/deg^2
    ##     self.kv['POLYN_X0'] = 0.0   # deg      Xobserver = X0 + X1*Xpositioner
    ##     self.kv['POLYN_X1'] = 1.0   # deg
    ##     self.kv['POLYN_Y0'] = 0.0   # deg      Yobserver = Y0 + Y1*Ypositioner
    ##     self.kv['POLYN_Y1'] = 1.0   # deg/deg
    ##     self.kv['PHYSICAL_RANGE_T'] = 380.0  # deg      theta range of travel
    ##     self.kv['PHYSICAL_RANGE_P'] = 200.0  # deg      phi range of travel

    ##     # defaults for backlash and limit handling
    ##     self.kv['BACKLASH'] = 3.0  # deg   in normal operation, always stay shy of the hardstops by this amount (at both ends of the travel range)
    ##     self.kv['HARDSTOP_CLEARANCE'] = 4.0  # deg   in normal operation, always stay shy of the hardstops by this amount (at both ends of the travel range)
    ##     self.kv['PRINCIPLE_HARDSTOP_DIR_T'] = -1.0  # +1 (use hardstop at max of range) or -1 (use hardstop at min of range) or 0 (no hardstop exists)
    ##     self.kv['PRINCIPLE_HARDSTOP_DIR_P'] = +1.0  # +1 (use hardstop at max of range) or -1 (use hardstop at min of range) or 0 (no hardstop exists)
    ##     self.kv['ALLOW_EXCEED_LIMITS'] = False  # boolean  flag to allow positioner to go past software limits or not. exercise some caution if setting this true
    ##     self.kv['LIMIT_SEEK_EXCEED_RANGE_FACTOR'] = 1.3  # factor beyond nominal range to use when seeking hardstops
    ##     self.kv['SHOULD_DEBOUNCE_HARDSTOPS'] = True  # boolean   flag to turn on/off automatic debounce from hardstops. typically leave on for homing, but turn off if need to measure full physical range of travel
    ##     self.kv['BACKLASH_REMOVAL_DIR_T'] = -1.0  # +1 (clockwise) or -1 (counter-clockwise)
    ##     self.kv['BACKLASH_REMOVAL_DIR_P'] = +1.0  # +1 (clockwise) or -1 (counter-clockwise)
    ##     self.kv['BACKLASH_REMOVAL_ON_CW_MOVES'] = True  # boolean   if true, always append a final backlash removal step to clockwise moves
    ##     self.kv['BACKLASH_REMOVAL_ON_CCW_MOVES'] = True  # boolean   if true, always append a final backlash removal step to counter-clockwise moves
    ##     self.kv['BACKLASH_REMOVAL_BACKUP_FRACTION'] = 0.5  # when move direction == backlash_removal_direction, undershoot by this fraction of BACKLASH, then backup by (1-fraction)*BACKLASH, then advance by BACKLASH

    ##     self.kv['ONLY_CREEP_TO_LIMITS']= False # boolean if true , when approaching hardstops only creep up on them
    ##     # defaults for motor currents
    ##     # note: 0 to 100, percent of full stall current
    ##     self.kv['CURR_SPIN_UP_DOWN'] = 100.0  # spin up / spin down current
    ##     self.kv['CURR_CRUISE'] = 70.0  # cruise current
    ##     self.kv['CURR_CREEP'] = 70.0  # creep current
    ##     self.kv['CURR_HOLD_AFTER_CREEP'] = 0.0  # can be set to zero to completely power off theta motors after moving

    ##     # default motor characteristics
    ##     self.kv['FIRST_CMD_AXIS'] = 'P'  # 'T' or 'P', defining which axis comes first in order when sending commands to motors
    ##     self.kv['MOTOR_CW_DIR_T'] = +1  # +1 or -1, defining as-wired motor's clockwise direction. note 5.N.01=-1, 5.M.01=+1, 6.M.01=-1, 6.M.02=+1
    ##     self.kv['MOTOR_CW_DIR_P'] = +1  # +1 or -1, defining as-wired motor's clockwise direction. note 5.N.01=-1, 5.M.01=-1, 6.M.01=-1, 6.M.02=+1
    ##     self.kv['GEAR_T'] = PosConstants.gear_ratio_maxon  # gear ratio of theta axis
    ##     self.kv['GEAR_P'] = PosConstants.gear_ratio_maxon  # gear ratio of phi axis

    ## def log_dir(self, arg):
    ##     """
    ##     create a directory
    ##     :param arg: a string
    ##     :return: no return
    ##     """
    ##     if arg:
    ##         slash = '/'
    ##         if slash != arg[str.__len__(arg) - 1]:
    ##             arg += slash
    ##         if not (os.path.isdir(arg)):
    ##             os.mkdir(arg)
    ##     self.log_dir = arg

    ## def log_state(self, *args, **kwargs):
    ##     """
    ##     Creates a new row in the log_table and returns the new row index.
    ##     Will always log timestamp and all the key/value pairs in state object
    ##     Additionally one can argue a containers.Map object with more key/value to log in this row.
    ##     """
    ##     timestamp = str(datetime.datetime.now())
    ##     self.log_table[self, 'timestamp'] = timestamp
    ##     self.log_table = self.last_known.copy()

    ##     # enter known key/values from this object then key/values argued by user
    ##     self.log_table = self.kv.copy()
    ##     if kwargs:
    ##         self.log_table = kwargs.copy()

    ## def write_log(self, *val1):
    ##     filepath = self.log_dir
    ##     if val1:
    ##         filepath += val1
    ##     else:
    ##         filepath += self.log_file_basename
    ##     filepath += '.csv'
    ##     for value in self.log_table.values():
    ##         filepath += value

    ## @property
    ## def log_file_basename(self):  # default name which log will be to (excluding directory and extension )
    ##     str1 = 'log'
    ##     if self.kv['SERIAL_ID'] is None:
    ##         str1 += '_noserialid'
    ##     else:
    ##         str1 += '_' + self.kv['SERIAL_ID']
    ##     if self.log_table['Properities', 'VariableNames'] == 'timestamp' or self.log_table['timestamp'] is None:
    ##         str1 += '_notimestamp'
    ##     else:
    ##         i = 0
    ##         while True:
    ##             i += 1
    ##             if self.log_table['timestamp', 'i'] is None:
    ##                 break
    ##         str1 += '-' + self.log_table['timestamp', 'i']
    ##     if not self.log_table['note'] is None:
    ##         str1 += '_' + self.log_table['note']
    ##     return str1
