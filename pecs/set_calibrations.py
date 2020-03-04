
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
path = "/data/focalplane/logs/kpno/20200213/00048406-arc_calibration-ptl2_88_disabled/calibdf.pkl.gz"
mode = int(input('Choose from the following three modes (enter single digit integer)\n'
                 '    0: apply to all positioners in the calibration file\n'
                 '    1: apply to only those specified in posids\n'
                 '    2: apply to all except those in posids_exclude\n: '))
# set posids to apply calibrations, leave mpty to apply to all
posids = ['M01282', 'M02440', 'M02449', 'M02499', 'M03037', 'M03067',
       'M03151', 'M03416', 'M04606', 'M04717', 'M05612', 'M05836',
       'M05952', 'M05961', 'M05967', 'M05970', 'M06812', 'M07127',
       'M07229', 'M05675', 'M06345', 'M02762', 'M04607', 'M05615',
       'M06278', 'M07129', 'M01383', 'M01476', 'M02284', 'M02367',
       'M02393', 'M02763', 'M02855', 'M03315', 'M03392', 'M04608',
       'M04610', 'M04626', 'M05041', 'M05358', 'M05592', 'M05600',
       'M05605', 'M05622', 'M05623', 'M05662', 'M05678', 'M05801',
       'M05809', 'M05839', 'M05948', 'M05950', 'M05969', 'M05971',
       'M06208', 'M06220', 'M06294', 'M06299', 'M06353', 'M06410',
       'M06418', 'M06503', 'M06695', 'M06697', 'M06699', 'M06714',
       'M06723', 'M06745', 'M06770', 'M06774', 'M06813', 'M06913',
       'M06942', 'M07022', 'M07108', 'M07110', 'M07187', 'M07195',
       'M07216', 'M07263', 'M07264', 'M07267', 'M07270', 'M07287',
       'M07289', 'M07294', 'M07295', 'M07296']
posids_exclude = []
calib = pd.read_pickle(path)['FIT']
pecs = PECS(interactive=False)
if mode == 0:
    posids = calib.index
elif mode == 1:
    posids = set(posids) & set(calib.index)
else:
    posids = set(calib.index) - set(posids_exclude)
pecs.ptl_setup(pecs.pcids, posids=posids)
print(f'Setting calibration for {len(posids)} positioners using file: {path}')
keys_fit = ['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
            'LENGTH_R1', 'LENGTH_R2']  # initial values for fitting
accepted, rejected = set(), set()
old, new = [], []
for posid in tqdm(posids):
    role = pecs._pcid2role(pecs.posinfo.loc[posid, 'PETAL_LOC'])
    update = {'DEVICE_ID': posid, 'MODE': 'set_calibrations'}
    update = pecs.ptlm.collect_calib(update, tag='',
                                     participating_petals=role)[role]
    old.append(update)
    ret = {key: pecs.ptlm.set_posfid_val(
                    posid, key, calib.loc[posid, key],
                    participating_petals=role)
                for key in keys_fit}
    if all(val == True for val in ret.values()):
        accepted.add(posid)
    else:
        print(f'{posid} rejected: {ret}')
        rejected.add(posid)
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
print(f'{len(accepted)} positioners accepted')
print(f'{len(rejected)} positioneres rejected one or more params:\n'
      f'{sorted(rejected)}')
