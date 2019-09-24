import os
import pandas as pd
import posconstants as pc
from pecs import PECS


class OnePoint(PECS):

    def __init__(self, petal_id=None, posids=None, mode='posTP',
                 interactive=False):
        super().__init__()
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(petal_id, posids)
        self.poslocP = 135  # phi arm angle for 1 point calibration
        self.one_point_calib(mode=mode, interactive=interactive)

    def one_point_calib(self, mode='posTP', tp_target='default',
                        auto_update=True, match_radius=80.0,
                        interactive=False):
        if interactive:
            if mode is None:  # Ask for mode
                mode = input('Please enter one point calibration mode '
                             '(posTP/offsetsTP/both): ')
                if mode not in ['posTP', 'offsetsTP', 'both']:
                    mode = input('Invalid entry, please try again.')
            if tp_target is None:  # Ask for tp_target
                user_text = self._parse_yn(
                    input('Do you want to move positioners? (y/n): '))
                if user_text:
                    tp_target = 'default'
                else:
                    tp_target = None
            if auto_update is None:  # Ask for auto_update
                auto_update = self._parse_yn(
                    input('Automatically update positioner calibration? '
                          '(y/n): '))
            if match_radius is None:  # Ask for match_radius
                match_radius = input('Enter the match_radius for spotmatch: ')
            self.one_point_calib(mode=mode, tp_target=tp_target,
                                 auto_update=auto_update,
                                 match_radius=match_radius)
        # build move requests
        rows = []
        for posid in self.posids:
            if tp_target == 'default':  # tp_target as target
                poslocTP = (0.0, self.poslocP)  # same target for all posids
            elif ((isinstance(tp_target, tuple) or isinstance(tp_target, list))
                  and len(tp_target) == 2):
                poslocTP = tp_target
            else:  # don't move, just use current position
                poslocTP = self.ptl.expected_current_position(posid,
                                                              'poslocTP')
            posintTP = self.ptl.postrans(posid,
                                         'poslocTP_to_posintTP', poslocTP)
            row = {'DEVICE_ID': posid,
                   'COMMAND': 'posintTP',
                   'X1': posintTP[0],
                   'X2': posintTP[1],
                   'LOG_NOTE': f'One point calibration {mode}'}
            rows.append(row)
        requests = pd.DataFrame(rows)
        self.ptl.prepare_move(requests, anticollision=None)
        self.ptl.execute_move()
        exppos, meapos, matched, unmatched = self.fvc_measure()
        used_pos = meapos.loc[sorted(list(matched))]  # only matched rows
        unused_pos = meapos.loc[sorted(list(unmatched))]
        updates = (
            self.ptl.test_and_update_TP(
                used_pos.reset_index(), mode=mode, auto_update=auto_update,
                tp_updates_tol=0.0, tp_updates_fraction=1.0)
            .set_index('DEVICE_ID').sort_index())
        # Drop QS so we don't get columns QS in updates with NaNs
        unused_pos.drop(['Q', 'S'], axis=1)
        # List unmeasured positioners in updates, even with no data
        updates.append(unused_pos, ignore_index=True, sort=False)
        # Clean up and record additional entries in updates
        updates['auto_update'] = auto_update
        updates['target_t'] = requests.set_index('DEVICE_ID')['X1']
        updates['target_p'] = requests.set_index('DEVICE_ID')['X2']
        # save results
        path = (os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-1p_calibration-{mode}.csv'))
        updates.to_csv(path)
        self.printfunc(updates[['POS_T', 'POS_P', 'dT', 'dP',
                                'OFFSET_T', 'OFFSET_P']])
        if input('Open 1p calibration data table? (y/n): ') in ['y', 'yes']:
            os.system(f'xdg-open {path}')
