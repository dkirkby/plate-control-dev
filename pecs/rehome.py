'''
Runs a one_point_calibration through petal and fvc proxies.
Needs running DOS instance. See pecs.py
'''
import os
import numpy as np
import pandas as pd
from pecs import PECS
# import pandas as pd
# from DOSlib.positioner_index import PositionerIndex
from seed_xy_offsets import XY_Offsets
import posconstants as pc


class Rehome(PECS):

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

    def rehome(self, posids=None, anticollision='freeze', attempt=0):
        # three atetmpts built in, two with ac freeze, one with ac None
        if posids is None:
            posids = self.posids
        self.printfunc(f'Attempt {attempt}, rehoming {len(posids)} '
                       f'positioners with anticollision: {anticollision} ')
        ptl = self.ptls[self.ptlid]
        ret = (ptl.rehome_pos(posids, axis=self.axis,
                              anticollision=anticollision)
               .rename(columns={'X1': 'posT', 'X2': 'posP'}))
        mask = ret['FLAG'] != 4
        retry_list = list(ret['DEVICE_ID'][mask])
        if len(retry_list) == 0:
            self.printfunc(f'Rehoming sucessful for all positioners.')
        else:  # non-empty list, need another attempt
            self.printfunc(f'{len(retry_list)} unsucessful: {retry_list}\n'
                           f'{ret.loc[mask].to_string()}\nRetrying...')
            if attempt < 2:
                if attempt == 0:  # set anticollision mode for 2nd attempt
                    ac = 'freeze'  # 2nd attempt ac mode
                elif attempt == 1:  # set anticollision mode for 3rd attempt
                    ac = None  # 3rd attempt ac mode
                attempt += 1
                self.rehome(retry_list, anticollision=ac, attempt=attempt)
            else:  # already at 3rd attempt. fail
                self.printfunc(f'3rd attempt did not complete successfully '
                               f'for positioners: {posids}')
        ret = ptl.get_positions(posids=self.posids, return_coord='obsXY')
        return ret.rename(columns={'X1': 'expectedX', 'X2': 'expectedY'})

    def compare_xy(self):
        ptl = self.ptls[self.ptlid]
        self.printfunc(f'Seeding XY offsets...')
        df = (XY_Offsets().seed_vals(selection=self.posids, auto_update=True)
              .sort_values(by='DEVICE_ID').reset_index())
        offsetX, offsetY = df['OFFSET_X'], df['OFFSET_Y']
        q = np.degrees(np.atan2(offsetY, offsetX))  # convert offsetXY to QS
        r = np.sqrt(np.square(offsetX) + np.square(offsetY))
        s = pc.R2S_lookup(r)  # convert offsetXY to QS
        expected_pos = ptl.get_positions(posids=self.posids, return_coord='QS')
        expected_pos['X1'], expected_pos['X2'] = q, s
        # take FVC measurement
        mr_old = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=80)  # set larger radius for calib
        measured_QS = (pd.DataFrame(self.fvc.measure(expected_pos))
                       .rename(columns={'id': 'DEVICE_ID'}))
        measured_QS.columns = measured_QS.columns.str.upper()
        self.fvc.set(match_radius=mr_old)  # restore old radius
        # convert QS to obsXY
        Q_rad = np.radians(measured_QS['Q'])
        R = pc.S2R_lookup(measured_QS['S'])
        expected_pos['measuredX'] = R * np.cos(Q_rad)
        expected_pos['measuredY'] = R * np.sin(Q_rad)
        expected_pos.rename(columns={'X1': 'expectedX', 'X2': 'expectedY'},
                            inplace=True)
        expected_pos['delta_obsX'] = (expected_pos['measuredX']
                                      - expected_pos['expectedX'])
        expected_pos['delta_obsY'] = (expected_pos['measuredY']
                                      - expected_pos['expectedY'])
        expected_pos['delta_r'] = (np.sqrt(
            np.square(expected_pos['delta_obsX'])
            + np.square(expected_pos['delta_obsY'])))
        return expected_pos.sort_values(by='delta_r').reset_index()

    def rehome_and_verify(self, posids=None):
        self.rehome(posids)
        self.printfunc('Taking FVC exposure to confirm home positions...')
        posdf = rh.compare_xy()
        posdf.to_csv(os.path.join(
            pc.dirs['all_logs'], 'calib_logs',
            f'{pc.filename_timestamp_str_now()}-rehome.csv'))
        mask = posdf['delta_r'] > 2
        posids = list(posdf[mask]['DEVICE_ID'])
        if len(posids) == 0:
            self.printfunc('All successful and verified to match measurement.')
            return True
        else:
            self.printfunc(f"Possibly not rehomed sucessfully "
                           "(radial deviations > 2 mm):\n{posdf[mask]}")
            retry = input(f'Rehome the above {len(posids)} posids again?'
                          f'\n(y/n): ')
            if retry == 'y':
                self.rehome_and_verify(posids=posids)
            else:
                self.printfunc(f'Deviations > 2 mm remain. Exiting.')
                return False


if __name__ == '__main__':
    warning = input(
        'WARNING: this script will drive positioners to their hardstops. '
        'Be sure you know what you are doing! (Enter to continue)')
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by '
                      'spaces. Leave blank to use all on petal: ')
    if user_text != '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    user_text = input('Please provide axis (both, theta_only, phi_only): ')
    if user_text not in ['both', 'theta_only', 'phi_only']:
        raise Exception('Invalid input!')
    rh = Rehome(selection=selection, axis=user_text)
    df = rh.rehome_and_verify()
