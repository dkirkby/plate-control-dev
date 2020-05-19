# -*- coding: utf-8 -*-
"""
Created on Thu Dec 12 12:21:10 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
from glob import glob
import os
import numpy as np
import pandas as pd
pd.options.mode.chained_assignment = None  # default='warn', hacky yes, but hey---that's pandas for ya
import posconstants as pc
from pecs import PECS
from fptestdata import CalibrationData
from poscalibrationfits import PosCalibrationFits
from postransforms import PosTransforms
import xy_targets_generator


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
               'online_fitting': True, 'poslocP': 135, 'mode': mode}
        if mode in ['arc', 'grid']:
            nTP = n_pts_TP_default[mode] if n_pts_TP is None else n_pts_TP
            cfg.update({'n_pts_T': nTP[0], 'n_pts_P': nTP[1]})
        test_name = input('Please name this test (calibration-{test_name}): ')
        # next initilaise test data object with loggers for each petal
        self.data = CalibrationData(test_name, cfg)
        self.logger = self.data.logger  # broadcast to all petals
        self.loggers = self.data.loggers
        super().__init__(fvc=fvc, ptlm=ptlm, interactive=interactive)
        self.data.posids = self.posids
        self.data.pcids = self.pcids
        self.exp_setup()  # set up exposure ID and product directory
        self.home_adc()
        self.set_schedule_stats(enabled=self.schedule_stats)
        self.data.petal_alignments = pd.DataFrame(self.petal_alignments).T
        self.data.petal_alignments.index.name = 'petal_loc'

    def collect_calib(self, posids):
        ret = self.ptlm.get_pos_vals(self.keys_collect, posids=posids)
        dfs = [ret[role] for role in self.ptl_roles]
        return pd.concat(dfs).set_index('DEVICE_ID').sort_index()

    def run_1p_calibration(self, tp_target='default', commit=False,
                           interactive=False, partial=False):
        '''err columns are target - measured'''
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
            return self.run_1p_calibration(tp_target=tp_target, commit=commit)
        self.data.calib_old = self.collect_calib(self.posids)
        do_move = True
        if tp_target == 'default':  # tp_target as target
            poslocTP = (0, self.data.poslocP)  # same target for all posids
        elif isinstance(tp_target, (tuple, list)) and len(tp_target) == 2:
            poslocTP = tp_target
        else:
            poslocTP, do_move = None, False
        self.data.test_cfg.update(
            {'commit': commit, 'tgt_poslocTP': poslocTP, 'do_move': do_move})
        self.print(f'Running one-point calibration, mode = {self.data.mode}, '
                   f'poslocTP = {poslocTP}, do_move = {do_move}, '
                   f'commit = {commit}')
        rows = []
        log_note = self.decorate_note(f'{self.data.mode}')
        if do_move:  # then build requests and make the moves
            for posid in self.posids:
                role = self.ptl_role_lookup(posid)
                posintTP = self.ptlm.postrans(posid,
                                              'poslocTP_to_posintTP', poslocTP,
                                              participating_petals=role)
                row = {'DEVICE_ID': posid, 'COMMAND': 'posintTP',
                       'X1': posintTP[0], 'X2': posintTP[1],
                       'LOG_NOTE': log_note}
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
                match_radius=self.match_radius)
        used_pos = meapos.loc[sorted(matched & (set(self.posids)))]
        unused_pos = exppos.loc[sorted(unmatched & (set(self.posids)))]
        if len(used_pos) == 0:  # at least got some positioners back, update
            self.logger.critical('No requested positioner was matched')
            return
        if self.data.mode == '1p_offsetsTP':
            update_mode = 'offsetsTP'
        elif self.data.mode == '1p_offsetTposintP':
            update_mode = 'offsetTposP'
        else:  # self.data.mode == '1p_posintTP', also covers calls by arc/grid
            update_mode = 'posTP'
        updates = self.ptlm.test_and_update_TP(
                used_pos.reset_index(), mode=update_mode, auto_update=commit,
                tp_updates_tol=0, tp_updates_fraction=1, log_note=log_note)
        if partial:  # skip the following as this is part of arc/grid cal
            return
        updates = (pd.concat(list(updates.values())).set_index('DEVICE_ID')
                   .sort_index()).rename(
                columns={'FLAGS': 'FLAG',
                         'MEAS_FLATX': 'mea_flatX', 'MEAS_FLATY': 'mea_flatY',
                         'EXP_FLATX': 'exp_flatX', 'EXP_FLATY': 'exp_flatY'})
        cols = [f'OLD_{key}' for key in self.keys_collect]
        updates.drop(cols, axis=1, inplace=True)  # clean up proposed change
        for df in [used_pos, unused_pos]:
            df.rename(columns={'Q': 'mea_Q', 'S': 'mea_S',
                               'DQ': 'mea_dQ', 'DS': 'mea_dS',
                               'FLAGS': 'FLAG'}, inplace=True)
        # List unmeasured positioners in updates, even with no data
        used_pos.drop('FLAG', axis=1, inplace=True)
        calib_fit = used_pos.join(updates).append(unused_pos, sort=True)
        calib_fit.sort_index(inplace=True)
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
        self.set_schedule_stats(enabled=False)
        self.fvc_collect()
        self.data.generate_data_products()

    def run_arc_calibration(self):
        '''err columns are interally tracked - measured'''
        # if interactive:
        #     commit = self._parse_yn(input(
        #                 'Automatically update calibration? (y/n): '))
        #     match_radius = float(input('Please provide a match radius: '))
        #     return self.run_arc_calibration(match_radius=self.match_radius)
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
            df = pd.concat(dfs).set_index('DEVICE_ID')
            common_note = self.decorate_note(f'arc calibration theta axis point {i+1} of {self.data.n_pts_T}')
            for idx, row in df.iterrows():
                df['LOG_NOTE'][idx] = common_note
            req_list_T.append(df)
        for j in range(self.data.n_pts_P):
            dfs = [df[1][j] for df in ret.values()]
            df = pd.concat(dfs).set_index('DEVICE_ID')
            common_note = self.decorate_note(f'arc calibration phi axis point {j+1} of {self.data.n_pts_P}')
            for idx, row in df.iterrows():
                df['LOG_NOTE'][idx] = common_note
            req_list_P.append(df)
        T_data = []  # move, measure
        for i, req in enumerate(req_list_T):
            self.print(f'Starting theta arc point {i+1} of '
                       f'{len(req_list_T)}...')
            T_data.append(
                self.move_measure(req, match_radius=self.match_radius))
            if i+1 < len(req_list_T):  # no pause after the last iteration
                self.pause()
        P_data = []
        for i, req in enumerate(req_list_P):
            self.print(f'Starting phi arc point {i+1} of '
                       f'{len(req_list_P)}...')
            if i+1 < len(req_list_T):  # pause before first iteration
                self.pause()
            P_data.append(
                self.move_measure(req, match_radius=self.match_radius))
        # put all arc measurement data in one dataframe
        T_arc = pd.concat(T_data, keys=range(self.data.n_pts_T))
        P_arc = pd.concat(P_data, keys=range(self.data.n_pts_P))
        self.data.data_arc = pd.concat(
            [T_arc, P_arc], keys=['T', 'P'],
            names=['axis', 'target_no', 'DEVICE_ID'])
        self.data.data_arc.to_pickle(
            os.path.join(self.data.dir, 'data_arc.pkl.gz'), compression='gzip')
        self.run_extra_points()
        self.data.t_f = pc.now()
        self.set_schedule_stats(enabled=False)
        self.fvc_collect()
        if self.data.online_fitting:
            fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                     loggers=self.loggers)
            self.data.movedf, calib_fit = (
                fit.calibrate_from_arc_data(self.data.data_arc))
            self.data.movedf_extra, self.data.calib_fit = \
                fit.verify_with_extra_points(self.data.data_extra, calib_fit)
            self.data.calib_new = self.collect_calib(self.posids)
            self.data.write_calibdf(self.data.calib_old, self.data.calib_fit,
                                    self.data.calib_new)
        try:
            self.data.generate_data_products()
        except Exception as e:
            print(e)
            self.data.dump_as_one_pickle()

    def run_grid_calibration(self):
        self.data.calib_old = self.collect_calib(self.posids)
        self.print(f'Running grid calibration, n_pts_T = {self.data.n_pts_T}, '
                   f'n_pts_P = {self.data.n_pts_P}, DB commit disabled')
        ret = self.ptlm.get_grid_requests(ids=self.posids,
                                          n_points_T=self.data.n_pts_T,
                                          n_points_P=self.data.n_pts_P)
        req_list, npts = [], self.data.n_pts_P*self.data.n_pts_T
        for i in range(npts):
            dfs = [dfs[i] for dfs in ret.values()]
            df = pd.concat(dfs).set_index('DEVICE_ID')
            common_note = self.decorate_note(f'grid calibration point {i+1} of {npts}')
            for idx, row in df.iterrows():
                df['LOG_NOTE'][idx] = common_note
            req_list.append(df)
        grid_data = []  # move, measure
        for i, request in enumerate(req_list):
            self.print(f'Measuring grid point {i+1} of {len(req_list)}...')
            grid_data.append(
                self.move_measure(request, match_radius=self.match_radius))
            if i+1 < len(req_list):  # no pause after the last iteration
                self.pause()
        self.data.data_grid = pd.concat(grid_data, keys=range(len(req_list)),
                                        names=['target_no', 'DEVICE_ID'])
        self.data.data_grid.to_pickle(os.path.join(
            self.data.dir, 'data_grid.pkl.gz'), compression='gzip')
        self.run_extra_points()
        self.data.t_f = pc.now()
        self.set_schedule_stats(enabled=False)
        self.fvc_collect()
        if self.data.online_fitting:
            fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                     loggers=self.loggers)
            self.data.movedf, calib_fit = (
                fit.calibrate_from_grid_data(self.data.data_grid))
            self.data.movedf_extra, self.data.calib_fit = \
                fit.verify_with_extra_points(self.data.data_extra, calib_fit)
            self.data.calib_new = self.collect_calib(self.posids)
            self.data.write_calibdf(self.data.calib_old, self.data.calib_fit,
                                    self.data.calib_new)
        try:
            self.data.generate_data_products()
        except Exception as e:
            print(e)
            self.data.dump_as_one_pickle()

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
            exppos=None, matched_only=True, match_radius=match_radius)
        # meapos may contain not only matched but all posids in expected pos
        matched_df = meapos.loc[sorted(matched & set(self.posids))]
        merged = matched_df.merge(request, how='outer',
                                  left_index=True, right_index=True)
        merged.rename(columns={'X1': 'tgt_posintT', 'X2': 'tgt_posintP',
                               'Q': 'mea_Q', 'S': 'mea_S', 'FLAGS': 'FLAG'},
                      inplace=True)
        mask = merged['FLAG'].notnull()
        merged.loc[mask, 'STATUS'] = pc.decipher_posflags(
            merged.loc[mask, 'FLAG'])
        # get expected (tracked) posintTP angles
        exppos = (self.ptlm.get_positions(return_coord='posintTP',
                                          participating_petals=self.ptl_roles)
                  .set_index('DEVICE_ID')[['X1', 'X2']])
        exppos.rename(columns={'X1': 'posintT', 'X2': 'posintP'}, inplace=True)
        return merged.join(exppos)

    def run_extra_points(self, max_radius=3.3, n_points=24):
        '''This function will move to and measure a grid of points, without
        any special calibration analysis performed. The purpose is to have an
        independent measurement of internally-tracked (t,p) vs measured (x,y),
        performed at the time of the calibration, with all the same conditions
        in place.
        
        INPUTS:
            max_radius ... target points shall be no further out than this
                           from nominal device center
            
            n_points   ... grid will be spaced to include this many points
                           (in some cases a slightly)
        '''
        self.logger.info('Performing one-point posintTP update before taking '
                         'extra points for calibration verification...')
        self.run_1p_calibration(tp_target=None, commit=True, partial=True)
        tgt_xy = xy_targets_generator.filled_circle(n_points=n_points, radius=max_radius)
        trans = PosTransforms(stateless=True)
        targets = []
        for poslocXY in tgt_xy:
            posintTP, unreachable = trans.poslocXY_to_posintTP(poslocXY)
            # Ignore "unreachable" here, since really we're just interested in
            # making a set of (theta, phi).
            targets.append(posintTP)
        req_temp = self.posinfo[['PETAL_LOC', 'DEVICE_LOC']].copy()
        req_temp['COMMAND'] = 'posintTP'

        def gen_req(i):
            req = req_temp.copy()
            req['X1'], req['X2'] = targets[i][0], targets[i][1]
            common_note = self.decorate_note(f'extra point {i+1} of {len(targets)} for {self.data.mode}')
            for idx, row in req.iterrows():
                req['LOG_NOTE'][idx] = common_note
            return req

        requests = [gen_req(i) for i in range(len(targets))]
        dfs = []
        for i, request in enumerate(requests):
            self.print(f'Measuring extra point {i+1} of {len(targets)}...')
            dfs.append(self.move_measure(request, match_radius=self.match_radius))
            if i+1 < len(requests):  # no pause after the last iteration
                self.pause()
        self.data.data_extra = pd.concat(dfs, keys=range(len(targets)),
                                         names=['target_no', 'DEVICE_ID'])
        self.data.data_extra.to_pickle(os.path.join(
            self.data.dir, 'data_extra.pkl.gz'), compression='gzip')

if __name__ == '__main__':
    expids = [37927, 37928, 37930, 37933]  # arcs
    for expid in expids:
        paths = glob(pc.dirs['kpno']+f'/*/{expid:08}/*data_*.pkl.gz')
        assert len(paths) == 1, paths
        path = paths[0]
        print(f'Re-processing FP test data:\n{path}')
        data_arc = pd.read_pickle(path)
        fit = PosCalibrationFits()
        movedf, calib_fit = fit.calibrate_from_arc_data(data_arc)
        movedf.to_pickle(os.path.join(os.path.dirname(path), 'movedf.pkl.gz'))
        calib_fit.to_pickle(
            os.path.join(os.path.dirname(path), 'calib_fit.pkl.gz'))
