#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Retrieves calibration parameters from online database. Can return them as
an astropy table (when run as an imported module) or save to disk as an ecsv.

???
Must join_instance in current terminal before running this script.
"""

# Note from slack discussion with Kevin, 2020-10-30
# How to import petal such that I get all the same config data as normally occur
# when starting up an instance. It's hella tricky, in the details. I think this
# might be the simplest.
#
# Supposing I do:
# from DOSlib.proxies import Petal
# ptl = Petal(3, expert_sim=True)
# Can you make it such that within PetalApp, the initialization args to petal include:
# simulator_on = True,
# db_commit_on = False,
# but everything else is as normal?
# I suspect that might give me everything I want. I promise I won't call any PetalApp functions, so I think it should be safe.
# 
# In this scenario, might just throw away all the psycopg2 code below, and instead
# grab stuff with a bunch of get_posfid_val calls. Or perhaps generalize / use
# quick_table. That gives me an astropy table straight-away, and is nice because
# might have other re-uses at a later date.


import os, sys
path_to_petal = '../petal'
sys.path.append(os.path.abspath(path_to_petal))
import posconstants as pc

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-ptl', '--petal_ids', type=str, default='kpno', help='Comma-separated integers, specifying one or more PETAL_ID number(s) for which to retrieve data. Defaults to all known petals at kpno database. Alternately argue "lbnl" for all known petals in lbnl (beyonce) database.')
parser.add_argument('-o', '--outdir', type=str, default='.', help='Path to directory where to save output file. Defaults to current dir.')
parser.add_argument('-m', '--comment', type=str, default='', help='Comment string which will be included in output file metadata.')
parser.add_argument('-c', '--collider_settings', type=str, default=pc.default_collider_filename, help=f'Specify a different collider settings filename. Default is {pc.default_collider_filename}. This option is unlikely to ever be necessary --- as of 2020-10-30 it is *always* the same default file --- but this arg is to help future-proof in case of change.')
uargs = parser.parse_args()

db_configs = {'kpno': {'petal_ids': {2, 3, 4, 5, 6, 7, 8, 9, 10, 11},
                       'host': 'db.replicator.dev-cattle.stable.spin.nersc.org',
                       'port': 60042,
                       'password_required': False},
              'lbnl': {'petal_ids': {0, 1},
                       'host': 'beyonce.lbl.gov',
                       'port': 5432, 
                       'password_required': True},
              }

import os
save_dir = os.path.realpath(uargs.outdir)
use_all_ptls = uargs.petal_ids in db_configs.keys()
if use_all_ptls:
    petal_ids = db_configs[uargs.petal_ids]['petal_ids']
else:
    petal_ids = uargs.petal_ids.split(',')
    petal_ids = {int(i) for i in petal_ids}
assert len(petal_ids) > 0

# proceed with bulk of imports
from astropy.table import Table
import psycopg2, getpass
import posstate
import posmodel

# keys and descriptions to retrieve
keys = {
        'POS_ID': 'unique serial id number of fiber positioner',
        'PETAL_ID': 'unique serial id number of petal',
        'DEVICE_LOC': 'location number on petal, c.f. DESI-0530',
        'CTRL_ENABLED': 'if True, move tables are allowed to be sent to the positioner',
        'LENGTH_R1': 'kinematic length between central axis and phi axis',
        'LENGTH_R2': 'kinematic length between phi axis and fiber',
        'OFFSET_T': 'mounting angle of positioner\'s x-axis (roughly halfway between theta hardstops) w.r.t. that of petal',
        'OFFSET_P': 'angle from hardstop at far clockwise position to phi=0',
        'OFFSET_X': 'x position of robot\'s central axis, in "flat" coordinate system',
        'OFFSET_Y': 'y position of robot\'s central axis, in "flat" coordinate system',
        'PHYSICAL_RANGE_T': 'angular distance between theta hardstops',
        'PHYSICAL_RANGE_P': 'angular distance between phi hardstops',
        'GEAR_CALIB_T': 'scale factor for theta shaft rotations, actual/nominal',
        'GEAR_CALIB_P': 'scale factor for phi shaft rotations, actual/nominal',
        'KEEPOUT_EXPANSION_PHI_RADIAL': 'radially expands phi keepout polygon by this amount',
        'KEEPOUT_EXPANSION_THETA_RADIAL': 'radially expands theta keepout polygon by this amount',
        'KEEPOUT_EXPANSION_PHI_ANGULAR': 'angularly expands phi keepout polygon by + and - this amount',
        'KEEPOUT_EXPANSION_THETA_ANGULAR': 'angularly expands theta keepout polygon by + and - this amount',
        'CLASSIFIED_AS_RETRACTED': 'identifies positioner for travel only within a restricted radius',
        }
descriptions = {desc: key for key, desc in keys.items()}

# units (where applicable)
angular_keys = {'POS_T', 'POS_P', 'OFFSET_T', 'OFFSET_P', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P', 'KEEPOUT_EXPANSION_PHI_ANGULAR', 'KEEPOUT_EXPANSION_THETA_ANGULAR'}
mm_keys = {'LENGTH_R1', 'LENGTH_R2', 'OFFSET_X', 'OFFSET_Y', 'KEEPOUT_EXPANSION_PHI_RADIAL', 'KEEPOUT_EXPANSION_THETA_RADIAL'}
units = {key: 'deg' for key in angular_keys}
units.update({key: 'mm' for key in mm_keys})

# initialize petals in simulation mode


# validate availability of data
available_keys_dict = ptl.quick_query()
available_keys = set()
for group_name, keys in available_keys_dict.items():
    if 'keys' in group_name:
        available_keys |= set(keys)
missing = set(keys) - available_keys
assert not any(missing), f'some keys are not available: {missing}'

# gather data and make table

t = Table(params_dict)


# add some metadata
meta = {}
meta['DATE_RETRIEVED'] = pc.timestamp_str()
for key in [db_moves, db_calib]:
    meta[f'{key}_KEYS'] = db_keys[key]
    meta[f'{key}_KEYS_DESCRIPTION'] = 'Indicates fields which are stored in the "{key}" tables of the posmovedb.'
meta['EO_RADIUS_WITH_MARGIN'] = None
t.meta = meta

# add units and descriptions
for key in t.columns:
    if key in descriptions:
        t[key].description = descriptions[key]
    if key in units:
        t[key].unit = units[key]

# dependently-calculated information
states = {}
models = {}
for posid in t['POS_ID']:
    state = posstate.PosState()
    model = posmodel.PosModel()
    posmodels[posid] = model

# columns for desimodel
'PETAL', 'DEVICE', 'PETAL_ID', 'DEVICE_ID', 'DEVICE_TYPE',
'OFFSET_X_CS5', 'OFFSET_Y_CS5',
'OFFSET_X_PTL', 'OFFSET_Y_PTL',
'OFFSET_X_FLAT', 'OFFSET_Y_FLAT',
'MAX_T', 'MIN_T', 'MAX_P', 'MIN_P'
'KEEPOUT_T', 'KEEPOUT_P' # --> and have these each be in local coords (i.e. placed at x0,y0 = 0,0)


if __name__ == '__main__':
    print('hello')
