import os
import configobj
import csv
import pprint
import posconstants as pc
try:
    from DBSingleton import *
    DB_COMMIT_AVAILABLE = True
except:
    DB_COMMIT_AVAILABLE = False

class PosState(object):
    """Variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object.

    This class is also used for tracking state of fiducials or petals.

    INPUTS: unit_id = POS_ID, FID_ID, or PETAL_ID of device
            logging = boolean whether to enable logging state data to disk
            type    = 'pos', 'fid', 'ptl' to say whether it is a positioner, fiducial, or petal

    Notes:
        Default settings are used if no unit_id is supplied.
        Values are stored in configobj files.
        There is a distinction between unit parameters (specific to one hardware
        unit) and general parameters (settings which apply uniformly to many units).
    """

    def __init__(self, unit_id=None, logging=False, device_type='pos', printfunc=print, petal_id=None):
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)
        self.logging = logging

        # data initialization from .conf file
        if self.type in ['pos', 'fid', 'ptl']:
            self.type = device_type
            self.settings_directory = pc.dirs[self.type + '_settings']
            self.logs_directory = pc.dirs[self.type + '_logs']
        else:
            raise DeviceError("Invalid device type.")
        template_directory = self.settings_directory
        if unit_id is not None:
            self.unit_basename = 'unit_' + str(unit_id)
            comment = 'Settings file for unit: ' + str(unit_id)
        else:
            self.unit_basename = 'unit_TEMP'
            self.logs_directory = pc.dirs['temp_files']
            self.settings_directory = pc.dirs['temp_files']
            comment = 'Temporary settings file for software test purposes, not associated with a particular unit.'
        unit_filename = self.settings_directory + self.unit_basename + '.conf'
        if not(os.path.isfile(unit_filename)):
            # unit config doesn't exisit, read in the generic template file
            temp_filename = template_directory + '_unit_settings_DEFAULT.conf'
            self.conf = configobj.ConfigObj(temp_filename, unrepr=True, encoding='utf-8')
            self.conf.initial_comment = [comment, '']
            self.conf.filename = unit_filename
            if self.type == 'pos':
                self.conf['POS_ID'] = str(unit_id)
            elif self.type == 'fid':
                self.conf['FID_ID'] = str(unit_id)
            elif self.type == 'ptl':
                self.conf['PETAL_ID'] = str(unit_id)
            self.conf.write()
        else:
            self.conf = configobj.ConfigObj(unit_filename, unrepr=True, encoding='utf-8')

        # determine petal_id
        # regardless of devide type, config has been read and the
        # correct petal_id is available in config, so let's just use config only
        # if self.type == 'ptl':
        self.petal_id = self.conf['PETAL_ID']
        # else:
        #     self.petal_id = petal_id

        # establishment of much faster access python dict, for in-memory operations
        self._val = self.conf.dict()

        # data initialization from database
        self.write_to_DB = os.getenv('DOS_POSMOVE_WRITE_TO_DB') if DB_COMMIT_AVAILABLE else False
        if self.write_to_DB:
            if unit_id != None:
                self.posmoveDB = DBSingleton(self.petal_id)
                if self.type == 'pos':
                    self._val.update(self.posmoveDB.get_pos_id_info(unit_id))
                    self._val.update(self.posmoveDB.get_pos_constants(unit_id))
                    self._val.update(self.posmoveDB.get_pos_move(unit_id))
                    self._val.update(self.posmoveDB.get_pos_calib(unit_id))
                else:
                    self._val.update(self.posmoveDB.get_fid_id_info(unit_id))
                    self._val.update(self.posmoveDB.get_fid_constants(unit_id))
                    self._val.update(self.posmoveDB.get_fid_data(unit_id))
                    print(self._val)
                    self._val.update(self.posmoveDB.get_fid_calib(unit_id))
            else:
                self.posmoveDB = DBSingleton()
                if self.type == 'pos':
                    self._val.update(self.posmoveDB.get_pos_def_constants())
                else:
                    self._val.update(self.posmoveDB.get_fid_def_constants())

        # text log file setup
        self.log_separator = '_log_'
        self.log_numformat = '08g'
        self.log_extension = '.csv'
        if not(self.log_basename):
            all_logs = os.listdir(self.logs_directory)
            unit_logs = [x for x in all_logs if self.unit_basename in x and self.log_extension in x]
            if unit_logs:
                unit_logs.sort(reverse=True)
                self.log_basename = unit_logs[0]
            else:
                log_basename = self.unit_basename + self.log_separator + format(0,self.log_numformat) + self.log_extension
                self.log_basename = self._increment_suffix(log_basename)
        self.max_log_length = 10000 # number of rows in log before starting a new file
        self.curr_log_length = self._count_log_length() # keep track of this in a separate variable so don't have to recount every time -- only when necessary
        if self.type == 'pos':
            self._val['MOVE_CMD'] = ''
            self._val['MOVE_VAL1'] = ''
            self._val['MOVE_VAL2'] = ''
        if os.path.isfile(self.log_path):
            with open(self.log_path,'r',newline='') as csvfile:
                headers = csv.DictReader(csvfile).fieldnames
            for key in self._val:
                if key not in headers:
                    self.log_basename = self._increment_suffix(self.log_basename) # start a new file if headers don't match up anymore with all the data we're trying to store
                    break
        self._update_legacy_keys()                
        self.log_fieldnames = ['TIMESTAMP'] + list(self._val.keys()) + ['NOTE'] # list of fieldnames we save to the log file.
        self.next_log_notes = ['software initialization'] # used for storing specific notes in the next row written to the log
        self.log_unit_called_yet = False # used for one time check whether need to make a new log file, or whether log file headers have changed since last run
        self.log_unit()

    def __str__(self):
        files = {'settings':self.conf.filename, 'log':self.log_path}
        return pprint.pformat({'files':files, 'values':self._val})
        
    def read(self,key):
        """Returns current value for a given key. Left in place for legacy usage,
        but it is much faster to directly access _val dictionary (for reading values).
        """
        return self._val[key]

    def store(self,key,val):
        """Store a value to memory. This is the correct way to store values, as
        it contains some checks on tolerance values. (Don't write directly to _val.)
        """
        if key in pc.nominals:
            nom = pc.nominals[key]['value']
            tol = pc.nominals[key]['tol']
            if val < nom - tol or val > nom + tol: # check for absurd values
                self.printfunc('Attempted to set ' + str(key) + ' of ' + str(self.unit_basename) + ' to value = ' + str(val) + ', which is outside the nominal = ' + str(nom) + ' +/- ' + str(tol) + '. Defaulting to nominal value instead.')
                val = nom
        if key in self._val:
            self._val[key] = val
        else:
            self.printfunc('value not set, because the key "' + repr(key) + '" was not found')
 
    def write(self):
        """Write all values to disk.
        """
        self.conf.update(self._val)
        self.conf.write()
    
    def log_unit(self):
        """All current unit parameters are written to the hardware unit's log file.
        """
        if self.logging:
            timestamp = pc.timestamp_str_now()
            def start_new_file():
                with open(self.log_path, 'w', newline='') as csvfile:
                    csv.writer(csvfile).writerow(self.log_fieldnames)
            if self.curr_log_length >= self.max_log_length:
                self.log_basename = self._increment_suffix(self.log_basename)
                self.curr_log_length = 0
                start_new_file()
            if not(self.log_unit_called_yet):
                if not(os.path.isfile(self.log_path)):
                    start_new_file()
                else:
                    with open(self.log_path, 'r', newline='') as csvfile:
                        fieldnames_found_in_old_logfile = csv.DictReader(csvfile).fieldnames
                    for key in self.log_fieldnames:
                        if key not in fieldnames_found_in_old_logfile:
                            start_new_file()
                            break
            with open(self.log_path, 'a', newline='') as csvfile: # now append a row of data
                row = self._val.copy()
                row.update({'TIMESTAMP':timestamp,'NOTE':str(self.next_log_notes)})
                writer = csv.DictWriter(csvfile,fieldnames=self.log_fieldnames)
                writer.writerow(row)
            self.curr_log_length += 1
            self.next_log_notes = []
            self.log_unit_called_yet = True # only need to check this the first time through
    
    @property
    def log_path(self):
        """Convenience method for consistent formatting of file path to log file.
        """
        return self.logs_directory + self.log_basename

    @property
    def log_basename(self):
        '''Property setter used here since the log basename is accessed in a few places,
        and want to make sure it is consistently tracked in the .conf file.
        '''
        if 'CURRENT_LOG_BASENAME' in self._val.keys():
            return self._val['CURRENT_LOG_BASENAME']
        return ''
    
    @log_basename.setter
    def log_basename(self, name):
        self._val['CURRENT_LOG_BASENAME'] = name

    def _increment_suffix(self,s):
        """Increments the numeric suffix at the end of s. This function was specifically written
        to have a regular method for incrementing the suffix on log filenames.
        """
        prefix = s.split(self.log_separator)[0]
        suffix = s.split(self.log_separator)[1]
        number = suffix.split(self.log_extension)[0]
        number2 = format(int(number) + 1, self.log_numformat)
        return prefix + self.log_separator + number2 + self.log_extension
    
    def _count_log_length(self):
        '''Counts the number of lines in the current log file.
        Header row is ignored from count.
        Returns 0 if no log file exists.
        '''
        n_lines = 0
        if os.path.isfile(self.log_path):
            with open(self.log_path,'r',newline='') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    n_lines += 1
            n_lines -= 1 # to ignore the header row
        return n_lines
    
    def _update_legacy_keys(self):
        '''Allows us to replace key labels in the config files with new names, and
        continue using the old files. We may be able to deprecate this at a later date, when such
        key labels are really finalized, but anyway it is a pretty low-cost operation since
        it only happens at initialization.
        '''
        #                                               old : new
        legacy_key_replacements = {'LAST_MOVE_CMD'          : 'MOVE_CMD',
                                   'LAST_MOVE_VAL1'         : 'MOVE_VAL1',
                                   'LAST_MOVE_VAL2'         : 'MOVE_VAL2',
                                   'LAST_MEAS_BRIGHTNESS'   : 'LAST_MEAS_PEAK',
                                   'LAST_MEAS_BRIGHTNESSES' : 'LAST_MEAS_PEAKS'}
        for old_key in legacy_key_replacements:
            if old_key in self._val:
                temp_val = self._val[old_key]
                del self._val[old_key]
                new_key = legacy_key_replacements[old_key]
                self._val[new_key] = temp_val
        # also insert any missing entirely new keys
        if self.type == 'pos':
            possible_new_keys_and_defaults = {'LAST_MEAS_FWHM':None}
        elif self.type == 'fid':
            possible_new_keys_and_defaults = {'LAST_MEAS_OBS_X':[],
                                              'LAST_MEAS_OBS_Y':[],
                                              'LAST_MEAS_FWHMS':[],
                                              'DEVICE_CLASSIFIED_NONFUNCTIONAL':False}
        elif self.type == 'ptl':
            possible_new_keys_and_defaults ={}

        for key in possible_new_keys_and_defaults:
            if key not in self._val:
                self._val[key] = possible_new_keys_and_defaults[key]

if __name__=="__main__":
    state = PosState()
