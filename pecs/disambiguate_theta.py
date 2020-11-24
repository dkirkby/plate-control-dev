# -*- coding: utf-8 -*-
"""
Measure positioners, and for any in the ambiguous zone near the theta hardstop,
do successive movements to disambiguate which side of the hardstop they are on.
This script is capable of striking hardstops on occasion, in the process. C.f.
DESI-5911.
"""

import os
script_name = os.path.basename(__file__)

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
max_retries = 10
parser.add_argument('-nt', '--num_retries', type=int, default=4, help='int, number of recursive retries of the algorithm (default is 4, max is {max_retries})')
max_fvc_iter = 10
parser.add_argument('-nm', '--num_meas', type=int, default=1, help=f'int, number of measurements by the FVC per move (default is 1, max is {max_fvc_iter})')
uargs = parser.parse_args()

# input validation
assert 1 <= uargs.num_retries <= max_retries, f'out of range argument {uargs.num_retries} for num_retries parameter'
assert 1 <= uargs.num_meas <= max_fvc_iter, f'out of range argument {uargs.num_meas} for num_meas parameter'

# other imports
from astropy.table import Table, vstack

# set up logger
import simple_logger
try:
    import posconstants as pc
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
log_dir = pc.dirs['sequence_logs']
log_timestamp = pc.filename_timestamp_str()
log_name = log_timestamp + '_disambig_theta.log'
log_path = os.path.join(log_dir, log_name)
logger = simple_logger.start_logger(log_path)
logger.info(f'Running {script_name} to ascertain true theta near hardstops.')
assert2 = simple_logger.assert2

# set up pecs
from pecs import PECS
pecs = PECS(interactive=True)
pecs.logger = logger
logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
enabled_posids = sorted(pecs.get_enabled_posids('all', include_posinfo=False))

# algorithm
def disambig(n_retries):
    '''See DESI-5911 for diagram and plain-language explanation of the basic algorithm.
    
    INPUTS:  
        n_retries ... Integer number of times to repeat. Repetition is done by recursing
                      this function. Note that the direction  of trial moves is flipped
                      with each repeat, so one would almost always want the initial call
                      to have n_tries >= 2. The idea of allowing more than 2 repeats is to
                      deal with cases where a robot needs its neighbors to be disambiguated
                      before it can be safely moved itself.
    
    OUTPUTS:
        Set of posids that are still in ambiguous zone. Disabled positioners are
        *excluded* from this set, regardless of what zone they are in.
    '''
            
    # This type of call to PetalMan (in the next line) returns *either* dict with keys = like
    # 'PETAL1', 'PETAL2', etc, and corresponding return data from those petals, OR just the return
    # data from that one petal. It's not perfectly clear when this does or doesn't happen. Hence
    # much easier to use this syntax on functions that *don't* return dicts!
    tables = pecs.ptlm.quick_table(as_table=True)  # quick_table gives back astropy tables
    if isinstance(tables, dict):
        tables = list(tables.values())
    else:
        tables = [tables]
    table = vstack(tables)
    ambig = set(table['POSID'][table['AMBIG_T'] == True])
    ambig &= enabled_posids
    if not ambig or n_retries == 0:
        return ambig
    unambig = enabled_posids - ambig
    current_locT = {row['POSID']: float(row['poslocT']) for row in table}
    locTP_targets = {posid: (current_locT[posid], 150.0) for posid in unambig}    
    
    # 3. For each non-ambiguous posid with >= one ambiguous neighbor:
    #     a. Randomly select one of the ambiguous neighbors
    #     b. Target T_EXT = same value as the neighbor’s T_EXT
    #     (this is a good config to minimize collision opportunity)
    # 4. Move all non-ambiguous positioners to targets.
    #     a. move requests method → request_targets()
    #     b. anticollision mode = ‘adjust_requested_only’
    # 5. Retract ambiguous positioners:
    #     a. Target POS_T = current values
    #     b. Target POS_P = 150°
    #     c. Calculate (dT, dP) delta moves
    #     d. move requests method → request_direct_dtdp()
    #     e. anticollision mode = ‘freeze’
    # 6. Theta test moves on ambiguous positioners:
    #     a. dT_abs = AMBIG_MAX - AMBIG_MIN + margin
    #     b. Presumed direction of no hardstop and non-ambiguity...
    #         i. T0 < 0 → dT = +dT_abs
    #         ii. T0 > 0 → dT = -dT_abs
    #     c. If n is even → dT *= -1
    #     d. move requests method → request_direct_dtdp()
    #     e. anticollision mode = ‘freeze’
    # 7. FVC measure and update TP
    # 8. return theta_hardstops_recovery(n-1)