# -*- coding: utf-8 -*-
"""
Created on Tue Dec 17 16:19:44 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an one-point calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
test = PosCalibrations('1p_offsetsTP', interactive=True)
test.run_1p_calibration(auto_update=True)
test.fvc_collect(destination=test.data.dir)
test.data.generate_data_products()
print(  # preview calibration updates
    test.data.calibdf[['POS_T', 'POS_P', 'OFFSET_T', 'OFFSET_P']])
