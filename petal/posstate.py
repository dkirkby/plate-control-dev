import os
import configobj
import datetime
import csv
import posconstants as pc

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
        settings_directory = os.getcwd() + '/pos_settings/'
        logs_directory = os.getcwd() + '/pos_logs/'
        self.max_log_length = 5 # increase after debugging
        if unit_id != None:
            self.unit_basename = 'unit_' + str(unit_id)
            unit_filename = settings_directory + self.unit_basename + '.conf'
            self.unit = configobj.ConfigObj(unit_filename,unrepr=True)
        else:
            temp_filename = settings_directory + '_unit_settings_DEFAULT.conf'        # read in the template file
            self.unit = configobj.ConfigObj(temp_filename,unrepr=True)
            self.unit_basename = '_unit_settings_TEMP'
            self.unit.filename = settings_directory + self.unit_basename + '.conf'  # now change file name so won't later accidentally overwrite the template
            self.unit.initial_comment = ['temporary test file, not associated with a particular positioner',''] # also strip out and replace header comments specific to the template file
            self.unit.write()
        genl_filename = settings_directory + self.unit['STATE']['GENERAL_SETTINGS_FILE']
        self.genl = configobj.ConfigObj(genl_filename,unrepr=True)
        all_logs = os.listdir(logs_directory)
        self.unit_logs = [x for x in all_logs if self.unit_basename in x]
        if self.unit_logs:
            self.unit_logs.sort(reverse=True)
            self.unit_latest_log = self.unit_logs[0]
            #check if maxed out, if so add another fresh log (possibly include this in the log_unit method?)
        else:
            #add another fresh log (possibly include this in the log_unit method?)
            pass
        self.log_unit(note='initialization')

    def read(self,key):
        """Returns current value for a given key.
        All sections of all configobj structures are searched to full-depth.
        """
        if key in self.unit.keys():
            if key == 'GEAR_T' or key == 'GEAR_P':
                return pc.gear_ratio[val]
            return self.unit[key]
        if key in self.genl.keys():
            return self.genl[key]
        print('no key "' + repr(key) + '" found')
        return None

    def write(self,key,val,write_to_disk=None):
        """Set a value.
        In the default usage, there is an important distinction made between unit parameters and general parameters:
            unit    ... the new value is stored in memory, but is ALSO written to the file on disk
            general ... the new value is only stored in memory, it is NOT written to disk
        This default behavior can be overridden (True or False) using the write_to_disk boolean argument.
        Caution should be exercised, since usually one does not a particular positioner to overwrite general settings.
        """
        if key in self.unit.keys():
            self.unit[key] = val
            if write_to_disk != False:
                self.unit.write()
        elif key in self.genl.keys():
            self.genl[key] = val
            if write_to_disk == True:
                self.genl.write()
        else:
            print('value not set, because the key "' + repr(key) + '" was not found')

    def log_unit(self,note=''):
        """All current unit parameters are written to the hardware unit's log file.
        """
        timestamp = datetime.datetime.now().strftime(pc.timestamp_format)
        d['NOTE'] = note
        # more to-do
        #self.log_filename = os.path.splitext(self.unit.filename)[0] + '_log_' + somenumber + '.csv'
        with open(self.log_filename, 'a', newline='') as csvfile: # kosher to make this append with 'a'?
            writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            if need_to_write_header: # make this real
                writer.writerow(['TIMESTAMP'] + self.unit.keys() + ['NOTE'])
            writer.writerow(timestamp + self.unit.values() + note)
