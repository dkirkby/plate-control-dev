# -*- coding: utf-8 -*-
"""
Created on Tue Jul 16 14:04:52 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""

import os
import numpy as np
from pecs import PECS
import posconstants as pc


class RehomeVerify(PECS):

    def __init__(self, fvc=None, ptls=None,
                 petal_id=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptls=ptls)
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_id, posids)
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
        exppos = (self.ptl.get_positions(return_coord='QS')
                  .sort_values(by='DEVICE_ID'))
        exp_obsXY = (self.ptl.get_positions(return_coord='obsXY')
                     .sort_values(by='DEVICE_ID')[['X1', 'X2']]).values.T
        # get guessed QS (theta centres in QS) for FVC measurement
        df = (self.ptl.get_pos_vals(['OFFSET_X', 'OFFSET_Y'],
                                    posids=sorted(list(exppos['DEVICE_ID'])))
              .set_index('DEVICE_ID'))  # indexed by DEVICE_ID
        offXY = df[['OFFSET_X', 'OFFSET_Y']].values.T
        hom_QS = self.ptl.ptltrans('flatXY_to_QS', offXY)  # 2xN array
        hom_obsXY = self.ptl.ptltrans('QS_to_obsXYZ', hom_QS)[:2]  # 3xN array
        # set nominal homed QS as expected postiions for FVC spotmatch
        exppos[['X1', 'X2']] = hom_QS.T
        self.printfunc('Taking FVC exposure to confirm home positions...')
        exppos, meapos, _, unmatched = self.fvc_measure(exppos=exppos,
                                                        match_radius=30)
        unmatched = set(unmatched).intersection(set(self.posids))
        umstr = f':\n{unmatched}' if len(unmatched) > 0 else ''
        self.printfunc(f'{len(unmatched)} selected positioners unmatched'
                       + umstr)
        for col in ['exp_obsX', 'hom_obsX', 'mea_obsX',
                    'exp_obsY', 'hom_obsY', 'mea_obsY']:
            meapos[col] = np.nan
        for col in meapos.columns:
            exppos.loc[meapos.index, col] = meapos[col]
        exppos[['exp_obsX', 'exp_obsY']] = exp_obsXY.T  # internally tracked
        exppos[['hom_obsX', 'hom_obsY']] = hom_obsXY.T
        mea_obsXY = self.ptl.ptltrans('QS_to_obsXYZ',
                                      meapos[['Q', 'S']].values.T)[:2]
        exppos.loc[meapos.index, ['mea_obsX', 'mea_obsY']] = mea_obsXY.T
        exppos['obsdX'] = exppos['mea_obsX'] - exppos['hom_obsX']
        exppos['obsdY'] = exppos['mea_obsY'] - exppos['hom_obsY']
        exppos['dr'] = np.linalg.norm(exppos[['obsdX', 'obsdY']], axis=1)
        # filter out only the selected positioners and drop duplicate col
        exppos = exppos.loc[self.posids].drop(
            columns=['PETAL_LOC', 'DEVICE_LOC'], errors='ignore')
        # add can bus ids
        device_info = (self.ptl.get_positioners(enabled_only=True,
                                                posids=exppos.index)
                       .set_index('DEVICE_ID'))
        exppos = exppos.join(device_info)
        tol = 1
        mask = exppos['dr'] > tol
        print_df = exppos[mask].sort_values(by='dr', ascending=False)
        bad_posids = sorted(print_df.index)
        if len(bad_posids) == 0:
            self.printfunc(
                f'All {len(exppos)} matched fibres verified to have rehomed, '
                f'with tolerance dr = √(dX² + dY²) ≤ {tol} mm.')
        else:
            self.printfunc(f'{len(bad_posids)} positioners not rehomed '
                           f'properly (√(dX² + dY²) > {tol} mm):\n\n'
                           f'{print_df}\n\n'
                           f'Positioner IDs for retry:\n{bad_posids}')
        return exppos


if __name__ == '__main__':
    RehomeVerify(interactive=True)
