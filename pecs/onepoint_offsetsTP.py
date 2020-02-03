# -*- coding: utf-8 -*-
"""
Created on Tue Dec 17 16:19:44 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an one-point calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
import pandas as pd
idx = pd.IndexSlice
test = PosCalibrations('1p_offsetsTP', interactive=True)
test.run_1p_calibration(commit=False, interactive=True)
if hasattr(test.data, 'calibdf'):
    print(test.data.calibdf.loc[:, idx[:, [  # preview calibration updates
        'POS_T', 'POS_P', 'OFFSET_T', 'OFFSET_P']]])
