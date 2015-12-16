import os
import configobj
import posconstants

class PosState(object):
    """State variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner in this
    single object.

    INPUTS: pos_id = SERIAL_ID of positioner
            config_name = section of the config file containing the particular value set to use

    Note: There is a default positioner config file if no pos_id is supplied
    Values are stored in a config file.
    """
    def __init__(self,pos_id=None,config_name='DEFAULT'):
        configpath = os.getcwd()+'/pos_configs/'
        if pos_id:
            self.pos_id = str(pos_id)
            configfile = configpath+'pos_' + str(self.pos_id) + '.conf'
            self.config = configobj.ConfigObj(configfile,unrepr=True)
        else:
            configfile = configpath + '_pos_template.conf'        # read in the template file
            self.config = configobj.ConfigObj(configfile,unrepr=True)
            self.config.filename = configpath + '_pos_xxxxx.conf'  # now change file name so won't later accidentally overwrite the template
            self.config.initial_comment = ['test file, not associated with a particular positioner',''] # also strip out and replace header comments specific to the template file
            self.pos_id = self.config[config_name]['SERIAL_ID']
        self.section = config_name
        self.config.write()

    def read(self,arg):
        """
        Returns current values of state variables as an array
        """
        if arg == 'GEAR_T' or arg == 'GEAR_P':
            gear_name = self.config[self.section][arg]
            return posconstants.gear_ratio[gear_name]
        else:
            return self.config[self.section][arg]

    def write(self,arg,val):
        """
        Change the values of the configuration file
        """
        self.config[self.section][arg] = val
        self.config.write()

    def log_config(self):
        pass

