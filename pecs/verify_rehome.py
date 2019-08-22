# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 14:04:52 2019

@author: givoltage
"""

import os
import numpy as np
import pandas as pd
from pecs import PECS
# from seed_xy_offsets import XY_Offsets
import posconstants as pc
# import pandas as pd
# from DOSlib.positioner_index import PositionerIndex


class VerifyRehome(PECS):

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
        df = self.compare_xy()
        df.to_csv(os.path.join(
            pc.dirs['all_logs'], 'calib_logs',
            f'{pc.filename_timestamp_str_now()}-rehome_verify.csv'))
        self.printfunc(f'Rehome verification data saved to calib logs.')

    def compare_xy(self):
        ptl = self.ptls[self.ptlid]
        # all backlit fibres, including those disabled, needed for FVC
        expected_pos = ptl.get_positions(return_coord='QS')
        df = (ptl.get_pos_vals(['OFFSET_X', 'OFFSET_Y'],
                               posids=list(expected_pos['DEVICE_ID']))
              .set_index('DEVICE_ID'))
        offX, offY = df['OFFSET_X'].values, df['OFFSET_Y'].values
        Q = np.degrees(np.arctan2(offY, offX))  # convert offsetXY to QS
        R = np.sqrt(np.square(offX) + np.square(offY))
        S = pc.R2S_lookup(R)  # convert offsetXY to QS
        # set nominal offsetsXY (in QS) as expected postiions for FVC spotmatch
        expected_pos['X1'], expected_pos['X2'] = Q, S
        self.printfunc('Taking FVC exposure to confirm home positions...')
        mr_old = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=80)  # set larger radius for calib
        # self.printfunc(f'Sending the following expected positions to FVC:\n'
        #                f'{expected_pos}')
        mQS = (pd.DataFrame(self.fvc.measure(expected_pos))  # measured_QS
               .rename(columns={'id': 'DEVICE_ID'})  # exp_pos changed in place
               .set_index('DEVICE_ID').sort_index())  # sorted
        mQS.columns = mQS.columns.str.upper()
        self.fvc.set(match_radius=mr_old)  # restore old radius
        # get expected positions again, only interested in flags
        # expected_pos = ptl.get_positions().set_index('DEVICE_ID')
        # find what's unmatched
        unmatched = sorted(set(self.posids) - set(mQS.index))
        self.printfunc(f'{len(unmatched)} unmatched positioners:\n{unmatched}')
        # write columns to measured_QS using auto index matching
        mQS['FLAG'] = \
            expected_pos.set_index('id').loc[mQS.index]['flags'].values
        mQS['STATUS'] = ptl.decipher_posflags(mQS['FLAG'])
        mQS['expectedX'] = df.loc[mQS.index]['OFFSET_X'].values
        mQS['expectedY'] = df.loc[mQS.index]['OFFSET_Y'].values
        # filter expected pos because there are unmatched fibres
        # expected_pos = expected_pos.loc[measured_QS.index]  # same order
        # expected_pos['expectedX'] = df.loc[measured_QS.index]['OFFSET_X']
        # expected_pos['expectedY'] = df.loc[measured_QS.index]['OFFSET_Y']
        # convert QS to obsXY for measuredXY
        Q_rad = np.radians(mQS['Q'])
        R = pc.S2R_lookup(mQS['S'])
        mQS['measuredX'] = R * np.cos(Q_rad)
        mQS['measuredY'] = R * np.sin(Q_rad)
        mQS['obsdX'] = mQS['measuredX'] - mQS['expectedX']
        mQS['obsdY'] = mQS['measuredY'] - mQS['expectedY']
        mQS['dr'] = np.sqrt(np.square(mQS['obsdX'])
                            + np.square(mQS['obsdY']))
        mQS = mQS.sort_values(by='dr', ascending=False).reset_index()
        mask = mQS['dr'] > 1
        bad_posids = list(mQS[mask].index)
        if len(bad_posids) == 0:
            self.printfunc(f'All {len(mQS)} matched fibres verified rehomed.')
        else:
            self.printfunc(f'Possibly {len(bad_posids)} positioners not '
                           f'rehomed (radial deviations > 1 mm):\n\n'
                           f'{mQS[mask]}\n\n'
                           f'Positioner IDs:\n{bad_posids}')
        self.printfunc(mQS)
        return mQS


if __name__ == '__main__':
    VerifyRehome()
