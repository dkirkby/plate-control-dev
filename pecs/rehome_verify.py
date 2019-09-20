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

    def __init__(self, petal_id=None, posids=None, interactive=False):
        super().__init__()
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_id, posids)
        self.printfunc(f'Verifying homing positions for '
                       f'{len(self.posids)} positioners...')
        df = self.compare_xy()
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-rehome_verify.csv')
        df.to_csv(path)
        self.printfunc(f'Rehome verification data saved to: {path}')
        if input('Open verification table? (y/n): ') in ['y', 'yes']:
            os.system(f'xdg-open {path}')

    def compare_xy(self):
        ptl = self.ptls[self.ptlid]
        # all backlit fibres, including those disabled, needed for FVC
        exppos = (ptl.get_positions(return_coord='QS')
                  .sort_values(by='DEVICE_ID'))
        exp_obsXY = (ptl.get_positions(return_coord='obsXY')
                     .sort_values(by='DEVICE_ID')[['X1', 'X2']]).values.T
        # get guessed QS (theta centres in QS) for FVC measurement
        df = (ptl.get_pos_vals(['OFFSET_X', 'OFFSET_Y'],  # offsets in flatXY
                               posids=sorted(list(exppos['DEVICE_ID'])))
              .set_index('DEVICE_ID'))  # indexed by DEVICE_ID
        offXY = df[['OFFSET_X', 'OFFSET_Y']].values.T
        hom_QS = ptl.ptltrans('flatXY_to_QS', offXY)  # 2xN array
        hom_obsXY = ptl.ptltrans('QS_to_obsXY', hom_QS)  # 2xN array
        # set nominal homed QS as expected postiions for FVC spotmatch
        exppos[['X1', 'X2']] = hom_QS.T
        self.printfunc('Taking FVC exposure to confirm home positions...')
        mr_old = self.fvc.get('match_radius')  # hold old match radius
        self.fvc.set(match_radius=80)  # set larger radius for calib
        # measured_QS, note that expected_pos was changed in place
        meapos = (
            pd.DataFrame(self.fvc.measure(exppos))
            .rename(columns={'id': 'DEVICE_ID'})
            .set_index('DEVICE_ID').sort_index())  # indexed by DEVICE_ID
        self.fvc.set(match_radius=mr_old)  # restore old radius after measure
        meapos.columns = meapos.columns.str.upper()  # clean up header to save
        # find the posids that are unmatched, missing from FVC return
        unmatched = sorted(set(self.posids) - set(meapos.index))
        umstr = f':\n{unmatched}' if len(unmatched) > 0 else ''
        self.printfunc(f'{len(unmatched)} unmatched positioners' + umstr)
        # write columns to measured_QS using auto index matching
        meapos['FLAG'] = (exppos.set_index('id')
                          .loc[meapos.index]['flags'].values)
        meapos['STATUS'] = ptl.decipher_posflags(meapos['FLAG'])
        for col in ['exp_obsX', 'hom_obsX', 'mea_obsX',
                    'exp_obsY', 'hom_obsY', 'mea_obsY']:
            meapos[col] = np.nan
        meapos[['exp_obsX', 'exp_obsY']] = exp_obsXY.T  # internally tracked
        meapos[['hom_obsX', 'hom_obsY']] = hom_obsXY.T
        mea_obsXY = ptl.ptltrans('QS_to_obsXY', meapos[['Q', 'S']].values.T)
        meapos[['mea_obsX', 'mea_obsY']] = mea_obsXY.T
        meapos['obsdX'] = meapos['mea_obsX'] - meapos['hom_obsX']
        meapos['obsdY'] = meapos['mea_obsY'] - meapos['hom_obsY']
        meapos['dr'] = np.linalg.norm(meapos[['obsdX', 'obsdY']], axis=1)
        meapos = meapos.sort_values(by='dr', ascending=False).reset_index()
        mask = meapos['dr'] > 1
        bad_posids = list(meapos[mask].index)
        # self.printfunc(meapos)
        if len(bad_posids) == 0:
            self.printfunc(
                f'All {len(meapos)} matched fibres verified to have rehomed.')
        else:
            self.printfunc(f'{len(bad_posids)} positioners not '
                           f'rehomed (radial deviations > 1 mm) properly:\n\n'
                           f'{meapos[mask].iloc[:, ]}\n\n'
                           f'Positioner IDs:\n{bad_posids}')
        return meapos


if __name__ == '__main__':
    RehomeVerify(interactive=True)
