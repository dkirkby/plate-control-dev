# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import numpy as np
import collections
import posconstants as pc
import posstate

init_data_keys = ['test loop data file',
                  'num pts calib T',
                  'num pts calib P',
                  'xytest log file',
                  'test operator',
                  'test station',
                  'supply voltage',
                  'temperature (C)',
                  'relative humidity',
                  'operator notes']
user_data_keys = init_data_keys[4:] # subset of init_data_keys that get manually entered by user

class Summarizer(object):
    '''Provides common functions for summarizing a fiber positioner's performance data.
    '''

    def __init__(self, pos_id, init_data, thresholds=[0.003,0.005]):
        ''' The dictionary init_data should contain values for all the keys given
        in the list init_data_keys.
        
        Make sure to also update_loop_inits() at the beginning of any new xytest loop.
        '''
        self.pos_id = pos_id
        self.state = posstate.PosState(pos_id)
        self.thresholds = thresholds # mm, possible values for correction move cut-off point
        self.row_template = collections.OrderedDict()
        self.row_template['start time']                     = ''
        self.row_template['finish time']                    = ''
        self.row_template['curr cruise']                    = 0
        self.row_template['curr creep']                     = 0
        self.row_template['num targets']                    = 0     # number of targets tested in this loop
        self.row_template['blind max']                      = None  # max error on the blind move 0
        self.err_keys = []
        for threshold in self.thresholds:
            suffix = Summarizer._threshold_suffix(threshold)
            self.err_keys.append('corr max'      + suffix)    # max error after correction moves (threshold is applied)
            self.err_keys.append('corr rms'      + suffix)    # rms error after correction moves (threshold is applied)
            self.err_keys.append('mean num corr' + suffix)    # avg number of correction moves it took to reach either threshold or end of submove data
            self.err_keys.append('max num corr'  + suffix)    # max number of correction moves it took to reach either threshold or end of submove data
        for key in self.err_keys:
            self.row_template[key] = None
        self.row_template['total move sequences at finish'] = None
        self.row_template['total limit seeks T at finish']  = None
        self.row_template['total limit seeks P at finish']  = None
        self.row_template['pos log files']                  = [self.state.log_basename]
        for key in init_data_keys:
            self.row_template[key] = init_data[key]
        self.basename = pos_id + '_summary.csv'
        self.filename = pc.test_summaries_directory + self.basename
        
        # now add some code to check if file already exists, and if not start a new one
        # then lower down make methods that encapsulate the writing of a new row
    
    def update_loop_inits(self, loop_data_file, n_pts_calib_T, n_pts_calib_P):
        '''At the start of a new loop within an xytest, always run this method
        to update values in the row logging function.
        
        The inputs to this method are those particular data which we cannot
        otherwise infer from positioner state, or the internal clock, etc.
        '''
        self.row_template['test loop data file'] = loop_data_file
        self.row_template['num pts calib T']     = n_pts_calib_T
        self.row_template['num pts calib P']     = n_pts_calib_P
        self.row_template['start time']          = pc.timestamp_str_now()
        self.row_template['curr cruise']         = self.state.read('CURR_CRUISE')
        self.row_template['curr creep']          = self.state.read('CURR_CREEP')
    
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
        See threshold_and_summarize() method for comments on the dictionary err_data.
        '''
        s = ''
        row = self.make_row(err_data)
        for key in row.keys():
            this_val = row[key]
            if key in self.err_keys:
                this_val = format(this_val * pc.um_per_mm, '.1f')
            else:
                this_val = str(this_val)
            s += this_val + ','
        s = s[:-1] # remove that last comma
        return s

    def threshold_and_summarize(err_data, threshold):
        '''Summarizes the error data for a single positioner, applying thresholds
        to determine which correction submoves are the ones at which in practice
        (on the mountain) we would stop correcting.
         
        INPUTS:
            err_data   ... list of lists, where the first index is the submove number,
                          and then selecting that gives you the list of all error data
                          for that submove. The units must be mm.
                          
            threshold  ... the first submove encountered which has an error value less than
                          or equal to threshold is considered the point at which a robot would
                          (in practice on the mountain) be held there and do no more corrections.
                          The units must be mm.
                            
        OUTPUTS:
            err_summary ... dictionary, with keys:
                              'blind max'
                              'corr max'
                              'corr rms'
                              'mean num corr'
                              'max num corr'
                              'all blind errs' ... list of all the blind move error values
                              'all corr errs'  ... list of all the corrected move error values (threshold is applied)
                              'all corr nums'  ... list of which how many correction moves it took for each target to reach the threshold (or end of submove data)
        '''
        err_summary = {}
        err_summary['all blind errs'] = err_data[0]
        err_summary['blind max'] = max(err_summary['all blind errs'])
        n = len(err_data[0])
        err_summary['all corr errs'] = [np.inf]*n
        err_summary['all corr nums'] = [0]*n
        has_hit_threshold = [False]*n
        for submove in range(len(err_data)):
            for i in range(n):
                this_err = err_data[submove][i]
                if not(has_hit_threshold[i]):
                    err_summary['all corr nums'][i] = submove
                    err_summary['all corr errs'][i] = this_err
                    if this_err <= threshold:
                        has_hit_threshold[i] = True
        suffix = Summarizer._threshold_suffix(threshold)
        err_summary['corr max'      + suffix] = max(err_summary['all corr errs'])
        err_summary['corr rms'      + suffix] = np.sqrt(np.sum(np.power(err_summary['all corr errs'],2))/n)
        err_summary['mean num corr' + suffix] = np.mean(err_summary['all corr nums'])
        err_summary['max num corr'  + suffix] = max(err_summary['all corr nums'])
        return err_summary

    def make_row(self, err_data):
        '''Makes a row of values. These are returned as an ordered dictionary based
        on the row template. See threshold_and_summarize() method for comments on err_data.
        '''
        if self.state.log_basename not in self.row_template['pos log files']:
            self.row_template['pos log files'].append(self.state.log_basename)
        row = self.row_template.copy()
        row['finish time'] = pc.timestamp_str_now()
        for threshold in self.thresholds:
            err_summary = self.threshold_and_summarize(err_data,threshold)
            for key in err_summary.keys():
                if key in self.err_keys:
                    row[key] = err_summary[key]
        row['num targets'] = len(err_summary['all blind errs'])
        row['total move sequences at finish'] = self.state.read('TOTAL_MOVE_SEQUENCES')
        row['total limit seeks T at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_T')
        row['total limit seeks P at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_P')      
        return row

    @staticmethod
    def _threshold_suffix(value):
        '''For consistent internal generation of certain keys.
        '''
        return ' - ' + str(value) + ' um threshold'