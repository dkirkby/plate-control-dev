# -*- coding: utf-8 -*-
"""
Resumed cleanup on Wed May 15 12:06:45 2019

@author: Duan Yutong (dyt@physics.bu.edu)

The purpose of thie script is to establish initial values for some petal and
positioner transformation parameters from nominal specis or metrology data,
right after petal assemblies are mounted to the ring on-mountain,
so that calibration can be done.

Calibration, or particularly spotmatch, relies on knowing a priori
approximately where things are, and searching within a search radius.
After calibration, the estimatd parameters will be updated with newly
measured values.

Petal transformation parameters (6 dof) have been measured by CMM during
focal plate alignment. Only three dof are needed here.
Then these three dof can serve as a starting point for calibration.
 (from constants database or petal configuration file)

A number of positioner control parameters are documented in DESI-1663,
which is quite oudated, but basically only x, y offsets would change once
petals are mounted. Unlike the theta offsets of positioners,
the x, y offsets of positioenrs for the central axis can be estimated
from the designed focal plate layout. So we'll use the theoretical
positioner x, y offsets as a starting point.
We are only doing this for positioners, no fiducials.

"""

import sys
import numpy as np
import pandas as pd
import posconstants as pc
from posstate import PosState
try:
    from DOSlib.constants import ConstantsDB
    USE_CONSTANTSDB = True
except ModuleNotFoundError:
    USE_CONSTANTSDB = False
try:
    from DOSlib.proxies import Petal
    USE_PROXY = True
except ModuleNotFoundError:
    from petal import Petal
    USE_PROXY = False

USE_CONSTANTSDB = False  # petal etrology does not exist in DB for now


def initialise_pos_xy_offsets(ptl_id_input):
    '''
    For each positioner, transform the nominal x, y in the petal local CS
    to CS5. The 2D petal transformation parameters are 3 dof only:
    x, y offsets and xy rotation

    Input are a petal id string or a list of strings specifying the petal ids
    and petal location as integer
    '''
    if type(ptl_id_input) is str:
        ptlids = [ptl_id_input]
    elif type(ptl_id_input) is list:
        ptlids = ptl_id_input
    else:
        raise Exception('Wrong input type, must be string or list')
    if USE_CONSTANTSDB:
        fp_DB = ConstantsDB().get_constants(
            snapshot='DESI', tag='CURRENT',
            group='focal_plane_metrology')['focal_plane_metrology']
        loc_lookup = {fp_DB[key]['petal_id']: key for key in fp_DB.keys()}
        ptl_DB = ConstantsDB().get_constants(
            snapshot='DESI', tag='CURRENT',
            group='petal_metrology')['petal_metrology']
    for ptlid in ptlids:
        if USE_CONSTANTSDB:
            petal_loc = loc_lookup[f'petal{int(ptlid)}']  # lookup loc from DB
            # load metrology measured device xy from DB, load petal location
            pos = pd.DataFrame(ptl_DB[f'petal{int(ptlid)}']).T
            pos['DEVICE_LOC'] = [int(i[11:]) for i in pos.index.values]
            pos.rename(columns={'x_meas': 'X',
                                'y_meas': 'Y',
                                'z_meas': 'Z'}, inplace=True)
            pos.set_index('DEVICE_LOC', inplace=True)
        else:
            # read in petal config to get petal_location in the ring
            ptl_state = PosState(ptlid, logging=True, device_type='ptl')
            petal_loc = ptl_state.conf['PETAL_LOCATION_ID']
            # load nominal device xy from file
            pos = np.genfromtxt(pc.dirs['positioner_locations_file'],
                                delimiter=',', names=True,
                                usecols=(0, 2, 3, 4))
        ptl = Petal(petal_id=ptlid, petal_loc=int(petal_loc),
                    simulator_on=True)
        for posid in ptl.posids:
            device_loc = ptl.get_posfid_val(posid, 'DEVICE_LOC')  # int
            metXYZ = np.array([pos['X'][device_loc],
                               pos['Y'][device_loc],
                               pos['Z'][device_loc]]).reshape(3, 1)
            x, y, _ = ptl.trans.metXYZ_to_obsXYZ(metXYZ).reshape(3)
            ptl.set_posfid_val(posid, 'OFFSET_X', x)
            ptl.set_posfid_val(posid, 'OFFSET_Y', y)
            ptl.altered_states.add(ptl.states[posid])  # for local commits
            ptl.altered_calib_states.add(ptl.states[posid])  # for DB commits
        ptl.commit()  # for local commits throgh petal.py
        ptl.commit_calibration(log_note='seed xy')  # DB commit through ptlApp


if __name__ == "__main__":
    if USE_PROXY:
        print('ALERT: The program expects a running PetalApp')
    if len(sys.argv) > 1:
        ptls = sys.argv[1]
    else:
        ptls = input('Enter a petal id or list of petal ids,'
                     "eg. ['02','03']: \n")
    initialise_pos_xy_offsets(ptls)
