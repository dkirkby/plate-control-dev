import os
import configobj
import posconstants

class PosState(object):
    """Variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object.

    INPUTS: unit_id = SERIAL_ID of positioner

    Notes:
        Default settings are used if no unit_id is supplied.
        Values are stored in configobj files.
        There is a distinction between unit parameters (specific to one hardware
        unit) and general parameters (settings which apply uniformly to many units).
    """
    def __init__(self, unit_id=None):
        directory = os.getcwd() + '/pos_settings/'
        if unit_id:
            filename = directory + 'unit_' + str(unit_id) + '.conf'
            self.unit = configobj.ConfigObj(filename,unrepr=True)
        else:
            filename = directory + '_unit_settings_DEFAULT.conf'        # read in the template file
            self.unit = configobj.ConfigObj(filename,unrepr=True)
            self.unit.filename = directory + '_unit_settings_TEMP.conf'  # now change file name so won't later accidentally overwrite the template
            self.unit.initial_comment = ['temporary test file, not associated with a particular positioner',''] # also strip out and replace header comments specific to the template file
            self.unit.write()
        filename = directory + self.unit['STATE']['GENERAL_SETTINGS_FILE']
        self.genl = configobj.ConfigObj(filename,unrepr=True)
        self.all_unit_keys = posstate.allkeys(self.unit)
        self.all_genl_keys = posstate.allkeys(self.genl)

    def read(self,key):
        """Returns current value for a given key.
        """
        if key in self.all_unit_keys:
            if key == 'GEAR_T' or key == 'GEAR_P':
                gear_name = self.unit[''][key]
                return posconstants.gear_ratio[gear_name]
            else:
                return self.unit[self.section][key]

    def write(self,key,val,write_to_disk=None):
        """Set a value.
        In the default usage, there is an important distinction made between
        unit parameters and general parameters:
            unit    ... the new value is stored in memory, but is ALSO written to the file on disk
            general ... the new value is only stored in memory, it is NOT written to disk
        This default behavior can be overridden (True or False) using the write_to_disk boolean argument.
        Caution should be exercised, since usually one does not a particular positioner to overwrite general settings.
        """
        self.config[self.section][key] = val
        self.config.write()

    def log_unit(self):
        """All current unit parameters are written to the hardware unit's log file.
        """
        pass

    @staticmethod
    def allkeys(confobj):
        """Return list of all lowest-level keys (recurseively found to any depth) in a configobj structure.
        """
        if confobj.sections == []:
            return confobj.keys()
        else:
            keyslist = []
            for section in confobj.sections:
                keyslist += allkeys(confobj[section])
            return keyslist

# MAYBE INSTEAD OF ALLKEYS, HAVE A FUNCTION THAT JUST RETURNS THE VALUE FOR A KEY AT ANY DEPTH? IF NO VALUE RETURNED, THEN IT WASN'T IN THERE
    @staticmethod
    def get_recursive(confobj,key)