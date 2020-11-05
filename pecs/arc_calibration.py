# -*- coding: utf-8 -*-
"""
Runs an Arc Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
"""
# Created on Thu Dec 12 12:27:01 2019
# @author: Duan Yutong (dyt@physics.bu.edu)

# argument defaults
def_npts_T = 12
def_npts_P = 12
def_npts_extra = 24
def_extra_pts_max_radius = 3.0
min_npts_T = 4
min_npts_P = 4

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-nt', '--num_points_theta', type=int, default=def_npts_T,
                    help=f'number of points to perform on theta arc (default={def_npts_T}, min={min_npts_T})')
parser.add_argument('-np', '--num_points_phi', type=int, default=def_npts_P,
                    help=f'number of points to perform on theta arc (default={def_npts_P}, min={min_npts_P})')
parser.add_argument('-nx', '--num_points_extra', type=int, default=def_npts_extra,
                    help='number of extra points to perform on phi arc (default={def_npts_extra}, argue 0 to skip)')
parser.add_argument('-rmx', '--extra_pts_max_radius', type=float, default=def_extra_pts_max_radius,
                    help='number of extra points to perform on phi arc (default={def_extra_pts_max_radius}, argue 0 to skip)')
args = parser.parse_args()
assert args.num_points_theta > min_npts_T
assert args.num_points_phi > min_npts_P
assert args.num_points_extra >= 0
assert args.extra_pts_max_radius > 0

# do the work
from poscalibrations import PosCalibrations
import pandas as pd
idx = pd.IndexSlice
test = PosCalibrations('arc',
                       n_pts_TP=(args.num_points_theta, args.num_points_phi),
                       interactive=True)
test.run_arc_calibration(extra_pts_num=args.num_points_extra,
                         extra_pts_max_radius=args.extra_pts_max_radius)
if hasattr(test.data, 'calibdf'):
    print(test.data.calibdf.loc[:, idx[:, [  # preview calibration updates
        'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
        'LENGTH_R1', 'LENGTH_R2']]])
