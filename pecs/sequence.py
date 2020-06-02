# -*- coding: utf-8 -*-
"""
Created on Mon Jun  1 16:20:26 2020

@author: joe
"""

col_defaults = {'command': '',
                'target0': 0.0,
                'target1': 0.0,
                'log_note': '',
                }

pos_defaults = {'CURR_SPIN_UP_DOWN': 70,
                'CURR_CRUISE': 70,
                'CURR_CREEP': 70,
                'CREEP_PERIOD': 2,
                'FINAL_CREEP_ON': True,
                'ANTIBACKLASH_ON': True,
                'ONLY_CREEP': False,
                'SPINUPDOWN_PERIOD': 12,
                'MIN_DIST_AT_CRUISE_SPEED': 180.0,
                }

col_defaults.update(pos_defaults)

pos_comments = {'CURR_SPIN_UP_DOWN': 'int, 0-100, spin up / spin down current',
                'CURR_CRUISE': 'int, 0-100, cruise current',
                'CURR_CREEP': 'int, 0-100, creep current',
                'CREEP_PERIOD': 'int, number of timer intervals corresponding to a creep step. a higher value causes slower creep',
                'FINAL_CREEP_ON': 'bool, if true do a finishing creep move after cruising',
                'ANTIBACKLASH_ON': 'boolean, if true do an antibacklash sequence at end of a move',
                'ONLY_CREEP': 'bool, if true disable cruising speed',
                'SPINUPDOWN_PERIOD': 'int, number of 55 us periods to repeat each displacement during spin up to cruise speed or spin down from cruise speed. a higher value causes slower acceleration, over a longer travel distance',
                'MIN_DIST_AT_CRUISE_SPEED': 'float, minimum rotor distance in deg to travel when at cruise speed before slowing back down',
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

valid_commands = {'QS', 'dQdS',
                  'obsXY', 'obsdXdY',
                  'ptlXY',
                  'poslocXY', 'poslocdXdY',
                  'poslocTP', 'posintTP', 'dTdP'}

import os
from astropy.table import Table

class TestSequence(object):
    '''Iterable structure that defines a positioner test, as a sequence of Move instances.
    
        short_name ... string, brief name for the test
        long_name  ... string, optional longer descriptive name for the test
        
    After initialization, populate the sequence using the "add_move" function.
    '''
    def __init__(self, short_name, long_name=''):
        names = [key for key in col_defaults.keys()]
        types = [type(val) for val in col_defaults.values()]
        self.table = Table(names=names, dtype=types)
        self.short_name = short_name
        self.long_name = str(long_name)
        
    @property
    def short_name(self):
        return self.table.meta['short_name']
    
    @short_name.setter
    def short_name(self, value):
        self.table.meta['short_name'] = str(value)

    @property
    def long_name(self):
        return self.table.meta['long_name']
    
    @long_name.setter
    def long_name(self, value):
        self.table.meta['long_name'] = str(value)
    
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
            expected_type =  type(pos_defaults[key])
            if isinstance(value, int) and isinstance(expected_type, float):
                value = float(value)
            assert isinstance(value, expected_type)
            row[key] = value
        if index:
            self.table.insert_row(index, row)
        else:
            self.table.add_row(row)
    
    def save(self, directory='.', basename='sequence'):
        '''Saves an ecsv file representing the sequence to directory/basename.ecsv
        '''
        path = os.path.join(directory, basename + '.ecsv')
        self.table.write(path, overwrite=True)
    
    def non_default_pos_settings(self, row_index):
        '''Return dict containing only those fields for which the given row
        has non-default pos settings values (as defined in pos_defaults).
        '''
        row = self.table[row_index]
        d = {key:row[key] for key in pos_defaults if pos_defaults[key] != row[key]}
        return d
    
    def __str__(self):
        s = self.short_name + ': ' + self.long_name + '\n'
        def truncate_and_fill(string, length):
            truncated = string[:length-2] + '..' if len(string) > length else string
            filled = format(truncated, str(length) + 's')
            return filled
        widths = {'note':40, 'settings':50}
        s += 'ROW '
        s += '   COMMAND '
        s += '      U '
        s += '      V  '
        s += truncate_and_fill('LOG_NOTE', widths['note']) + '  '
        s += truncate_and_fill('SETTINGS', widths['settings'])
        for i in range(len(self.table)):
            move = self.table[i]
            s += '\n'
            s += format(i, '3d') + ' '
            s += format(move['command'], '>10s') + ' '
            s += format(move['target0'], '7g') + ' '
            s += format(move['target1'], '7g') + '  '
            s += truncate_and_fill(str(move['log_note']), widths['note']) + '  '
            s += truncate_and_fill(str(self.non_default_pos_settings(i)), widths['settings'])
        return s