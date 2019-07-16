# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 14:04:52 2019

@author: givoltage
"""

import os
import numpy as np
import pandas as pd
from pecs import PECS
from seed_xy_offsets import XY_Offsets
import posconstants as pc
# import pandas as pd
# from DOSlib.positioner_index import PositionerIndex


class RehomeVerify(PECS):

    def __init__(self, petal_id=None, platemaker_instrument=None,
                 fvc_role=None, printfunc=print,
                 selection=None, enabled_only=True, axis='both'):
        PECS.__init__(self, ptlids=petal_id,
                      platemaker_instrument=platemaker_instrument,
                      fvc_role=fvc_role, printfunc=printfunc)
        self.printfunc = printfunc
        self.ptlid = list(self.ptls.keys())[0]
        self.axis = axis
        if not selection:
            self.posids = list(self.ptls[self.ptlid].get_positioners(
                enabled_only=enabled_only).loc[:, 'DEVICE_ID'])
        elif selection[0][0] == 'c':  # User passed busids
            self.posids = list(
                self.ptls[self.ptlid].get_positioners(
                    enabled_only=enabled_only, busids=selection)
                .loc[:, 'DEVICE_ID'])
        else:  # assume is a list of posids
            self.posids = sorted(selection)
        self.printfunc(f'Verifying homing positions for all '
                       f'{len(self.posids)} enabled positioners...')

    def compare_xy(self):
        ptl = self.ptls[self.ptlid]
        self.printfunc(f'Seeding XY offsets...')
        df = (XY_Offsets().seed_vals(auto_update=True)
              .set_index('DEVICE_ID'))  # all 502 fibres including dark
        expected_pos = (ptl.get_positions(return_coord='QS')
                        .set_index('DEVICE_ID'))  # all good fibres
        df = df.loc[expected_pos.index]
        offsetX, offsetY = df['OFFSET_X'], df['OFFSET_Y']  # all backlit fibres
        Q = np.degrees(np.arctan2(offsetY, offsetX))  # convert offsetXY to QS
        R = np.sqrt(np.square(offsetX) + np.square(offsetY))
        S = pc.R2S_lookup(R)  # convert offsetXY to QS
        # set nominal offsetsXY (in QS) as expected postiions for FVC spotmatch
        expected_pos['X1'], expected_pos['X2'] = Q, S
        self.printfunc('Taking FVC exposure to confirm home positions...')
        mr_old = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=80)  # set larger radius for calib
        expected_pos.reset_index(inplace=True)
        # self.printfunc(f'Sending the following expected positions to FVC:\n'
        #                f'{expected_pos}')
        measured_QS = (pd.DataFrame(self.fvc.measure(expected_pos))
                       .rename(columns={'id': 'DEVICE_ID'})
                       .set_index('DEVICE_ID').sort_index())
        measured_QS.columns = measured_QS.columns.str.upper()  # sorted
        self.fvc.set(match_radius=mr_old)  # restore old radius
        # overwrite columns in expected positions
        expected_pos = (ptl.get_positions(return_coord='obsXY')
                        .rename(columns={'X1': 'expectedX', 'X2': 'expectedY'})
                        .set_index('DEVICE_ID'))
        # what's unmatched
        all_posids = set(expected_pos['DEVICE_ID'])
        measured_posids = set(measured_QS['DEVICE_ID'])
        unmatched = all_posids - measured_posids
        self.printfunc(f'Missing {len(unmatched)} unmatched positioners:\n'
                       f'{unmatched}')
        # filter expected pos because there are unmatched fibres
        expected_pos = expected_pos.loc[measured_QS.index]  # same order
        expected_pos['expectedX'] = offsetX.loc[measured_QS.index]
        expected_pos['expectedY'] = offsetY.loc[measured_QS.index]
        # convert QS to obsXY for measuredXY
        Q_rad = np.radians(measured_QS['Q'])
        R = pc.S2R_lookup(measured_QS['S'])
        expected_pos['measuredX'] = R * np.cos(Q_rad)
        expected_pos['measuredY'] = R * np.sin(Q_rad)
        expected_pos['delta_obsX'] = (expected_pos['measuredX']
                                      - expected_pos['expectedX'])
        expected_pos['delta_obsY'] = (expected_pos['measuredY']
                                      - expected_pos['expectedY'])
        expected_pos['delta_r'] = (np.sqrt(
            np.square(expected_pos['delta_obsX'])
            + np.square(expected_pos['delta_obsY'])))
        expected_pos = expected_pos.sort_values(
            by='delta_r', ascending=False).reset_index()
        mask = expected_pos['delta_r'] > 2
        bad_posids = list(expected_pos[mask]['DEVICE_ID'])
        if len(bad_posids) == 0:
            self.printfunc('All successful and verified to match measurement.')
            return True
        else:
            self.printfunc(f'Possibly not rehomed sucessfully '
                           f'(radial deviations > 1 mm):\n\n'
                           f'{expected_pos[mask]}\n\n'
                           f'Positioner IDs:\n'
                           f'{list(expected_pos[mask].DEVICE_ID})')
        return expected_pos


if __name__ == '__main__':
    rv = RehomeVerify()
    df = rv.compare_xy()
    path = os.path.join(pc.dirs['all_logs'], 'calib_logs',
                        f'{pc.filename_timestamp_str_now()}-rehome_verify.csv')
    df.to_csv(path)
    print(f'Rehome verification data saved to: {path}')
