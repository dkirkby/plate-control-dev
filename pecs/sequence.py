# -*- coding: utf-8 -*-
"""
Represents a sequence of positioner moves, with detailed control over motor
and move scheduling parameters.
"""

move_defaults = {'command': '',
                 'target0': 0.0,
                 'target1': 0.0,
                 'log_note': '',
                 }

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

col_defaults = move_defaults.copy()
col_defaults.update(pos_defaults)

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

general_commands = {'QS', 'dQdS',
                    'obsXY', 'obsdXdY',
                    'ptlXY',
                    'poslocXY', 'poslocdXdY',
                    'poslocTP', 'posintTP', 'dTdP',
                   }

homing_commands = {'home_and_debounce', 'home_no_debounce'}
# When setting up homing rows in a sequence table, set target0 = 1 if you want
# to home theta axis, target1 = 1 to home phi axis, or both to home both axes.

valid_commands = general_commands.copy()
valid_commands.update(homing_commands)

import os
from astropy.table import Table
import numpy as np

is_number = lambda x: isinstance(x, (int, float, np.integer, np.floating))
is_bool = lambda x: isinstance(x, (bool, np.bool_))

def read(path):
    '''Reads in and validates format for a saved Sequence from a file. E.g.
        sequence = Sequence.read(path)
    '''
    table = Table.read(path)
    example = Sequence(short_name='dummy')
    example.add_move(command='QS', target0=0.0, target1=0.0)
    for col in table.columns:
        assert col in example.table.columns
        for i in range(len(table)):
            val = table[col][i]
            test = example.table[col][0]
            if is_number(val) and is_number(test) or is_bool(val) and is_bool(test):
                continue
            assert isinstance(val, type(test))
        try:
            np.isfinite(example.table[col][0])
            isnumber = True
        except:
            isnumber = False
        if isnumber:
            assert all(np.isfinite(table[col]))
    for row in table:
        assert row['command'] in valid_commands
    sequence = Sequence(short_name=table.meta['short_name'],
                        long_name=table.meta['long_name'])
    sequence.table = table
    return sequence

class Sequence(object):
    '''Iterable structure that defines a positioner test, as a sequence of Move instances.
    
        short_name ... string, brief name for the test
        long_name  ... string, optional longer descriptive name for the test
        details ... string, optional additional string to explain the test's purpose, etc
        
    After initialization, populate the sequence using the "add_move" function.
    '''
    def __init__(self, short_name, long_name='', details=''):
        names = [key for key in col_defaults.keys()]
        types = [type(val) for val in col_defaults.values()]
        self.table = Table(names=names, dtype=types)
        self.short_name = short_name
        self.long_name = str(long_name)
        self.details = str(details)
        
    @property
    def short_name(self):
        return self.table.meta['short_name']
    
    @short_name.setter
    def short_name(self, value):
        self.table.meta['short_name'] = str(value)

    @property
    def normalized_short_name(self):
        '''A particular format, used for example when saving files to disk.'''
        return self.short_name.replace(' ','_').upper()

    @property
    def long_name(self):
        return self.table.meta['long_name']
    
    @long_name.setter
    def long_name(self, value):
        self.table.meta['long_name'] = str(value)
        
    @property
    def details(self):
        return self.table.meta['details']
    
    @details.setter
    def details(self, value):
        self.table.meta['details'] = str(value)
        
    def add_move(self, command, target0, target1, log_note='', pos_settings={}, index=None):
        '''Add a move to the sequence.
        
        Inputs
            command      ... move command string as described in petal.request_targets()
            target0      ... 1st target coordinate or delta, as described in petal.request_targets()
            target1      ... 2nd target coordinate or delta, as described in petal.request_targets()
            log_note     ... optional string to store alongside log data for this move
            pos_settings ... optional dict of positioner settings to apply during the move
            index        ... optional index value to insert move at a particular location (default behavior is to append)
        '''
        assert command in valid_commands
        row = col_defaults.copy()
        row['command'] = command
        row['target0'] = float(target0)
        row['target1'] = float(target1)
        row['log_note'] = str(log_note)
        for key, value in pos_settings.items():
            assert key in pos_defaults
            example = pos_defaults[key]
            expected_type =  type(example)
            if isinstance(value, (int, np.integer)) and isinstance(example, (float, np.floating)):
                value = float(value)
            assert isinstance(value, expected_type)
            row[key] = value
        if index:
            self.table.insert_row(index, row)
        else:
            self.table.add_row(row)
            
    def delete_move(self, index):
        '''Delete a move from the sequence. (Note you can also use the more
        generic and pythonic del syntax.)'''
        assert 0 <= index <= len(self.table), f'error index {index} not in sequence'
        del self.table[index]
    
    def save(self, directory='.', basename=''):
        '''Saves an ecsv file representing the sequence to directory/basename.ecsv
        '''
        if not basename:
            basename = f'seq_{self.normalized_short_name}'
        path = os.path.join(directory, basename + '.ecsv')
        self.table.write(path, overwrite=True, delimiter=',')
    
    def pos_settings(self, row_index):
        '''Return dict containing all pos settings. Will be shaped like
        pos_defaults.'''
        row = self.table[row_index]
        d = {key:row[key] for key in pos_defaults if key}
        return d
    
    def non_default_pos_settings(self, row_index):
        '''Return dict containing only those fields for which the given row
        has non-default pos settings values (as defined in pos_defaults).
        '''
        row = self.table[row_index]
        d = {key:row[key] for key in pos_defaults if pos_defaults[key] != row[key]}
        return d
    
    def __str__(self):
        s = f'{self.normalized_short_name}'
        if self.long_name:
            s += f': {self.long_name}'
        if self.details:
            s += f'\n{self.details}'
        s += '\n'
        def truncate_and_fill(string, length):
            truncated = string[:length-2] + '..' if len(string) > length else string
            filled = format(truncated, str(length) + 's')
            return filled
        width_note = 40
        width_settings = 50
        width_command = max(7, max({len(row['command']) for row in self.table}))
        s += 'ROW   '
        s += format('COMMAND', f'<{width_command}.{width_command}')
        s += '     U '
        s += '      V  '
        s += truncate_and_fill('LOG_NOTE', width_note) + '  '
        s += truncate_and_fill('SETTINGS', width_settings)
        for i in range(len(self.table)):
            move = self.table[i]
            s += '\n'
            s += format(i, '3d') + ' '
            s += truncate_and_fill(f'  {move["command"]} ', width_command) + ' '
            s += format(move['target0'], '7g') + ' '
            s += format(move['target1'], '7g') + '  '
            s += truncate_and_fill(str(move['log_note']), width_note) + '  '
            s += truncate_and_fill(str(self.non_default_pos_settings(i)), width_settings)
        return s
    
    def __repr__(self):
        return self.__str__()
    
    # Standard sequence functions
    def __iter__(self):
        self.__idx = 0
        return self
        
    def __next__(self):
        if self.__idx < len(self.table):
            row = self.table[self.__idx]
            self.__idx += 1
            return row
        else:
            raise StopIteration
    
    def __len__(self):
        return len(self.table)
    
    def __getitem__(self, key):
        return self.table[key]
        
    def __setitem__(self, key, value):
        self.table[key] = value

    def __delitem__(self, key):
        del self.table[key]
        
    def __contains__(self, value):
        return value in self.table