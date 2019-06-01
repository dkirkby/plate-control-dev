"""Provides functions to retrieve repeatable sequences of positioner sets
and move request sets.
"""

import csv
import harness_constants as hc

# Define sequences here. The user selects them by the key (the sequnce id).
positioner_param_sequences = {0:[0],
                              1:[0,1],
                              2:[2],
                              3:[3]}

move_request_sequences     = {0:[0],
                              1:[0,1],
							  2:[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                              3:[20,21,22,23,24],
                              4:[20,21]}

def get_positioner_param_sequence(sequence_id, device_loc_ids='all'):
    """Select a sequence of positioner parameter sets.
        
        sequence_id    ... Identifies which sequence to return, per the above
                           definition of positioner_param_sequences.
        
        device_loc_ids ... 'all' --> returns positioner data for all locations on the petal
                           iterable collection of ints --> returns only data for the argued device_loc_ids
        
    Return value is a list of dicts. Each dict has keys = posid, value = subdictionary.
    The subdictionary keys / values correspond to PosState parameters. The idea is that
    these can be immediately stored to state objects to generate a new configuration of
    the simulated petal.
    """
    return _get_sequence(sequence_id,device_loc_ids,get_positioner_param_sequence)

def get_move_request_sequence(sequence_id, device_loc_ids='all'):
    """Select a sequence of move requests.
        
        sequence_id    ... Identifies which sequence to return, per the above
                           definition of move_request_sequences.
        
        device_loc_ids ... 'all' --> returns move request data for all locations on the petal
                           iterable collection of ints --> returns only data for the argued device_loc_ids
        
    Return value is a list of request dictionaries. The request dictionaries have keys
    being device_location_id (rather than posid), so that they can be used for any petal
    generically. The other keys in each request dictionary are 'command','u','v', and
    have the same meaning as described in petal's "request_targets()" method.
    """
    return _get_sequence(sequence_id,device_loc_ids,get_move_request_sequence)

def _get_sequence(sequence_id, device_loc_ids, caller):
    """Internal implementation of sequence retrieval from data files.
    """
    if caller == get_positioner_param_sequence:
        sequence_defs = positioner_param_sequences
        directory = hc.pos_dir
        prefix = hc.pos_prefix
        key_label = 'POS_ID'
    elif caller == get_move_request_sequence:
        sequence_defs = move_request_sequences
        directory = hc.req_dir
        prefix = hc.req_prefix
        key_label = 'DEVICE_LOC'
    else:
        return
    sequence = []
    for data_id in sequence_defs[sequence_id]:
        with open(hc.filepath(directory, prefix, data_id), 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            new = {}
            for row in reader:
                if device_loc_ids == 'all' or hc.data_types['DEVICE_LOC'](row['DEVICE_LOC']) in device_loc_ids:
                    main_key = hc.data_types[key_label](row[key_label])
                    new[main_key] = {key:hc.data_types[key](val) for key,val in row.items()}
            sequence.append(new)
    return sequence


        