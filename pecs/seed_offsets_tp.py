'''
Sets offsetsTP to nominal values. Needs running DOS instance
'''
import os
import pandas as pd
from pecs import PECS
import posconstants as pc

interactive = True
seed = PECS(fvc=None, ptls=None)
if interactive:
    seed.interactive_ptl_setup()
else:
    seed.ptl_setup(pcid=None, posids=None)
print('Seeding offsetsTP...')
updates = []
for posid in seed.posids:
    update = {'DEVICE_ID': posid,
              'MODE': 'seed_offsets_tp'}
    update = seed.ptl.collect_calib(update, tag='OLD_')
    seed.ptl.set_posfid_val(posid, 'OFFSET_T',
                            pc.nominals['OFFSET_T']['value'])
    seed.ptl.set_posfid_val(posid, 'OFFSET_P',
                            pc.nominals['OFFSET_P']['value'])
    updates.append(seed.ptl.collect_calib(update, tag=''))
seed.ptl.commit(mode='calib', log_note='seed_offsets_tp')
updates = pd.DataFrame(updates)
path = os.path.join(pc.dirs['calib_logs'],
                    f'{pc.filename_timestamp_str()}-seed_offsets_tp.csv')
updates.to_csv(path)
# preview calibration updates
print(updates[['DEVICE_ID', 'POS_T', 'POS_P',
               'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
               'LENGTH_R1', 'LENGTH_R2']])
print(f'Seed offsets TP data saved to: {path}')
