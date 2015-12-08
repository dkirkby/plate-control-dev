

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
        pass



