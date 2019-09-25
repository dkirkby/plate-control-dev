# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 16:31:41 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""

from seed_armlengths import SeedArmlengths
from seed_offsets_xy import SeedOffsetsXY
from seed_offsets_tp import SeedOffsetsTP
from OnePoint import OnePointCalib

calib = SeedArmlengths()
SeedOffsetsXY(fvc=calib.fvc, ptls=calib.ptls)
SeedOffsetsTP(fvc=calib.fvc, ptls=calib.ptls)
OnePointCalib(fvc=calib.fvc, ptls=calib.ptls, mode='offsetsTP',
              interactive=False)
