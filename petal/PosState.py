#############################
# Classes: PosState         #
# Version: Python 3         #
# Date: Dec. 9, 2015        #
# Author: P. Fagrelius      #
#############################

import os, sys
import datetime
#import newdict
from configobj import ConfigObj
from validate import Validator
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
    def __init__(self,pos_id=None):
        if pos_id is None:
            self.pos_id = 'DEF'
        else:
            self.pos_id = str(pos_id)
            
        self.verbose = PosConstants.verbose
        configfile = os.getcwd()+'/configfile.conf' #Need to decide where to put this
        configspecfile = os.getcwd()+'/configspec.ini' # Validation file
        #configfile = os.environ.get('CONFPATH')+'configfile.conf'
        self.config = ConfigObj(configfile,configspec = configspecfile)

        #Validate
        validator = Validator()
        try:
            self.config.validate(validator)
        except:
            print('Something is wrong with the config file')
    
    def read(self,arg):
        """
        Returns current values of state variables as an array
        """
        if arg == 'GEAR_T':
            gear_name = self.config[self.pos_id][arg]
            self.value = PosConstants.gear_ratio[gear_name]
        elif arg == 'GEAR_P':
            gear_name = self.config[self.pos_id][arg]
            self.value = PosConstants.gear_ratio[gear_name]
        else: 
            try:
                self.value = self.config[self.pos_id][arg]
                return self.value

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
        pass
