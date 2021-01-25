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
max_tries = 10
parser.add_argument('-nt', '--num_tries', type=int, default=4, help='int, max number of tries of the algorithm (default is 4, max is {max_tries})')
max_fvc_iter = 10
parser.add_argument('-nm', '--num_meas', type=int, default=1, help=f'int, number of measurements by the FVC per move (default is 1, max is {max_fvc_iter})')
parser.add_argument('-r', '--match_radius', type=int, default=None, help='int, specify a particular match radius, other than default')
parser.add_argument('-u', '--check_unmatched', action='store_true', help='turns on auto-disabling of unmatched positioners, default is False')
uargs = parser.parse_args()

# input validation
assert 1 <= uargs.num_tries <= max_tries, f'out of range argument {uargs.num_tries} for num_tries parameter'
assert 1 <= uargs.num_meas <= max_fvc_iter, f'out of range argument {uargs.num_meas} for num_meas parameter'

# other imports
import random
import pandas

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
log_dir = pc.dirs['calib_logs']
log_timestamp = pc.filename_timestamp_str()
log_name = log_timestamp + '_disambig_theta.log'
log_path = os.path.join(log_dir, log_name)
logger, _, _ = simple_logger.start_logger(log_path)
logger.info(f'Running {script_name} to ascertain true theta near hardstops.')
assert2 = simple_logger.assert2

# set up pecs
from pecs import PECS
pecs = PECS(interactive=True)
pecs.logger = logger
logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
pecs.tp_tol = 0.0   # correct POS_T, POS_P for FVC measurements above this err value
pecs.tp_frac = 1.0  # when correcting POS_T, POS_P, do so by this fraction of err distance

# some boilerplate
common_move_meas_kwargs = {'match_radius': uargs.match_radius,
                           'check_unmatched': uargs.check_unmatched,
                           'test_tp': True,
                           'num_meas': uargs.num_meas,
                           }

# global collections
enabled_posids = set(pecs.get_enabled_posids('all', include_posinfo=False))
allowed_to_fix = set(pecs.get_enabled_posids('sub', include_posinfo=False))
unambig = set()  # stores all posids that have been resolved
neighbor_data = pecs.ptlm.app_get("collider.pos_neighbors")
neighbors = {}
for these in neighbor_data.values():
    neighbors.update(these)

# algorithm
def disambig(n_try):
    '''See DESI-5911 for diagram and plain-language explanation of the basic algorithm.
    
    INPUTS:  
        n_try ... Integer, indicates number of times to repeat. Repetition is done by
                  recursing this function. If n_try == 0 --> break. The direction
                  of trial moves is flipped with each repeat, so one would almost always
                  want the initial call to have n_try >= 2. Even values do the first move
                  away from the presumed hardstop, odd values go toward it. The idea of
                  allowing more than 2 repeats is to deal with cases where a robot needs
                  its neighbors to be disambiguated before it can be safely moved itself.
    
    OUTPUTS:
        Set of posids that are still in ambiguous zone. Disabled positioners are
        *excluded* from this set, regardless of what zone they are in.
    '''
    logger.info(f'Starting disambiguation iteration {uargs.num_tries - n_try + 1} of {uargs.num_tries}')

    # get ambiguous and unambiguous posids
    global unambig
    ambig_dict = pecs.quick_query('in_theta_hardstop_ambiguous_zone', posids=enabled_posids)
    in_ambig_zone = {posid for posid, val in ambig_dict.items() if val == True}
    all_ambig = in_ambig_zone - unambig  # because previous parking moves may have put already-resolved pos into ambig theta territory
    unambig |= enabled_posids - all_ambig
    logger.info(f'{len(all_ambig)} enabled positioner(s) are in theta hardstop ambiguous zone: {all_ambig}')
    logger.info(f'{len(unambig)} enabled positioner(s) are unambiguous')
    do_not_fix = all_ambig - allowed_to_fix
    ambig = all_ambig & allowed_to_fix
    if do_not_fix:
        logger.info(f'{len(do_not_fix)} positioner(s) are not within the allowed-to-fix selection group. Excluded posids: {do_not_fix}')
    if not ambig or n_try == 0:
        return ambig
    logger.info(f'Disambiguation attempt {uargs.num_tries - n_try + 1} of {uargs.num_tries}')
    logger.info(f'Will attempt to resolve {len(ambig)} posid(s): {ambig}')
    
    # targets for unambiguous pos
    active_posids = ambig | unambig
    locT_current = pecs.quick_query(key='poslocT', posids=active_posids)
    locT_targets = {posid: locT_current[posid] for posid in unambig}
    locP_target = 150.0
    
    # where possible, target unambiguous posids "opposite" ambiguous neighbors,
    # to maximize clearance
    for posid in unambig:
        these_neighbors = neighbors[posid]
        these_ambig = {n for n in these_neighbors if n in ambig}
        if these_ambig:
            selected = random.choice(list(these_ambig))
            locT_targets[posid] = locT_current[selected]  # this is a good config to minimize collision opportunity
        
    # move unambiguous positioners to targets
    sorted_unambig = sorted(unambig)
    anticollision = 'adjust_requested_only'
    request_data = {'DEVICE_ID': sorted_unambig,
                    'COMMAND': 'poslocTP',
                    'X1': [locT_targets[posid] for posid in sorted_unambig],
                    'X2': locP_target,
                    'LOG_NOTE': pc.join_notes(script_name, 'parking move for unambiguous positioner'),
                    }
    request = pandas.DataFrame(request_data)
    if request.empty:
        logger.info('No unambiguous + enabled positioners detected.')
    else:
        logger.info(f'Doing parking move for {len(request)} unambiguous positioners. Anticollision mode: {anticollision}')
        pecs.move_measure(request=request, anticollision=anticollision, **common_move_meas_kwargs)

    # retract ambiguous positioners' phi axes, again to maximize clearance
    # (this is safely done by *not* allowing extra theta anticollision moves)
    anticollision = 'freeze'
    intP_current = pecs.quick_query(key='posintP', posids=ambig)
    intP_target = 150.0  # this also helps *extend* fully-retracted arms a little --> improves the theta measurement
    dP = {posid: intP_target - intP_current[posid] for posid in ambig}
    dtdp_requests = {posid: {'target': [0.0, dP[posid]],
                             'log_note': pc.join_notes(script_name, 'retraction move for ambiguous positioner'),
                             } for posid in ambig
                     }
    logger.info(f'Doing retraction move for {len(dtdp_requests)} ambiguous positioners. Anticollision mode: {anticollision}')
    pecs.ptlm.request_direct_dtdp(dtdp_requests, return_posids_only=True)
    pecs.ptlm.schedule_moves(anticollision=anticollision)
    pecs.move_measure(request=None, anticollision=anticollision, **common_move_meas_kwargs)
    
    # theta test moves on ambiguous positioners
    anticollision = 'freeze'
    intT_current = pecs.quick_query(key='posintT', posids=ambig)
    ambig_max = pecs.quick_query(key='max_theta_hardstop_ambiguous_zone', posids=ambig)
    ambig_min = pecs.quick_query(key='min_theta_hardstop_ambiguous_zone', posids=ambig)
    dT_abs = {posid: ambig_max[posid] - ambig_min[posid] + pc.theta_hardstop_ambig_exit_margin for posid in ambig}
    presumed_no_hardstop_dir = {posid: 1 if intT_current[posid] < 0 else -1 for posid in ambig}
    move_dir = {posid: presumed_no_hardstop_dir[posid] * (-1 if n_try % 2 else 1) for posid in ambig}
    dT = {posid: dT_abs[posid] * move_dir[posid] for posid in ambig}
    dir_note = {posid: f'{"away from" if presumed_no_hardstop_dir[posid] == move_dir[posid] else "toward"} currently-presumed closest hardstop' for posid in ambig}
    dtdp_requests = {posid: {'target': [dT[posid], 0.0],
                             'log_note': pc.join_notes(script_name, 'theta test move on ambiguous positioner', dir_note[posid]),
                             } for posid in ambig
                     }
    logger.info(f'Doing theta test move for {len(dtdp_requests)} ambiguous positioners. Anticollision mode: {anticollision}')
    pecs.ptlm.request_direct_dtdp(dtdp_requests, return_posids_only=True)
    pecs.ptlm.schedule_moves(anticollision=anticollision)
    pecs.move_measure(request=None, anticollision=anticollision, **common_move_meas_kwargs)
    return disambig(n_try=n_try - 1)

if __name__ == '__main__':
    ambig = disambig(n_try=uargs.num_tries)
    logger.info('Disambiguation loops complete.')
    if ambig:
        details = pecs.ptlm.quick_table(posids=ambig, coords=['posintTP', 'poslocTP'], as_table=False, sort='POSID')
        if pc.is_string(details):
            details_str = details
        else:
            details_str = ''
            for petal_id, table_str in details.items():
                details_str += f'\n{petal_id}\n{table_str}\n'
        logger.warning(f'{len(ambig)} positioners remain *unresolved*. Details:\n{details_str}')
    else:
        logger.info('All selected ambiguous cases were resolved!')

