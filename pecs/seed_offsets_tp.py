'''
Sets offsetsTP to nominal values. Needs running DOS instance. See pecs.py
'''
import os
import pandas as pd
from pecs import PECS
import posconstants as pc


class SeedOffsetsTP(PECS):
    def __init__(self, fvc=None, ptls=None,
                 pcid=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptls=ptls)
        self.printfunc('\nSeeding offsetsTP...\n')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(pcid, posids)
        updates = self.seed_vals()
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str()}-seed_offsets_tp.csv')
        updates.to_csv(path)
        self.printfunc(  # preview calibration updates
            updates[['DEVICE_ID', 'POS_T', 'POS_P',
                     'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
                     'LENGTH_R1', 'LENGTH_R2']])
        self.printfunc(f'Seed offsets TP data saved to: {path}')
        if interactive:
            if self._parse_yn(input('Open offsets TP table? (y/n): ')):
                os.system(f'xdg-open {path}')
        self.printfunc('Please check DB to ensure new values are committed.')

    def seed_vals(self):
        updates = []
        for posid in self.posids:
            update = {'DEVICE_ID': posid,
                      'MODE': 'seed_offsets_tp'}
            update = self.ptl.collect_calib(update, tag='OLD_')
            self.ptl.set_posfid_val(posid, 'OFFSET_T',
                                    pc.nominals['OFFSET_T']['value'])
            self.ptl.set_posfid_val(posid, 'OFFSET_P',
                                    pc.nominals['OFFSET_P']['value'])
            update = self.ptl.collect_calib(update, tag='')
            updates.append(update)
        self.ptl.commit(mode='calib', log_note='initialize_offsets_xy')
        return pd.DataFrame(updates)


if __name__ == '__main__':
    SeedOffsetsTP(interactive=True)
