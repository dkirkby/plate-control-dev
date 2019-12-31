# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:27:01 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an Arc Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
import pandas as pd
idx = pd.IndexSlice
test = PosCalibrations('arc', n_pts_TP=(6, 6), interactive=True)
test.run_arc_calibration()
test.fvc_collect(destination=test.data.dir)
test.data.generate_data_products()
print(test.data.calibdf.loc[:, idx[:, [  # preview calibration updates
    'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
    'LENGTH_R1', 'LENGTH_R2']]])
