'''
Runs a one_point_calibration through petal and fvc proxies.
Needs running DOS instance. See pecs.py
'''
import os
from pecs import PECS
# import pandas as pd
# from DOSlib.positioner_index import PositionerIndex
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
               .rename(columns={'X1': 'posT', 'X2': 'posP'})
               .sort_values(by='DEVICE_ID').reset_index())
        mask = ret['FLAG'] != 4
        retry_list = list(ret['DEVICE_ID'][mask])
        if len(retry_list) == 0:
            self.printfunc(f'Rehoming sucessful for all positioners.')
        else:  # non-empty list, need another attempt
            self.printfunc(f'{len(retry_list)} unsucessful: {retry_list}\n'
                           f'{ret.loc[mask].reset_index().to_string()}\n'
                           f'Retrying...')
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
    df = rh.rehome()
    path = os.path.join(pc.dirs['all_logs'], 'calib_logs',
                        f'{pc.filename_timestamp_str_now()}-rehome.csv')
    df.to_csv(path)
    print(f'Rehome data saved to: {path}')
