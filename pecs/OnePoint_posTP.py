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
        self.obsP = 135 # phi_close angle in posmovemeasure
        self.ptlid = list(self.ptls.keys())[0]
        self.index = PositionerIndex()

    def one_point_calib(self, selection=None, enabled_only=True, mode='posTP',
                        auto_update=True, tp_target='default',
                        match_radius=80.0):
        ptl = self.ptls[self.ptlids[0]]
        # Interpret selection, decide what positioner to use
        if selection is None: 
            posids = list(ptl.get_positioners(
                enabled_only=enabled_only)['DEVICE_ID'])
        elif 'can' in selection[0]:  # User passed a list of canids
            posids = list(ptl.get_positioners(
                enabled_only=enabled_only, busids=selection)['DEVICE_ID'])
        else:  # assume is a list of posids
            posids = selection
        # Interpret tp_target and move if target != None
        offsetPs = {}
        if tp_target == 'default':  # use (0, self.obsP to posP) as target
            rows = []
            for posid in posids:
                offsetP = ptl.get_posfid_val(posid, 'OFFSET_P')
                offsetPs[posid] = offsetP
                tp_target = [0.0,self.obsP]
                row = {'DEVICE_ID': posid,
                       'COMMAND': 'posTP',
                       'X1': 0.0,
                       'X2': self.obsP - offsetP, #conversion obsP to posP as in posmovemeasure
                       'LOG_NOTE': f'One point calibration {mode}'}
                rows.append(row)
            ptl.prepare_move(pd.DataFrame(rows), anticollision=None)
            expected_pos = ptl.execute_move()
        elif isinstance(tp_target, list):
            row = []
            for posid in posids:
                offsetP = ptl.get_posfid_val(posid, 'OFFSET_P')
                offsetPs[posid] = offsetP
                row = {'DEVICE_ID': posid,
                       'COMMAND': 'posTP',
                       'X1': tp_target[0],
                       'X2': tp_target[1] - offsetP, #conversion obsP to posP as in posmovemeasure
                       'LOG_NOTE': f'One point calibration {mode}'}
                rows.append(row)
            ptl.prepare_move(pd.DataFrame(rows), anticollision=None)
            expected_pos = ptl.execute_move()
        else:  # don't move, just use current position
            expected_pos = ptl.get_positions()
        # Prepare FVC and measure targets
        old_radius = self.fvc.get('match_radius')  # hold old radius
        self.fvc.set(match_radius=match_radius)  # set larger radius for calib
        measured_pos = (pd.DataFrame(self.fvc.measure(expected_pos,matched_only=True))
                        .rename(columns={'id': 'DEVICE_ID'}))
        measured_pos.columns = measured_pos.columns.str.upper()
        self.fvc.set(match_radius=old_radius)  # restore old radius
        used_pos = measured_pos[measured_pos['DEVICE_ID'].isin(posids)] #filter only selected positioners
        # Do analysis with test_and_update_TP
        updates = ptl.test_and_update_TP(
            used_pos, tp_updates_tol=0.0, tp_updates_fraction=1.0,
            tp_updates=mode, auto_update=auto_update)
        # Clean up and record additional entries in updates
        updates['auto_update'] = auto_update
        target_t, target_p = [], []
        for posid in posids:
            if posid in matched_used_pos['DEVICE_ID'].values:
                try: #ask for forgiveness later
                    target_t.append(tp_target[0])
                    target_p.append(tp_target[1] - offsetPs[posid])
                except:
                    target_t = tp_target #Positioners weren't moved so
                    target_p = tp_target #tp_target is not 'default' or a list
                    break
            else:  # was not measured by FVC and ommited in the return
                pass  # skip this posid because length is shorted by Nunmatched
        updates['target_t'] = target_t
        updates['target_p'] = target_p
        updates['enabled_only'] = enabled_only
        unmatched = set(posids) - set(updates['DEVICE_ID'])
        print(f'Missing {len(unmatched)} of the selected positioners:\n{unmatched}')
        unmatched_used_pos.drop(['Q','S'],axis=1) #Drop QS so we don't get columns QS in updates with NaNs
        updates.append(unmatched_used_pos,ignore_index=True) #List unmeasured positioners in updates, even with no data
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
    user_text = input('Do you want to move positioners? (y/n) ')
    if 'y' in user_text:
        tp_target = 'default'
    else:
        tp_target = None
    user_text = input('Automatically update calibration? (y/n) ')
    if 'y' in user_text:
        auto_update = True
    else:
        auto_update = False
    updates = op.one_point_calib(selection=selection, mode='posTP',
                                 auto_update=auto_update, tp_target=tp_target)
    updates.to_csv(os.path.join(
        pc.dirs['all_logs'], 'calib_logs',
        f'{pc.filename_timestamp_str_now()}-onepoint_calibration-posTP.csv'))
    print(updates[['DEVICE_ID','POS_T','POS_P','dT','dP']])
