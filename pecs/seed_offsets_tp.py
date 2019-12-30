'''
Sets offsetsTP to nominal values. Needs running DOS instance
'''
import os
import pandas as pd
from pecs import PECS
import posconstants as pc

seed = PECS(fvc=None, ptls=None, interactive=True)
print('Seeding offsetsTP...')
updates = []
for posid in self.posids:
    role = self.get_owning_ptl_role(posid)
    update = {'DEVICE_ID': posid,
              'MODE': 'seed_offsets_tp'}
    update = self.ptlm.collect_calib(update, tag='OLD_',
                                     participating_petals=role)[role]
    self.ptlm.set_posfid_val(posid, 'OFFSET_T',
                             pc.nominals['OFFSET_T']['value'],
                             participating_petals=role)
    self.ptlm.set_posfid_val(posid, 'OFFSET_P',
                             pc.nominals['OFFSET_P']['value'],
                             participating_petals=role)
    update = self.ptlm.collect_calib(update, tag='',
                                     participating_petals=role)[role]
    updates.append(update)
seed.ptlm.commit(mode='calib', log_note='seed_offsets_tp')
updates = pd.DataFrame(updates)
path = os.path.join(pc.dirs['calib_logs'],
                    f'{pc.filename_timestamp_str()}-seed_offsets_tp.csv')
updates.to_csv(path)
# preview calibration updates
print(updates[['DEVICE_ID', 'POS_T', 'POS_P',
               'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
               'LENGTH_R1', 'LENGTH_R2']])
print(f'Seed offsets TP data saved to: {path}')
