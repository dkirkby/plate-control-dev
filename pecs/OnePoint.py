'''
OnePoint.py - contains OnePoint class
Run OnePoint_posTP.py and OnePoint_offsetsTP.py scripts for calibration
'''
import os
import pandas as pd
import posconstants as pc
from pecs import PECS

class OnePointCalib(PECS):
    '''mode is in posTP, offsetsTP, or both
    subclass of PECS that adds functions to run a OnePoint calibration.
    In the future: add methods to display, judge and analyze calibration.
    '''
    def __init__(self, fvc=None, ptls=None, mode='posTP',
                 pcid=None, posids=None, interactive=False,
                 tp_target='default',auto_update=True, match_radius=80.0):
        super().__init__(fvc=fvc, ptls=ptls)
        self.printfunc(f'Running 1p calibration, mode = {mode}')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(pcid, posids)
        self.poslocP = 135  # phi arm angle for 1 point calibration
        updates = self.calibrate(mode=mode, interactive=interactive,
                                 tp_target=tp_target, auto_update=auto_update,
                                 match_radius=match_radius)
        # save results
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-1p_calibration-{mode}.csv')
        updates.to_csv(path)
        self.printfunc(  # preview calibration updates
            updates[['POS_T', 'POS_P', 'dT', 'dP', 'OFFSET_T', 'OFFSET_P']])
        self.printfunc(f'Seed offsets TP data saved to: {path}')
        if interactive:
            if self._parse_yn(input(
                    'Open 1p calibration data table? (y/n): ')):
                os.system(f'xdg-open {path}')

    def calibrate(self, mode='posTP', tp_target='default',
                  auto_update=True, match_radius=80.0, interactive=False):
        if interactive:
            user_text = self._parse_yn(
                input('Do you want to move positioners? (y/n): '))
            if user_text:
                tp_target = 'default'
            else:
                tp_target = None
            auto_update = self._parse_yn(input(
                    'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                'Please provide a spotmatch radius: '))
            return self.calibrate(mode=mode, tp_target=tp_target,
                                  auto_update=auto_update,
                                  match_radius=match_radius)
        do_move = True
        if tp_target == 'default':  # tp_target as target
            poslocTP = (0.0, self.poslocP)  # same target for all posids
        elif isinstance(tp_target, (tuple, list)) and len(tp_target) == 2:
            poslocTP = tp_target
        else:
            do_move = False
        rows = []
        if do_move:  # then build requests and make the moves
            for posid in self.posids:
                posintTP = self.ptl.postrans(posid,
                                             'poslocTP_to_posintTP', poslocTP)
                rows.append({'DEVICE_ID': posid,
                             'COMMAND': 'posintTP',
                             'X1': posintTP[0],
                             'X2': posintTP[1],
                             'LOG_NOTE': f'One point calibration {mode}'})
            requests = pd.DataFrame(rows)
            self.ptl.prepare_move(requests, anticollision=None)
            self.ptl.execute_move()
        else:  # then use current position as targets in requests
            requests = self.ptl.get_positions(posids=self.posids,
                                              return_coord='posintTP')
        exppos, meapos, matched, unmatched = self.fvc_measure(
                match_radius=match_radius)
        used_pos = meapos.loc[sorted(matched & (set(self.posids)))]
        unused_pos = exppos.loc[sorted(unmatched & (set(self.posids)))]
        updates = (
            self.ptl.test_and_update_TP(
                used_pos.reset_index(), mode=mode, auto_update=auto_update,
                tp_updates_tol=0.0, tp_updates_fraction=1.0)
            .set_index('DEVICE_ID').sort_index())
        cols = used_pos.columns.difference(updates.columns)
        updates = updates.join(used_pos[cols])  # include QS measurements
        # List unmeasured positioners in updates, even with no data
        updates.append(unused_pos, sort=False)
        # overwrite flags with focalplane flags and add status
        updates['FLAGS'] = self.ptl.get_pos_flags(list(updates.index))
        updates['STATUS'] = self.ptl.decipher_posflags(updates['FLAG'])
        # Clean up and record additional entries in updates
        updates['auto_update'] = auto_update
        updates['target_t'] = requests.set_index('DEVICE_ID')['X1']
        updates['target_p'] = requests.set_index('DEVICE_ID')['X2']
        return updates

    # def set_calibration(self, posids=None, reset=False,
    #                     avoid_big_changes=True):
    #     '''
    #     calls set_calibration function in petalApp

    #     allows a filter on posids using the posids kwarg
    #     if reset, the calibration values will reset to their old values
    #     if avoid_big_changes petalApp will avoid setting widly different
    #     values
    #     '''
    #     assert self.data is not None, 'Must have data to set!'
    #     assert self.ptl is not None, 'Must set an active petal!'
    #     if posids is not None:
    #         calib_df = self.data.loc[sorted(posids)]
    #     else:
    #         calib_df = self.data
    #     if reset:
    #         tag = '_OLD'
    #     else:
    #         tag = ''
    #     self.ptl.set_calibration(calib_df, tag=tag,
    #                              avoid_big_changes=avoid_big_changes)
