"""Provides functions to retrieve repeatable sequences of positioner sets
and move request sets.
"""

import csv
import harness_constants as hc

# Define sequences here. The user selects them by the key (the sequnce id).
positioner_param_sequences = {'cmds_unit_test':[90000],
                              0:[99000],
                              1:[99000,99001],
                              2:[99002],
                              3:[99003],
                              'one real petal':[98004],
                              'two real petals':[98002,98003],
                              'many real petals':[98002,98003,98004,98005,98006,
                                                  98007,98008,98009,98010,98011],
                              'PTL03_03001':[3001],
                              'PTL01_01001':[1001],
                              'PTL01_01002':[1002], # has expanded keepouts
                              }

move_request_sequences     = {'cmds_unit_test':[i for i in range(90000,90020)],
                              0:[0],
                              1:[0,1],
                              2:[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                              3:[20,21,22,23,24],
                              4:[20,21],
                              5:[21],
                              'many':[i for i in range(100)],
                              '04000':[4000],
                              '04000-04001':[4000,4001],
                              '04000-04009':[i for i in range(4000,4010)],
                              '04006-04007':[i for i in range(4006,4008)],
                              '04000-04019':[i for i in range(4000,4020)],
                              '04000-04049':[i for i in range(4000,4050)],
                              '04000-04099':[i for i in range(4000,4100)],
                              '04000-04999':[i for i in range(4000,5000)],
                              '04108-04110':[i for i in range(4108,4111)],
                              '03000':[3000],
                              '03000-03001':[i for i in range(3000,3002)],
                              '03000-03009':[i for i in range(3000,3010)],
                              '03000-03999':[i for i in range(3000,4000)],
                              '01000':[1000],
                              '01000-01001':[i for i in range(1000,1002)],
                              '01000-01999':[i for i in range(1000,2000)],
                             }

stress_sequences_petal3_subset7a = {'03001_ntarg001_set000': [3229],
                                    '03001_ntarg005_set000': [3395, 3674, 3295, 3076, 3971],
                                    '03001_ntarg005_set001': [3265, 3691, 3518, 3919, 3939],
                                    '03001_ntarg010_set000': [3209, 3262, 3276, 3321, 3594, 3817, 3689, 3862, 3610, 3117],
                                    '03001_ntarg010_set001': [3321, 3075, 3017, 3443, 3545, 3974, 3612, 3399, 3908, 3639],
                                    '03001_ntarg010_set002': [3159, 3715, 3784, 3787, 3504, 3886, 3705, 3635, 3785, 3679],
                                    '03001_ntarg047_set000': [3077, 3066, 3202, 3589, 3346, 3549, 3162, 3596, 3879, 3634, 3158, 3426, 3582, 3033, 3346, 3370, 3759, 3507, 3744, 3384, 3102, 3383, 3609, 3159, 3739, 3937, 3978, 3745, 3261, 3930, 3503, 3409, 3626, 3450, 3160, 3170, 3205, 3996, 3958, 3507, 3678, 3591, 3001, 3677, 3421, 3978, 3273, 3009, 3542, 3385],
                                    '03001_ntarg050_set000': [3009, 3697, 3408, 3680, 3267, 3796, 3760, 3266, 3484, 3610, 3622, 3836, 3820, 3394, 3019, 3048, 3837, 3160, 3820, 3115, 3321, 3159, 3073, 3207, 3051, 3532, 3193, 3254, 3640, 3635, 3482, 3703, 3595, 3067, 3134, 3072, 3609, 3508, 3481, 3160, 3697, 3548, 3282, 3099, 3763, 3576, 3085, 3597, 3264, 3099, 3975, 3399, 3960, 3160, 3073, 3628],
                                    }
move_request_sequences.update(stress_sequences_petal3_subset7a)

stress_sequences_petal1_subset7b1 = {'01001_ntarg001_set000': [1113],
                                     '01001_ntarg005_set000': [1895, 1469, 1825, 1971, 1362],
                                     '01001_ntarg005_set001': [1474, 1669, 1423, 1321, 1699],
                                     '01001_ntarg010_set000': [1872, 1912, 1600, 1391, 1971, 1622, 1061, 1099, 1723, 1055],
                                     '01001_ntarg010_set001': [1014, 1399, 1515, 1447, 1483, 1576, 1654, 1422, 1388, 1981],
                                     '01001_ntarg010_set002': [1284, 1743, 1424, 1379, 1061, 1852, 1670, 1875, 1449, 1647],
                                     '01001_ntarg050_set000': [1126, 1401, 1223, 1043, 1941, 1230, 1157, 1216, 1391, 1551, 1166, 1981, 1973, 1160, 1409, 1657, 1860, 1486, 1906, 1343, 1491, 1491, 1646, 1217, 1592, 1231, 1357, 1955, 1874, 1798, 1040, 1160, 1279, 1752, 1825, 1576, 1684, 1768, 1061, 1099, 1855, 1041, 1243, 1041, 1020, 1826, 1348, 1172, 1160, 1636, 1963, 1502, 1875, 1498],
                                     }
move_request_sequences.update(stress_sequences_petal1_subset7b1)

stress_sequences_petal1_subset7b2 = {'01002_ntarg001_set000': [1851],
                                     '01002_ntarg005_set000': [1975, 1351, 1495, 1714, 1437],
                                     '01002_ntarg005_set001': [1306, 1753, 1892, 1923, 1647],
                                     '01002_ntarg010_set000': [1389, 1972, 1658, 1071, 1094, 1767, 1066, 1008, 1405, 1538],
                                     '01002_ntarg010_set001': [1456, 1505, 1614, 1692, 1432, 1380, 1984, 1273, 1797, 1444],
                                     '01002_ntarg010_set002': [1368, 1070, 1868, 1717, 1904, 1461, 1690, 1128, 1408, 1220],
                                     '01002_ntarg050_set000': [1049, 1953, 1229, 1161, 1211, 1391, 1572, 1166, 1984, 1980, 1163, 1414, 1693, 1880, 1511, 1917, 1332, 1515, 1515, 1684, 1213, 1633, 1233, 1348, 1963, 1900, 1830, 1042, 1163, 1267, 1801, 1852, 1613, 1738, 1821, 1071, 1094, 1872, 1046, 1236, 1048, 1019, 1854, 1338, 1172, 1163, 1672, 1968, 1527, 1903, 1522, 1603, 1691],
                                     }
move_request_sequences.update(stress_sequences_petal1_subset7b2)

def get_positioner_param_sequence(sequence_id, device_loc_ids='all'):
    """Select a sequence of positioner parameter sets.

        sequence_id    ... Identifies which sequence to return, per the above
                           definition of positioner_param_sequences.

        device_loc_ids ... 'all' --> returns positioner data for all locations on the petal
                           iterable collection of ints --> returns only data for the argued device_loc_ids

    Return value is a dict of dicts. The primary keys are ids of positioner parameter
    groups at each step in the sequence.

    Each subdict has keys = posid, value = sub-sub-dictionary.

    The sub-sub-dictionary keys / values correspond to PosState parameters. The
    idea is that these can be immediately stored to state objects to generate a
    new configuration of the simulated petal.
    """
    return _get_sequence(sequence_id, device_loc_ids, get_positioner_param_sequence)

def get_move_request_sequence(sequence_id, device_loc_ids='all'):
    """Select a sequence of move requests.

        sequence_id    ... Identifies which sequence to return, per the above
                           definition of move_request_sequences.

        device_loc_ids ... 'all' --> returns move request data for all locations on the petal
                           iterable collection of ints --> returns only data for the argued device_loc_ids

    Return value is a dict of request dictionaries. The primary keys are ids of
    each step in the sequence.

    At each step, there is a subdictionary, containing all the target requests
    for that step in the sequence. The keys for these are device_location_id.

    Then the subdictionaries have keys device_location_id. (Rather than posid, so
    that they can be used for any petal generically.

    Finally, there is a lowest third level of dictionary. These contain the actual
    move request data for each device. The keys for these are:
        'command','u', and 'v'
    having the same meanings as described in petal's "request_targets()" method.
    """
    return _get_sequence(sequence_id, device_loc_ids, get_move_request_sequence)

_pos_dir = hc.pos_dir
_req_dir = hc.req_dir
_pos_prefix = hc.pos_prefix
_req_prefix = hc.req_prefix

def _get_sequence(sequence_id, device_loc_ids, caller):
    """Internal implementation of sequence retrieval from data files.
    """
    if caller == get_positioner_param_sequence:
        sequence_defs = positioner_param_sequences
        directory = _pos_dir
        prefix = _pos_prefix
        key_label = 'POS_ID'
    elif caller == get_move_request_sequence:
        sequence_defs = move_request_sequences
        directory = _req_dir
        prefix = _req_prefix
        key_label = 'DEVICE_LOC'
    else:
        return
    sequence = {}
    for data_id in sequence_defs[sequence_id]:
        new = _read_data(data_id,directory,prefix,device_loc_ids,key_label)
        sequence[data_id] = new
    return sequence

def _read_data(data_id, directory=_pos_dir, prefix=_pos_prefix, device_loc_ids='all',key_label='POS_ID'):
    with open(hc.filepath(directory, prefix, data_id), 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            new = {}
            for row in reader:
                if device_loc_ids == 'all' or hc.data_types['DEVICE_LOC'](row['DEVICE_LOC']) in device_loc_ids:
                    main_key = hc.data_types[key_label](row[key_label])
                    new[main_key] = {key:hc.data_types[key](val) for key,val in row.items()}
    return new


