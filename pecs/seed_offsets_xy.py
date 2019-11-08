'''
Seeds offsetsXY using nominal hole locations and the petal location.
Needs running DOS instance. See pecs.py
'''
import os
import numpy as np
import pandas as pd
from DOSlib.positioner_index import PositionerIndex
import posconstants as pc
from pecs import PECS


class SeedOffsetsXY(PECS):
    def __init__(self, fvc=None, ptls=None,
                 pcid=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptls=ptls)
        self.printfunc('\nSeeding offsets XY...\n')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(pcid, posids)
        updates = self.seed_vals()
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-seed_offsets_xy.csv')
        updates.to_csv(path)
        self.printfunc(  # preview calibration updates
            updates[['DEVICE_ID', 'DEVICE_LOC', 'OFFSET_X', 'OFFSET_Y',
                     'POS_T', 'POS_P', 'LENGTH_R1', 'LENGTH_R2']])
        self.printfunc(f'Seed offsets XY data saved to: {path}')
        if interactive:
            if self._parse_yn(input('Open offsets XY table? (y/n): ')):
                os.system(f'xdg-open {path}')
        self.printfunc('Please check DB to ensure new values are committed.')

    def seed_vals(self):
        '''
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
        index = PositionerIndex()
        data = np.genfromtxt(pc.dirs['positioner_locations_file'],
                             delimiter=',', names=True,
                             usecols=(0, 2, 3, 4))  # in nominal ptlXY
        # convert structured array to normal np array of shape (3, 543)
        pos = data.view(np.float64).reshape(data.shape[0], 4)[:, 1:].T
        pos = self.ptl.ptltrans('ptlXYZ_to_flatXY', pos)
        updates = []
        for posid in self.posids:
            pos_info = index.find_by_device_id(posid)
            device_loc = int(pos_info['DEVICE_LOC'])
            x, y = pos[0, device_loc], pos[1, device_loc]
            update = {'DEVICE_ID': posid,
                      'DEVICE_LOC': pos_info['DEVICE_LOC'],
                      'PETAL_LOC': pos_info['PETAL_LOC'],
                      'MODE': 'initialize_offsets_xy'}
            update = self.ptl.collect_calib(update, tag='OLD_')
            self.ptl.set_posfid_val(posid, 'OFFSET_X', x)
            self.ptl.set_posfid_val(posid, 'OFFSET_Y', y)
            update = self.ptl.collect_calib(update, tag='')
            updates.append(update)
        self.ptl.commit(mode='calib', log_note='initialize_offsets_xy')
        return pd.DataFrame(updates)


if __name__ == '__main__':
    off = SeedOffsetsXY(interactive=True)
