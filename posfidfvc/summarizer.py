# For description of plan for what this module will produce and the overall test data architecture, see:
# https://docs.google.com/spreadsheets/d/1XG8HlfBhMVonhohbZknwzM72AP0cquVI2t4Qyq_Af9s/edit?ts=58b6fc39#gid=0

import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import numpy as np
import collections
import posconstants as pc
import csv
import datetime

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

class Summarizer(object):
    '''Provides common functions for summarizing a fiber positioner's performance data.
    '''

    def __init__(self, state, init_data, thresholds_mm=[0.003,0.005]):
        ''' The dictionary init_data should contain values for all the keys given
        in the list init_data_keys.
        
        Make sure to also update_loop_inits() at the beginning of any new xytest loop.
        '''
        self.state = state
        self.thresholds_um = [t*pc.um_per_mm for t in thresholds_mm] # operate in um
        self.row_template = collections.OrderedDict()
        self.row_template['start time']                     = ''
        self.row_template['finish time']                    = ''
        self.row_template['curr cruise']                    = 0
        self.row_template['curr creep']                     = 0
        self.row_template['num targets']                    = 0     # number of targets tested in this loop 
        self.err_keys = ['blind max (um)']                          # max error on the blind move 0
        for threshold in self.thresholds_um:
            suffix = Summarizer._threshold_suffix(threshold)
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
        self.filename = pc.xytest_summaries_directory + self.basename
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
        self.row_template['start time']          = datetime.datetime.now()
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
        row['finish time'] = datetime.datetime.now()
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
            err_data   ... list of lists, where the first index is the submove number,
                          and then selecting that gives you the list of all error data
                          for that submove. The units must be mm.
                          
            threshold  ... the first submove encountered which has an error value less than
                          or equal to threshold is considered the point at which a robot would
                          (in practice on the mountain) be held there and do no more corrections.
                          The units must be mm.
                            
        OUTPUTS:
            err_summary ... dictionary, with keys:
                              'blind max (um)'
                              'corr max (um)'
                              'corr rms (um)'
                              'mean num corr'
                              'max num corr'
                              'all blind errs (um)' ... list of all the blind move error values
                              'all corr errs (um)'  ... list of all the corrected move error values (threshold is applied)
                              'all corr nums'       ... list of which how many correction moves it took for each target to reach the threshold (or end of submove data)
        '''
        err_data = []
        for submove_data in err_data_mm:
            err_data.append([x * pc.um_per_mm for x in submove_data])
        err_summary = {}
        err_summary['all blind errs (um)'] = err_data[0]
        err_summary['blind max (um)'] = max(err_summary['all blind errs (um)'])
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
        suffix = Summarizer._threshold_suffix(threshold_um)
        err_summary['corr max (um)' + suffix] = max(err_summary['all corr errs (um)'])
        err_summary['corr rms (um)' + suffix] = np.sqrt(np.sum(np.power(err_summary['all corr errs (um)'],2))/n)
        err_summary['mean num corr' + suffix] = np.mean(err_summary['all corr nums'])
        err_summary['max num corr'  + suffix] = max(err_summary['all corr nums'])
        return err_summary

    @staticmethod
    def _threshold_suffix(value):
        '''For consistent internal generation of certain keys.
        '''
        return ' with ' + str(value) + ' um threshold'
    
if __name__=="__main__":
    # run test cases for threshold_and_summarize()
    # "true" values are from an excel spreadsheet calculation on real-world data
    err_data = [[0.028169452013332,0.021436811598223,0.023928159045896,0.024339236279999,0.031831043836598,0.034609541686335,0.023621655142686,0.020402133168994,0.028652613331112,0.033175378665464,0.026614576128739,0.041078462988307,0.023884844353844,0.026105129073477,0.018933721272118,0.01618311911478,0.013677214087998,0.012099116464476,0.019385674835018,0.021887908217353,0.020976683421511,0.016668289464721,0.01341539430437,0.012203607390022,0.007815563242094,0.017099508476174,0.015600822884922,0.016584027196105,0.016810059117646,0.01552520005531,0.007391547461906,0.007252068538014,0.011592666896079,0.011082980638929,0.010800879022651,0.003391265059674,0.012535850737464,0.004387897938428,0.015969054884395,0.008458762887985,0.016868250391597,0.005695955276547,0.020027522111801,0.000845768378139],
                [0.004794174357359,0.003641585669747,0.002108625877434,0.001340605068994,0.004326917668511,0.001623646153267,0.000852159314832,0.000151442419284,0.000332732460091,0.00565438068241,0.002455295314705,0.00464278144297,0.002181445953209,0.00182872135294,0.001999190186998,0.003206162996257,0.001506354604211,0.002726798565418,0.002474931866478,0.000358945544821,0.002849470458558,0.004500668087429,0.002398135801399,0.001275330714124,0.003219054631011,0.001353435379599,0.003153951227507,0.001094113660144,0.004142619536975,0.001261361965688,0.000995809171527,0.00187777587623,0.001125517847051,0.002765140323848,0.001855050786611,0.000332737873872,0.003221622909516,0.002281780336601,0.005400464474233,0.002217467041436,0.006406583722401,0.000324688821745,0.005422933145789,0.001658287974615],
                [0.003336121974541,0.000679012086957,0.001332133818887,0.002966143287441,0.001833742277795,0.001966634143416,0.000300631809676,0.001401120144275,0.001893191985907,0.003204597344948,0.006311611666338,0.007191381373886,0.002846822978382,0.00272202422593,0.000684825526799,0.002136871220576,0.000730729240323,0.001989741033593,0.001782835108649,0.001806545347983,0.000647751686366,0.000218315774483,0.001118941042961,0.000421816707346,0.000219344604132,9.72637324678929E-05,0.001852404320124,0.000154826640447,0.001231737062061,0.001284084004358,0.002519970079442,0.001206413388389,0.000437009728294,0.0003686734607,0.000262301420282,0.000612299769062,0.002311908594873,0.000668134655038,0.000714256017467,0.00163836318095,0.005142929130147,0.000986956758298,0.006637697342092,0.000378191781701],
                [0.002584805683331,0.000548639181369,0.000208857177722,0.001855268913839,0.000353719503139,0.001724087492575,0.000744996530456,0.00067036979768,0.003263324841986,0.001525170538827,0.000426540654257,0.001417458473573,0.002456035587335,0.000662834720693,7.80486244991122E-05,0.000697052281869,0.001088429066988,0.002730852977829,0.002312130337657,0.000331730348798,0.000364506283744,0.001064664329409,0.000486716245743,0.000507730749569,0.00113415745198,0.00119567876286,0.000257951680312,0.000686562469686,0.001259778017192,0.000914741821213,0.002747213612962,0.001447302280182,0.001418156646772,0.002089908763,0.000701918468109,0.000352211217988,0.000798973374287,0.000757025200624,0.000355575795804,0.000880713024189,0.005701276690373,0.000351164926666,0.006399230167376,0.000855158919996]]
    thresholds = [3,5] # um
    true_err_max = [6.399230167376,6.399230167376]
    true_err_rms = [2.108590212502,2.846248709431]
    true_num_max = [3,3]
    true_num_avg = [1.40909090909091,1.06818181818182]
    for i in range(len(thresholds)):
        err_summary = Summarizer.threshold_and_summarize(err_data,thresholds[i])
        suffix = Summarizer._threshold_suffix(thresholds[i])
        print('Threshold: ' + str(thresholds[i]) + ' um')
        print('  true err max = ' + str(true_err_max[i]) + ',  Summarizer err max = ' + str(err_summary['corr max (um)' + suffix]))
        print('  true err rms = ' + str(true_err_rms[i]) + ',  Summarizer err rms = ' + str(err_summary['corr rms (um)' + suffix]))
        print('  true max num corr = ' + str(true_num_max[i]) + ',  Summarizer max num corr = ' + str(err_summary['max num corr' + suffix]))
        print('  true avg num corr = ' + str(true_num_avg[i]) + ',  Summarizer avg num corr = ' + str(err_summary['mean num corr' + suffix]))


