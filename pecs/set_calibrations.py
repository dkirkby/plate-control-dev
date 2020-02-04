# -*- coding: utf-8 -*-
"""
Created on Mon Feb  3 18:54:30 2020

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
from tqdm import tqdm
import pandas as pd
import posconstants as pc
from pecs import PECS

# set source calibration file
path = "/data/focalplane/logs/kpno/20200203/00046362-arc_calibration-754_previously_disabled/calibdf.pkl.gz"
# set posids to apply calibrations, leave empty to apply to all
posids = []
calib = pd.read_pickle(path)['FIT']
posids = set(posids) & set(calib.index) if posids else calib.index
pecs = PECS(interactive=False)
pecs.ptl_setup(pecs.pcids, posids=posids)
keys_fit = ['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
            'LENGTH_R1', 'LENGTH_R2']  # initial values for fitting
old, new = [], []
for posid in tqdm(posids):
    role = pecs._pcid2role(pecs.posinfo.loc[posid, 'PETAL_LOC'])
    update = {'DEVICE_ID': posid, 'MODE': 'set_calibrations'}
    update = pecs.ptlm.collect_calib(update, tag='',
                                     participating_petals=role)[role]
    old.append(update)
    for key in keys_fit:
        pecs.ptlm.set_posfid_val(posid, key, calib.loc[posid, key])
    update = pecs.ptlm.collect_calib(update, tag='',
                                     participating_petals=role)[role]
    new.append(update)
pecs.ptlm.commit(mode='calib',
                 log_note=f'set_calibrations: {os.path.basename(path)}')
old = pd.DataFrame(old).set_index('DEVICE_ID').sort_index()
new = pd.DataFrame(new).set_index('DEVICE_ID').sort_index()
calibdf = pd.concat([old, calib, new], axis=1,
                    keys=['OLD', 'FIT', 'NEW'],
                    names=['label', 'field'], sort=False)
path = os.path.join(pc.dirs['calib_logs'],
                    f'{pc.filename_timestamp_str()}-set_calibrations.pkl.gz')
calibdf.to_pickle(path)
# preview calibration updates
print(calibdf['NEW'][['POS_T', 'POS_P', 'LENGTH_R1', 'LENGTH_R2',
                      'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P']])
print(f'set_calibrations data saved to: {path}')
