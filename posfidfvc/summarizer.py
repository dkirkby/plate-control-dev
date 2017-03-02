# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import numpy as np
import collections

class Summarizer(object):
    '''Provides common functions for summarizing fiber positioner performance data.
    '''

    def __init__(self, this_test_data):
        self._data_key_defs = collections.OrderedDict([
            # DATA KEY                          # WHEN IT CHANGES
            ('start time',                      'loop'),
            ('finish time',                     'move'),
            ('curr cruise',                     'loop'),
            ('curr creep',                      'loop'),
            ('num targets',                     'move'),
            ('blind max (um)',                  'move'),   # max error on the blind move 0
            ('corr max (um) - 3 um threshold',  'move'),   # max error after correction moves (3 um threshold is applied)
            ('corr rms (um) - 3 um threshold',  'move'),   # rms error after correction moves (3 um threshold is applied)
            ('mean num corr - 3 um threshold',  'move'),   # avg number of correction moves it took to reach either 3 um threshold or end of submove data
            ('max num corr - 3 um threshold',   'move'),   # max number of correction moves it took to reach either 3 um threshold or end of submove data
            ('corr max (um) - 5 um threshold',  'move'),   # max error after correction moves (5 um threshold is applied)
            ('corr rms (um) - 5 um threshold',  'move'),   # rms error after correction moves (5 um threshold is applied)
            ('mean num corr - 5 um threshold',  'move'),   # avg number of correction moves it took to reach either 5 um threshold or end of submove data
            ('max num corr - 5 um threshold',   'move'),   # max number of correction moves it took to reach either 5 um threshold or end of submove data
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
    
        self.all_keys = list(self._data_key_defs.keys())
        self.loop_keys = [k for k in self.all_keys if self._data_key_defs[k] == 'loop']
        self.move_keys = [k for k in self.all_keys if self._data_key_defs[k] == 'move']
        self.test_keys = [k for k in self.all_keys if self._data_key_defs[k] == 'test']    
        
        self.row_template = collections.OrderedDict.fromkeys(self.all_keys)
        for key in this_test_data.keys():
            if key in self.all_keys:
                self.row_template[key] = this_test_data[key]
            else:
                print('Warning: ' + str(key) + ' is not a valid key for the summarizer.')
        for key in self.test_keys:
            if key not in this_test_data.keys():
                print('Warning: ' + str(key) + ' was not provided when initializing summarizer.')

    def error_summary(err_data, threshold=0.003):
        '''Summarizes the error data for a single positioner.
        
        INPUTS:
            err_data  ... list of lists, where the first index is the submove number,
                          and then selecting that gives you the list of all error data
                          for that submove.
                          
            threshold ... the first submove encountered which has an error value less than
                          or equal to threshold is considered the point at which a robot would
                          (in practice on the mountain) be held there and do no more corrections
                            
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

    def csv_writeable_line(err_data, threshold=0.003, printscale=1000):
        '''Makes a string that is formatted for writing error summary data to a csv file.
        
        INPUTS: See error_summary() method for comments on err_data and thereshold.
                printscale multiplies any values by that much before returning the string (e.g. if data is in mm but you want the string in um)
                
        OUTPUT: the string
        '''
        summary = error_summary(err_data,threshold)
        for key in summary.keys():
            if key in 
        s = ''.join([format(summary[key]*printscale,'.1f') + ',' for key in single_val_keys])
        s = s[:-1] # remove that last comma
        return s
    
    def csv_writeable_header():
        '''Returns a string with descriptive headers for each of the columns in csv_writeable_summary.
        '''
        s = ''.join([s + ',' for s in single_val_keys])
        s = s[:-1] # remove that last comma
        return s

    