import os
import configobj
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

    def __init__(self, unit_id=None, logging=False, device_type='pos', printfunc=print):
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)
        self.logging = logging
        self.type = device_type
        if self.type == 'pos':
            self.settings_directory = pc.pos_settings_directory
            self.logs_directory = pc.pos_logs_directory
        else:
            self.settings_directory = pc.fid_settings_directory
            self.logs_directory = pc.fid_logs_directory
        if unit_id != None:
            self.unit_basename = 'unit_' + str(unit_id)
            comment = 'Settings file for unit: ' + str(unit_id)
        else:
            self.unit_basename = 'unit_TEMP'
            self.logs_directory = pc.temp_files_directory
            self.settings_directory = pc.temp_files_directory
            comment = 'Temporary settings file for software test purposes, not associated with a particular unit.'
        unit_filename = self.settings_directory + self.unit_basename + '.conf'
        if not(os.path.isfile(unit_filename)):
            temp_filename = self.settings_directory + '_unit_settings_DEFAULT.conf' # read in the template file
            self.unit = configobj.ConfigObj(temp_filename,unrepr=True,encoding='utf-8')
            self.unit.initial_comment = [comment,'']
            self.unit.filename = unit_filename
            if self.type == 'pos':
                self.unit['POS_ID'] = str(unit_id)
            else:
                self.unit['FID_ID'] = str(unit_id)
            self.unit.write()
        else:
            self.unit = configobj.ConfigObj(unit_filename,unrepr=True,encoding='utf-8')
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
            self.unit['MOVE_CMD'] = ''
            self.unit['MOVE_VAL1'] = ''
            self.unit['MOVE_VAL2'] = ''
        if os.path.isfile(self.log_path):
            with open(self.log_path,'r',newline='') as csvfile:
                headers = csv.DictReader(csvfile).fieldnames
            for key in self.unit.keys():
                if key not in headers:
                    self.log_basename = self._increment_suffix(self.log_basename) # start a new file if headers don't match up anymore with all the data we're trying to store
                    break
        self._update_legacy_keys()                
        self.next_log_notes = ['software initialization'] # used for storing specific notes in the next row written to the log
        self.log_unit_called_yet = False # used for one time check whether need to make a new log file, or whether log file headers have changed since last run
        self.log_unit()

    def __str__(self):
        files = {'settings':self.unit.filename, 'log':self.log_path}
        if self.type == 'pos':
            return pprint.pformat({'files':files, 'unit':self.unit})
        else:
            return pprint.pformat({'files':files, 'unit':self.unit})

    def read(self,key):
        """Returns current value for a given key.
        """
        if key in self.unit.keys():
            return self.unit[key]
        self.printfunc('no key ' + repr(key) + ' found')
        self.printfunc('keys: ' + str(self.unit.keys()))
        return None

    def store(self,key,val):
        """Store a value to memory.
        """
        if key in pc.nominals.keys():
            nom = pc.nominals[key]['value']
            tol = pc.nominals[key]['tol']
            if val < nom - tol or val > nom + tol: # check for absurd values
                self.printfunc('Attempted to set ' + str(key) + ' of ' + str(self.unit_basename) + ' to value = ' + str(val) + ', which is outside the nominal = ' + str(nom) + ' +/- ' + str(tol) + '. Defaulting to nominal value instead.')
                val = nom
        if key in self.unit.keys():
            self.unit[key] = val
        else:
            self.printfunc('value not set, because the key "' + repr(key) + '" was not found')
 
    def write(self):
        """Write all values to disk.
        """
        self.unit.write()
    
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
                row = self.unit.copy()
                row.update({'TIMESTAMP':timestamp,'NOTE':str(self.next_log_notes)})
                writer = csv.DictWriter(csvfile,fieldnames=self.log_fieldnames)
                writer.writerow(row)
            self.curr_log_length += 1
            self.next_log_notes = []
            self.log_unit_called_yet = True # only need to check this the first time through
    
    @property
    def log_fieldnames(self):
        '''Returns list of fieldnames we save to the log file.
        '''
        return ['TIMESTAMP'] + self.unit.keys() + ['NOTE']
    
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
        if 'CURRENT_LOG_BASENAME' in self.unit.keys():
            return self.unit['CURRENT_LOG_BASENAME']
        return ''
    
    @log_basename.setter
    def log_basename(self, name):
        self.unit['CURRENT_LOG_BASENAME'] = name

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
        #                                       old : new
        legacy_key_replacements = {'LAST_MOVE_CMD'  : 'MOVE_CMD',
                                   'LAST_MOVE_VAL1' : 'MOVE_VAL1',
                                   'LAST_MOVE_VAL2' : 'MOVE_VAL2'}
        for old_key in legacy_key_replacements.keys():
            if old_key in self.unit.keys():
                temp_val = self.unit[old_key]
                del self.unit[old_key]
                new_key= legacy_key_replacements[old_key]
                self.unit[new_key] = temp_val

if __name__=="__main__":
    state = PosState()