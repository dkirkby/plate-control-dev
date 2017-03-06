import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
import numpy as np
import collections
import csv
import datetime
import posstate

init_data_keys = ['test loop data file',
                  'num pts calib T',
                  'num pts calib P',
                  'xytest log file',
                  'code version',
                  'test operator',
                  'test station',
                  'supply voltage',
                  'temperature (C)',
                  'relative humidity',
                  'operator notes']
user_data_keys = init_data_keys[5:] # subset of init_data_keys that get manually entered by user

# reporting constants
thresholds_um = [3.0,5.0] # [um] candidate 2D error thresholds to calculate where in real operation on the mountain we would have stopped correcting
stat_cuts = [0.95,1.00] # statistical cutoffs for best moves at which to report

class Summarizer(object):
    '''Provides common functions for summarizing a fiber positioner's performance data.
    When run as an application, summarizer.py provides a utility for making summary files out of
    existing movedata log files.
    '''

    def __init__(self, state, init_data, directory=''):
        '''INPUTS:
            init_data   ... dictionary, should contain values for all the keys given in the list init_data_keys
            state       ... PosState object for the positioner this summarizer will refer to
            directory   ... (optional) override the standard directory for reading / writing summary files
        
        Make sure to also update_loop_inits() at the beginning of any new xytest loop.
        '''
        self.state = state
        self.row_template = collections.OrderedDict()
        self.row_template['start time']                     = ''
        self.row_template['finish time']                    = ''
        self.row_template['curr cruise']                    = 0
        self.row_template['curr creep']                     = 0
        self.row_template['num targets']                    = 0     # number of targets tested in this loop 
        self.err_keys = ['blind max (um)']                          # max error on the blind move 0
        for cut in stat_cuts:
            for threshold in thresholds_um:
                suffix = Summarizer.err_suffix(cut,threshold)
                self.err_keys.append('corr max (um)' + suffix)          # max error after correction moves (threshold is applied)
                self.err_keys.append('corr rms (um)' + suffix)          # rms error after correction moves (threshold is applied)
                self.err_keys.append('mean num corr' + suffix)          # avg number of correction moves it took to reach either threshold or end of submove data
                self.err_keys.append('max num corr'  + suffix)          # max number of correction moves it took to reach either threshold or end of submove data
        for key in self.err_keys:
            self.row_template[key] = None
        self.row_template['total move sequences at finish'] = None
        self.row_template['total limit seeks T at finish']  = None
        self.row_template['total limit seeks P at finish']  = None
        self.row_template['pos log files']                  = [self.state.log_basename]
        for key in init_data_keys:
            if 'file' in key:
                init_data[key] = os.path.basename(init_data[key])
            self.row_template[key] = init_data[key]
        self.basename = self.state.read('POS_ID') + '_summary.csv'
        if not(directory):
            directory = pc.xytest_summaries_directory
        self.filename = directory + self.basename
        if not(os.path.isfile(self.filename)): # checking whether need to start a new file
            with open(self.filename, 'w', newline='') as csvfile:
                csv.writer(csvfile).writerow(self.row_template.keys()) # write header row
    
    def update_loop_inits(self, loop_data_file, n_pts_calib_T, n_pts_calib_P):
        '''At the start of a new loop within an xytest, always run this method
        to update values in the row logging function.
        
        It will initialize some values for the loop, as well as tell the code that
        the next call to write_row() should append a new row, rather than overwriting
        the most recent one.
        
        The inputs to this method are those particular data which we cannot
        otherwise infer from positioner state, or the internal clock, etc.
        '''
        self.row_template['test loop data file'] = os.path.basename(loop_data_file)
        self.row_template['num pts calib T']     = n_pts_calib_T
        self.row_template['num pts calib P']     = n_pts_calib_P
        self.row_template['start time']          = pc.timestamp_str_now()
        self.row_template['curr cruise']         = self.state.read('CURR_CRUISE')
        self.row_template['curr creep']          = self.state.read('CURR_CREEP')
        self.next_row_is_new = True

    def write_row(self, err_data_mm):
        '''Makes a row of values and writes them to the csv file.
        See threshold_and_summarize() method for comments on err_data.
        '''
        if self.state.log_basename not in self.row_template['pos log files']:
            self.row_template['pos log files'].append(self.state.log_basename)
        row = self.row_template.copy()
        row['finish time'] = pc.timestamp_str_now()
        for threshold in self.thresholds_um:
            err_summary = Summarizer.threshold_and_summarize(err_data_mm,threshold)
            for key in err_summary.keys():
                if key in self.err_keys:
                    row[key] = format(err_summary[key], '.1f')
        row['num targets'] = len(err_summary['all blind errs (um)'])
        row['total move sequences at finish'] = self.state.read('TOTAL_MOVE_SEQUENCES')
        row['total limit seeks T at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_T')
        row['total limit seeks P at finish'] = self.state.read('TOTAL_LIMIT_SEEKS_P')
        with open(self.filename,'r', newline='') as csvfile:
            rows = list(csv.reader(csvfile))
        row_vals = list(row.values())
        if self.next_row_is_new:
            rows.append(row_vals)
            self.next_row_is_new = False
        else:
            rows[-1] = list(row_vals)
        with open(self.filename, 'w', newline='') as csvfile:
            csv.writer(csvfile).writerows(rows)

    @staticmethod
    def threshold_and_summarize(err_data_mm, threshold_um):
        '''Summarizes the error data for a single positioner, applying thresholds
        to determine which correction submoves are the ones at which in practice
        (on the mountain) we would stop correcting.
         
        INPUTS:
            err_data      ... list of lists, where the first index is the submove number,
                              and then selecting that gives you the list of all error data
                              for that submove. The units must be mm.
            
            threshold_um  ... the first submove encountered which has an error value less than
                              or equal to threshold is considered the point at which a robot would
                              (in practice on the mountain) be held there and do no more corrections.
                              The units must be um.
                            
        OUTPUTS:
            err_summary   ... dictionary, with keys:
                                  'blind max (um)' + err_suffix(stat_cut,threshold_um)
                                  'corr max (um)'  + err_suffix(stat_cut,threshold_um)
                                  'corr rms (um)'  + err_suffix(stat_cut,threshold_um)
                                  'mean num corr'  + err_suffix(stat_cut,threshold_um)
                                  'max num corr'   + err_suffix(stat_cut,threshold_um)
                                  'all blind errs (um)' ... numpy array of all the blind move error values
                                  'all corr errs (um)'  ... numpy array of all the corrected move error values (threshold is applied)
                                  'all corr nums'       ... numpy array of which how many correction moves it took for each target to reach the threshold (or end of submove data)
        '''
        err_data = []
        for submove_data in err_data_mm:
            err_data.append([x * pc.um_per_mm for x in submove_data])
        err_summary = {}
        n = len(err_data[0])
        err_summary['all corr errs (um)'] = [np.inf]*n
        err_summary['all corr nums'] = [0]*n
        has_hit_threshold = [False]*n
        for submove in range(len(err_data)):
            for i in range(n):
                this_err = err_data[submove][i]
                if not(has_hit_threshold[i]):
                    err_summary['all corr nums'][i] = submove
                    err_summary['all corr errs (um)'][i] = this_err
                    if this_err <= threshold_um:
                        has_hit_threshold[i] = True
        err_summary['all blind errs (um)'] = np.sort(err_data[0])
        corr_sort_idxs = np.argsort(err_summary['all corr errs (um)'])
        err_summary['all corr errs (um)'] = np.array(err_summary['all corr errs (um)'])[corr_sort_idxs]
        err_summary['all corr nums'] = np.array(err_summary['all corr nums'])[corr_sort_idxs]
        for cut in stat_cuts:
            if cut >= 1:
                idxs = range(n)
            else:
                idxs = range(int(np.ceil(cut*n)))
            suffix = Summarizer.statcut_suffix(cut)
            err_summary['blind max (um)' + suffix] = max(err_summary['all blind errs (um)'][idxs])
            suffix = Summarizer.err_suffix(cut,threshold_um)
            err_summary['corr max (um)' + suffix] = max(err_summary['all corr errs (um)'])
            err_summary['corr rms (um)' + suffix] = np.sqrt(np.sum(np.power(err_summary['all corr errs (um)'][idxs],2))/n)
            err_summary['mean num corr' + suffix] = np.mean(err_summary['all corr nums'][idxs])
            err_summary['max num corr'  + suffix] = max(err_summary['all corr nums'][idxs])
        return err_summary

    @staticmethod
    def err_suffix(stat_cut, threshold):
        '''For consistent internal generation of certain keys.'''
        return Summarizer.statcut_suffix(stat_cut) + ' with ' + str(threshold) + ' um threshold'
    
    @staticmethod
    def statcut_suffix(stat_cut):
        '''For consistent internal generation of certain keys.'''
        return ' best ' + str(stat_cut)
    
if __name__=="__main__":
    import tkinter
    import tkinter.messagebox
    import tkinter.filedialog
    
    # get the files list
    filetypes = (('Comma-separated Values','*.csv'),('All Files','*'))
    gui_root = tkinter.Tk()
    process_all_files = tkinter.messagebox.askyesno(title='Batch summarize directory?',message='Yes  -->  Process all files in the folder of your choice.\n\nNo -->  Process just one or multiple file(s) of your choice.')
    if not(process_all_files):
        files = list(tkinter.filedialog.askopenfilenames(initialdir=pc.xytest_summaries_directory, filetypes=filetypes, title='Select movedata file(s) to process.'))
    else:
        directory = tkinter.filedialog.askdirectory(initialdir=pc.all_logs_directory+os.path.sep+'..',title='Select directory.')
        files = os.listdir(directory)
        files = [directory + os.path.sep + file for file in files]
    gui_root.withdraw()
    files = [file for file in files if 'movedata.csv' in file]
    
    # gather the data by positioner and data file
    d = {}
    e = {}
    for file in files:
        namesplit = os.path.basename(file).split('_')
        pos_id = namesplit[0]
        logsuffix = ''.join(namesplit[3:]).replace('_movedata.csv','')
        with open(file,'r',newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            err_xy_fields = [field for field in reader.fieldnames if 'err_xy' in field]
            if err_xy_fields:
                if pos_id not in d.keys():
                    d[pos_id] = {}
                    e[pos_id] = {}
                d[pos_id]['test loop data file'] = os.path.basename(file)
                err_data = [[] for field in err_xy_fields]
                timestamps = []
                cycles = []
                pos_logs = set()
                for row in reader:
                    for i in range(len(err_xy_fields)):
                        err_data[i].append(row[err_xy_fields[i]])
                    if 'timestamp' in reader.fieldnames:
                        timestamp = row['timestamp']
                        if '_' in timestamp: # convert from occasional usage of filename format inside some of the data logs
                            timestamp = datetime.datetime.strptime(timestamp,pc.filename_timestamp_format)
                            timestamp = datetime.datetime.strftime(timestamp,pc.timestamp_format)
                        timestamps.append(timestamp)
                    if 'cycle' in reader.fieldnames:
                        cycles.append(row['cycle'])
                    if 'move_log' in reader.fieldnames:
                        pos_logs.add(row['move_log'])
                if timestamps:
                    d[pos_id]['start time'] = timestamps[0]
                    d[pos_id]['finish time'] = timestamps[-1]
                else:
                    timestamp = datetime.datetime.strptime(namesplit[1:2],pc.filename_timestamp_format)
                    timestamp = datetime.datetime.strftime(timestamp,pc.timestamp_format)
                    d[pos_id]['start time'] = timestamp
                if cycles:
                    d[pos_id]['total move sequences at finish'] = cycles[-1]
                if logsuffix:    
                    d[pos_id]['operator notes'] = [logsuffix]
                if pos_logs:
                    d[pos_id]['pos log files'] = list(pos_logs)
                e[pos_id] = err_data
    
    # find out where the user wants to save outputs
    gui_root = tkinter.Tk()
    save_directory = tkinter.filedialog.askdirectory(initialdir='~',title='Folder to save outputs?')
    gui_root.withdraw()
    
    # run the summarizer
    for pos_id in d.keys():
        state = posstate.PosState(pos_id)
        init_data = d[pos_id]
        for key in init_data.keys():
            if key not in init_data_keys:
                init_data[key] = 'unknown'
        summ = Summarizer(state,init_data,save_directory)
        with open(summ.filename,'r',newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            already_summarized = set()
            for row in reader:
                already_summarized.add(row['test loop data file'])
        if os.path.basename(summ.filename) not in already_summarized:
            summ.next_row_is_new = True
            summ.write_row(e[pos_id])
