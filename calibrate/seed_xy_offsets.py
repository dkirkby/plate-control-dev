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
focal plate alignment. Only three dof are needed here. We need to find the
effective 3 dof transformation from the as-aligned full 6 dof results.
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

import os
import sys
import numpy as np
sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
from posstate import PosState
from petal import Petal

USE_CONSTANTSDB = False


if USE_CONSTANTSDB:
    #  try:  # debug this
    from DOSlib.constants import ConstantsDB
    constants = ConstantsDB().get_constants(
        snapshot='DOS', tag='CURRENT', group='focal_plane_metrology')
    # except:  # what exception can happen here? do not use bare except
    #     USE_CONSTANTSDB = False


def initialise_pos_xy_offsets(ptl_id_input):
    '''
    For each positioner, transform the nominal x, y in the petal local CS
    to CS5. The 2D petal transformation parameters are 3 dof only:
    x, y offsets and xy rotation

    Input are a petal id string or a list of strings specifying the petal ids
    and petal location as integer
    '''
    if type(ptl_id_input) is str:
        ptl_ids = [ptl_id_input]
    elif type(ptl_id_input) is list:
        ptl_ids = ptl_id_input
    else:
        raise Exception('Wrong input type, must be string or list')
    nominal = np.genfromtxt(pc.dirs['positioner_locations_file'],
                            delimiter=',', names=True, usecols=(0, 2, 3))
    for ptl_id in ptl_ids:
        # first read in petal config to get petal_location in the ring
        ptl_state = PosState(ptl_id, logging=True, device_type='ptl')
        petal_loc = ptl_state.conf['PETAL_LOCATION_ID']
        ptl = Petal(petal_id=ptl_id, petal_loc=int(petal_loc),
                    simulator_on=True)
        for posid in ptl.posids:
            device_loc = ptl.get_posfid_val(posid, 'DEVICE_LOC')
            metXYZ = np.array([nominal[device_loc]['X'],
                               nominal[device_loc]['Y'],
                               nominal[device_loc]['Z']]).reshape(3, 1)
            x, y, _ = ptl.trans.metXYZ_to_obsXYZ(metXYZ).reshape(3)
            ptl.set_posfid_val(posid, 'OFFSET_X', x)
            ptl.set_posfid_val(posid, 'OFFSET_Y', y)
            ptl.states[posid].write()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ptls = sys.argv[1]
    else:
        ptls = input('Enter a petal id or list of petal ids,'
                     'eg. [\'02\',\'03\']: \n')
    initialise_pos_xy_offsets(ptls)
