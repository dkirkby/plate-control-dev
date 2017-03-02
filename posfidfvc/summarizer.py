# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import numpy as np
import collections

class Summarizer(object):
    '''Provides common functions for summarizing fiber positioner performance data.
    '''

    def __init__(self, this_test_data):
        self.thresholds = [0.003, 0.005] # mm, possible values for correction move cut-off point
        data_key_defs_list = [('start time',                      'loop'), # the second string in all these tuples says at what points the value may change
                              ('finish time',                     'move'),
                              ('curr cruise',                     'loop'),
                              ('curr creep',                      'loop'),
                              ('num targets',                     'move')] 
        self.err_keys =      [ 'blind max'] # max error on the blind move 0
        for threshold in self.thresholds:
            self.err_keys.append( ('corr max'      + self._threshold_suffix(threshold),  'move')) # max error after correction moves (threshold is applied)
            self.err_keys.append( ('corr rms'      + self._threshold_suffix(threshold),  'move')) # rms error after correction moves (threshold is applied)
            self.err_keys.append( ('mean num corr' + self._threshold_suffix(threshold),  'move')) # avg number of correction moves it took to reach either threshold or end of submove data
            self.err_keys.append( ('max num corr'  + self._threshold_suffix(threshold),  'move')) # max number of correction moves it took to reach either threshold or end of submove data
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
        self.row_template = collections.OrderedDict.fromkeys(self.all_keys)
        for key in this_test_data.keys():
            if key in self.all_keys:
                self.row_template[key] = this_test_data[key]
            else:
                print('Warning: ' + str(key) + ' is not a valid key for the summarizer.')
        for key in self.test_keys:
            if key not in this_test_data.keys():
                print('Warning: ' + str(key) + ' was not provided when initializing summarizer.')

    def _threshold_suffix(self, value):
        '''For consistent internal generation of certain keys.
        '''
        return ' - ' + str(value) + ' um threshold'

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
        summary['corr max'] = max(summary['all corr errs'])
        summary['corr rms'] = np.sqrt(np.sum(np.power(summary['all corr errs'],2))/n)
        summary['mean num corr'] = np.mean(summary['all corr nums'])
        summary['max num corr'] = max(summary['all corr nums'])
        return summary

    def row_data(self, err_data):
        '''Makes a row of values. These are returned as an ordered dictionary based
        on the row template. See error_summary() method for comments on err_data.
        '''
        # (deep?) copy the row_template ordered dict, then fill it in below
        for threshold in self.thresholds:
            summary = self.error_summary(err_data,threshold)
        

    def csv_writeable_row(err_data):
        '''Makes a string that is formatted for writing a new line to a csv log file.
        See error_summary() method for comments on the dictionary err_data.
        '''
        s = ''
        um_per_mm = 1000
        row_data = self.row_data(err_data)
        for key in row_data.keys():
            this_val = row_data[key]
            if key in self.err_keys:
                this_val = format(this_val * um_per_mm, '.1f')
            else:
                this_val = str(this_val)
            s += this_val + ','
        s = s[:-1] # remove that last comma
        return s
    
    def csv_writeable_header():
        '''Returns a string with descriptive headers for each of the columns in csv_writeable_summary.
        '''
        s = ''.join([s + ',' for s in single_val_keys])
        s = s[:-1] # remove that last comma
        
        # put in something here to add the unit ' (um)' as a suffix on some pre-defined list of the keys that need scaling
        return s

    