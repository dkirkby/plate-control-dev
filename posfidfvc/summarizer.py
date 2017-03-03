# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import numpy as np
import collections
import posconstants as pc
import posstate

init_data_keys = ['test loop data file',
                  'num pts calib T',
                  'num pts calib P',
                  'test operator',
                  'test station',
                  'supply voltage',
                  'temperature (C)',
                  'relative humidity',
                  'operator notes']

class Summarizer(object):
    '''Provides common functions for summarizing a fiber positioner's performance data.
    '''

    def __init__(self, pos_id, xytest_log_file, init_data, thresholds=[0.003,0.005]):
        ''' The dictionary init_data should contain values for all the keys given
        in the list init_data_keys.
            
        
        Usage is to initialize a new summarizer at the beginning of every test loop.
        '''
        self.pos_id = pos_id
        self.state = posstate.PosState(pos_id)
        self.thresholds = thresholds # mm, possible values for correction move cut-off point
        self._row_template = collections.OrderedDict()
        self._row_template['start time']                     = pc.timestamp_str_now()
        self._row_template['finish time']                    = ''
        self._row_template['curr cruise']                    = self.state.read('CURR_CRUISE')
        self._row_template['curr creep']                     = self.state.read('CURR_CREEP')
        self._row_template['num targets']                    = 0     # number of targets tested in this loop
        self._row_template['blind max']                      = None  # max error on the blind move 0
        self.err_keys = []
        for threshold in self.thresholds:
            suffix = Summarizer._threshold_suffix(threshold)
            self.err_keys.append('corr max'      + suffix)           # max error after correction moves (threshold is applied)
            self.err_keys.append('corr rms'      + suffix)           # rms error after correction moves (threshold is applied)
            self.err_keys.append('mean num corr' + suffix)           # avg number of correction moves it took to reach either threshold or end of submove data
            self.err_keys.append('max num corr'  + suffix)           # max number of correction moves it took to reach either threshold or end of submove data
        for key in self.err_keys:
            self._row_template[key] = None
        self._row_template['total move sequences at finish'] = None
        self._row_template['total limit seeks T at finish']  = None
        self._row_template['total limit seeks P at finish']  = None
        self._row_template['xytest log file']                = xytest_log_file
        self._row_template['pos log files']                  = [self.state.log_basename]
        for key in init_data_keys:
            self._row_template[key] = init_data[key]
    
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
        if self.state.log_basename not in self._row_template['pos log files']:
            self._row_template['pos log files'].append(self.state.log_basename)
        row = self._row_template.copy()
        row['start time'] = self._loop_start_time
        row['finish time'] = pc.timestamp_str_now()
        for threshold in self.thresholds:
            summary = self.error_summary(err_data,threshold)
            for key in summary.keys():
                if key in self.err_keys:
                    row[key] = summary[key]
        row['num targets'] = len(summary['all blind errs'])
        row['total move sequences at finish'] = self.state.read('TOTAL_MOVE_SEQUENCES')
        row['total limit seeks T at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_T')
        row['total limit seeks P at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_P')
                              ('num pts calib T',                 'loop'),
                              ('num pts calib P',                 'loop'),
                              ('test operator',                   'test'),
                              ('test station',                    'test'),
                              ('supply voltage',                  'test'),
                              ('temperature (C)',                 'test'),
                              ('relative humidity',               'test'),
                              ('operator notes',                  'test')])        
            

        
        return row

    @staticmethod
    def _threshold_suffix(value):
        '''For consistent internal generation of certain keys.
        '''
        return ' - ' + str(value) + ' um threshold'