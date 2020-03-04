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
path = "/data/focalplane/logs/kpno/20200212/00048283-arc_calibration-all_good_after_canrestart/calibdf.pkl.gz"
mode = int(input('Choose mode\n'
                 '    0: apply to all positioners in the calibration file\n'
                 '    1: apply to specified positioners in posids\n'
                 '    2: apply to all except those in posids_exclude\n: '))
# set posids to apply calibrations, leave mpty to apply to all
posids = ['M00282', 'M00284', 'M01023', 'M01077', 'M01255', 'M01325',
       'M01471', 'M01702', 'M01712', 'M01814', 'M02011', 'M02021',
       'M02054', 'M02056', 'M02192', 'M02239', 'M02240', 'M02250',
       'M02268', 'M02269', 'M02341', 'M02381', 'M02408', 'M02422',
       'M02435', 'M02460', 'M02461', 'M02470', 'M02501', 'M02515',
       'M02549', 'M02576', 'M02584', 'M02586', 'M02588', 'M02599',
       'M02647', 'M02655', 'M02669', 'M02706', 'M02730', 'M02739',
       'M02760', 'M02764', 'M02765', 'M02766', 'M02789', 'M02808',
       'M02865', 'M02868', 'M02890', 'M02900', 'M02903', 'M02911',
       'M02925', 'M02940', 'M02978', 'M02979', 'M02984', 'M02987',
       'M02988', 'M02999', 'M03000', 'M03004', 'M03013', 'M03017',
       'M03038', 'M03046', 'M03076', 'M03097', 'M03113', 'M03122',
       'M03136', 'M03144', 'M03152', 'M03173', 'M03201', 'M03203',
       'M03205', 'M03223', 'M03228', 'M03229', 'M03243', 'M03292',
       'M03312', 'M03313', 'M03323', 'M03338', 'M03358', 'M03363',
       'M03375', 'M03387', 'M03391', 'M03395', 'M03414', 'M03432',
       'M03438', 'M03548', 'M03604', 'M03646', 'M03944', 'M04047',
       'M04286', 'M04328', 'M04528', 'M04609', 'M04611', 'M04798',
       'M04799', 'M04802', 'M04903', 'M05008', 'M05010', 'M05014',
       'M05026', 'M05060', 'M05309', 'M05339', 'M05340', 'M05341',
       'M05357', 'M05418', 'M05539', 'M05544', 'M05545', 'M05546',
       'M05547', 'M05548', 'M05555', 'M05556', 'M05557', 'M05558',
       'M05561', 'M05562', 'M05563', 'M05564', 'M05565', 'M05566',
       'M05567', 'M05568', 'M05569', 'M05570', 'M05571', 'M05572',
       'M05575', 'M05576', 'M05577', 'M05578', 'M05579', 'M05580',
       'M05584', 'M05586', 'M05587', 'M05589', 'M05591', 'M05593',
       'M05594', 'M05595', 'M05596', 'M05597', 'M05598', 'M05599',
       'M05601', 'M05603', 'M05604', 'M05606', 'M05608', 'M05609',
       'M05610', 'M05611', 'M05613', 'M05614', 'M05618', 'M05619',
       'M05620', 'M05621', 'M05625', 'M05626', 'M05628', 'M05631',
       'M05632', 'M05633', 'M05634', 'M05635', 'M05636', 'M05637',
       'M05645', 'M05658', 'M05659', 'M05661', 'M05664', 'M05665',
       'M05666', 'M05667', 'M05668', 'M05670', 'M05671', 'M05672',
       'M05673', 'M05674', 'M05676', 'M05677', 'M05680', 'M05681',
       'M05682', 'M05683', 'M05684', 'M05685', 'M05794', 'M05800',
       'M05802', 'M05803', 'M05804', 'M05805', 'M05806', 'M05807',
       'M05808', 'M05810', 'M05812', 'M05822', 'M05824', 'M05825',
       'M05834', 'M05835', 'M05838', 'M05840', 'M05944', 'M05945',
       'M05946', 'M05949', 'M05951', 'M05953', 'M05954', 'M05955',
       'M05962', 'M05963', 'M05968', 'M06059', 'M06091', 'M06181',
       'M06182', 'M06183', 'M06184', 'M06185', 'M06186', 'M06205',
       'M06206', 'M06207', 'M06209', 'M06210', 'M06213', 'M06215',
       'M06216', 'M06219', 'M06264', 'M06265', 'M06270', 'M06271',
       'M06272', 'M06274', 'M06275', 'M06276', 'M06279', 'M06280',
       'M06281', 'M06282', 'M06284', 'M06285', 'M06295', 'M06296',
       'M06297', 'M06298', 'M06342', 'M06348', 'M06349', 'M06350',
       'M06352', 'M06354', 'M06355', 'M06356', 'M06408', 'M06409',
       'M06411', 'M06412', 'M06413', 'M06414', 'M06450', 'M06456',
       'M06457', 'M06458', 'M06459', 'M06460', 'M06461', 'M06468',
       'M06492', 'M06493', 'M06496', 'M06508', 'M06509', 'M06584',
       'M06694', 'M06696', 'M06698', 'M06700', 'M06701', 'M06702',
       'M06703', 'M06704', 'M06715', 'M06716', 'M06717', 'M06718',
       'M06719', 'M06720', 'M06722', 'M06744', 'M06746', 'M06747',
       'M06748', 'M06749', 'M06772', 'M06773', 'M06803', 'M06804',
       'M06808', 'M06809', 'M06811', 'M06814', 'M06867', 'M06868',
       'M06870', 'M06894', 'M06899', 'M06900', 'M06901', 'M06902',
       'M06903', 'M06904', 'M06906', 'M06908', 'M06909', 'M06910',
       'M06911', 'M06912', 'M06914', 'M06935', 'M06936', 'M06937',
       'M06939', 'M06940', 'M06941', 'M07019', 'M07020', 'M07021',
       'M07023', 'M07060', 'M07105', 'M07106', 'M07111', 'M07113',
       'M07115', 'M07117', 'M07126', 'M07128', 'M07131', 'M07153',
       'M07154', 'M07157', 'M07158', 'M07159', 'M07184', 'M07185',
       'M07186', 'M07188', 'M07189', 'M07190', 'M07191', 'M07192',
       'M07194', 'M07196', 'M07197', 'M07199', 'M07200', 'M07201',
       'M07204', 'M07206', 'M07207', 'M07208', 'M07209', 'M07210',
       'M07212', 'M07213', 'M07214', 'M07215', 'M07234', 'M07235',
       'M07257', 'M07280', 'M07285', 'M07286', 'M07291', 'M07301',
       'M07304', 'M07312', 'M07351', 'M07352', 'M07353', 'M07394',
       'M07395', 'M07396'] 
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
