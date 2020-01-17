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
from petaltransforms import PetalTransforms


class RehomeVerify(PECS):

    def __init__(self, fvc=None, ptlm=None,
                 petal_roles=None, posids=None, interactive=False):
        super().__init__(fvc=fvc, ptlm=ptlm, interactive=interactive)

    def compare_xy(self):
        self.printfunc(f'Verifying home positions for '
                       f'{len(self.posids)} positioners...')
        # all backlit fibres, including those disabled, needed for FVC
        import pdb; pdb.set_trace()
        exppos = (self.ptlm.get_positions(return_coord='QS')
                  .sort_values(by='DEVICE_ID'))
        exp_obsXY = (self.ptlm.get_positions(return_coord='obsXY')
                     .sort_values(by='DEVICE_ID')[['X1', 'X2']]).values.T
        # get guessed QS (theta centres in QS) for FVC measurement
        ret = self.ptlm.get_pos_vals(['OFFSET_X', 'OFFSET_Y'],
                                     posids=exppos['DEVICE_ID'])
        for role, df in ret.items():
            home = self.ptlm.ptltrans('flatXY_to_QS',
                                      df[['OFFSET_X', 'OFFSET_Y']].values.T,
                                      participating_petals=role)[role]
            df['HOME_Q'], df['HOME_S'] = home[0], home[1]
        df = pd.concat(list(ret.values())).set_index('DEVICE_ID').sort_index()
        hom_QS = df[['HOME_Q', 'HOME_S']].T
        hom_obsXY = PetalTransforms.QS_to_obsXY(hom_QS)  # 2xN array
        # set nominal homed QS as expected postiions for FVC spotmatch
        exppos[['X1', 'X2']] = hom_QS.T.values
        # make sure no fiducial ID is in exppos DEVICE_ID column
        if np.any(['P' in device_id for device_id in exppos['DEVICE_ID']]):
            raise Exception('Expected positions of positioners by PetalApp '
                            'are contaminated by fiducials.')
        self.printfunc('Taking FVC exposure to confirm home positions...')
        exppos, meapos, matched, unmatched = self.fvc_measure(exppos=exppos,
                                                              match_radius=50)
        unmatched = unmatched & (set(self.posids))
        matched = matched & (set(self.posids))
        if len(unmatched) > 0:
            self.printfunc(f'{len(unmatched)} selected positioners not '
                           f'matched: :\n{sorted(unmatched)}')
        for col in ['exp_obsX', 'hom_obsX', 'mea_obsX',
                    'exp_obsY', 'hom_obsY', 'mea_obsY']:
            meapos[col] = np.nan
        for col in meapos.columns:
            exppos.loc[meapos.index, col] = meapos[col]
        exppos[['exp_obsX', 'exp_obsY']] = exp_obsXY.T  # internally tracked
        exppos[['hom_obsX', 'hom_obsY']] = hom_obsXY.T
        exppos.loc[meapos.index, ['mea_obsX', 'mea_obsY']] = (
            PetalTransforms.QS_to_obsXY(meapos[['Q', 'S']].values.T).T)
        exppos['obsdX'] = exppos['mea_obsX'] - exppos['hom_obsX']
        exppos['obsdY'] = exppos['mea_obsY'] - exppos['hom_obsY']
        exppos['dr'] = np.linalg.norm(exppos[['obsdX', 'obsdY']], axis=1)
        # filter out only the selected positioners and drop duplicate col
        exppos = exppos.loc[self.posids].drop(
            columns=['PETAL_LOC', 'DEVICE_LOC'], errors='ignore')
        # add can bus ids
        df_info = pd.concat(list(self.ptlm.get_positioners(
            enabled_only=True, posids=exppos.index).values()))
        df_info = df_info.set_index('DEVICE_ID').sort_index()
        cols = df_info.columns.difference(exppos.columns)
        exppos = exppos.join(df_info[cols])
        # overwrite flags with focalplane flags and add status
        flags = [pd.DataFrame.from_dict(  # device_id in dict becomes index
                     flags_dict, orient='index', columns=['FLAG'])
                 for flags_dict in self.ptlm.get_pos_flags().values()]
        exppos['FLAG'] = pd.concat(flags)
        exppos['STATUS'] = pc.decipher_posflags(exppos['FLAG'])
        tol = 1
        # now only consider matched, selected positioners, check deviations
        mask = exppos.index.isin(matched) & (exppos['dr'] > tol)
        print_df = (exppos[mask].sort_values(by='dr', ascending=False)
                    [['dr', 'BUS_ID', 'DEVICE_LOC', 'PETAL_LOC', 'STATUS']])
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
    rv = RehomeVerify(interactive=True)
    df = rv.compare_xy()
    path = os.path.join(pc.dirs['calib_logs'],
                        f'{pc.filename_timestamp_str()}-rehome_verify.csv')
    df.to_csv(path)
    print(f'Rehome verification data saved to: {path}')
