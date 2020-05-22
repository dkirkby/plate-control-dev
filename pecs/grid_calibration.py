# -*- coding: utf-8 -*-
"""
Created on Tue Dec 17 11:00:53 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an Grid Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
import pandas as pd
idx = pd.IndexSlice
test = PosCalibrations('grid', n_pts_TP=(6, 6), interactive=True)
test.run_grid_calibration(extra_pts_num=24, extra_pts_max_radius=3.3)
if hasattr(test.data, 'calibdf'):
    print(test.data.calibdf.loc[:, idx[:, [  # preview calibration updates
        'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
        'LENGTH_R1', 'LENGTH_R2']]])
