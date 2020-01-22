# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:21:10 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
from glob import glob
import os
import numpy as np
import pandas as pd
import posconstants as pc
from pecs import PECS
from fptestdata import CalibrationData
from poscalibrationfits import PosCalibrationFits


class PosCalibrations(PECS):
    '''mode can be:     1p_offsetsTP, 1p_posintTP, 1p_offsetTposintP,
                        arc, grid'''
    keys_collect = [
        'POS_T', 'POS_P', 'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
        'LENGTH_R1', 'LENGTH_R2', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
        'GEAR_CALIB_T', 'GEAR_CALIB_P']

    def __init__(self, mode, n_pts_TP=None, fvc=None, ptlm=None,
                 pcid=None, posids=None, interactive=False):
        # first determine what test we are running, set test params/cfg
        n_pts_TP_default = {'arc': (6, 6), 'grid': (7, 5)}
        cfg = {'pcids': PECS().pcids, 'anticollision': None,
               'online_fitting': True}
        if '1p_' in mode:  # phi arm angle for 1p calib is 135 deg
            cfg.update({'mode': mode, 'poslocP': 135})
        elif mode in ['arc', 'grid']:
            nTP = n_pts_TP_default[mode] if n_pts_TP is None else n_pts_TP
            cfg.update({'mode': mode, 'n_pts_T': nTP[0], 'n_pts_P': nTP[1]})
        else:
            raise Exception(f'Invalid mode: {mode}')
        # next initilaise test data object with loggers for each petal
        self.data = CalibrationData(cfg)
        self.logger = self.data.logger  # broadcast to all petals
        self.loggers = self.data.loggers
        super().__init__(fvc=fvc, ptlm=ptlm, interactive=interactive)
        self.data.t_i = pc.now()
        self.exp_setup()  # set up exposure ID and product directory

    def collect_calib(self, posids):
        ret = self.ptlm.get_pos_vals(self.keys_collect, posids=posids)
        dfs = [ret[role] for role in self.ptl_roles]
        return pd.concat(dfs).set_index('DEVICE_ID')

    def run_1p_calibration(self, tp_target='default', commit=False,
                           match_radius=50, interactive=False):
        if interactive:
            user_text = self._parse_yn(
                input('Move positioners? (y/n): '))
            if user_text:  # moving positioners to default TP target
                tp_target = 'default'
            else:  # not moving positioners, use current position
                tp_target = None
            commit = self._parse_yn(input(
                    'Commit calibration results? (y/n): '))
            # match_radius = float(input('Spotmatch radius: '))
            return self.run_1p_calibration(tp_target=tp_target,
                                           commit=commit,
                                           match_radius=match_radius)
        self.data.calib_old = self.collect_calib(self.posids)
        do_move = True
        if tp_target == 'default':  # tp_target as target
            poslocTP = (0, self.data.poslocP)  # same target for all posids
        elif isinstance(tp_target, (tuple, list)) and len(tp_target) == 2:
            poslocTP = tp_target
        else:
            poslocTP, do_move = None, False
        self.data.test_cfg.update(
            {'commit': commit, 'tgt_poslocTP': poslocTP, 'do_move': do_move,
             'match_radius': match_radius})
        self.print(f'Running one-point calibration, mode = {self.data.mode}, '
                   f'poslocTP = {poslocTP}, do_move = {do_move}, '
                   f'commit = {commit}')
        rows = []
        if do_move:  # then build requests and make the moves
            for posid in self.posids:
                role = self.ptl_role_lookup(posid)
                posintTP = self.ptlm.postrans(posid,
                                              'poslocTP_to_posintTP', poslocTP,
                                              participating_petals=role)
                row = {'DEVICE_ID': posid, 'COMMAND': 'posintTP',
                       'X1': posintTP[0], 'X2': posintTP[1],
                       'LOG_NOTE': f'{self.data.mode}'}
                row.update(self.posinfo.loc[posid].to_dict())
                rows.append(row)
            req = pd.DataFrame(rows)
            self.ptlm.prepare_move(req, anticollision=None)
            self.ptlm.execute_move(reset_flags=False, control={'timeout': 120})
        else:  # then use current position as targets in requests
            req = self.ptlm.get_positions(return_coord='posintTP')
            # PetalMan.get_positions() does not take posids arg, filter
            req = req[req['DEVICE_ID'].isin(self.posids)]
        exppos, meapos, matched, unmatched = self.fvc_measure(
                match_radius=match_radius)
        used_pos = meapos.loc[sorted(matched & (set(self.posids)))]
        unused_pos = exppos.loc[sorted(unmatched & (set(self.posids)))]
        if len(used_pos) == 0:  # at least got some positioners back, update
            self.logger.critical('No requested positioner was matched')
            return
        if self.data.mode == '1p_offsetsTP':
            update_mode = 'offsetsTP'
        elif self.data.mode == '1p_posintTP':
            update_mode = 'posTP'
        elif self.data.mode == '1p_offsetTposintP':
            update_mode = 'offsetTposP'
        updates = self.ptlm.test_and_update_TP(
                used_pos.reset_index(), mode=update_mode, auto_update=commit,
                tp_updates_tol=0, tp_updates_fraction=1)
        updates = (pd.concat(list(updates.values())).set_index('DEVICE_ID')
                   .sort_index()).rename(
                columns={'FLAGS': 'FLAG',
                         'MEAS_FLATX': 'mea_flatX', 'MEAS_FLATY': 'mea_flatY',
                         'EXP_FLATX': 'exp_flatX', 'EXP_FLATY': 'exp_flatY'})
        cols = [f'OLD_{key}' for key in self.keys_collect]
        updates.drop(cols, axis=1, inplace=True)  # clean up proposed change
        # updates.rename(columns={f'OLD_{key}': key
        #                         for key in self.keys_collect}, inplace=True)
        for df in [used_pos, unused_pos]:
            df.rename(columns={'Q': 'mea_Q', 'S': 'mea_S',
                               'DQ': 'mea_dQ', 'DS': 'mea_dS',
                               'FLAGS': 'FLAG'}, inplace=True)
        # List unmeasured positioners in updates, even with no data
        used_pos.drop('FLAG', axis=1, inplace=True)
        calib_fit = used_pos.join(updates).append(unused_pos, sort=False)
        # overwrite flags with focalplane flags and add status
        flags = [pd.DataFrame.from_dict(  # device_id in dict becomes index
                     flags_dict, orient='index', columns=['FLAG'])
                 for flags_dict in self.ptlm.get_pos_flags().values()]
        calib_fit['FLAG'] = pd.concat(flags)
        calib_fit['STATUS'] = pc.decipher_posflags(calib_fit['FLAG'])
        # clean up and record additional entries in updates
        calib_fit['tgt_posintT'] = req.set_index('DEVICE_ID')['X1']
        calib_fit['tgt_posintP'] = req.set_index('DEVICE_ID')['X2']
        for posid, row in calib_fit.iterrows():
            role = self.ptl_role_lookup(posid)
            mea_posintTP, _ = self.ptlm.postrans(
                posid, 'QS_to_posintTP',
                row[['mea_Q', 'mea_S']].values.astype(float),
                participating_petals=role)
            tgt_flatXY = self.ptlm.postrans(
                posid, 'posintTP_to_flatXY',
                row[['tgt_posintT', 'tgt_posintP']].values.astype(float),
                participating_petals=role)
            calib_fit.loc[posid, 'mea_posintT'] = mea_posintTP[0]
            calib_fit.loc[posid, 'mea_posintP'] = mea_posintTP[1]
            calib_fit.loc[posid, 'tgt_flatX'] = tgt_flatXY[0]
            calib_fit.loc[posid, 'tgt_flatY'] = tgt_flatXY[1]
        calib_fit['err_flatX'] = (
            calib_fit['mea_flatX'] - calib_fit['tgt_flatX'])
        calib_fit['err_flatY'] = (
            calib_fit['mea_flatY'] - calib_fit['tgt_flatY'])
        calib_fit['err_flatXY'] = np.linalg.norm(
            calib_fit[['mea_flatX', 'tgt_flatX']], axis=1)
        calib_fit['err_posintT'] = (calib_fit['mea_posintT']
                                    - calib_fit['tgt_posintT'])
        calib_fit['err_posintP'] = (calib_fit['mea_posintP']
                                    - calib_fit['tgt_posintP'])
        self.data.calib_fit = calib_fit
        self.data.calib_new = self.collect_calib(self.posids)
        self.data.write_calibdf(self.data.calib_old, self.data.calib_fit,
                                self.data.calib_new)
        self.data.t_f = pc.now()
        self.fvc_collect()

    def run_arc_calibration(self, match_radius=50, interactive=False):
        if interactive:
            # commit = self._parse_yn(input(
            #             'Automatically update calibration? (y/n): '))
            match_radius = float(input('Please provide a spotmatch radius: '))
            return self.run_arc_calibration(match_radius=match_radius)
        self.data.test_cfg['match_radius'] = match_radius
        self.data.calib_old = self.collect_calib(self.posids)
        self.print(f'Running arc calibration, n_pts_T = {self.data.n_pts_T}, '
                   f'n_pts_P = {self.data.n_pts_P}, DB commit disabled')
        ret = self.ptlm.get_arc_requests(
            ids=self.posids,
            n_points_T=self.data.n_pts_T, n_points_P=self.data.n_pts_P)
        req_list_T = []
        req_list_P = []
        for i in range(self.data.n_pts_T):
            dfs = [df[0][i] for df in ret.values()]
            req_list_T.append(pd.concat(dfs).reset_index())
        for j in range(self.data.n_pts_P):
            dfs = [df[1][j] for df in ret.values()]
            req_list_P.append(pd.concat(dfs).reset_index())
        T_data = []  # move, measure
        for i, req in enumerate(req_list_T):
            self.print(f'Starting theta arc point {i+1} of '
                       f'{len(req_list_T)}...')
            T_data.append(self.move_measure(req, match_radius=match_radius))
            if i+1 < len(req_list_T):  # no pause after the last iteration
                self.pause()
        P_data = []
        for i, req in enumerate(req_list_P):
            self.print(f'Starting phi arc point {i+1} of '
                       f'{len(req_list_P)}...')
            if i+1 < len(req_list_T):  # pause before first iteration
                self.pause()
            P_data.append(self.move_measure(req, match_radius=match_radius))
        # put all arc measurement data in one dataframe
        T_arc = pd.concat(T_data, keys=range(self.data.n_pts_T))
        P_arc = pd.concat(P_data, keys=range(self.data.n_pts_P))
        self.data_arc = pd.concat([T_arc, P_arc], keys=['T', 'P'],
                                  names=['axis', 'target_no', 'DEVICE_ID'])
        self.data_arc.to_pickle(os.path.join(self.data.dir, 'data_arc.pkl.gz'),
                                compression='gzip')
        self.data.t_f = pc.now()
        self.fvc_collect()
        if self.data.online_fitting:
            fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                     loggers=self.loggers)
            self.data.movedf, self.data.calib_fit = (
                fit.calibrate_from_arc_data(self.data_arc))
            self.data.calib_new = self.collect_calib(self.posids)
            self.data.write_calibdf(self.data.calib_old, self.data.calib_fit,
                                    self.data.calib_new)

    def run_grid_calibration(self, match_radius=50,
                             interactive=False):
        if interactive:
            # commit = self._parse_yn(input(
            #             'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.run_grid_calibreq_listration(match_radius=match_radius)
        self.data.test_cfg['match_radius'] = match_radius
        self.data.calib_old = self.collect_calib(self.posids)
        self.print(f'Running grid calibration, n_pts_T = {self.data.n_pts_T}, '
                   f'n_pts_P = {self.data.n_pts_P}, DB commit disabled')
        ret = self.ptlm.get_grid_requests(ids=self.posids,
                                          n_points_T=self.data.n_pts_T,
                                          n_points_P=self.data.n_pts_P)
        req_list = []
        for i in range(self.data.n_pts_P*self.data.n_pts_T):
            dfs = [dfs[i] for dfs in ret.values()]
            req_list.append(pd.concat(dfs).reset_index())
        grid_data = []  # move, measure
        for i, request in enumerate(req_list):
            self.print(f'Measuring grid point {i+1} of {len(req_list)}...')
            grid_data.append(self.move_measure(request,
                                               match_radius=match_radius))
            if i+1 < len(req_list):  # no pause after the last iteration
                self.pause()
        self.data_grid = pd.concat(grid_data, keys=range(len(req_list)),
                                   names=['target_no', 'DEVICE_ID'])
        self.data_grid.to_pickle(os.path.join(
            self.data.dir, 'data_grid.pkl.gz'), compression='gzip')
        self.data.t_f = pc.now()
        self.fvc_collect()
        if self.data.online_fitting:
            fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                     loggers=self.loggers)
            self.data.movedf, self.data.calib_fit = (
                fit.calibrate_from_grid_data(self.data_grid))
            self.data.calib_new = self.collect_calib(self.posids)
            self.data.write_calibdf(self.data.calib_old, self.data.calib_fit,
                                    self.data.calib_new)

    @property
    def petal_alignments(self):
        return {self._role2pcid(role): alignment
                for role, alignment in self.ptlm.alignment.items()}

    def move_measure(self, request, match_radius=50):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Returns data merged with request
        '''
        self.logger.info('Moving positioners...')
        self.ptlm.prepare_move(request, anticollision=None)
        self.ptlm.execute_move(reset_flags=False, control={'timeout': 120})
        _, meapos, matched, _ = self.fvc_measure(
            matched_only=True, match_radius=match_radius)
        # meapos may contain not only matched but all posids in expected pos
        matched_df = meapos.loc[sorted(matched & set(self.posids))]
        request.set_index('DEVICE_ID', inplace=True)
        merged = matched_df.merge(request, how='outer',
                                  left_index=True, right_index=True)
        merged.rename(columns={'X1': 'tgt_posintT', 'X2': 'tgt_posintP',
                               'Q': 'mea_Q', 'S': 'mea_S', 'FLAGS': 'FLAG'},
                      inplace=True)
        mask = ~merged['FLAG'].isnull()
        merged.loc[mask, 'STATUS'] = pc.decipher_posflags(
            merged.loc[mask, 'FLAG'])
        return merged


if __name__ == '__main__':
    expids = [37927,37928,37930,37933]  # arcs
    for expid in expids:
        paths = glob(pc.dirs['kpno']+f'/*/{expid:08}/*data_*.pkl.gz')
        assert len(paths) == 1, paths
        path = paths[0]
        print(f'Re-processing FP test data:\n{path}')
        data_arc = pd.read_pickle(path)
        fit = PosCalibrationFits()
        movedf, calib_fit = fit.calibrate_from_arc_data(data_arc)
        movedf.to_pickle(os.path.join(os.path.dirname(path), 'movedf.pkl.gz'))
        calib_fit.to_pickle(os.path.join(os.path.dirname(path), 'calib_fit.pkl.gz'))
