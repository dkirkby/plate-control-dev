# -*- coding: utf-8 -*-
"""
Created on Tue Dec 17 11:00:53 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an Grid Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
test = PosCalibrations('grid', n_pts_TP=(3, 3), interactive=True)
test.run_grid_calibration(auto_update=False)
print(test.data.calibdf[['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
                         'LENGTH_R1', 'LENGTH_R2']])
test.fvc_collect(destination=test.data.dir)
test.data.generate_data_products()
