'''
Runs an Arc Calibration using fvc and petal proxies.
Requires running DOS instance. See pecs.py
Currently only runs one Petal at a time, awaiting a petalMan proxy.

'''
import os
import pandas as pd
from ast import literal_eval
import posconstants as pc
from pecs import PECS

class Arc(PECS):
    '''
    Arc
    subclass of PECS that adds functions to run an Arc
    calibration. Also contains method to interactively run
    a Arc calibration.

    In the future: add methods to display, judge and analyze
    calibration.
    '''

    def __init__(self, ptlids=None, printfunc=print,
                 platemaker_instrument=None, fvc_role=None,
                 illuminator_role=None, constants_version=None):
        super().__init__(ptlids=None, printfunc=print,
                         platemaker_instrument=None, fvc_role=None,
                         illuminator_role=None, constants_version=None)
        # Total points = P + T
        self.n_points_P = 6
        self.n_points_T = 6
        self.ptl = None
        self.ptlid = None
        self.posids = None
        self.data = None
        self.data_path = None

    def calibration(self, auto_update=True, user_input=False, match_radius=80):
        '''
        Executes an Arc calibration and sets data and data_path attributes
        '''
        assert self.ptl is not None, 'Must set petal!'
        assert self.posids is not None, 'Must set posids!'
        req_list_T, req_list_P = self.ptl.get_arc_requests(ids=self.posids,
                                                n_points_T=self.n_points_T,
                                                n_points_P=self.n_points_P)
        T_data = []
        i = 1
        for request in req_list_T:
            self.printfunc(f'Measuring theta arc point {i} of {len(req_list_T)}')
            i += 1 
            merged_data = self.move_measure(request, match_radius=match_radius)
            T_data.append(merged_data)
            if user_input:
                input('Please check temperatures and press enter to continue')
        P_data = []
        i = 1
        for request in req_list_P:
            self.printfunc(f'Measuring phi arc point {i} of {len(req_list_P)}')
            i += 1
            merged_data = self.move_measure(request, match_radius=match_radius)
            P_data.append(merged_data)
            if user_input:
                input('Please check temperatures and press enter to continue')
        data = self.ptl.calibrate_from_arc_data(T_data, P_data, auto_update=auto_update)
        data['auto_update'] = auto_update
        self.data = data
        # save data
        self.data_path = (os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str_now()}-arc_calibration.csv'))
        self.printfunc(data[['DEVICE_ID', 'LENGTH_R1', 'LENGTH_R2', 'OFFSET_X',
                             'OFFSET_Y', 'OFFSET_T', 'OFFSET_P']])

    def move_measure(self, request, match_radius=80):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Prints missing positioners, returns data merged with request
        '''
        self.ptl.prepare_move(request, anticollision=None)
        exppos = self.ptl.execute_move()
        exppos, meapos, matched, unmatched = self.fvc_measure(exppos,
                                                              match_radius=match_radius)
        # Want to collect both matched and unmatched
        used_pos = meapos.loc[sorted(self.posids)].reset_index()
        used_pos.rename(columns={'q':'MEASURED_Q', 's':'MEASURED_S',
                                 'flags':'FLAGS', 'id':'DEVICE_ID'}, inplace=True)
        request.rename(columns={'X1':'TARGET_T', 'X2':'TARGET_P'}, inplace=True)
        merged = used_pos.merge(request, how='outer', on='DEVICE_ID')
        return merged

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

        filename is a file to read in, otherwise checks for
        self.data_path to be set.
        '''
        converters = {'TARG_POSINTP_DURING_P_SWEEP':literal_eval,
                      'TARG_POSINTT_DURING_T_SWEEP':literal_eval,
                      'MEAS_POSINTP_DURING_P_SWEEP':literal_eval,
                      'MEAS_POSINTT_DURING_T_SWEEP':literal_eval,
                      'MEASURED_PTLXY_T':literal_eval,
                      'MEASURED_PTLXY_P':literal_eval,
                      'FLAGS_LIST':literal_eval,
                      'TARGET_T':literal_eval,
                      'TARGET_P':literal_eval}
        if filename is None and self.data_path is not None:
            self.data = pd.from_csv(self.data_path, index_col=0,
                                    converters=converters)
        else:
            self.data = pd.from_csv(filename, index_col=0,
                                    converters=converters)


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

    def run_interactively(self, petal=None, posids=None, auto_update=None,
                          user_input=None, match_radius=None):
        '''
        Interactively walk through calibration
        '''
        self.printfunc('Running interactive Arc Calibraiton')
        if self.ptl is not None:
            if not self._parse_yn(input(f'Keep using petal {self.ptlid}? (y/n) ')):
                self.set_petal(petal)
        else:
            self.set_petal(petal)
        if self.posids is not None:
            if not self._parse_yn(input(f'Keep using the following posids? {self.posids} (y/n) ')):
                self.set_posids(posids)
        else:
            self.set_posids(posids)
        if auto_update is None:
            auto_update = self._parse_yn(input('Automatically update calibration? (y/n) '))
        if user_input is None:
            user_input = self._parse_yn(input('Require user input between moves? (y/n) '))
        if match_radius is None:
            match_radius = float(input('Please privide a spotmatch radius: '))
        self.calibration(auto_update, match_radius)
        if self._parse_yn(input('Open Arc calibration data table? (y/n): ')):
            os.system(f'xdg-open {self.data_path}')


if __name__ == '__main__':
    arc = Arc()
    arc.run_interactively(user_input=True, match_radius=80)
