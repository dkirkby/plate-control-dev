# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 21:23:25 2019

@author: Duan Yutong (dyt@physics.bu.edu)

positioner calibration calculations.
arc and grid target move requests have been generated assuming
the calibration values in DB at runtime. the calculations here shouldn't
require knowledge of the calibration values then, but they will be saved
in the test data products nevertheless. the seeded/initial calibration values
only serve to ensure spotmatch does not fail.
"""

from posstate import PosState
from posmodel import PosModel
from postransforms import PosTransforms


def calibrate_from_arc_data(self, data, auto_update=False):
    """
    input data containing targets and FVC measurements is a pd dataframe with
        index:      (['T', 'P'], target_no, DEVICE_ID)
        columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                    tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

    for each positioner, calculate measured flatXY, fit with two circles
    to find centres and radii, calculate R1, F2, and then derive offsetsTP
    and convert measured QS -> flatXY -> poslocTP -> posintTP.
    From the fit we get radial deviations w.r.t. circle models and
    differences between target and measured/expected posintTP.

    return input dataframe with columns added:
        mea_posintT, mea_posintP, mea_flatX, mea_flatY,
        err_flatX, err_flatY, err_Q, err_S,
        err_posintT, err_posintP, err_radial  # measured - target or model

    and a calibration dataframe with
        index:      DEVICE_ID
        columns:    (['OFFSET_T', 'OFFSET_P', 'OFFSET_X', 'OFFSET_Y',
                      'LENGTH_R1', 'LENGTH_R2', ...# from collect_calib(),
                      'GEAR_RATIO_T', 'GEAR_RATIO_P',
                      'CENTRE_T', 'CENTRE_P', 'RADIUS_T', 'RADIUS_P'],
                     ['OLD', 'NEW'])
    """


def calibrate_from_grid_data(self, data, auto_update=False):
    """
    grid target move requests have been generated assuming
    the calibration values in DB at runtime. the calculations here shouldn't
    require knowledge of the calibration values then, but they will be saved
    in the test data products nevertheless.
    input data containing targets and FVC measurements is a pd dataframe with
        index:      (target_no, DEVICE_ID)
        columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                    tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

    For each positioner, calculate measured flatXY, and fit it with floating
    tgt_posintTP -> tgt_flatXY. From the fit we get 6 calibration params
    all at the same time, the residuals, and the fitted, expected posintTP

    return input dataframe with columns added:
        mea_posintT, mea_posintP, mea_flatX, mea_flatY,
        exp_posintT, exp_posintP, exp_flatX, exp_flatY, exp_Q, exp_S,
        err_flatX, err_flatY, err_Q, err_S  # measured - expected after calib

    and a calibration dataframe with
        index:  DEVICE_ID
        column: (['OFFSET_T', 'OFFSET_P', 'OFFSET_X', 'OFFSET_Y',
                  'LENGTH_R1', 'LENGTH_R2', ...],  # from collect_calib()
                 ['OLD', 'NEW'])
    """
