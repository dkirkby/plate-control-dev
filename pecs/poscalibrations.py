# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:21:10 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import pandas as pd
import posconstants as pc
from pecs import PECS
from fptestdata import CalibrationData
from poscalibrationfits import PosCalibrationFits


class PosCalibrations(PECS):
    '''
    subclass of PECS that adds functions to run an Arc calibration.
    In the future: add methods to display, judge and analyze calibration.
    '''

    def __init__(self, mode, fvc=None, ptls=None, pcid=None, posids=None,
                 interactive=False):
        cfg = {'pcids': PECS().pcids}
        if mode == 'arc':
            cfg.update({'mode': 'arc', 'n_pts_T': 6, 'n_pts_P': 6})
        elif mode == 'grid':
            cfg.update({'mode': 'grid', 'n_pts_T': 7, 'n_pts_P': 5})
        else:
            raise Exception(f'Invalid mode: {mode}')
        self.data = CalibrationData(mode, PECS().pcids,
                                    n_pts_T=self.npts_T, n_pts_P=self.npts_P)
        self.loggers = self.data.loggers  # use these loggers to write to logs
        self.logger = self.data.logger  # broadcast to all petals
        super().__init__(
            fvc=fvc, ptls=ptls,
            printfunc={p: self.loggers[p].info for p in self.data.pcids})
        self.data.t_i = pc.now()
        self.exp_setup()  # set up exposure ID and product directory
        self.logger.info(f'Running arc calibration')
        if interactive:
            self.interactive_ptl_setup()
        else:
            self.ptl_setup(pcid, posids)

    def collect_calib(self, posids):
        keys_collect = [
            'POS_T', 'POS_P', 'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
            'LENGTH_R1', 'LENGTH_R2', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
            'GEAR_CALIB_T', 'GEAR_CALIB_P']
        return pd.concat(
            [self.ptls[pcid].get_pos_vals(keys_collect, posids=posids)
             for pcid in self.pcids])

    def run_arc_calibration(self, auto_update=False, match_radius=50,
                            interactive=False):
        if interactive:
            auto_update = self._parse_yn(input(
                        'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.run_arc_calibration(auto_update=auto_update,
                                            match_radius=match_radius)
        self.data.test_cfg['auto_update'] = auto_update
        self.data.test_cfg['match_radius'] = match_radius
        old_calibdf = self.collect_calib(self.posids)
        req_list_T, req_list_P = self.ptl.get_arc_requests(  # build requests
            ids=self.posids, n_points_T=self.n_pts_T, n_points_P=self.n_pts_P)
        T_data = []  # move, measure
        for i, req in enumerate(req_list_T):
            self.printfunc(f'Measuring theta arc point {i+1} of '
                           f'{len(req_list_T)}...')
            T_data.append(self.move_measure(req, match_radius=match_radius))
            if i+1 < len(req_list_T):  # no pause after the last iteration
                self.pause()
        P_data = []
        for i, req in enumerate(req_list_P):
            self.printfunc(f'Measuring phi arc point {i+1} of '
                           f'{len(req_list_P)}...')
            if i+1 < len(req_list_T):  # pause before first iteration
                self.pause()
            P_data.append(self.move_measure(req, match_radius=match_radius))
        # put all arc measurement data in one dataframe
        T_arc = pd.concat(T_data, keys=range(self.n_pts_T))
        P_arc = pd.concat(P_data, keys=range(self.n_pts_P))
        data_arc = pd.concat([T_arc, P_arc], keys=['T', 'P'],
                             names=['arc', 'target_no', 'DEVICE_ID'])
        # run fitting
        petal_alignments = {i: self.ptls[i].alignment for i in self.pcids}
        posmodels = {}
        for pcid in self.pcids:
            posmodels.update(self.ptls[pcid].posmodels)
        calib = PosCalibrationFits(petal_alignemnts=petal_alignments,
                                   posmodels=posmodels,
                                   printfunc=self.logger.info)
        self.data.movedf, calibdf = calib.calibrate_from_arc_data(data_arc)
        self.data.write_calibdf(old_calibdf, calibdf)
        if auto_update:
            [self.ptls[pcid].set_calibration(calibdf) for i in self.pcids]

    def run_grid_calibration(self, auto_update=False, match_radius=50,
                             interactive=False):
        if interactive:
            auto_update = self._parse_yn(input(
                        'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.run_grid_calibration(auto_update=auto_update,
                                             match_radius=match_radius)
        self.data.test_cfg['auto_update'] = auto_update
        self.data.test_cfg['match_radius'] = match_radius
        old_calibdf = self.collect_calib(self.posids)
        req_list = self.ptl.get_grid_requests(ids=self.posids,
                                              n_points_T=self.n_points_T,
                                              n_points_P=self.n_points_P)
        grid_data = []  # move, measure
        for i, request in enumerate(req_list):
            self.printfunc(f'Measuring grid point {i+1} of {len(req_list)}...')
            grid_data.append(self.move_measure(request,
                                               match_radius=match_radius))
            if i+1 < len(req_list):  # no pause after the last iteration
                self.pause()
        data_grid = pd.concat(grid_data, keys=range(len(req_list)),
                              names=['target_no', 'DEVICE_ID'])
        # run fitting
        petal_alignments = {i: self.ptls[i].alignment for i in self.pcids}
        posmodels = {}
        for pcid in self.pcids:
            posmodels.update(self.ptls[pcid].posmodels)
        calib = PosCalibrationFits(petal_alignemnts=petal_alignments,
                                   posmodels=posmodels,
                                   printfunc=self.logger.info)
        self.data.movedf, calibdf = calib.calibrate_from_grid_data(data_grid)
        self.data.write_calibdf(old_calibdf, calibdf)
        if auto_update:
            [self.ptls[pcid].set_calibration(calibdf) for i in self.pcids]

    def move_measure(self, request, match_radius=30):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Returns data merged with request
        '''
        self.ptl.prepare_move(request, anticollision=None)
        self.ptl.execute_move()
        _, meapos, matched, _ = self.fvc_measure(
            matched_only=True, match_radius=match_radius)
        # meapos contains not only matched ones but all posids in expected pos
        matched_df = meapos.loc[sorted(matched & set(self.posids))]
        request.rename(columns={'X1': 'TARGET_T', 'X2': 'TARGET_P'},
                       inplace=True).set_index('DEVICE_ID')
        return matched_df.merge(request, how='outer')
