# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:21:10 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import pandas as pd
import posconstants as pc
from pecs import PECS
from fptestdata import CalibrationData
from poscalibrationfits import PosCalibrationFits


class PosCalibrations(PECS):
    '''mode can be:     1p_offsetsTP, 1p_posintTP, 1p_offsetTposintP,
                        arc, grid'''

    def __init__(self, mode, n_pts_TP=None, fvc=None, ptls=None,
                 pcid=None, posids=None, interactive=False):
        n_pts_TP_default = {'arc': (6, 6), 'grid': (7, 5)}
        cfg = {'pcids': PECS().pcids, 'anticollision': None}
        if '1p_' in mode:  # phi arm angle for 1p calib is 135 deg
            cfg.update({'mode': mode, 'poslocP': 135})
        elif mode in ['arc', 'grid']:
            nTP = n_pts_TP_default[mode] if n_pts_TP is None else n_pts_TP
            cfg.update({'mode': mode, 'n_pts_T': nTP[0], 'n_pts_P': nTP[1]})
        else:
            raise Exception(f'Invalid mode: {mode}')
        self.data = CalibrationData(cfg)
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
             .set_index('DEVICE_ID') for pcid in self.pcids])

    def run_1p_calibration(self, tp_target='default', auto_update=True,
                           match_radius=50, interactive=False):
        if interactive:
            user_text = self._parse_yn(
                input('Do you want to move positioners? (y/n): '))
            if user_text:  # moving positioners to default TP target
                tp_target = 'default'
            else:  # not moving positioners, use current position
                tp_target = None
            auto_update = self._parse_yn(input(
                    'Automatically update calibration? (y/n): '))
            # match_radius = float(input('Spotmatch radius: '))
            return self.run_1p_calibration(
                tp_target=tp_target, auto_update=auto_update,
                match_radius=match_radius)
        self.data.test_cfg['auto_update'] = auto_update
        self.data.test_cfg['match_radius'] = match_radius
        calib_old = self.collect_calib(self.posids)
        do_move = True
        if tp_target == 'default':  # tp_target as target
            poslocTP = (0, self.data.poslocP)  # same target for all posids
        elif isinstance(tp_target, (tuple, list)) and len(tp_target) == 2:
            poslocTP = tp_target
        else:
            poslocTP, do_move = None, False
        self.printfunc(
            f'Running one-point calibration, mode = {self.data.mode}, '
            f'poslocTP = {poslocTP}, do_move = {do_move}, '
            f'auto_update = {auto_update}')
        rows = []
        if do_move:  # then build requests and make the moves
            for posid in self.posids:
                posintTP = self.ptl.postrans(posid,
                                             'poslocTP_to_posintTP', poslocTP)
                rows.append({'DEVICE_ID': posid,
                             'COMMAND': 'posintTP',
                             'X1': posintTP[0],
                             'X2': posintTP[1],
                             'LOG_NOTE': f'{self.data.mode}'})
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
        if self.data.mode == '1p_offsetsTP':
            update_mode = 'offsetsTP'
        elif self.data.mode == '1p_posintTP':
            update_mode = 'posTP'
        elif self.data.mode == '1p_offsetTposintP':
            update_mode = 'offsetTposP'
        updates = (
            self.ptl.test_and_update_TP(
                used_pos.reset_index(), mode=update_mode,
                auto_update=auto_update,
                tp_updates_tol=0.0, tp_updates_fraction=1.0)
            .set_index('DEVICE_ID').sort_index()).rename(
                columns={'FLAGS': 'FLAG',
                         'MEAS_FLATX': 'mea_flatX', 'MEAS_FLATY': 'mea_flatY',
                         'EXP_FLATX': 'exp_flatX', 'EXP_FLATY': 'exp_flatY'})
        cols = [col for col in updates.columns
                if 'OLD_' in col or 'NEW_' in col]
        updates.drop(cols, axis=1, inplace=True)  # clean up update df
        used_pos.rename(columns={'Q': 'mea_Q', 'S': 'mea_S',
                                 'DQ': 'mea_dQ', 'DS': 'mea_dS',
                                 'FLAGS': 'FLAG'}, inplace=True)
        unused_pos.rename(columns={'Q': 'mea_Q', 'S': 'mea_S',
                                   'DQ': 'mea_dQ', 'DS': 'mea_dS',
                                   'FLAGS': 'FLAG'}, inplace=True)
        calib_up = used_pos
        calib_up.update(updates)
        # List unmeasured positioners in updates, even with no data
        calib_up.append(unused_pos, sort=False)
        # overwrite flags with focalplane flags and add status
        calib_up['FLAG'] = pd.DataFrame.from_dict(
            self.ptl.get_pos_flags(list(calib_up.index)),
            orient='index', columns=['FLAG'])
        calib_up['STATUS'] = pc.decipher_posflags(calib_up['FLAG'])
        # Clean up and record additional entries in updates
        calib_up['tgt_posintT'] = requests.set_index('DEVICE_ID')['X1']
        calib_up['tgt_posintP'] = requests.set_index('DEVICE_ID')['X2']
        calib_new = self.collect_calib(self.posids)
        calib_new.update(calib_up)
        self.data.write_calibdf(calib_old, calib_new)

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
        calib_old = self.collect_calib(self.posids)
        self.printfunc(
            f'Running arc calibration, n_pts_T = {self.data.n_pts_T}, '
            f'n_pts_P = {self.data.n_pts_P}, auto_update = {auto_update}')
        req_list_T, req_list_P = self.ptl.get_arc_requests(  # build requests
            ids=self.posids,
            n_points_T=self.data.n_pts_T, n_points_P=self.data.n_pts_P)
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
        T_arc = pd.concat(T_data, keys=range(self.data.n_pts_T))
        P_arc = pd.concat(P_data, keys=range(self.data.n_pts_P))
        data_arc = pd.concat([T_arc, P_arc], keys=['T', 'P'],
                             names=['arc', 'target_no', 'DEVICE_ID'])
        data_arc.to_pickle(os.path.join(self.data.dir, 'data_arc.pkl.gz'),
                           compression='gzip')
        # run fitting
        petal_alignments = {i: self.ptls[i].alignment for i in self.pcids}
        fit = PosCalibrationFits(petal_alignments=petal_alignments,
                                 printfunc=self.logger.info)
        self.data.movedf, calib_fit = fit.calibrate_from_arc_data(data_arc)
        calib_new = self.collect_calib(self.posids)
        calib_new.update(calib_fit)
        self.data.write_calibdf(calib_old, calib_new)
        if auto_update:
            [self.ptls[pcid].set_calibration(calib_new) for pcid in self.pcids]

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
        calib_old = self.collect_calib(self.posids)
        self.printfunc(
            f'Running grid calibration, n_pts_T = {self.data.n_pts_T}, '
            f'n_pts_P = {self.data.n_pts_P}, auto_update = {auto_update}')
        req_list = self.ptl.get_grid_requests(ids=self.posids,
                                              n_points_T=self.data.n_pts_T,
                                              n_points_P=self.data.n_pts_P)
        grid_data = []  # move, measure
        for i, request in enumerate(req_list):
            self.printfunc(f'Measuring grid point {i+1} of {len(req_list)}...')
            grid_data.append(self.move_measure(request,
                                               match_radius=match_radius))
            if i+1 < len(req_list):  # no pause after the last iteration
                self.pause()
        data_grid = pd.concat(grid_data, keys=range(len(req_list)),
                              names=['target_no', 'DEVICE_ID'])
        data_grid.to_pickle(os.path.join(self.data.dir, 'data_grid.pkl.gz'),
                            compression='gzip')
        # run fitting
        petal_alignments = {i: self.ptls[i].alignment for i in self.pcids}
        fit = PosCalibrationFits(petal_alignments=petal_alignments,
                                 printfunc=self.logger.info)
        self.data.movedf, calib_fit = fit.calibrate_from_grid_data(data_grid)
        calib_new = self.collect_calib(self.posids)
        calib_new.update(calib_fit)
        self.data.write_calibdf(calib_old, calib_new)
        if auto_update:
            [self.ptls[pcid].set_calibration(calib_new) for pcid in self.pcids]

    def move_measure(self, request, match_radius=50):
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
        request.set_index('DEVICE_ID', inplace=True)
        merged = matched_df.merge(request, how='outer',
                                  left_index=True, right_index=True)
        merged.rename(columns={'X1': 'tgt_posintT', 'X2': 'tgt_posintP',
                               'Q': 'mea_Q', 'S': 'mea_S', 'FLAGS': 'FLAG'},
                      inplace=True)
        merged['STATUS'] = pc.decipher_posflags(merged['FLAG'])
        return merged
