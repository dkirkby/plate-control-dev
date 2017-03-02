# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import numpy as np
import collections
import posconstants as pc

class Summarizer(object):
    '''Provides common functions for summarizing fiber positioner performance data.
    '''

    def __init__(self, this_test_data):
        ''' The dictionary this_test_data should contain values for all keys with
        type 'test' listed in the tuples below.
        '''
        
        self.thresholds = [0.003, 0.005] # mm, possible values for correction move cut-off point
        data_key_defs_list = [('start time',                      'loop'), # the second string in all these tuples says at what points the value may change
                              ('finish time',                     'move'),
                              ('curr cruise',                     'loop'),
                              ('curr creep',                      'loop'),
                              ('num targets',                     'move')] 
        self.err_keys =      [ 'blind max'] # max error on the blind move 0
        for threshold in self.thresholds:
            suffix = Summarizer._threshold_suffix(threshold)
            self.err_keys.append( ('corr max'      + suffix,      'move')) # max error after correction moves (threshold is applied)
            self.err_keys.append( ('corr rms'      + suffix,      'move')) # rms error after correction moves (threshold is applied)
            self.err_keys.append( ('mean num corr' + suffix,      'move')) # avg number of correction moves it took to reach either threshold or end of submove data
            self.err_keys.append( ('max num corr'  + suffix,      'move')) # max number of correction moves it took to reach either threshold or end of submove data
        data_key_defs_list.extend(self.err_keys)
        data_key_defs_list.extend([
                              ('total move sequences at finish',  'move'),
                              ('total limit seeks T at finish',   'move'),
                              ('total limit seeks P at finish',   'move'),
                              ('xytest data file',                'loop'),
                              ('xytest log file',                 'test'),
                              ('pos log files',                   'move'),
                              ('num pts calib T',                 'loop'),
                              ('num pts calib P',                 'loop'),
                              ('test operator',                   'test'),
                              ('test station',                    'test'),
                              ('supply voltage',                  'test'),
                              ('temperature (C)',                 'test'),
                              ('relative humidity',               'test'),
                              ('operator notes',                  'test')])
        data_key_defs_dict = collections.OrderedDict(data_key_defs_list)
    
        self.all_keys = list(data_key_defs_dict.keys())
        self.loop_keys = [k for k in self.all_keys if data_key_defs_dict[k] == 'loop']
        self.move_keys = [k for k in self.all_keys if data_key_defs_dict[k] == 'move']
        self.test_keys = [k for k in self.all_keys if data_key_defs_dict[k] == 'test']    
        self._row_template = collections.OrderedDict.fromkeys(self.all_keys)
        for key in this_test_data.keys():
            if key in self.all_keys:
                self._row_template[key] = this_test_data[key]
            else:
                print('Warning: ' + str(key) + ' is not a valid key for the summarizer.')
        for key in self.test_keys:
            if key not in this_test_data.keys():
                print('Warning: ' + str(key) + ' was not provided when initializing summarizer.')

    
    def csv_writeable_header(self):
        '''Returns a string with descriptive headers for each of the columns in csv_writeable_summary.
        '''
        s = ''
        for key in self.all_keys:
            s += key
            if key in self.err_keys:
                s += ' (um)'
            s += ','
        s = s[:-1] # remove that last comma
        return s

    def csv_writeable_row(self, err_data):
        '''Makes a string that is formatted for writing a new line to a csv log file.
        See error_summary() method for comments on the dictionary err_data.
        '''
        s = ''
        um_per_mm = 1000
        row = self.make_row(err_data)
        for key in row.keys():
            this_val = row[key]
            if key in self.err_keys:
                this_val = format(this_val * um_per_mm, '.1f')
            else:
                this_val = str(this_val)
            s += this_val + ','
        s = s[:-1] # remove that last comma
        return s

    def error_summary(err_data, threshold):
        '''Summarizes the error data for a single positioner.
        
        INPUTS:
            err_data  ... list of lists, where the first index is the submove number,
                          and then selecting that gives you the list of all error data
                          for that submove. The units must be mm.
                          
            threshold ... the first submove encountered which has an error value less than
                          or equal to threshold is considered the point at which a robot would
                          (in practice on the mountain) be held there and do no more corrections.
                          The units must be mm.
                            
        OUTPUTS:
            summary   ... dictionary, with keys:
                            'blind max'
                            'corr max'
                            'corr rms'
                            'mean num corr'
                            'max num corr'
                            'all blind errs' ... list of all the blind move error values
                            'all corr errs'  ... list of all the corrected move error values (threshold is applied)
                            'all corr nums'  ... list of which how many correction moves it took for each target to reach the threshold (or end of submove data)
        '''
        summary = {}
        summary['all blind errs'] = err_data[0]
        summary['blind max'] = max(summary['all blind errs'])
        n = len(err_data[0])
        summary['all corr errs'] = [np.inf]*n
        summary['all corr nums'] = [0]*n
        has_hit_threshold = [False]*n
        for submove in range(len(err_data)):
            for i in range(n):
                this_err = err_data[submove][i]
                if not(has_hit_threshold[i]):
                    summary['all corr nums'][i] = submove
                    summary['all corr errs'][i] = this_err
                    if this_err <= threshold:
                        has_hit_threshold[i] = True
        suffix = Summarizer._threshold_suffix(threshold)
        summary['corr max'      + suffix] = max(summary['all corr errs'])
        summary['corr rms'      + suffix] = np.sqrt(np.sum(np.power(summary['all corr errs'],2))/n)
        summary['mean num corr' + suffix] = np.mean(summary['all corr nums'])
        summary['max num corr'  + suffix] = max(summary['all corr nums'])
        return summary

    def make_row(self, err_data):
        '''Makes a row of values. These are returned as an ordered dictionary based
        on the row template. See error_summary() method for comments on err_data.
        '''
        row = self._row_template.copy()
        row['finish time'] = pc.
                              ('curr cruise',                     'loop'),
                              ('curr creep',                      'loop'),
                              ('num targets',                     'move')] 
        self.err_keys =      [ 'blind max'] # max error on the blind move 0
        for threshold in self.thresholds:
            suffix = Summarizer._threshold_suffix(threshold)
            self.err_keys.append( ('corr max'      + suffix,      'move')) # max error after correction moves (threshold is applied)
            self.err_keys.append( ('corr rms'      + suffix,      'move')) # rms error after correction moves (threshold is applied)
            self.err_keys.append( ('mean num corr' + suffix,      'move')) # avg number of correction moves it took to reach either threshold or end of submove data
            self.err_keys.append( ('max num corr'  + suffix,      'move')) # max number of correction moves it took to reach either threshold or end of submove data
        data_key_defs_list.extend(self.err_keys)
        data_key_defs_list.extend([
                              ('total move sequences at finish',  'move'),
                              ('total limit seeks T at finish',   'move'),
                              ('total limit seeks P at finish',   'move'),
                              ('xytest data file',                'loop'),
                              ('xytest log file',                 'test'),
                              ('pos log files',                   'move'),
                              ('num pts calib T',                 'loop'),
                              ('num pts calib P',                 'loop'),
                              ('test operator',                   'test'),
                              ('test station',                    'test'),
                              ('supply voltage',                  'test'),
                              ('temperature (C)',                 'test'),
                              ('relative humidity',               'test'),
                              ('operator notes',                  'test')])        
            
        for threshold in self.thresholds:
            summary = self.error_summary(err_data,threshold)
            for key in summary.keys():
                if key in self.err_keys:
                    row[key] = summary[key]
        
        return row

    @staticmethod
    def _threshold_suffix(value):
        '''For consistent internal generation of certain keys.
        '''
        return ' - ' + str(value) + ' um threshold'