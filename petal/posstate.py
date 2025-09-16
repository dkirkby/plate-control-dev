# -*- coding: utf-8 -*-
import os
from configobj import ConfigObj
import csv
import pprint
import posconstants as pc
try:
    from DOSlib.positioner_index import PositionerIndex
except:
    print('DOSlib.positioner_index module not available. (This may be ok for some environments.)')
try:
    from DBSingleton import DBSingleton
    DB_COMMIT_AVAILABLE = True
except ModuleNotFoundError:
    DB_COMMIT_AVAILABLE = False


class PosState(object):
    """Variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object.

    This class is also used for tracking state of fiducials or petals.

    INPUTS:
        unit_id:  POS_ID, FID_ID, or PETAL_ID of device, must be str
        logging:  boolean whether to enable logging state data to disk
        type:     'pos', 'fid', 'ptl'
        petal_id: '00' to '11', '900' to '909', must be string
        alt_move_adder: function handle the state can use to add itself to petal's altered_states collection
        alt_calib_adder: function handle the state can use to add itself to petal's altered_calib_states collection

    Notes:
        Default settings are used if no unit_id is supplied.
        Values are stored in configobj files.
        There is a distinction between unit parameters (specific to one
        hardware unit) and general parameters (settings which apply
        uniformly to many units).

        to enable config read and write, set DOS_POSMOVE_WRITE_TO_DB to false

    For testing:
        use petal 03, pos M05055, fid P051, which are all available in DB
    """

    def __init__(self, unit_id=None, device_type='pos', petal_id=None,
                 logging=False, printfunc=print, defaults=None,
                 alt_move_adder=None, alt_calib_adder=None):
        self.printfunc = printfunc
        self.logging = logging
        self.write_to_DB = False
        self._set_altered_state_adders(func_move=alt_move_adder, func_calib=alt_calib_adder)
        if DB_COMMIT_AVAILABLE and (os.getenv('DOS_POSMOVE_WRITE_TO_DB')
                                    in ['True', 'true', 'T', 't', '1', None]):
            self.write_to_DB = True
        # data initialization
        if device_type in ['pos', 'fid', 'ptl']:
            self.type = device_type
        else:
            raise Exception('Invalid device_type')
        # DOS change
        if device_type == 'ptl':
            self.petal_state_defaults = defaults
        else:
            self.petal_state_defaults = None
        if self.write_to_DB:  # data initialization from database
            #self.printfunc('posstate DB write on')
            if petal_id is not None:  # ptlid is given, simple
                self.ptlid = petal_id
                if unit_id is not None:  # both ptlid and unit_id given
                    if self.type == 'ptl':
                        assert self.ptlid == unit_id, 'inconsistent input'
                        # TODO fix this; still reading from a template config
                        self.load_from_cfg(unit_id=self.ptlid)
                    else:
                        self.load_from_db(unit_id=unit_id)
                    self.unit_id = unit_id
            else:  # ptlid unkonwn
                if unit_id is not None:  # only unit id given
                    self.unit_id = unit_id
                    if self.type == 'ptl':  # no ptlid, but unit_id given
                        self.ptlid = unit_id
                        # TODO fix this; still reading from a template config
                        self.load_from_cfg(unit_id=self.ptlid)
                    else:
                        try:
                            self.set_ptlid_from_pi(unit_id)  # lookup ptlid
                            self.load_from_db(unit_id=unit_id)
                        except KeyError:  # test posid, not existent
                            self.load_from_cfg(unit_id=unit_id)
                else:  # both unit_id and ptlid are unkonwn, read template
                    self.ptlid = None  # assume ptlid = -1
                    if self.type == 'ptl':  # unit_id and ptlid both unkonwn
                        # TODO fix this; still reading from a template config
                        self.load_from_cfg()
                    else:
                        self.load_from_db()
        else:
            # no DB commit, use local cfg only, skipped after switchover
            # below is directly repositioned from old version
            if petal_id is None:  # ptlid is none, what about unit id?
                if unit_id is not None and self.type == 'ptl':
                    self.unit_id = self.ptlid = unit_id
            else:
                self.unit_id = unit_id
                self.ptlid = petal_id
                self.unit_basename = 'unit_' + str(unit_id)
            self.load_from_cfg(unit_id=unit_id)
            # local text log file setup
            self.log_separator = '_log_'
            self.log_numformat = '08g'
            self.log_extension = '.csv'
            if not(self.log_basename):
                all_logs = os.listdir(self.logs_dir)
                unit_logs = [x for x in all_logs if self.unit_basename in x
                             and self.log_extension in x]
                if unit_logs:
                    unit_logs.sort(reverse=True)
                    self.log_basename = unit_logs[0]
                else:
                    log_basename = (self.unit_basename + self.log_separator
                                    + format(0, self.log_numformat)
                                    + self.log_extension)
                    self.log_basename = self._increment_suffix(log_basename)
            # number of rows in log before starting a new file
            self.max_log_length = 10000
            # keep track of this in a separate variable so don't have to
            # recount every time -- only when necessary
            self.curr_log_length = self._count_log_length()
            if os.path.isfile(self.log_path):  # create local log file
                with open(self.log_path, 'r', newline='') as csvfile:
                    headers = csv.DictReader(csvfile).fieldnames
                for key in self._val:
                    if key not in headers:
                        # start a new file if headers don't match up anymore
                        # with all the data we're trying to store
                        self.log_basename = self._increment_suffix(
                            self.log_basename)
                        break
            # list of fieldnames we save to the log file.
            self.log_fieldnames = (['TIMESTAMP'] + list(self._val.keys()))
            # used for storing specific notes in the next row written to log
            self._append_log_note('software initialization')
            # used for one time check whether need to make a new log file,
            # or whether log file headers have changed since last run
            self.log_unit_called_yet = False
            self.log_unit()
            self._update_legacy_keys()  # only config files need this update
            # used for storing specific notes in the next row written to log
            # log notes aren't recorded in DB :(
            # but we still need to 'collect' them

        # reset some positioner values in the beginning
        if self.type == 'pos':
            self._val['MOVE_CMD'] = ''
            self._val['MOVE_VAL1'] = ''
            self._val['MOVE_VAL2'] = ''
        self._clear_last_meas_entries()
        self.clear_log_notes()
        self.clear_calib_notes()
        self.clear_late_commit_entries()

    def set_ptlid_from_pi(self, unit_id):
        ''' lookup petal id using unit_id for pos, fid from PositionerIndex '''
        pi = PositionerIndex()
        ret = pi.find_by_arbitrary_keys(DEVICE_TYPE=self.type.upper(),
                                        DEVICE_ID=unit_id)
        assert len(ret) == 1, f'lookup not unique, {ret}'
        self.ptlid = f'{ret[0]["PETAL_ID"]:02}'

    def load_from_db(self, unit_id=None):

        self._val = {}  # no local config used to create _val, make empty one
        ptlid_int = None if self.ptlid is None else int(self.ptlid)
        self.pDB = DBSingleton(petal_id=ptlid_int)
        if unit_id is None:  # unit id not supplied, load templates
            unit_id = 'xxxxx'
            if self.type == 'pos':
                # group = 'fiber_positioner' + '_default'
                self._val.update(self.pDB.get_pos_def_constants()[unit_id])
            elif self.type == 'fid':
                # group = 'fiducials' + '_default'
                self._val.update(self.pDB.get_fid_def_constants()[unit_id])
            else:
                raise Exception('PTL settings cannot be loaded from DB yet')
        else:  # unit id is supplied
            if self.type == 'pos':
                # group = 'fiber_positioner'
                # self.printfunc(f'Loading PTL {self.ptlid}, pos {unit_id}...')
                self._val.update(self.pDB.get_pos_id_info(unit_id))
                self._val.update(self.pDB.get_pos_constants(unit_id))
                self._val.update(self.pDB.get_pos_move(unit_id))
                self._val.update(self.pDB.get_pos_calib(unit_id))
            elif self.type == 'fid':
                # group = 'fiducials'
                # self.printfunc(f'Loading PTL {self.ptlid}, fid {unit_id}...')
                self._val.update(self.pDB.get_fid_id_info(unit_id))
                self._val.update(self.pDB.get_fid_constants(unit_id))
                self._val.update(self.pDB.get_fid_data(unit_id))
                self._val.update(self.pDB.get_fid_calib(unit_id))
            else:
                raise Exception('PTL settings cannot be loaded from DB yet')
        # TODO: check overlap between self.cDB and self._val ?
        # self.cdB = self.pDB.constantsDB.get_constants(
        #     snapshot='DESI', tag='CURRENT', group=group)[group][unit_id]
        self.unit_id = unit_id
        self.clear_log_notes() # used here to initialize
        self.clear_calib_notes() # used here to initialize

    def load_from_cfg(self, unit_id=None):
        # do this here because used in 2 different places below
        typical_settings_dir = pc.dirs[self.type + '_settings']
        if unit_id is not None:
            self.unit_basename = 'unit_' + str(unit_id).zfill(2)
            self.logs_dir = pc.dirs[self.type + '_logs']
            self.settings_dir = typical_settings_dir
            comment = 'Settings file for unit: ' + str(unit_id)
        else:  # unit ID is None
            self.unit_id = 'TEMP_' + self.type
            self.unit_basename = 'unit_' + self.unit_id
            self.logs_dir = pc.dirs['temp_files']
            self.settings_dir = pc.dirs['temp_files']
            comment = 'Temporary settings file for software test purposes'\
                      ', not associated with aany particular unit.'
        unit_fn = os.path.join(self.settings_dir, f'{self.unit_basename}.conf')
        if not(os.path.isfile(unit_fn)):
            # unit config doesn't exisit, read in the generic template file
            tmpfn = os.path.join(typical_settings_dir,
                                 '_unit_settings_DEFAULT.conf')
            self.conf = ConfigObj(tmpfn, unrepr=True, encoding='utf-8')
            self.conf.initial_comment = [comment, '']
            self.conf.filename = unit_fn
            if self.type == 'pos':
                self.conf['POS_ID'] = str(unit_id)
            elif self.type == 'fid':
                self.conf['FID_ID'] = str(unit_id)
            elif self.type == 'ptl':
                self.conf['PETAL_ID'] = str(unit_id)
                # DOS change
                if isinstance(self.petal_state_defaults, dict):
                    self.conf.update(self.petal_state_defaults)
            # DOS change
            if self.type != 'ptl':
                self.conf.write()
        else:
            # self.printfunc(f'Loading existing unit config for '
            #                f'device_type = {self.type}, path: {unit_fn}')
            self.conf = ConfigObj(unit_fn, unrepr=True, encoding='utf-8')
        self._val = self.conf.dict()
        self.clear_log_notes() # used here to initialize
        self.clear_calib_notes() # used here to initialize

    def __str__(self):
        files = {'settings':self.conf.filename, 'log':self.log_path}
        return pprint.pformat({'files':files, 'values':self._val})

    def read(self,key):
        """Returns current value for a given key. Left in place for legacy usage,
        but it is much faster to directly access _val dictionary (for reading values).
        """
        return self._val[key]

    def store(self, key, val, register_if_altered=True):
        """Store a value to memory. This is the correct way to store values, as
        it contains some checks on tolerance values. (You should NEVER EVER write
        directly to the state._val dictionary!)

        Returns a boolean stating whether the store operation was accepted. This
        will be False in cases where:

            - invalid key
            - value outside an allowed range
            - value is identical to existing value

        Special handling is applied to the note fields, 'LOG_NOTE' and 'CALIB_NOTE'.
        For these, the argued value string is appended to the existing note, rather
        than replacing it. (This simplifies syntax for the numerous cases where multiple
        notes are getting added at differing steps in the code. One can clear a note
        with the special functions clear_log_notes and clear_calib notes. A blank note
        string is ignored.)

        Normally, if a value is changed, then the state will register itself
        with petal as having been altered. That way petal knows to push its
        data to posmovedb upon the next commit(). This registration can be
        turned off in special cases by arguing register_if_altered=False.
        """
        if key not in self._val.keys():  # 1st check: validate the key name
            self.printfunc(f'Unit {self.unit_id}: invalid Key {key}')
            return False
        if key in pc.nominals:  # 2nd check: reject values too far from nominal
            nom, tol = pc.nominals[key]['value'], pc.nominals[key]['tol']
            val = float(val)  # helps clear out numpy floats (which are slower) when they sneak into system
            if not nom - tol <= val <= nom + tol:  # check for absurd values
                self.printfunc(
                    f'Unit {self.unit_id}: new value {val} for posstate key '
                    f'{key} rejected, outside nominal range {nom} ± {tol}')
                # val = nom
                return False
        if self._val[key] == val:
            return False  # no change, hence not "accepted"
        if key == 'LOG_NOTE':
            self._append_log_note(val, is_calib_note=False)
        elif key == 'CALIB_NOTE':
            self._append_log_note(val, is_calib_note=True)
        else:
            self._val[key] = val  # set value if all checks above are passed
            # self.printfunc(f'Key {key} set to value: {val}.')  # debug line
        if register_if_altered:
            if pc.is_calib_key(key):
                self._register_altered_calib()
            elif not pc.is_constants_key(key):
                # any other key must be in the moves db
                self._register_altered_move()
            if pc.is_cached_in_posmodel(key):
                self._refresh_posmodel()
        return True

    def write(self):
        """Write all values to disk.
        """
        if 'TIME_RECORDED' in self._val.keys():
            date_object = self._val['TIME_RECORDED']
            self._val['TIME_RECORDED'] = self._val['TIME_RECORDED'].isoformat()
            self.conf.update(self._val)
            self._val['TIME_RECORDED'] = date_object
        else:
            self.conf.update(self._val)
        self.conf.write()

    def log_unit(self):
        """All current unit parameters are written to the hardware unit's log file.
        """
        if self.logging:
            timestamp = pc.timestamp_str()
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
                row.update({'TIMESTAMP':timestamp})
                writer = csv.DictWriter(csvfile,fieldnames=self.log_fieldnames)
                writer.writerow(row)
            self.curr_log_length += 1
            self.clear_log_notes()
            self.clear_calib_notes()
            self.log_unit_called_yet = True # only need to check this the first time through

    @property
    def log_path(self):
        """Convenience method for consistent formatting of file path to log file.
        """
        return self.logs_dir + self.log_basename

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

    def _append_log_note(self, note, is_calib_note=False):
        '''Adds a log note to the existing note data that will be written to
        log upon commit or writetodb. Arg calib operates on CALIB_NOTE field
        rather than LOG_NOTE.
        '''
        key = 'CALIB_NOTE' if is_calib_note else 'LOG_NOTE'
        if key not in self._val:
            self._val[key] = str(note)
        else:
            self._val[key] = pc.join_notes(self._val[key], note)

    def clear_log_notes(self):
        '''Re-initializes the stored log notes. Can be used as an initiializer
        if no LOG_NOTE field yet established.'''
        self._val['LOG_NOTE'] = ''

    def clear_calib_notes(self):
        '''Like clear_log_notes, but for CALIB_NOTE field.'''
        self._val['CALIB_NOTE'] = ''

    def clear_late_commit_entries(self):
        '''Clears the "late commit" data fields.'''
        for key, value in pc.late_commit_defaults.items():
            if key in self._val:
                self._val[key] = value

    def _set_altered_state_adders(self, func_move=None, func_calib=None):
        '''Set function handles for registering when state changes. The intent
        here is that PosState can add itself to Petal's altered_state and
        altered_calib_state sets.'''
        if func_move and func_calib:
            self._register_altered_move = lambda: func_move(self)
            self._register_altered_calib = lambda: func_calib(self)
        else:
            self._register_altered_move = lambda: None
            self._register_altered_calib = lambda: None

    def set_posmodel_cache_refresher(self, func):
        '''Set function handle for refreshing posmodel cache when a relevant
        state value changes.'''
        self._refresh_posmodel = func

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
            possible_new_keys_and_defaults = {'LAST_MEAS_FWHM': None,
                                              'KEEPOUT_EXPANSION_PHI_RADIAL': 0.0,
                                              'KEEPOUT_EXPANSION_PHI_ANGULAR': 0.0,
                                              'KEEPOUT_EXPANSION_THETA_RADIAL': 0.0,
                                              'KEEPOUT_EXPANSION_THETA_ANGULAR': 0.0,
                                              'CLASSIFIED_AS_RETRACTED': False,
                                              'EXPOSURE_ID': None,
                                              'EXPOSURE_ITER': None,
                                              'DEVICE_CLASSIFIED_NONFUNCTIONAL': False,
                                              'FIBER_INTACT': True,
                                              'CALIB_NOTE': '',
                                              }
            possible_new_keys_and_defaults.update(pc.late_commit_defaults)
        elif self.type == 'fid':
            possible_new_keys_and_defaults = {'LAST_MEAS_OBS_X':[],
                                              'LAST_MEAS_OBS_Y':[],
                                              'LAST_MEAS_FWHMS':[],
                                              'DEVICE_CLASSIFIED_NONFUNCTIONAL':False,
                                              }
        elif self.type == 'ptl':
            possible_new_keys_and_defaults = {}

        for key in possible_new_keys_and_defaults:
            if key not in self._val:
                self._val[key] = possible_new_keys_and_defaults[key]

    def _clear_last_meas_entries(self):
        '''Clears specific values from legacy "LAST_MEAS_*" fields. Intended
        to be run upon initialization, to halt useless forward propagation of
        any old data.'''
        keys = {key for key in self._val.keys() if 'LAST_MEAS' in key}
        for key in keys:
            self._val[key] = None

if __name__ == "__main__":
    # unit tests below, enable DB write
    os.environ['DOS_POSMOVE_WRITE_TO_DB'] = 'True'
    # pos init
    state = PosState(unit_id='M05055', device_type='pos', petal_id='03')
    # fid init
    state = PosState(unit_id='P051', device_type='fid', petal_id='03')
    # ptl init
    state = PosState(device_type='ptl', petal_id='03')
    # None input
    state = PosState()
