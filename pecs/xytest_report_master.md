% DESI Positioner Accuracy Test Report
% Focal Plane Team
% 2019-11-20 (master template last revised)

```python name='grading', echo=False
# -*- coding: utf-8 -*-
"""
generates html/pdf report for xy accuracy test

Created on Wed Oct 30 12:57:04 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import sys
import pickle
from functools import reduce
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
colours = {grade: f'C{i}' for i, grade in enumerate(grades)}

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
            err_corr_95p_max = err_corr_95p_rms = np.nan
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
    data.gradedf = pd.DataFrame(rows).set_index('DEVICE_ID').join(data.posdf)


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
data.gradedf.to_pickle(os.path.join(data.dir, 'gradedf.pkl.gz'),
                        compression='gzip')
data.gradedf.to_csv(os.path.join(data.dir, 'gradedf.csv'))
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

```python name='posfid temperature', echo=False, results='raw'

def plot_posfid_temp(pcid=None):

    def plot_petal(pcid, max_on=True, mean_on=False, median_on=True):
        query = data.telemetry[data.telemetry['pcid'] == pcid]
        if max_on:
            ax.plot(query['time'], query['posfid_temps_max'], '-o',
                    label=f'PC{pcid:02} posfid max')
        if mean_on:
            ax.plot(query['time'], query['posfid_temps_mean'], '-o',
                    label=f'PC{pcid:02} posfid mean')
        if median_on:
            ax.plot(query['time'], query['posfid_temps_median'], '-o',
                    label=f'PC{pcid:02} posfid median')

    fig, ax = plt.subplots()
    if pcid is None:  # loop through all petals, plot max only
        for pc in data.pcids:
            plot_petal(pc,
                       max_on=True, mean_on=False, median_on=False)
    else:  # pcid is an integer
        plot_petal(pcid)
    
    ax.legend()
    ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
    ax.xaxis.set_tick_params(rotation=45)
    ax.set_xlabel('Time (UTC)')
    ax.set_ylabel('Temperature (°C)')
    suffix = '' if pcid is None else f'_pc{pcid:02}'
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

```python name='grade distributions', echo=False

def add_hist_annotation(ax):
    for rect in ax.patches:  # add annotations
        height = rect.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords='offset points',
                    ha='center', va='bottom')
    ax.set_ylim([0.1, ax.get_ylim()[1]*3])

def plot_grade_dist(pcid=None):
    if pcid is None:  # show all positioners tested
        grade_counts = data.gradedf['grade'].value_counts()
        ptlstr = 'petals' if len(data.pcids) > 1 else 'petal'
        title = (
            f'Overall grade distribution '
            f'({len(data.posids)} positioners, {len(data.pcids)} '
            + ptlstr + ')')
    else:
        mask = data.gradedf['PCID'] == pcid
        grade_counts = data.gradedf[mask]['grade'].value_counts()
        title = (f'PC{pcid:02} grade distribution '
                 f'({len(data.posids_pc[pcid])} positioners)')
    for grade in grades:
        if grade not in grade_counts.index:  # no count, set to zero
            grade_counts[grade] = 0

    fig, ax = plt.subplots()
    grade_counts.reindex(grades).plot(
        ax=ax, kind='bar', log=True,
        figsize=(6, 3), title=title, rot=0, alpha=0.8)
    add_hist_annotation(ax)
    ax.set_xlabel('Postiioner grade')
    ax.set_ylabel('Count')
    suffix = '' if pcid is None else f'_pc{pcid:02}'
    fig.savefig(os.path.join(data.dir, 'figures',
                             f'grade_distribution{suffix}.pdf'),
                bbox_inches='tight')
    return grade_counts

# show overall statistics across all petals
_ = plot_grade_dist()
```

```python name='error distributions', echo=False, width='linewidth'

def plot_error_dist(pcid=None, grade=None):
    if pcid is None:  # show all positioners tested
        err = data.gradedf
        ptlstr = 'petals' if len(data.pcids) > 1 else 'petal'
        title = (
            f'Overall {{}} distribution '
            f'\n({len(data.posids)} positioners, {len(data.pcids)} '
            + ptlstr + ')')
    else:
        err = data.gradedf[data.gradedf['PCID'] == pcid]
        if grade is not None:
            err = err[err['grade']==grade]
        title = (f'PC{pcid:02} {{}} distribution '
                 f'\n({len(data.posids_pc[pcid])} positioners)')

    def plot_error_hist(ax, column_name, cuts, title, vlines=None):
        grades_present = sorted(err['grade'].unique())
        if 'N/A' in grades_present:
            grades_present.pop('N/A')
        ax.hist([err[err['grade'] == grade][column_name]
                 for grade in grades_present],
                log=True, histtype='bar', stacked=True, alpha=0.8,
                color = [colours[grade] for grade in grades_present],
                label=[f'Grade {grade}' for grade in grades_present])
        add_hist_annotation(ax)
        ax.set_ylim(top=min([ax.get_ylim()[1]*10, 1e3]))
        ax.set_title(title)
        ax.set_xlabel('Error (μm)')
        ax.set_ylabel('Count')
        if vlines is not None:
            for vline in vlines:
                ax.axvline(vline)
        ax.legend()

        # add text for counts
        rows = []
        cuts = (list(cuts) + [err[column_name].max()]
                if sorted(cuts)[-1] < err[column_name].max()
                else list(cuts))
        for cut in cuts:
            rows.append({'Error within (μm)': int(cut),
                        'Count': int(np.sum(err[column_name] <= cut))})
        text = pd.DataFrame(rows).to_string(index=False)
        ax.text(0.7, 0.95, text, ha='right', va='top',
                family='monospace', transform=ax.transAxes,
                bbox={'boxstyle': 'round', 'alpha': 0.2,
                          'facecolor': 'white', 'edgecolor': 'lightgrey'})

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    plot_error_hist(axes[0], 'err_0_max', [0, 100, 200, 300, 400, 500, 1000],
                    title.format('max blind move error'))
    plot_error_hist(axes[1], 'err_corr_rms', [0, 5, 10, 20, 30, 50, 100, 200],
                    title.format('rms corrective move error'))
    plt.tight_layout()
    suffix1 = '' if pcid is None else f'_pc{pcid:02}'
    suffix2 = '' if grade is None else f'_grade_{grade}'.lower()
    fig.savefig(os.path.join(data.dir, 'figures',
                             f'error_distribution{suffix1}{suffix2}.pdf'),
                bbox_inches='tight')

plot_error_dist()
```

```python name='abnormal positioners', echo=False, results='raw'
# get postiioners with abnormal flags
masks = []
for i in range(data.num_corr_max+1):
    masks.append(data.movedf[f'pos_flag_{i}'] != 4)
mask = reduce(lambda x, y: x | y, masks)
df_abnormal = data.movedf[mask]
posids_abnormal = df_abnormal.index.droplevel(0).unique()

def abnormal_pos_df(pcid=None):
    if pcid is None:
        df = df_abnormal
    else:
        df = df_abnormal[df_abnormal['PCID']==pcid]
    rows = []
    for posid in posids_abnormal:
        counts_list = []  # counts by submove
        for i in range(data.num_corr_max+1):
            counts_list.append(
                df.loc[idx[:, posid], :][f'pos_status_{i}'].value_counts())
        counts = reduce(lambda x, y: x.add(y, fill_value=0), counts_list)  # total
        rows.append(counts)
    df_status = pd.DataFrame(rows, index=posids_abnormal).drop('Normal positioner', axis=1)
    return df_status

##### Abnormal status: ``<%=len(posids_abnormal)%>`` positioners

# ```python name='abnormal pos print', echo=False
# abnormal_pos_df().reset_index().astype(int, errors='ignore')
# ```

```
