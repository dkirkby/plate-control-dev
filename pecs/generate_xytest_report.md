% DESI Positioner Accuracy Test Report
% Focal Plane Team
% 2019-11-01

```python, echo=False, results='hidden'
# -*- coding: utf-8 -*-
"""
generates html/pdf report for xy accuracy test

Created on Wed Oct 30 12:57:04 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import sys
import pickle
import numpy as np
# from scipy.stats import sigmaclip
import pandas as pd
from datetime import timezone
import posconstants as pc
sys.path.append(os.path.abspath('.'))
idx = pd.IndexSlice
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))
np.nanrms = lambda x: np.sqrt(np.nanmean(np.square(x)))
grades = ['N/A', 'A', 'B', 'C', 'D', 'F']

#def calculate_percentiles(data, individual_ptl=True):
#    # grade positioners by comparing to performance of all peers tested
#    # and also taking 95 percentile of all targets for each submove
#    # for each positioner, in case it missed one or two targets
#    d = []
#    for perc in [95, 98, 100]:
#        for i in range(data.num_corr_max):
#            sm_data = data.movedf[f'err_xy_{i}'] * 1000  # mm to microns
#            # if ptlid is not None:  # restrict cuts within petal
#            #     sm_data = sm_data[sm_data['PETAL_ID']==ptlid]
#            pos_data_sm = np.percentile(sm_data, perc)
#            d.append[perc,
#                     i,
#                     np.max(pos_data_sm),
#                     np.min(pos_data_sm),
#                     np.rms(pos_data_sm),
#                     np.mean(pos_data_sm)]
#    data.perc_df = pd.DataFrame(
#        d,
#        columns=['submove', 'max_err', 'min_err', 'rms_err', 'mean_err'])

def calculate_grades(data):
    rows = []
    for posid in data.posids:
        pos_data = (data.movedf.loc[idx[:, posid], :]
                    .reset_index(drop=True).copy())
        # exclude entries where posflag is not equal to 4, set to nan
        for i in range(data.num_corr_max+1):
            mask = pos_data[f'pos_flag_{i}'] != 4
            pos_data.loc[mask, f'err_xy_{i}'] = np.nan
        err_0_max = np.max(pos_data['err_xy_0'])  # max blind error, skip nan
        err_corr = pos_data[  # select corrective moves only
            [f'err_xy_{i}' for i in range(1, data.num_corr_max+1)]].values
        err_corr = err_corr[~np.isnan(err_corr)]  # filter out nan
        if len(err_corr) == 0:
            err_corr_max = err_corr_rms = np.nan
            grade = 'N/A'
        else:
            err_corr_max = np.max(err_corr)
            err_corr_rms = np.rms(err_corr)
            # take reduced sample at 95 percentile, excluding 5% worst pots
            err_corr_95p = err_corr[err_corr <= np.percentile(err_corr, 95)]
            err_corr_95p_max = np.max(err_corr_95p)
            grade = grade_pos(err_0_max*1000, err_corr_max*1000,
                              err_corr_rms*1000, err_corr_95p_max*1000)
        rows.append({'DEVICE_ID': posid,
                     'PETAL_ID': pos_data['PETAL_ID'][0],
                     'err_0_max': err_0_max,  # max blind move xy error
                     'err_corr_max': err_corr_max,  # max corrective move err
                     'err_corr_rms': err_corr_rms,
                     'grade': grade})
    data.grade_df = pd.DataFrame(rows).set_index('DEVICE_ID')


def grade_pos(err_0_max, err_corr_max, err_corr_rms,
              err_corr_95p_max):
    '''these criteria were set by UMich lab tests, all in microns
    '''
    if np.any(np.isnan([err_0_max, err_corr_max, err_corr_rms,
              err_corr_95p_max])):
        return grades[0]
    if (err_0_max <= 100) & (err_corr_max <= 15) & (err_corr_rms <= 5):
        grade = grades[1]
    elif ((err_0_max <= 250) & (err_corr_max <= 25) & (err_corr_95p_max <= 15)
          & (err_corr_rms <= 10) & (err_corr_rms <= 5)):
        grade = grades[2]
    elif ((err_0_max <= 250) & (err_corr_max <= 50) & (err_corr_95p_max <= 25)
          & (err_corr_rms <= 20) & (err_corr_rms <= 10)):
        grade = grades[3]
    elif ((err_0_max <= 500) & (err_corr_max <= 50) & (err_corr_95p_max <= 25)
          & (err_corr_rms <= 20) & (err_corr_rms <= 10)):
        grade = grades[4]
    else:
        grade = grades[5]
    return grade


# read input and output paths
with open(os.path.join(pc.dirs['xytest_data'], 'pweave_test_src.txt'),
          'r') as h:
    path_input = h.read()
# load FPTestData as pickle
with open(path_input, "rb") as h:
    data = pickle.load(h)

# h = open(path_input, "rb")
# data = pickle.load(h)
# h.close()
```

+------------------------+---------------------------------------------------------------------------------------------------------------+
| **Start time**\        | ``<%=data.start_time.isoformat()%>`` KPNO, ``<%=data.start_time.astimezone(timezone.utc).isoformat()%>`` UTC\ |
| **End time**\          | ``<%=data.end_time.isoformat()%>`` KPNO, ``<%=data.end_time.astimezone(timezone.utc).isoformat()%>`` UTC\     |
| **Duration**\          | ``<%=str(data.end_time-data.start_time)%> ``\                                                                 |
| **Petal IDs**\         | ``<%=data.ptlids%>``\                                                                                         |
| **Product directory**\ | ``<%=data.dir%>``\                                                                                            |
+------------------------+---------------------------------------------------------------------------------------------------------------+
| **Test logs**\         | ``<%=data.log_paths%>``                                                                                       |
+------------------------+---------------------------------------------------------------------------------------------------------------+

# Test Configuration

+-------------------------------------+------------------------------------------------+
| **Anticollision mode**\             | ``<%=data.anticollision%>``\                   |
| **Number of corrections**\          | ``<%=data.num_corr_max%> ``\                   |
| **Min radius of targets**\          | ``<%=data.test_cfg['targ_min_radius']%> mm``\  |
| **Max radius of targets**\          | ``<%=data.test_cfg['targ_max_radius']%> mm``\  |
| **Number of targets**\              | ``<%=data.ntargets%>``\                        |
+------------------------+-------------------------------------------------------------+
| **Grid target points (poslocXY)**\  | ``<%=repr([list(t) for t in data.targets])%>`` |
+-------------------------------------+------------------------------------------------+


```python, fig=True, width='12 cm', echo=False
calculate_grades(data)
ptlid = data.ptlids[0]  # turn the following into a loop in future version
grades_ptl = data.grade_df[data.grade_df['PETAL_ID'] == ptlid]
masks = []
for grade in grades:
    masks.append(grades_ptl['grade'] == grade)
```

# Test Results

### PTL<%=str(ptlid).zfill(2)%>
``<%=len(data.posids_ptl[ptlid])%>`` positioners tested total

grade histogram here

temperature time plot here

##### Grade A: ``<%=masks[1].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[1]].index)%>``

##### Grade B: ``<%=masks[2].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[2]].index)%>``

##### Grade C: ``<%=masks[3].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[3]].index)%>``

##### Grade D: ``<%=masks[4].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[4]].index)%>``

##### Grade F: ``<%=masks[5].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[5]].index)%>``

##### Grade N/A: ``<%=masks[0].sum()%>`` positioners
``<%=sorted(data.grade_df[masks[0]].index)%>``


```python, fig=True, width='12 cm', echo=False
if data.test_cfg['report_temperature']:
    # turn this into time plots, with max, min, mean as floating texts
    print('max, min, median posfid temperatures: ',
          np.max(data.temp_query['posfid_temps_max']),
          np.min(data.temp_query['posfid_temps_mean']),
          np.mean(data.temp_query['posfid_temps_median']))
    print('max fiducial temperatures:',
          np.max(data.temp_query['fid_temps_max']))
```

#### Complete list of positioners tested
``<%=sorted(data.posids_ptl[ptlid])%>``
