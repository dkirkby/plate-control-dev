'''Provides common functions for summarizing fiber positioner performance data.
'''

import numpy as np

err_keys = ['max_blind','max_corr','rms_corr','mean_num_corr']
'''These are the keys used to commonly reference the different summary values.
    'max_blind'     ... maximum error on the blind move 0
    'max_corr'      ... maximum error after correction moves (threshold is applied)
    'rms_corr'      ... rms error after correction moves (threshold is applied)
    'mean_num_corr' ... average number of correction moves done to reach either threshold or end of submove data
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
    
    
    return summary

def csv_writeable_summary(err_data, threshold=0.003):
    '''Makes a string that is formatted for writing error summary data to a csv file.
    
    INPUTS: See error_summary() method for comments on inputs.
    OUTPUT: the string
    '''
    summary = error_summary(err_data,threshold)
    s = ''
    for key in err_keys:
        s += summary[key]
        if key != err_keys[-1]:
            s += ','
    return s

if __name__=="__main__":
    err_data = [[10,3,2,6],[40,5,4,39],[2,10,12,1],[30,40,50,60]]
    summary = error_summary(err_data,threshold=3)
    print(csv_writeable_summary(err_data,threshold=3))
    