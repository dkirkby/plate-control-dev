# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 14:04:52 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""

import os
import numpy as np
import pandas as pd
from pecs import PECS
import posconstants as pc


class RehomeVerify(PECS):

    def __init__(self, fvc=None, ptlm=None,
                 petal_roles=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptlm=ptlm)
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_roles, posids)
        self.printfunc(f'Verifying rehome positions for '
                       f'{len(self.posids)} positioners...')
        df = self.compare_xy()
        path = os.path.join(  # save results
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-rehome_verify.csv')
        df.to_csv(path)
        self.printfunc(f'Rehome verification data saved to: {path}')
        if input('Open verification table? (y/n): ') in ['y', 'yes']:
            os.system(f'xdg-open {path}')

    def compare_xy(self):
        # ptl = self.ptls[self.ptlid]
        # all backlit fibres, including those disabled, needed for FVC
        exppos = (self.ptlm.get_positions(return_coord='QS')
                  .sort_values(by='DEVICE_ID'))
        exp_obsXY = (self.ptlm.get_positions(return_coord='obsXY')
                     .sort_values(by='DEVICE_ID')[['X1', 'X2']]).values.T
        # get guessed QS (theta centres in QS) for FVC measurement
        ret = self.ptlm.get_pos_vals(['OFFSET_X', 'OFFSET_Y'],
                                    posids=sorted(list(exppos['DEVICE_ID'])))
        if isinstance(ret, dict):
            dflist = []
            for d in ret.items():
                dflist.append(d)
            df = pd.concat(dflist).set_index('DEVICE_ID').sort_index()
        else:
            df = ret.set_index('DEVICE_ID').sort_index()
        offXY = df[['OFFSET_X', 'OFFSET_Y']].values.T
        # Just use one petal for ptltrans
        a_ptl = list(self.ptlm.Petals.keys())
        hom_QS = self.ptlm.ptltrans('flatXY_to_QS', offXY, participating_petals=a_ptl)  # 2xN array
        hom_obsXY = self.ptlm.ptltrans('QS_to_obsXYZ', hom_QS, participating_petals=a_ptl)[:2]  # 3xN array
        # set nominal homed QS as expected postiions for FVC spotmatch
        exppos[['X1', 'X2']] = hom_QS.T
        self.printfunc('Taking FVC exposure to confirm home positions...')
        exppos, meapos, matched, unmatched = self.fvc_measure(exppos=exppos,
                                                        match_radius=30)
        unmatched = set(unmatched).intersection(set(self.posids))
        matched = set(matched).intersection(set(self.posids))
        umstr = f':\n{sorted(unmatched)}' if len(unmatched) > 0 else ''
        self.printfunc(f'{len(unmatched)} selected positioners not matched'
                       + umstr)
        for col in ['exp_obsX', 'hom_obsX', 'mea_obsX',
                    'exp_obsY', 'hom_obsY', 'mea_obsY']:
            meapos[col] = np.nan
        for col in meapos.columns:
            exppos.loc[meapos.index, col] = meapos[col]
        exppos[['exp_obsX', 'exp_obsY']] = exp_obsXY.T  # internally tracked
        exppos[['hom_obsX', 'hom_obsY']] = hom_obsXY.T
        mea_obsXY = self.ptlm.ptltrans('QS_to_obsXYZ',
                                      meapos[['Q', 'S']].values.T,
                                      participating_petals=a_ptl)[:2]
        exppos.loc[meapos.index, ['mea_obsX', 'mea_obsY']] = mea_obsXY.T
        exppos['obsdX'] = exppos['mea_obsX'] - exppos['hom_obsX']
        exppos['obsdY'] = exppos['mea_obsY'] - exppos['hom_obsY']
        exppos['dr'] = np.linalg.norm(exppos[['obsdX', 'obsdY']], axis=1)
        # filter out only the selected positioners and drop duplicate col
        exppos = exppos.loc[self.posids].drop(
            columns=['PETAL_LOC', 'DEVICE_LOC'], errors='ignore')
        # add can bus ids
        retcode = self.ptlm.get_positioners(enabled_only=True,
                                                posids=exppos.index)
        if isinstance(retcode, dict):
            dflist = []
            for d in retcode.items():
                dflist.append(d)
            device_info = pd.concat(dflist).set_index('DEVICE_ID').sort_index()
        else:
            device_info = retcode.set_index('DEVICE_ID').sort_index()
        exppos = exppos.join(device_info)
        tol = 1
        # now only consider matched, selected positioners, check deviations
        mask = exppos.index.isin(matched) & (exppos['dr'] > tol)
        print_df = exppos[mask].sort_values(by='dr', ascending=False)
        bad_posids = sorted(print_df.index)
        if len(bad_posids) == 0:
            self.printfunc(
                f'All {len(matched)} matched fibres verified to have rehomed, '
                f'with tolerance dr = √(dX² + dY²) ≤ {tol} mm.')
        else:
            self.printfunc(f'{len(bad_posids)} positioners not rehomed '
                           f'properly (√(dX² + dY²) > {tol} mm):\n\n'
                           f'{print_df}\n\n'
                           f'Positioner IDs for retry:\n{bad_posids}')
        return exppos


if __name__ == '__main__':
    RehomeVerify(interactive=True)
