'''
Runs a one_point_calibration through petal and fvc proxies.
Needs running DOS instance. See pecs.py
'''
import os
from pecs import PECS
import pandas as pd
from DOSlib.positioner_index import PositionerIndex
import posconstants as pc


class OnePoint(PECS):

    def __init__(self, petal_id=None, platemaker_instrument=None,
                 fvc_role=None, printfunc=print):
        PECS.__init__(self, ptlids=petal_id, fvc_role=fvc_role,
                      platemaker_instrument=platemaker_instrument,
                      printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]
        self.index = PositionerIndex()

    def one_point_calib(self, selection=None, enabled_only=True, mode='posTP',
                        auto_update=True, tp_target='default',
                        match_radius=80.0):
        ptl = self.ptls[self.ptlids[0]]
        if selection is None:
            posids = list(ptl.get_positioners(
                enabled_only=enabled_only)['DEVICE_ID'])
        elif 'can' in selection[0]:  # User passed a list of canids
            posids = list(ptl.get_positioners(
                enabled_only=enabled_only, busids=selection)['DEVICE_ID'])
        else:  # assume is a list of posids
            posids = selection
        if tp_target == 'default':  # use (0, 107) as target, move positioners
            targets = {0: [0] * len(posids),  # 0 for theta, 1 for phi
                       1: [self.Eo_phi+self.clear_angle_margin] * len(posids)}
            if mode in ['offsetT', 'offsetP']:  # move this axis only
                axis = (['offsetT', 'offsetP'].index(mode) + 1) % 2  # keep it
                ret = ptl.get_positions(posids=posids, return_coord='obsTP')
                targets[axis] = list(ret['X'+str(axis+1)])  # copy current pos
                mode = 'offsetsTP'  # for updating purposes, after targets set
            elif mode in ['offsetsTP', 'posTP']:
                pass  # use default targets for all, move both axes
            else:
                raise Exception('Invalid input 1P calibration mode')
            rows = []
            for i, posid in enumerate(posids):
                row = {'DEVICE_ID': posid,
                       'COMMAND': 'obsTP',
                       'X1': targets[0][i],
                       'X2': targets[1][i],
                       'LOG_NOTE': f'One point calibration {mode}'}
                rows.append(row)
            ptl.prepare_move(pd.DataFrame(rows), anticollision=None)
            expected_pos = ptl.execute_move()
        else:  # don't move, just use current position
            expected_pos = ptl.get_positions()
        # expected_pos.to_csv('test.csv')
        old_radius = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=match_radius)  # set larger radius for calib
        measured_pos = (pd.DataFrame(self.fvc.measure(expected_pos))
                        .rename(columns={'id': 'DEVICE_ID'}))
        measured_pos.columns = measured_pos.columns.str.upper()
        self.fvc.set(match_radius=old_radius)  # restore old radius
        used_pos = measured_pos[measured_pos['DEVICE_ID'].isin(posids)]
        updates = ptl.test_and_update_TP(
            used_pos, tp_updates_tol=0.0, tp_updates_fraction=1.0,
            tp_updates=mode, auto_update=auto_update)
        updates['auto_update'] = auto_update
        target_t, target_p = [], []
        for i, posid in enumerate(posids):
            if posid in used_pos['DEVICE_ID'].values:
                target_t.append(targets[0][i])
                target_p.append(targets[1][i])
            else:  # was not measured by FVC and ommited in the return
                pass  # skip this posid because length is shorted by Nunmatched
        updates['target_t'] = target_t
        updates['target_p'] = target_p
        updates['enabled_only'] = enabled_only
        return updates


if __name__ == '__main__':
    op = OnePoint()
    user_text = input(
        'Please list BUSIDs or POSIDs (not both) seperated by spaces, '
        'leave it blank to use all on petal: ')
    if user_text == '':
        selection = None
    else:
        selection = [item for item in user_text.split()]
    user_text = input(
        'Please provide calibration mode, valid options are\n'
        '\t offsetsTP, offsetT, offsetP, posTP\n'
        '(leave blank for posTP): ')
    if user_text == '':
        mode = 'posTP'
    else:
        mode = user_text
    updates = op.one_point_calib(selection=selection, mode=mode)
    print(updates)
    updates.to_csv(os.path.join(
        pc.dirs['all_logs'], 'calib_logs',
        f'{pc.filename_timestamp_str_now()}-onepoint_calibration-{mode}.csv'))
