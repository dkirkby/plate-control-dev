'''
OnePoint.py - contains OnePoint class to run
OnePoint calibrations. See OnePoint_posTP.py or
OnePoint_offsetsTP.py for example usage.
'''
import os
import pandas as pd
import posconstants as pc
from pecs import PECS


class OnePoint(PECS):
    '''
    OnePoint
    subclass of PECS that adds functions to run a OnePoint
    calibration. Also contains method to interactively run
    a OnePoint calibration.

    In the future: add methods to display, judge and analyze
    calibration.
    '''

    def __init__(self, ptlids=None, printfunc=print,
                 platemaker_instrument=None, fvc_role=None,
                 illuminator_role=None, constants_version=None):
        super().__init__(ptlids=None, printfunc=print,
                         platemaker_instrument=None, fvc_role=None,
                         illuminator_role=None, constants_version=None)
        # defaul tphi arm angle for 1 point calibration
        self.poslocP = 135
        self.ptl = None
        self.ptlid = None
        self.posids = None
        self.data = None
        self.data_path = None

    def calibration(self, mode='posTP', tp_target='default',
                    auto_update=True, match_radius=80):
        '''
        Runs a OnePoint calibration. Sets/overwrites the data
        attribute with a new pandas.Dataframe.
        '''
        assert mode in ['posTP', 'offsetsTP'], 'Invalid mode!'
        assert self.ptl is not None, 'Must set petal!'
        assert self.posids is not None, 'Must set posids!'
        # build move requests
        rows = []
        move = True
        for posid in self.posids:
            if tp_target == 'default':  # tp_target as target
                poslocTP = (0.0, self.poslocP)  # same target for all posids
            elif (isinstance(tp_target, (tuple,list)) and len(tp_target) == 2):
                poslocTP = tp_target
            else:  # don't move, just use current position
                poslocTP = self.ptl.expected_current_position(posid,
                                                              'poslocTP')
                move = False
            posintTP = self.ptl.postrans(posid,
                                         'poslocTP_to_posintTP', poslocTP)
            row = {'DEVICE_ID': posid,
                   'COMMAND': 'posintTP',
                   'X1': posintTP[0],
                   'X2': posintTP[1],
                   'LOG_NOTE': f'One point calibration {mode}'}
            rows.append(row)
        requests = pd.DataFrame(rows)
        if move:
            self.ptl.prepare_move(requests, anticollision=None)
            exppos = self.ptl.execute_move()
        else:
            exppos = self.ptl.get_positions(return_coord='QS')
        exppos, meapos, matched, unmatched = self.fvc_measure(exppos=exppos,
                                                              match_radius=match_radius)
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
        # set data
        self.data = updates
        # save results
        self.data_path = (os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-1p_calibration-{mode}.csv'))
        updates.to_csv(self.data_path)
        self.printfunc(updates[['POS_T', 'POS_P', 'dT', 'dP',
                                'OFFSET_T', 'OFFSET_P']])

    def set_petal(self, petal_id=None):
        '''
        self.ptl/self.ptlid setter
        '''
        if petal_id is not None:
            assert petal_id not in self.ptlids, f'petal_id '\
            f'{petal_id} not in {self.ptlids}!'
        else:
            petal_id = self._interactively_get_ptl()
        self.ptlid = petal_id
        self.ptl = self.ptls[petal_id]

    def set_posids(self, posids=None):
        '''
        self.posids setter
        '''
        assert self.ptl is not None, 'Must call set_petal'
        if posids is not None:
            assert isinstance(posids, list) and \
            isinstance(posids[0], str), f'posids {posids} is invalid!'
        else:
            posids = self._interactively_get_posids(self.ptlid)
        self.posids = posids

    def set_data(self, filename=None):
        '''
        self.data/self.data_path setter
        '''
        if filename is None and self.data_path is not None:
            self.data = pd.from_csv(self.data_path, index_col=0)
        else:
            self.data = pd.from_csv(filename, index_col=0)


    def set_calibration(self, posids=None, reset=False, avoid_big_changes=True):
        '''
        calls set_calibration function in petalApp

        allows a filter on posids using the posids kwarg
        if reset, the calibration values will reset to their old values
        if avoid_big_changes petalApp will avoid setting widly different values
        '''
        assert self.data is not None, 'Must have data to set!'
        assert self.ptl is not None, 'Must set an active petal!'
        if posids is not None:
            calib_df = self.data.loc[sorted(posids)]
        else:
            calib_df = self.data
        if reset:
            tag = '_OLD'
        else:
            tag = ''
        self.ptl.set_calibration(calib_df, tag=tag,
                                 avoid_big_changes=avoid_big_changes)

    def run_interactively(self, petal=None, posids=None, mode=None,
                          tp_target=None, auto_update=None,
                          match_radius=None):
        '''
        Interactively walk through calibration
        '''
        self.printfunc('Running interactive OnePoint Calibration')
        if self.ptl is not None:
            if not self._parse_yn(input(f'Keep using petal {self.ptlid}? (y/n) ')):
                self.set_petal(petal)
        else:
            self.set_petal(petal)
        if self.posids is not None:
            if not self._parse_yn(input(f'Keep using posids {self.posids}? (y/n) ')):
                self.set_posids(posids)
        else:
            self.set_posids(posids)
        if mode is None:
            mode = input('Please enter the mode (posTP, offsetsTP): ')
        if auto_update is None:
            auto_update = self._parse_yn(input('Automatically update calibration? (y/n) '))
        if match_radius is None:
            match_radius = float(input('Please privide a spotmatch radius: '))
        self.calibration(mode, tp_target, auto_update, match_radius)
        if self._parse_yn(input('Open 1p calibration data table? (y/n): ')):
            os.system(f'xdg-open {self.data_path}')
