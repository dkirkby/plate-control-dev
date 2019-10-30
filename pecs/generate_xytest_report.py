# -*- coding: utf-8 -*-
"""
generates html/pdf report for xy accuracy test
by looking for the latest xytest run and importing FPTestData

Created on Wed Oct 30 12:57:04 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import pickle
import numpy as np
import pandas as pd
import posconstants as pc
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))


def calculate_percentiles(data, individual_ptl=True):
    # grade positioners by comparing to performance of all peers tested
    # and also taking 95 percentile of all targets for each submove
    # for each positioner, in case it missed one or two targets
    d = []
    for perc in [95, 98, 100]:
        for i in range(data.num_corr_max):
            sm_data = data.movedf[f'err_xy_{i}'] * 1000  # mm to microns
            if ptlid is not None:  # restrict cuts within petal
                sm_data = sm_data[sm_data['PETAL_ID']==ptlid]

            pos_data_sm = np.percentile(sm_data, perc)
            d.append[perc,
                     i,
                     np.max(pos_data_sm),
                     np.min(pos_data_sm),
                     np.rms(pos_data_sm),
                     np.mean(pos_data_sm)]
    data.perc_df = pd.DataFrame(
        d,
        columns=['submove', 'max_err', 'min_err', 'rms_err', 'mean_err'])

def grade_positioners():
    G = {}
    for posid in np.unique(test.movedf['DEVICE_ID']):
        pos_data = test.movedf[test.movedf['DEVICE_ID'] == posid]
        max_blind = np.max(pos_data['err_xy_0'])
        corr_data = np.hstack(pos_data['err_xy_1'])
        max_corr = np.max(corr_data)
        rms_corr = np.mean(corr_data)
        corr_data_95 = np.percentile(corr_data, 95)
        max_corr_95 = np.max(corr_data_95)
        rms_corr_95 = np.rms(corr_data_95)
        grade = grade_pos(max_blind,
                          max_corr, rms_corr,
                          max_corr_95, rms_corr_95)
        G[posid] = [max_blind, max_corr, rms_corr, grade]
    test.grade_df = pd.DataFrame.from_dict(
        G, orient='index',
        columns=['max_blind', 'max_corr', 'rms_corr', 'grade'])


def grade_pos(max_blind, max_corr, rms_corr, max_corr_95, rms_corr_95):
    if (max_blind <= 100) & (max_corr <= 15) & (rms_corr <= 5):
        grade = 'A'
    elif ((max_blind <= 250) & (max_corr <= 25) & (max_corr_95 <= 15)
          & (rms_corr <= 10) & (rms_corr <= 5)):
        grade = 'B'
    elif ((max_blind <= 250) & (max_corr <= 50) & (max_corr_95 <= 25)
          & (rms_corr <= 20) & (rms_corr <= 10)):
        grade = 'C'
    elif ((max_blind <= 500) & (max_corr <= 50) & (max_corr_95 <= 25)
          & (rms_corr <= 20) & (rms_corr <= 10)):
        grade = 'D'
    else:
        grade = 'F'
    return grade


# read input and output paths
with open(os.path.join(pc.dirs['xytest_data'], 'pweave_test_src.txt'),
          'r') as h:
    path_input, path_output = h.read().splitlines()
# load FPTestData as pickle
with open(path_input, "rb") as h:
    data = pickle.load(h, protocol=pickle.HIGHEST_PROTOCOL)


#' % DESI Focal Plane XY Accuracy Test Report
#' % Start time: <%=data.start_time%>
#' % End time: <%=data.end_time%>
#' % Petal IDs: <%=data.ptlids%>
#' % Product directory: <%=data.dir%>
#' % Test logs: <%=data.log_paths%>

#' # Test Configuration
#' Number of targets: <%=data.ntargets%>
#' Grid target points (poslocXY): <%=data.targets%>
#' Number of corrections:  <%=data.num_corr_max%>
#' Anticollision mode: <%=data.anticollision%>
#' Max radius of targets: <%=data.test_cfg['targ_max_radius']%> mm
#' Min radius of targets: <%=data.test_cfg['targ_min_radius']%> mm


ptlid = data.ptlids[0]  # turn the following into a loop in future version
#' PTL<%=str(ptlid).zfill(2)%>
#' <%=len(test.posids_ptl[ptlid])%> positioners tested:
#' <%=sorted(test.posids_ptl[ptlid])%>
calc_cuts(data, ptlid=ptlid)  # now acqures a grade_df attribute
if data.test_cfg['report_temperature']:
    # turn this into time plots, with max, min, mean as floating texts
    print('max, min, median posfid temperatures: ',
          np.max(data.temp_query['posfid_temps_max']),
          np.min(data.temp_query['posfid_temps_mean']),
          np.mean(data.temp_query['posfid_temps_median']))
    print('max fiducial temperatures:',
          np.max(data.temp_query['fid_temps_max']))
