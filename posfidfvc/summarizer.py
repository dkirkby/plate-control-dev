'''Provides common functions for summarizing fiber positioner performance data.
'''

# REALLY NEED TO DESIGN A MOCK-UP SPREADSHEET OF WHAT I WANT THE SUMMARY SHEET
# TO LOOK LIKE AT THE END OF A TEST. IN PARTICULAR, I SEE 3 DIMENSIONS WHICH I
# WANT TO REDUCE:
#       - loop number num targets measured, and settings like CURR_CRUISE, CURR_CREEP, num calib points, num cycles, num hardstop strikes, etc
#       - positioner id (and performance grade?)
#       - values for 'blind_max','corr_max','corr_rms','mean_num_corr'
# Maybe best is to have 

import numpy as np

single_val_keys = ['blind_max','corr_max','corr_rms','mean_num_corr']
all_err_keys = single_val_keys + ['blind_errs','corr_errs','corr_nums']
'''These are the keys used to commonly reference the different summary values.
    'blind_max'     ... maximum error on the blind move 0
    'corr_max'      ... maximum error after correction moves (threshold is applied)
    'corr_rms'      ... rms error after correction moves (threshold is applied)
    'mean_num_corr' ... average number of correction moves it took to reach either threshold or end of submove data
    'blind_errs'    ... list of all the blind move error values
    'corr_errs'     ... list of all the corrected move error values (threshold is applied)
    'corr_nums'     ... list of which how many correction moves it took for each target to reach the threshold (or end of submove data)
'''

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
        summary   ... dictionary, with keys and values per err_keys above
    '''
    summary = {}
    summary['blind_errs'] = err_data[0]
    summary['blind_max'] = max(summary['blind_errs'])
    n = len(err_data[0])
    summary['corr_errs'] = [np.inf]*n
    summary['corr_nums'] = [0]*n
    has_hit_threshold = [False]*n
    for submove in range(len(err_data)):
        for i in range(n):
            this_err = err_data[submove][i]
            if not(has_hit_threshold[i]):
                summary['corr_nums'][i] = submove
                summary['corr_errs'][i] = this_err
                if this_err <= threshold:
                    has_hit_threshold[i] = True
    summary['corr_max'] = max(summary['corr_errs'])
    summary['corr_rms'] = np.sqrt(np.sum(np.power(summary['corr_errs'],2))/n)
    summary['mean_num_corr'] = np.mean(summary['corr_nums'])
    return summary

def csv_writeable_summary(err_data, threshold=0.003, printscale=1000):
    '''Makes a string that is formatted for writing error summary data to a csv file.
    
    INPUTS: See error_summary() method for comments on err_data and thereshold.
            printscale multiplies any values by that much before returning the string (e.g. if data is in mm but you want the string in um)
            
    OUTPUT: the string
    '''
    summary = error_summary(err_data,threshold)
    s = ''.join([format(summary[key]*printscale,'.1f') + ',' for key in single_val_keys])
    s = s[:-1] # remove that last comma
    return s

def csv_writeable_header():
    '''Returns a string with descriptive headers for each of the columns in csv_writeable_summary.
    '''
    s = ''.join([s + ',' for s in single_val_keys])
    s = s[:-1] # remove that last comma
    return s

    