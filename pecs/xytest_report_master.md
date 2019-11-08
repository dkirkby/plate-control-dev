% DESI Positioner Accuracy Test Report
% Focal Plane Team
% 2019-11-08 (master template last revised)

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
import pandas as pd
from datetime import timezone
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
# plt.rcParams.update({'font.family': 'sans-serif',  # both are default
#                      'mathtext.fontset': 'dejavusans'})  # both are default
import posconstants as pc
sys.path.append(os.path.abspath('.'))
idx = pd.IndexSlice
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))
np.nanrms = lambda x: np.sqrt(np.nanmean(np.square(x)))
grades = ['A', 'B', 'C', 'D', 'F', 'N/A']

#def calculate_percentiles(data, individual_ptl=True):
#    # grade positioners by comparing to performance of all peers tested
#    # and also taking 95 percentile of all targets for each submove
#    # for each positioner, in case it missed one or two targets
#    d = []
#    for perc in [95, 98, 100]:
#        for i in range(data.num_corr_max):
#            sm_data = data.movedf[f'err_xy_{i}'] * 1000  # mm to microns
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
        err_0_max = np.max(pos_data['err_xy_0']) * 1000  # max blind error, μm
        err_corr = pos_data[  # select corrective moves only
            [f'err_xy_{i}' for i in range(1, data.num_corr_max+1)]].values
        err_corr = err_corr[~np.isnan(err_corr)]  # filter out nan
        if len(err_corr) == 0:
            err_corr_max = err_corr_rms = np.nan
            grade = 'N/A'
        else:
            err_corr_max = np.max(err_corr) * 1000  # μm
            err_corr_rms = np.rms(err_corr) * 1000  # μm
            # take reduced sample at 95 percentile, excluding 5% worst points
            err_corr_95p = err_corr[err_corr <= np.percentile(err_corr, 95)]
            err_corr_95p_max = np.max(err_corr_95p) * 1000  # μm
            err_corr_95p_rms = np.rms(err_corr_95p) * 1000  # μm
            grade = grade_pos(err_0_max,
                              err_corr_max, err_corr_rms,
                              err_corr_95p_max, err_corr_95p_rms)
        rows.append({'DEVICE_ID': posid,
                     'err_0_max': err_0_max,  # max blind move xy error
                     'err_corr_max': err_corr_max,  # max corrective move err
                     'err_corr_rms': err_corr_rms,  # max corrective move rms
                     'err_corr_95p_max': err_corr_95p_max,  # best 95 percent
                     'err_corr_95p_rms': err_corr_95p_rms,  # best 95 percent
                     'grade': grade})
    data.grade_df = pd.DataFrame(rows).set_index('DEVICE_ID').join(data.posdf)


def grade_pos(err_0_max, err_corr_max, err_corr_rms,
              err_corr_95p_max, err_corr_95p_rms):
    '''these criteria were set by UMich lab tests, all in microns
    '''
    if np.any(np.isnan([err_0_max, err_corr_max, err_corr_rms,
              err_corr_95p_max])):
        return grades[-1]
    if (err_0_max <= 100) & (err_corr_max <= 15) & (err_corr_rms <= 5):
        grade = grades[0]
    elif ((err_0_max <= 250) & (err_corr_max <= 25) & (err_corr_rms <= 10)
          & (err_corr_95p_max <= 15) & (err_corr_95p_rms <= 5)):
        grade = grades[1]
    elif ((err_0_max <= 250) & (err_corr_max <= 50) & (err_corr_rms <= 20)
          & (err_corr_95p_max <= 25) & (err_corr_95p_rms <= 10)):
        grade = grades[2]
    elif ((err_0_max <= 500) & (err_corr_max <= 50) & (err_corr_rms <= 20)
          & (err_corr_95p_max <= 25) & (err_corr_95p_rms <= 10)):
        grade = grades[3]
    else:
        grade = grades[4]
    return grade


# read input and output paths
with open(os.path.join(pc.dirs['xytest_data'], 'pweave_test_src.txt'),
          'r') as h:
    path_input = h.read()
# load FPTestData as pickle
with open(path_input, "rb") as h:
    data = pickle.load(h)

targets = getattr(data, 'targets', data.targets_pos[list(data.targets_pos)[0]])

data.read_telemetry()
calculate_grades(data)
data.grade_df.to_pickle(os.path.join(data.dir, 'grade_df.pkl.gz'),
                        compression='gzip')
data.grade_df.to_csv(os.path.join(data.dir, 'grade_df.csv'))
with open(os.path.join(data.dir, 'data_dump.pkl'), 'wb') as handle:
    pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)

```

+------------------------+---------------------------------------------------------------------------------------------------------------+
| **Start time**\        | ``<%=data.start_time.isoformat()%>`` KPNO, ``<%=data.start_time.astimezone(timezone.utc).isoformat()%>`` UTC\ |
| **End time**\          | ``<%=data.end_time.isoformat()%>`` KPNO, ``<%=data.end_time.astimezone(timezone.utc).isoformat()%>`` UTC\     |
| **Duration**\          | ``<%=str(data.end_time-data.start_time)%> ``\                                                                 |
| **PCIDs**\             | ``<%=data.pcids%>``\                                                                                         |
| **Product directory**\ | ``<%=data.dir%>``\                                                                                            |
+------------------------+---------------------------------------------------------------------------------------------------------------+
| **Test logs**\         | ``<%=data.log_paths%>``                                                                                       |
+------------------------+---------------------------------------------------------------------------------------------------------------+

# Test Configuration

+-----------------------------+-----------------------------------------------+
| **Anticollision mode**\     | ``<%=data.anticollision%>``\                  |
| **Number of corrections**\  | ``<%=data.num_corr_max%> ``\                  |
| **Min radius of targets**\  | ``<%=data.test_cfg['targ_min_radius']%> mm``\ |
| **Max radius of targets**\  | ``<%=data.test_cfg['targ_max_radius']%> mm``\ |
| **Number of targets**\      | ``<%=data.ntargets%>``\                       |
+------------------------+----------------------------------------------------+
| **Target points**\          | ``<%=repr([list(t) for t in targets])%>``     |
+-----------------------------+-----------------------------------------------+

# Temperature

```python, echo=False, results='raw'

def plot_posfid_temp(pcid=None):

    def plot_petal(pcid, max=True, mean=True, median=True):
        query = data.telemetry[data.telemetry['pcid'] == pcid]
        if max:
            ax.plot(query['time'], query['posfid_temps_max'],
                    label=f'PC{pcid:02} max temp')
        if mean:
            ax.plot(query['time'], query['posfid_temps_mean'],
                    label=f'PC{pcid:02} mean temp')
        if median:
            ax.plot(query['time'], query['posfid_temps_median'],
                    label=f'PC{pcid:02} median temp')

    fig, ax = plt.subplots()
    if pcid is None:  # loop through all petals, plot max only
        for pcid in data.pcids:
            plot_petal(pcid, max=True, mean=False, median=False)
    else:  # pcid is an integer
        plot_petal(pcid)
    
    ax.legend()
    ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
    ax.xaxis.set_tick_params(rotation=45)
    ax.set_xlabel('Time (UTC)')
    ax.set_ylabel('Temperature (°C)')
    suffix = '' if pcid is None else f'_pc{pcid:2}'
    fig.savefig(os.path.join(data.dir, 'figures',
                         f'posfid_temp{suffix}.pdf'),
            bbox_inches='tight')

# plot overall temperatures for all petals
if data.db_telemetry_available:
    pd.plotting.register_matplotlib_converters()
    plot_posfid_temp()
else:
    print('DB telemetry query unavailable on this platform\n')
```

# Results

```python, echo=False, results='hidden'

def plot_grade_hist(pcid=None):
    if pcid is None:  # show all positioners tested
        grade_counts = data.grade_df['grade'].value_counts()
        title_suffix = 'petals' if len(data.pcids) > 1 else 'petal'
        title = (
            f'Overall grade distribution '
            f'({len(data.posids)} positioners, {len(data.pcids)} '
            + title_suffix + ')')
    else:
        grade_counts = data.grade_df['grade'].value_counts()
        title = (f'PC{pcid:02} grade distribution '
                 f'({len(data.posids_pc[pcid])} positioners)')
    for grade in grades:
        if grade not in grade_counts.index:  # no count, set to zero
            grade_counts[grade] = 0

    fig, ax = plt.subplots()
    grade_counts.reindex(grades).plot(
        ax=ax, kind='bar', figsize=(6, 3), title=title, rot=0,
        ylim=(0, grade_counts.max()+80))
    ax.set_xlabel('Postiioner grade')
    ax.set_ylabel('Count')
    for rect in ax.patches:  # add annotations
        height = rect.get_height()
        ax.annotate(f'{height}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom')
    suffix = '' if pcid is None else f'_pc{pcid:2}'
    fig.savefig(os.path.join(data.dir, 'figures',
                             f'grade_distribution{suffix}.pdf'),
                bbox_inches='tight')
    return grade_counts

# show overall statistics across all petals
plot_grade_hist()

```
