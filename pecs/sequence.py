# -*- coding: utf-8 -*-
"""
Represents a sequence of positioner moves, with detailed control over motor
and move scheduling parameters.
"""

import os
from astropy.table import Table, vstack
import numpy as np
import datetime
import pandas
import sys
sys.path.append('../petal')
import posconstants as pc

pos_defaults = {'CURR_SPIN_UP_DOWN': 70,
                'CURR_CRUISE': 70,
                'CURR_CREEP': 70,
                'CREEP_PERIOD': 2,
                'SPINUPDOWN_PERIOD': 12,
                'FINAL_CREEP_ON': True,
                'ANTIBACKLASH_ON': True,
                'ONLY_CREEP': False,
                'MIN_DIST_AT_CRUISE_SPEED': 180.0,
                'ALLOW_EXCEED_LIMITS': False,
                'BACKLASH': 3.0,
                'PRINCIPLE_HARDSTOP_CLEARANCE_T': 3.0,
                'PRINCIPLE_HARDSTOP_CLEARANCE_P': 3.0,
                'MOTOR_CCW_DIR_P': -1,
                'MOTOR_CCW_DIR_T': -1,
                }

pos_comments = {'CURR_SPIN_UP_DOWN': 'int, 0-100, spin up / spin down current',
                'CURR_CRUISE': 'int, 0-100, cruise current',
                'CURR_CREEP': 'int, 0-100, creep current',
                'CREEP_PERIOD': 'int, number of timer intervals corresponding to a creep step. a higher value causes slower creep',
                'SPINUPDOWN_PERIOD': 'int, number of 55 us periods to repeat each displacement during spin up to cruise speed or spin down from cruise speed. a higher value causes slower acceleration, over a longer travel distance',
                'FINAL_CREEP_ON': 'bool, if true do a finishing creep move after cruising',
                'ANTIBACKLASH_ON': 'boolean, if true do an antibacklash sequence at end of a move',
                'ONLY_CREEP': 'bool, if true disable cruising speed',
                'MIN_DIST_AT_CRUISE_SPEED': 'float, minimum rotor distance in deg to travel when at cruise speed before slowing back down',
                'ALLOW_EXCEED_LIMITS': 'bool, flag to allow positioner to go past software limits or not. exercise some caution if setting',
                'BACKLASH': 'deg, backlash removal distance',
                'PRINCIPLE_HARDSTOP_CLEARANCE_T': 'float, minimum distance in deg to stay clear of theta principle hardstop',
                'PRINCIPLE_HARDSTOP_CLEARANCE_P': 'float, minimum distance in deg to stay clear of phi principle hardstop',
                'MOTOR_CCW_DIR_P': '+1 or -1, defining as-wired motor counter-clockwise direction',
                'MOTOR_CCW_DIR_T': '+1 or -1, defining as-wired motor counter-clockwise direction',
                }

nominals = {}
nominals['gear_ratio'] = ((46+14)/14)**4
nominals['timer_update_rate'] = 18e3 # Hz
nominals['stepsize_creep'] = 0.1 # deg
nominals['stepsize_cruise'] = 3.3 # deg
nominals['motor_speed_cruise'] = 9900.0 * 360.0 / 60.0 # deg/sec (= RPM *360/60)
nominals['spinupdown_dist_per_period'] = sum(range(round(nominals['stepsize_cruise']/nominals['stepsize_creep']) + 1))*nominals['stepsize_creep']
nominals['spinupdown_distance'] = nominals['spinupdown_dist_per_period'] * pos_defaults['SPINUPDOWN_PERIOD']
nominals['spinupdown_distance_output'] = nominals['spinupdown_distance'] / nominals['gear_ratio']

global_commands = {'QS', 'obsXY', 'ptlXY'}
abs_local_commands = {'poslocXY', 'poslocTP', 'posintTP'}
delta_commands = {'dQdS', 'obsdXdY', 'poslocdXdY', 'dTdP'}
abs_commands = global_commands | abs_local_commands
general_commands = abs_commands | delta_commands
homing_commands = {'home_and_debounce', 'home_no_debounce'}
local_commands = abs_local_commands | delta_commands | homing_commands
valid_commands = general_commands.copy()
valid_commands.update(homing_commands)

is_number = lambda x: isinstance(x, (int, float, np.integer, np.floating))
is_bool = lambda x: isinstance(x, (bool, np.bool_))

class Sequence(object):
    '''Iterable structure that defines a positioner test, as a sequence of Move instances.
    Typical operations you can do on a list work here (indexing, slices, del, etc).
    However, all elements must have type Move (see class lower in this module).
    
        short_name ... string, brief name for the test
        long_name  ... string, optional longer descriptive name for the test
        details ... string, optional additional string to explain the test's purpose, etc
        
    After initialization, populate the sequence using the "add_move" function.
    '''    
    def __init__(self, short_name, long_name='', details=''):
        self.moves = []
        self.short_name = short_name
        self.long_name = str(long_name)
        self.details = str(details)
        self.creation_date = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')

    @property
    def normalized_short_name(self):
        '''A particular format, used for example when saving files to disk.'''
        return self.short_name.replace(' ','_').upper()
    
    @staticmethod
    def read(path):
        '''Reads in and validates format for a saved Sequence from a file. E.g.
        sequence = Sequence.read(path)
        '''
        table = Table.read(path)
        table = Sequence._validate_table(table)
        sequence = Sequence(short_name='dummy')
        for key, value in table.meta.items():
            setattr(sequence, key, value)
        move_idxs = sorted(set(table['move_idx']))
        for m in move_idxs:
            subtable = table[m == table['move_idx']]
            kwargs = {key: subtable[key][0] for key in Move.single_keys}
            kwargs.update({key: subtable[key] for key in Move.multi_keys})
            move = Move(**kwargs)
            sequence.append(move)
        return sequence
    
    def save(self, directory='.', basename=''):
        '''Saves an ecsv file representing the sequence to directory/basename.ecsv
        Returns the path of the saved file.
        '''
        if not basename:
            basename = f'seq_{self.normalized_short_name}'
        tables = []
        for i in range(len(self)):
            move = self.moves[i]
            this_dict = move.to_dict()
            this_table = Table(this_dict())
            this_table['move_idx'] = [i] * len(this_table)
            tables.append(this_table)
        table = vstack(tables)
        path = os.path.join(directory, basename + '.ecsv')
        table.write(path, overwrite=True, delimiter=',')
        return path
    
    def __str__(self):
        s = f'{self.normalized_short_name}'
        if self.long_name:
            s += f': {self.long_name}'
        if self.creation_date:
            s += f'\nCreated: {self.creation_date}'
        if self.details:
            s += f'\n{self.details}'
        s += '\n'
        def truncate_and_fill(string, length):
            truncated = string[:length-2] + '..' if len(string) > length else string
            filled = format(truncated, str(length) + 's')
            return filled
        width_note = 50
        width_settings = 50
        width_command = max(7, max({len(move.command) for move in self}))
        width_command = min(width_command, 14)
        s += 'MOVE   '
        s += format('COMMAND', f'<{width_command}.{width_command}')
        s += '         U '
        s += '      V '
        s += ' LOC '
        s += ' ALLOW_CORR  '
        s += truncate_and_fill('LOG_NOTE', width_note) + '  '
        s += truncate_and_fill('SETTINGS', width_settings)
        for m in range(len(self)):
            move = self.moves[m]
            for i in range(len(move)):
                s += '\n'
                s += format(m, '4d') + ' '
                s += '  ' + truncate_and_fill(f'{move.command}', width_command) + '  '
                s += format(move.target0[i], '7g') + ' '
                s += format(move.target1[i], '7g') + ' '
                s += format(move.posloc[i], '3g') + ' '
                s += format(move.allow_corr, '11g') + '  '
                s += truncate_and_fill(str(move.log_note), width_note) + '  '
                s += truncate_and_fill(str(move.non_default_pos_settings), width_settings)
        return s
    
    def __repr__(self):
        return self.__str__()
    
    # Standard sequence functions
    def __iter__(self):
        self.__idx = 0
        return self
        
    def __next__(self):
        if self.__idx < len(self.table):
            move = self.moves[self.__idx]
            self.__idx += 1
            return move
        else:
            raise StopIteration
    
    def __len__(self):
        return len(self.moves)
    
    def __getitem__(self, key):
        return self.moves[key]
        
    def __setitem__(self, key, value):
        assert isinstance(value, Move), f'{value} must be an instance of Move class'
        self.moves[key] = value

    def __delitem__(self, key):
        del self.moves[key]
        
    def __contains__(self, value):
        return value in self.moves
    
    def _validate_table(table):
        '''Validates an astropy table representing a sequence. Returns a new
        table, which may be slightly modified. For example, adding any new columns
        which have been added to sequence since that table was saved to disk.
        '''
        new = table.copy()
        example_move = Move(command='dTdP', target0=0.0, target1=0.0)
        example_dict = example_move.to_table()
        example_table = Table(example_dict)
        for col in new.columns:
            assert col in example_table.columns
            for i in range(len(new)):
                val = new[col][i]
                test = example_table[col][0]
                if is_number(val) and is_number(test) or is_bool(val) and is_bool(test):
                    continue
                assert isinstance(val, type(test))
            try:
                np.isfinite(example_table[col][0])
                isnumber = True
            except:
                isnumber = False
            if isnumber:
                assert all(np.isfinite(new[col]))
        for row in new:
            assert row['command'] in valid_commands
        missing_col = set(example_table.columns) - set(new.columns)
        defaults = pos_defaults.copy()  # future-proof in case someone wants to add entries to defaults
        missing_col_default_available = missing_col & set(defaults)
        for col in missing_col_default_available:
            values = defaults[col]*len(new)
            new[col] = values
        if 'move_idx' not in new.columns:
            new['move_idx'] = range(len(new))
        return new
    
class Move(object):
    '''Encapsulates the command and settings data for a simultaneous movement of
    one or more fiber positioners.
    
        command      ... move command string as described in petal.request_targets()
        target0      ... 1st target coordinate(s) or delta(s), as described in petal.request_targets()
        target1      ... 2nd target coordinate(s) or delta(s), as described in petal.request_targets()
        posloc       ... optional sequence of which positioner device locations should be commanded
        log_note     ... optional string to store alongside log data for this move
        pos_settings ... optional dict of positioner settings to apply during the move
        allow_corr   ... optional boolean, whether correction moves are allowed to be performed after the primary ("blind") move
        
    Multiple positioners, same targets:
        By default, posloc='any', which means that the move command should be applied
        to any positioners selected at runtime (presumably by the PECS initialization
        process). In this case, all positioners get the same target0 and target1. The
        command string must be one of local_commands, as defined in this module.
        
    Multiple positioners, multiple targets:
        By arguing ordered sequences for target0, target1, and posloc, the user
        can specify different targets for different positioners. The command will be
        the same in all cases, and must be one of general_commands, as defined in this
        module.
        
    Homing commands:
        Set target0 = 1 if you want to home theta axis, target1 = 1 to home phi axis,
        or set both to home both axes.
    '''
    def __init__(self, command, target0, target1, posloc='any', log_note='', pos_settings={}, allow_corr=False):
        if posloc == 'any':
            assert command in local_commands, f'cannot apply a non-local command {command} to multiple positioners'
            for x in [target0, target1]:
                assert is_number(x), f'target {x} is not a number'
            self.target0 = [target0]
            self.target1 = [target1]
            self.posloc = [posloc]
        else:
            assert command in general_commands, f'command {command} not recognized, see general_commands collection'
            assert len(target0) == len(target1) == len(posloc), 'args target0, target1, and posloc are not of equal length'
            self.target0 = list(target0)
            self.target1 = list(target1)
            self.posloc = list(posloc)
        for X in [self.target0, self.target1]:
            assert all([is_number(x) for x in X]), 'all elements of target0 or target1 must be numbers'
        if command in homing_commands:
            assert target0[0] or target1[0], 'for a homing command, need to set target0 to 1 for theta ' + \
                                             'homing, target1 to 1 for phi homing, or both simultaneously'
        possible_device_locs = pc.generic_pos_neighbor_locs.keys()
        assert all([x in possible_device_locs for x in self.posloc]), 'all elements of posloc must be valid device locations'
        self.command = command
        self.log_note = str(log_note)
        self._pos_settings = self._validate_pos_settings(pos_settings)
        self.allow_corr = bool(allow_corr)
    
    # properties of Move with single values vs multiple values
    single_keys = {'command', 'log_note', 'pos_settings', 'allow_corr'}
    multi_keys = {'target0', 'target1', 'posloc'}         
    
    @staticmethod
    def _validate_pos_settings(settings):
        '''Returns a new, validated pos_settings dict, with possible type casts
        of values.'''
        new = settings.copy()
        for key, value in settings.items():
            assert key in pos_defaults
            example = pos_defaults[key]
            expected_type =  type(example)
            if isinstance(value, (int, np.integer)) and isinstance(example, (float, np.floating)):
                value = float(value)
                new[key] = value
            assert isinstance(value, expected_type)
        return new
    
    @property
    def pos_settings(self):
        '''Dict containing all pos settings. Will be shaped like pos_defaults.'''
        d = pos_defaults.copy()
        d.update(self._pos_settings)
        return d
    
    @property
    def non_default_pos_settings(self):
        '''Dict containing only those pos settings which have non-default values
        (as defined in pos_defaults).
        '''
        d = {key: self._pos_settings[key] for key in pos_defaults if pos_defaults[key] != self._pos_settings[key]}
        return d        
    
    def __len__(self):
        return len(self.posloc)
    
    @property
    def has_multiple_targets(self):
        '''Boolean whether this move has mulitple targets.'''
        return len(self) > 1
    
    def to_dict(self):
        '''Returns a dict, which is ready for direct conversion to an astropy
        table or pandas dataframe. Keys = column names and values = equal-length
        lists of column data.
        '''
        data = {}
        for key in self.single_keys:
            data[key] = [getattr(self, key)] * len(self)
        for key in self.multi_keys:
            data[key] = getattr(self, key)
        return data
    
    def make_request(self, loc2id_map, log_note=''):
        '''Make a move request data structure, ready for sending to the online control system.
        Any positioners known to this move instance, but not included in loc2id_map, will be
        skipped.
        
        INPUT:  loc2id_map ... keys=posloc, values=posids
                log_note ... optional string, will be appended to any existing log note
        
        OUTPUT: pandas dataframe with columns 'DEVICE_ID', 'COMMAND', 'X1', 'X2', 'LOG_NOTE'
        '''
        assert self.command not in homing_commands, 'Cannot make a request for homing. Try make_homing_kwargs() instead.'
        posids, target0, target1 = [], [], []
        if self.has_multiple_targets:
            for i in range(len(self)):
                posloc = self.posloc[i]
                if posloc in loc2id_map:
                    posids += [loc2id_map[posloc]]
                    target0 += [self.target0[i]]
                    target1 += [self.target1[i]]
        else:
            posids = [loc2id_map.values()]
            target0 = self.target0[0] * len(posids)
            target1 = self.target1[0] * len(posids)  
        log_note = pc.join_notes(self.log_note, log_note)
        request_data = {'DEVICE_ID': posids,
                        'COMMAND': self.command,
                        'X1': target0,
                        'X2': target1,
                        'LOG_NOTE': log_note,
                        }
        request = pandas.DataFrame(request_data)
        return request
        
    def make_homing_kwargs(self, posids, log_note=''):
        '''Make a kwargs dictionary for homing moves, ready for sending to the online
        control system.
        
        INPUT:  posids ... positioners to home
                log_note ... optional string, will be appended to any existing log note
        
        OUTPUT: kwargs dictionary
        '''
        assert self.command in homing_commands, 'Cannot make homing kwargs for non-homing. Try make_request() instead.'
        should_debounce = self.command == 'home_and_debounce'
        axis = 'theta_only' if not self.target1[0] else 'phi_only' if not self.target0[0] else 'both'
        log_note = pc.join_notes(self.log_note, log_note)
        kwargs = {'posids': posids,
                  'axis': axis,
                  'debounce': should_debounce,
                  'log_note': log_note,
                  }
        return kwargs
        
