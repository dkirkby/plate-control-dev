'''
Sets offsetsXY to nominal values. Needs running DOS instance

Also called seed xy offsets, this script establishes initial values for
positioner offsets using nominal specs or
metrology data, right after petal assemblies are mounted to the ring
on-mountain, so that calibration can be done.

Calibration, or particularly spotmatch, relies on knowing a priori
approximately where things are, and searching within a search radius.
After calibration, the estimatd parameters will be updated with newly
measured values.

The x, y offsets of positioenrs for the central axis can be estimated
from the designed focal plate layout. So we'll use the theoretical
positioner x, y offsets as a starting point.

In the new local coordinate transformation scheme, xy offsets are
in the petal's local CS, from petal's nominal origin to positioner
centre (of patrol area).
We are only doing this for positioners, no fiducials.

Returns two pandas Dataframes with columns
DEVICE_ID, PETAL_LOC, DEVICE_LOC, old and new calibration vals, with
MODE for updates and old values.
'''
import os
import numpy as np
import pandas as pd
from DOSlib.positioner_index import PositionerIndex
import posconstants as pc
from pecs import PECS

interactive = True
seed = PECS(fvc=None, ptls=None)
if interactive:
    seed.interactive_ptl_setup()
else:
    seed.ptl_setup(pcid=None, posids=None)
print('Seeding offsets XY...')
pi = PositionerIndex()
# array of shape (3, 543) in nominal ptlXY
ptlXYZ = (pd.read_csv(pc.dirs['positioner_locations_file'])
        [['X', 'Y', 'Z']].values.T)
pos = seed.ptl.ptltrans('ptlXYZ_to_flatXY', ptlXYZ)
updates = []
for posid in seed.posids:
    pos_info = pi.find_by_device_id(posid)
    device_loc = int(pos_info['DEVICE_LOC'])
    x, y = pos[0, device_loc], pos[1, device_loc]
    update = {'DEVICE_ID': posid,
              'DEVICE_LOC': pos_info['DEVICE_LOC'],
              'PETAL_LOC': pos_info['PETAL_LOC'],
              'MODE': 'initialize_offsets_xy'}
    update = seed.ptl.collect_calib(update, tag='OLD_')
    seed.ptl.set_posfid_val(posid, 'OFFSET_X', x)
    seed.ptl.set_posfid_val(posid, 'OFFSET_Y', y)
    updates.append(seed.ptl.collect_calib(update, tag=''))
seed.ptl.commit(mode='calib', log_note='seed_offsets_xy')
updates = pd.DataFrame(updates)
path = os.path.join(pc.dirs['calib_logs'],
                    f'{pc.filename_timestamp_str()}-seed_offsets_xy.csv')
updates.to_csv(path)
# preview calibration updates
print(updates[['DEVICE_ID', 'DEVICE_LOC', 'OFFSET_X', 'OFFSET_Y',
               'POS_T', 'POS_P', 'LENGTH_R1', 'LENGTH_R2']])
print(f'Seed offsets XY data saved to: {path}')
