# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:27:01 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Runs an Arc Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
from poscalibrations import PosCalibrations
test = PosCalibrations('arc', interactive=True)
test.run_arc_calibration(auto_update=False)
test.fvc_collect(destination=test.data.dir)
test.data.generate_data_products()
print(test.data.calibdf[['DEVICE_ID', 'OFFSET_X', 'OFFSET_Y',
                         'OFFSET_T', 'OFFSET_P''LENGTH_R1', 'LENGTH_R2']])
