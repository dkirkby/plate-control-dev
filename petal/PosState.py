#############################
# Classes: PosState         #
# Version: Python 3         #
# Date: Dec. 9, 2015        #
# Author: P. Fagrelius      #
#############################

import os, sys
import datetime
#import newdict
from configobj import ConfigObj, flatten_errors
from validate import Validator
import PosConstants


class PosState(object):
    """State variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner in this
    single object.
    
    INPUTS: pos_id = SERIAL_ID of positioner
            conf   = configuration of positioner. If blank is DEFAULT

    Note: There is a default positioner config file if no pos_id is supplied
    Values are stored in a config file.
    """
    def __init__(self,pos_id=None,conf=False):

        #Set positioner ID. If blank, will use default (pos_def.conf)
        if pos_id is None:
            self.pos_id = 'def'
        else:
            self.pos_id = str(pos_id)

        #Call the configuration file + validation file
        configpath = os.getcwd()+'/pos_configs/'
        configfile = configpath+'pos_'+str(self.pos_id)+'.conf'
        configspecfile = configpath+'/configspec.ini'     
        #configfile = os.environ.get('CONFPATH')+'configfile.conf'
        config = ConfigObj(configfile,configspec = configspecfile)
        
        #Validate
        validator = Validator()
        try:
            results = config.validate(validator)
        except:
            print('Validation of file failed')

        #Set configuration of given positioner
        if conf is False:
            self.conf = 'DEFAULT'
        else:
            self.conf = str(conf)
            
        self.config = config[str(self.conf)]

    
    def read(self,arg):
        """
        Returns current values of state variables as an array
        """
        if arg == 'GEAR_T':
            gear_name = self.config[arg]
            self.value = PosConstants.gear_ratio[gear_name]
        elif arg == 'GEAR_P':
            gear_name = self.config[arg]
            self.value = PosConstants.gear_ratio[gear_name]
        else: 
            try:
                self.value = self.config[arg]
                return self.value

            except:
                print('Error in reading Config file')
                return False

    def write(self,arg,val):
        """
        Change the values of the configuration file
        """
        try:
            self.config[arg] = val
            return True
        except:
            print('Could not write to Config file')
            return False

    def log_config(self):
        pass

