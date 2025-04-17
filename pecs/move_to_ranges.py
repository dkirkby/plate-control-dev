#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=fixme, line-too-long, C0103, W0703
"""
move_to_ranges moves positioners to ranges specified in the input csv file which must contain the header
POSID, Theta_Lower_Limit, Theta_Upper_Limit, Phi_Lower_Limit, Phi_Upper_Limit
"""

import sys
import csv
import argparse
from pecs import PECS

parser = argparse.ArgumentParser()
parser.add_argument('-rc', '--ranges_csv', type=str, default=None, help='Name of csv file containing posids, theta ranges, and phi ranges')
max_iter = 10
parser.add_argument('-iter', '--iterations', type=int, default=2, help=f'Number of iterations to try to get positioners within desired rang before giving up. Must be less than {max_iter}.')
park_options = ['posintTP', 'poslocTP', 'None', 'False']
default_park = park_options[0]
parser.add_argument('-prep', '--prepark', type=str, default=default_park, help=f'str, controls initial parking move, prior to running does not count as an iteration. Valid options are: {park_options}, default is {default_park}.')
modes = ['posintTP', 'poslocTP']
parser.add_argument('-m', '--mode', type=str, default=modes[0], help=f'str, controls which tp coordinate type checks are done. Options: {modes}. Defaults to {modes[0]}.')
default_padding = 10.0
parser.add_argument('-d', '--disable', action='store_true', help='Argue to disable positioners that remain out of range at the end of iterations.')
parser.add_argument('-a', '--anticollision', type=str, default='freeze', help='anticollision mode, can be "adjust", "adjust_requested_only", "freeze" or None. Default is "freeze"')
parser.add_argument('-v', '--verbose', action='store_true', help='Argue to print extra messages about the axes to be moved.')
uargs = parser.parse_args()
if uargs.anticollision == 'None':
    uargs.anticollision = None
assert uargs.anticollision in {'adjust', 'adjust_requested_only', 'freeze', None}, f'bad argument {uargs.anticollision} for anticollision parameter'
assert uargs.iterations < max_iter, f'cannot exceed {max_iter} iterations.'
command = uargs.mode
assert command in modes, f'Invalid mode type {command}. Must be in {modes}.'
assert uargs.prepark in park_options, f'invalid park option, must be one of {park_options}'
uargs.prepark = None if uargs.prepark in ['None', 'False'] else uargs.prepark
rc = uargs.ranges_csv
assert rc is not None, 'Must specify csv file with positioners and ranges'

d_pos_limits = {}

with open(rc, newline='', encoding="utf-8") as f:
    rcsv = csv.DictReader(f)
    try:
        for row in rcsv:
#           print(row)  # DEBUG
#           NOTE order of list: [upper_limit, lower_limit]
            for lmt in ['Theta_Upper_Limit','Theta_Lower_Limit','Phi_Upper_Limit','Phi_Lower_Limit']:
                if str(row[lmt]).upper() == 'NONE':
                    row[lmt] = None
                else:
                    row[lmt] = float(row[lmt])
            d_pos_limits[row['POSID']] = {'T': [row['Theta_Upper_Limit'], row['Theta_Lower_Limit']], 'P': [row['Phi_Upper_Limit'], row['Phi_Lower_Limit']]}
    except csv.Error as e:
        sys.exit(f'file {rc}, line {rcsv.line_num}: {e}')

posids_to_check = list(d_pos_limits)

# cs = PECS(interactive=False, posids=posids_to_check)
cs = PECS(interactive=True)

# axis_limits = {'T': [tu, tl], 'P': [pu, pl]}
columns = {'T': 'X1', 'P': 'X2'}

def check_if_out_of_limits():
    ''' Check if any axes are out of limits for all positioners in the csv file '''
    all_pos = cs.ptlm.get_positions(return_coord=command, drop_devid=False)
    pos = all_pos[all_pos['DEVICE_ID'].isin(cs.posids)]
    violating_pos = set()
    for c_posid, c_axis_limits in d_pos_limits.items():
        c_cond_a = pos['DEVICE_ID'] == c_posid
        for c_axis, c_limits in c_axis_limits.items():
            if c_limits[0] is not None:
                c_cond_b = pos[columns[c_axis]] > c_limits[0]
                violating_pos |= set(pos[c_cond_a & c_cond_b]['DEVICE_ID'])
            if c_limits[1] is not None:
                c_cond_b = pos[columns[c_axis]] < c_limits[1]
                violating_pos |= set(pos[c_cond_a & c_cond_b]['DEVICE_ID'])
    if not violating_pos:
        return False
    return violating_pos


if uargs.prepark:
    cs.park_and_measure('all', test_tp=True)
else:
    cs.fvc_measure(test_tp=True)

for i in range(uargs.iterations):
    out_of_limits = check_if_out_of_limits()
    if not out_of_limits:
        break
    start = cs.ptlm.get_positions(return_coord=command, drop_devid=False)
    selected = start[start['DEVICE_ID'].isin(out_of_limits)].drop(columns='FLAGS')
#   print('selected\n',selected.to_string())    # DEBUG
#   print('d_pos_limits\n', "\n".join(f"{k}\t{v}" for k, v in d_pos_limits.items()))  # DEBUG
    for posid, axis_limits in d_pos_limits.items():
        cond_a = selected['DEVICE_ID'] == posid
        for axis, limits in axis_limits.items():
#           print(f'axis = {axis}, column = {columns[axis]}, limits = {str(limits)}')   # DEBUG
            if set(limits) != {None}:
                if limits[0] is not None:
                    cond_b = selected[columns[axis]] > limits[0]
                    above_df = selected[cond_a & cond_b]
                    if limits[1] is not None:
                        cond_c = selected[columns[axis]] < limits[1]
                        below_df = selected[cond_a & cond_c]
                        # Have limits on both ends - move to middle
                        target_for_those_above = (limits[0] + limits[1])/2
                        target_for_those_below = (limits[0] + limits[1])/2
                        # Note these change selected!
#                       print(f'above_df = {str(above_df)}\n, below_df = {str(below_df)}\n')    # DEBUG
                        if not above_df.empty:
                            if uargs.verbose:
                                print(f'Will move {posid} {axis} from {selected.loc[cond_a & cond_b, columns[axis]]} to {target_for_those_above}')
                            selected.loc[cond_a & cond_b, columns[axis]] = target_for_those_above
                        if not below_df.empty:
                            if uargs.verbose:
                                print(f'Will move {posid} {axis} from {selected.loc[cond_a & cond_c, columns[axis]]} to {target_for_those_below}')
                            selected.loc[cond_a & cond_c, columns[axis]] = target_for_those_below
                    else:
                        # Only have upper limit - target past it
                        target_for_those_above = limits[0] - float(uargs.angle_padding)
                        if not above_df.empty:
                            if uargs.verbose:
                                print(f'Will move {posid} {axis} from {selected.loc[cond_a & cond_b, columns[axis]]} to {target_for_those_above}')
                            selected.loc[cond_a & cond_b, columns[axis]] = target_for_those_above
                else:
                    # Only have lower limit (since we know both aren't None)
                    cond_c = selected[columns[axis]] < limits[1]
                    below_df = selected[cond_a & cond_c]
                    target_for_those_below = limits[1] + float(uargs.angle_padding)
                    if not below_df.empty:
                        if uargs.verbose:
                            print(f'Will move {posid} {axis} from {selected.loc[cond_a & cond_c, columns[axis]]} to {target_for_those_below}')
                        selected.loc[cond_a & cond_c, columns[axis]] = target_for_those_below
    selected['COMMAND'] = command
    selected['LOG_NOTE'] = 'Moving to specified limits; move_to_ranges.py'
    # Now selected is a proper move request
    cs.move_measure(selected, test_tp=True, anticollision=uargs.anticollision)

out_of_limits = check_if_out_of_limits()
if not out_of_limits:
    print(f'SUCCESS! All {len(cs.posids)} selected positioners within desired limits!')
else:
    print(f'FAILED. {len(out_of_limits)} positioners remain beyond desired limits. POSIDS: {sorted(list(out_of_limits))}')
    if uargs.disable:
        print('Disabling posids that remain out of range.')
        cs.ptlm.disable_positioners(out_of_limits, comment='move_to_range: disabled because still out of range.')
