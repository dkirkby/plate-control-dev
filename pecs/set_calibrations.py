'''Store fiber positioner calibration values to the online database. This is a
powerful function with risk of major operational errors if used incorrectly.
Only for focal plane experts, and only to be used with consensus of the focal
plane team.
'''
# Created on Mon Feb  3 18:54:30 2020
# @author: Duan Yutong (dyt@physics.bu.edu)
# 
# 2020-06-11 [JHS] Significant mods to interface. Pull in data from CSV
# and use command line args. For earlier (Spring 2020) method of pulling in data
# from pickle-of-pandas file, it's probably easiest to convert that to a CSV
# first. But you could get an old rev (r130548) from the SVN if necessary.

# input file format
format_info = 'For data model and procedures to generate these values, see DESI-5732.'
valid_keys = {'LENGTH_R1', 'LENGTH_R2', 'OFFSET_T', 'OFFSET_P', 'OFFSET_X',
              'OFFSET_Y', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
              'GEAR_CALIB_T', 'GEAR_CALIB_P', 'SCALE_T', 'SCALE_P'}
commit_prefix = 'COMMIT_'
commit_keys = {key: commit_prefix + key for key in valid_keys}

# command line argument parsing
import argparse
doc = f'{__doc__} Input CSV file must contain a POS_ID column. Input should'
doc += f' contain all or any subset of the following parameter columns: {valid_keys}.'
doc += f' For every parameter column there must be a corresponding boolean column'
doc += f' prefixed with "{commit_prefix}", stating in each row whether that value is'
doc += f' intended to be saved to the online db. {format_info}'
parser = argparse.ArgumentParser(description=doc)
parser.add_argument('-i', '--infile', type=str, required=True, help='path to input csv file')
parser.add_argument('-s', '--simulate', action='store_true', help='perform the script "offline" with no storing to memory or database')
args = parser.parse_args()

# import and validate table format
from astropy.table import Table
table = Table.read(args.infile)
assert 'POS_ID' in table.columns, 'No POS_ID column found in input table'
keys = valid_keys & set(table.columns)
assert len(keys) > 0, 'No valid parameter columns found in input table'
no_commit_key = {key for key in keys if commit_keys[key] not in table.columns}
assert len(no_commit_key) == 0, f'Input table params {no_commit_key} lack {commit_prefix}-prefixed fields. {format_info}'

# some basic data validation (type and bounds checking)
# not a guarantee of quality of parameters
import numpy as np
try:
    import posconstants as pc
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
for key in keys:
    column = table[key]
    commit_key = commit_keys[key]
    commit_type_ok = table[commit_key].dtype in [np.int, np.bool]
    assert commit_type_ok, f'{commit_key} data type must be boolean or integer representing boolean'
    data_type_ok = column.dtype in [np.int, np.float]
    assert data_type_ok, f'{key} data type must be numeric'
    commit_requested = table[commit_key]
    def assert_ok(is_valid_array, err_desc):
        cannot_commit = [table['POS_ID'][row] for row in table if not is_valid_array[row]]
        assert not(any(cannot_commit)), f'cannot commit {err_desc} at key: {key}, posid(s): {cannot_commit}'
    assert_ok(np.isfinite(column), 'non-finite value(s)')
    nom = pc.nominals[key]
    nom_min = nom['value'] - nom['tol']
    nom_max = nom['value'] + nom['tol']
    assert_ok(column >= nom_min, f'value(s) below {nom_min}')
    assert_ok(column <= nom_max, f'value(s) above {nom_max}')

# set up a log file
# I intentionally only bother doing this *after* the basic formatting validations have passed
import os
import logging
import time
log_dir = os.path.dirname(args.infile)
log_name = pc.filename_timestamp_str() + '_set_calibrations.log'
log_path = os.path.join(log_dir, log_name)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
[logger.removeHandler(h) for h in logger.handlers]
fh = logging.FileHandler(filename=log_path, mode='a', encoding='utf-8')
sh = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S %z')
formatter.converter = time.gmtime
fh.setFormatter(formatter)
sh.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(sh)
logger.info('Running script to set positioner calibration parameters.')
logger.info(f'Input file is: {args.infile}')
if args.simulate:
    logger.info('Running in simulation mode. No data will stored to petal memory nor database.')

# set up pecs (access to online system)
if args.simulate:
    logger.info(f'Skipping PECS initialization (simulation mode)')
    from pecs import PECS
    pecs = PECS(interactive=False)
    logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
    pecs.ptl_setup(pecs.pcids)

# interactive human checks, since it is important to get everything right

# store the data
logger.info(f'Storing data to memory (not yet to database) for {len(table)} positioners.')
for row in table:
    posid = row['POS_ID']
    if not args.simulate:
        role = pecs._pcid2role(pecs.posinfo.loc[posid, 'PETAL_LOC'])
    stored = {}
    for key in keys:
        value = row[key]
        if not args.simulate:
            result = pecs.ptlm.set_posfid_val(posid, key, value, participating_petals=role)
        else:
            result = True
        if result == True:
            stored[key] = value
        else:
            logger.error(f'set_posfid_val(posid={posid}, key={key}, value={value}')
    if stored:
        log_note = f'set calibration parameters {stored} from file: {args.infile}'
        if not args.simulate:
            pecs.ptlm.set_posfid_val(posid, 'LOG_NOTE', log_note)
        stored['LOG_NOTE'] = log_note
        logger.info(f'{posid}: {stored}')
        
# commit to online database
logger.info(f'Committing the data set to online database.')
if not args.simulate:
    pecs.ptlm.commit(mode='both', log_note='')  # mode 'both' since LOG_NOTE goes in "moves" db. and blank log_note since done positioner-by-positioner above
logger.info(f'Commit complete. Please remember to archive the input CSV file,' +
            ' and the .log file (generated in the same folder) to docdb.')