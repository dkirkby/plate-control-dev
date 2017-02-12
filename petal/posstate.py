import os
import configobj
import datetime
import csv
import pprint
import posconstants as pc

class PosState(object):
    """Variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object.

    This class is also used for tracking state of fiducials.

    INPUTS: unit_id = POS_ID of positioner
            logging = boolean whether to enable logging state data to disk
            type    = 'pos' or 'fid' to say whether it is a positioner or a fiducial

    Notes:
        Default settings are used if no unit_id is supplied.
        Values are stored in configobj files.
        There is a distinction between unit parameters (specific to one hardware
        unit) and general parameters (settings which apply uniformly to many units).
    """

    def __init__(self, unit_id=None, logging=False, type='pos'):
        self.logging = logging
        self.type = type
        if self.type == 'pos':
            self.settings_directory = pc.pos_settings_directory
            self.logs_directory = pc.move_logs_directory
        else:
            self.settings_directory = pc.fid_settings_directory
            self.logs_directory = pc.fid_logs_directory
        if unit_id != None:
            self.unit_basename = 'unit_' + str(unit_id)
            comment = 'Settings file for unit: ' + str(unit_id)
        else:
            self.unit_basename = 'unit_TEMP'
            comment = 'Temporary settings file for software test purposes, not associated with a particular unit.'
        unit_filename = self.settings_directory + self.unit_basename + '.conf'
        if not(os.path.isfile(unit_filename)):
            temp_filename = self.settings_directory + '_unit_settings_DEFAULT.conf' # read in the template file
            self.unit = configobj.ConfigObj(temp_filename,unrepr=True)
            self.unit.initial_comment = [comment,'']
            self.unit.filename = unit_filename
            if self.type == 'pos':
                self.unit['POS_ID'] = str(unit_id)
            else:
                self.unit['FID_ID'] = str(unit_id)
            self.unit.write()
        else:
            self.unit = configobj.ConfigObj(unit_filename,unrepr=True)
     
        all_logs = os.listdir(self.logs_directory)
        unit_logs = [x for x in all_logs if self.unit_basename in x]
        if unit_logs:
            unit_logs.sort(reverse=True)
            log_basename = os.path.splitext(unit_logs[0])[0]
        else:
            log_basename = self.unit_basename + '_log_'
        self.log_basename = PosState.increment_suffix(log_basename)
        self.max_log_length = 1000 # number of rows in log before starting a new file
        self.curr_log_length = 0
        if self.type == 'pos':
            self.unit['LAST_MOVE_CMD'] = '(software initialization)'
            self.unit['LAST_MOVE_VAL1'] = ''
            self.unit['LAST_MOVE_VAL2'] = ''
        self.log_unit()

    def __str__(self):
        files = {'settings':self.unit.filename, 'log':self.log_path}
        if self.type == 'pos':
            return pprint.pformat({'files':files, 'unit':self.unit})
        else:
            return pprint.pformat({'files':files, 'unit':self.unit})

    def read(self,key):
        """Returns current value for a given key.
        All sections of all configobj structures are searched to full-depth.
        """
        self.unit.reload()
        if key in self.unit.keys():
            return self.unit[key]
        print('no key "' + repr(key) + '" found')
        print('keys: ' + str(self.unit.keys()))
        return None

    def write(self,key,val,write_to_disk=None):
        """Set a value.
        """
        if key in pc.nominals.keys():
            nom = pc.nominals[key]['value']
            tol = pc.nominals[key]['tol']
            if val < nom - tol or val > nom + tol: # check for absurd values
                print('Attempted to set ' + str(key) + ' of ' + str(self.unit_basename) + ' to value = ' + str(val) + ', which is outside the nominal = ' + str(nom) + ' +/- ' + str(tol) + '. Defaulting to nominal value instead.')
                val = nom
        if key in self.unit.keys():
            self.unit[key] = val
            if write_to_disk != False:
                self.unit.write()
        else:
            print('value not set, because the key "' + repr(key) + '" was not found')
 
    def log_unit(self,note=''):
        """All current unit parameters are written to the hardware unit's log file.
        """
        if self.logging:
            timestamp = pc.timestamp_str_now()
            if note == '':
                note = ' ' # just to make csv file cell look blank in excel
            if self.curr_log_length >= self.max_log_length:
                self.log_basename = PosState.increment_suffix(self.log_basename)
                self.curr_log_length = 0
            if not(os.path.isfile(self.log_path)): # checking whether need to start a new file
                with open(self.log_path, 'w', newline='') as csvfile:
                    csv.writer(csvfile).writerow(['TIMESTAMP'] + self.unit.keys() + ['NOTE'])
            with open(self.log_path, 'a', newline='') as csvfile: # now append a row of data
                csv.writer(csvfile).writerow([timestamp] + self.unit.values() + [str(note)])
            self.curr_log_length += 1

    @property
    def log_path(self):
        """Convenience method for consistent formatting of file path to log file.
        """
        return self.logs_directory + self.log_basename + '.csv'

    @staticmethod
    def increment_suffix(s):
        """Increments the numeric suffix at the end of s. This function was specifically written
        to have a regular method for incrementing the suffix on log filenames.
        """
        separator = '_'
        numformat = '%08i'
        split = s.split(separator)
        suffix = split[-1]
        if suffix.isdigit():
            suffix = numformat % (int(suffix) + 1)
        else:
            suffix = numformat % 0
            if split[-1] != '':
                split += ['']
        split[-1] = suffix
        return separator.join(split)
