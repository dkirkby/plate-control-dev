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

import os
script_name = os.path.basename(__file__)

# input file format
format_info = 'For data model and procedures to generate these values, see DESI-5732.'
valid_keys = {'LENGTH_R1', 'LENGTH_R2', 'OFFSET_T', 'OFFSET_P', 'OFFSET_X',
              'OFFSET_Y', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
              'GEAR_CALIB_T', 'GEAR_CALIB_P', 'SCALE_T', 'SCALE_P'}
commit_prefix = 'COMMIT_'
commit_keys = {key: commit_prefix + key for key in valid_keys}
def dbkey_for_key(key):
    '''Maps special cases of keys that may have different terminology in input file
    online database.'''
    remap = {'SCALE_T': 'GEAR_CALIB_T',
             'SCALE_P': 'GEAR_CALIB_P',
             'COMMIT_SCALE_T': 'COMMIT_GEAR_CALIB_T',
             'COMMIT_SCALE_P': 'COMMIT_GEAR_CALIB_P',
             }
    if key in remap:
        return remap[key]
    return key

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

# read input data
from astropy.table import Table
table = Table.read(args.infile)

# set up a log file
import logging
import time
try:
    import posconstants as pc
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
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
logger.info(f'Running {script_name} to set positioner calibration parameters.')
logger.info(f'Input file is: {args.infile}')
logger.info(f'Table contains {len(table)} rows')
if args.simulate:
    logger.info('Running in simulation mode. No data will stored to petal memory nor database.')
def assert2(test, message):
    '''Like an assert, but cleaner handling of logging.'''
    if not test:
        logger.error(message)
        logger.warning('Now quitting, so user can check inputs.')
        raise SystemExit
def input2(message):
    '''Wrapper for input which will log the interaction.'''
    logger.info(f'PROMPT: {message}')
    user_input = input('>>> ')
    logger.info(f'USER ENTERED >>> {user_input}')
    return user_input

# validate the table format
assert 'POS_ID' in table.columns, 'No POS_ID column found in input table'
for key in set(table.columns):  # set op provides a copy
    remapped_key = dbkey_for_key(key)
    if key != remapped_key:
        remap_conflict = key in table.columns and remapped_key in table.columns
        assert2(not(remap_conflict), f'Columns {key} and {remapped_key} conflict in the input file (two columns with same meaning, so cannot disambiguate)')
        table.rename_column(key, dbkey_for_key(key))
        logger.warning(f'For compatibility with online DB, renamed column {key} to {remapped_key}')
keys = valid_keys & set(table.columns)
assert2(len(keys) > 0, 'No valid parameter columns found in input table')
no_commit_key = {key for key in keys if commit_keys[key] not in table.columns}
assert2(len(no_commit_key) == 0, f'Input table params {no_commit_key} lack {commit_prefix}-prefixed fields. {format_info}')
logger.info('Checked formatting of input table')

# some basic data validation (type and bounds checking)
# not a guarantee of quality of parameters
import numpy as np
requested_posids = set()
for key in keys:
    column = table[key]
    commit_key = commit_keys[key]
    commit_column_str = table[commit_key].astype(str).tolist()
    commit_column_str_bool = []
    for val in commit_column_str:
        if val.lower() in {'true', 't', 'yes', 'y', '1'}:
            commit_column_str_bool.append(True)
        elif val.lower() in {'false', 'f', 'no', 'n', '0'}:
            commit_column_str_bool.append(False)
        else:
            commit_column_str_bool.append(None)
    if all(isinstance(val, bool) for val in commit_column_str_bool):
        table[commit_key] = commit_column_str_bool
    commit_type_ok = table[commit_key].dtype in [np.int, np.bool]
    assert2(commit_type_ok, f'{commit_key} data type must be boolean or integer representing boolean')
    data_type_ok = column.dtype in [np.int, np.float]
    assert2(data_type_ok, f'{key} data type must be numeric')
    commit_requested = table[commit_key]
    def assert_ok(is_valid_array, err_desc):
        rng = range(len(table))
        cannot_commit = [table['POS_ID'][i] for i in rng if not is_valid_array[i] and commit_requested[i]]
        assert2(not(any(cannot_commit)), f'Input table rejected: {key} contains {err_desc} for posid(s) {cannot_commit}')
    isfinite = np.isfinite(column)
    assert_ok(isfinite, 'non-finite value(s)')
    nom = pc.nominals[key]
    nom_min = nom['value'] - nom['tol']
    nom_max = nom['value'] + nom['tol']
    column[isfinite == False] = np.inf  # dummy value to suppress astropy warnings when performing >= or <= ops below, on values that we don't plan to commit anyway. ok to do here because already checked commit values for finitude above
    assert_ok(column >= nom_min, f'value(s) below limit {nom_min}')
    assert_ok(column <= nom_max, f'value(s) above limit {nom_max}')
    requested_posids |= set(table['POS_ID'][commit_requested])
logger.info('Checked data types and bounds')

# set up pecs (access to online system)
try:
    from pecs import PECS
    pecs = PECS(interactive=False)
    logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
    posids = set(table['POS_ID'])
    pecs.ptl_setup(pecs.pcids, posids=posids)
    pecs_on = True
except:
    logger.warning(f'PECS initialization failed')
    pecs_on = False

# gather some interactive information from the user
user = ''
while not user:
    user = input2('For the log, please enter your NAME or INITIALS:')
archive_ref = ''
while not archive_ref:
    archive_ref = input2('For the log, enter DESI-XXXX DOCUMENT where this input csv table is archived:')
comment = ''
while not comment:
    comment = input2('For the log, enter any additional COMMENT, giving context/rationale for posting these new values:')

# interactive human checks, since it is important to get everything right
if pecs_on:
    # Most checks should be done ahead of time with preparation script in desimeter.
    # Here we would only check about stuff that is known to the online system.
    # Like maybe validating the posids, etc. Might not be essential to do so here.
    pass
else:
    #logger.warning('Skipping interactive checks, since PECS not initialized')
    pass

# store the data
logger.info(f'Storing data to memory (not yet to database) for {len(table)} positioners.')
for row in table:
    posid = row['POS_ID']
    if not args.simulate:
        role = pecs._pcid2role(pecs.posinfo.loc[posid, 'PETAL_LOC'])
    stored = {}
    for key in keys:
        if row[commit_keys[key]]:
            value = row[key]
            if not args.simulate:
                val_accepted = pecs.ptlm.set_posfid_val(posid, key, value, participating_petals=role)
            else:
                val_accepted = True
            if val_accepted:
                stored[key] = value
            else:
                logger.error(f'set_posfid_val(posid={posid}, key={key}, value={value}')
    if stored:
        # [JHS] Would be nice to include analysis metadata fields in the log_note, drawn
        # from the input table. Presumably when that table is in ecsv format.
        log_note = pc.join_notes(script_name, f'user {user}', f'comment {comment}', f'input_file {args.infile}', f'archive_ref {archive_ref}', f'params {stored}')
        if not args.simulate:
            pecs.ptlm.set_posfid_val(posid, 'LOG_NOTE', log_note)
        logger.info(f'{posid}: {stored}')
        
# commit to online database
logger.info(f'Committing the data set to online database.')
if not args.simulate:
    pecs.ptlm.commit(mode='both', log_note='')  # mode 'both' since LOG_NOTE goes in "moves" db. and blank log_note since done positioner-by-positioner above
logger.info(f'Commit complete. Please remember to archive the input CSV file,' +
            ' and the .log file (generated in the same folder) to docdb.')