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

    def __init__(self, mode, n_pts_TP=None, fvc=None, ptlm=None,
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
            fvc=fvc, ptlm=ptlm, interactive=interactive,
            printfunc={p: self.loggers[p].info for p in self.data.pcids})
        self.data.t_i = pc.now()
        self.exp_setup()  # set up exposure ID and product directory
        self.logger.info(f'Running {mode} calibration')

    def collect_calib(self, posids):
        keys_collect = [
            'POS_T', 'POS_P', 'OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
            'LENGTH_R1', 'LENGTH_R2', 'PHYSICAL_RANGE_T', 'PHYSICAL_RANGE_P',
            'GEAR_CALIB_T', 'GEAR_CALIB_P']
        return pd.concat(
            [self.ptlm.get_pos_vals(keys_collect, posids=posids)[role]
             .set_index('DEVICE_ID') for role in self.ptl_roles])

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
        self.data.test_cfg['commit'] = commit
        self.data.test_cfg['match_radius'] = match_radius
        calib_old = self.collect_calib(self.posids)
        do_move = True
        if tp_target == 'default':  # tp_target as target
            poslocTP = (0, self.data.poslocP)  # same target for all posids
        elif isinstance(tp_target, (tuple, list)) and len(tp_target) == 2:
            poslocTP = tp_target
        else:
            poslocTP, do_move = None, False
        self.logger.info(
            f'Running one-point calibration, mode = {self.data.mode}, '
            f'poslocTP = {poslocTP}, do_move = {do_move}, '
            f'commit = {commit}')
        rows = []
        if do_move:  # then build requests and make the moves
            for posid in self.posids:
                role = self.ptl_role_lookup(posid)
                posintTP = self.ptlm.postrans(posid,
                                              'poslocTP_to_posintTP', poslocTP,
                                              participating_petals=role)[role]
                rows.append({'DEVICE_ID': posid,
                             'COMMAND': 'posintTP',
                             'X1': posintTP[0],
                             'X2': posintTP[1],
                             'LOG_NOTE': f'{self.data.mode}'})
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
        if self.data.mode == '1p_offsetsTP':
            update_mode = 'offsetsTP'
        elif self.data.mode == '1p_posintTP':
            update_mode = 'posTP'
        elif self.data.mode == '1p_offsetTposintP':
            update_mode = 'offsetTposP'
        # if isinstance(updates, dict):
        #     updates = pd.concat(list(updates.values()))
        updates = (
            self.ptlm.test_and_update_TP(
                used_pos.reset_index(), mode=update_mode, auto_update=commit,
                tp_updates_tol=0, tp_updates_fraction=1)
            .set_index('DEVICE_ID').sort_index()).rename(
                columns={'FLAGS': 'FLAG',
                         'MEAS_FLATX': 'mea_flatX', 'MEAS_FLATY': 'mea_flatY',
                         'EXP_FLATX': 'exp_flatX', 'EXP_FLATY': 'exp_flatY'})
        cols = [col for col in updates.columns  # columns to drop
                if 'OLD_' in col or 'NEW_' in col]
        updates.drop(cols, axis=1, inplace=True)  # clean up update df
        for df in [used_pos, unused_pos]:
            df.rename(columns={'Q': 'mea_Q', 'S': 'mea_S',
                               'DQ': 'mea_dQ', 'DS': 'mea_dS',
                               'FLAGS': 'FLAG'}, inplace=True)
        # List unmeasured positioners in updates, even with no data
        calib_up = used_pos.join(updates).append(unused_pos, sort=False)
        # overwrite flags with focalplane flags and add status
        flags_dicts = self.ptlm.get_pos_flags(list(calib_up.index))
        flags = [pd.DataFrame.from_dict(
                     flags_dict, orient='index', columns=['FLAG'])
                 for flags_dict in flags_dicts]
        calib_up['FLAG'] = pd.concat(flags)
        calib_up['STATUS'] = pc.decipher_posflags(calib_up['FLAG'])
        # clean up and record additional entries in updates
        calib_up['tgt_posintT'] = req.set_index('DEVICE_ID')['X1']
        calib_up['tgt_posintP'] = req.set_index('DEVICE_ID')['X2']
        calib_new = self.collect_calib(self.posids)
        self.data.write_calibdf(calib_old, calib_up, calib_new)

    def run_arc_calibration(self, match_radius=50, interactive=False):
        if interactive:
            # commit = self._parse_yn(input(
            #             'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.run_arc_calibration(match_radius=match_radius)
        self.data.test_cfg['match_radius'] = match_radius
        calib_old = self.collect_calib(self.posids)
        self.logger.info(
            f'Running arc calibration, n_pts_T = {self.data.n_pts_T}, '
            f'n_pts_P = {self.data.n_pts_P}, with no automatic DB commit')
        # req_list_T, req_list_P = self.ptlm.get_arc_requests(  # build req
        #     ids=self.posids,
        #     n_points_T=self.data.n_pts_T, n_points_P=self.data.n_pts_P)
        ret = self.ptlm.get_arc_requests(
            ids=self.posids,
            n_points_T=self.n_points_T, n_points_P=self.n_points_P)
        if isinstance(ret, dict):
            print('fix me! get_arc_requests returned dict')
            import pdb; pdb.set_trace()
            req_list_T = []
            req_list_P = []
            for i in range(self.n_points_T):
                dflist = [df[0][i] for df in ret.values()]
                req_list_T.append(pd.concat(dflist).reset_index())
            for j in range(self.n_points_P):
                dflist = [df[1][j] for df in ret.values()]
                req_list_P.append(pd.concat(dflist).reset_index())
        else:
            print('fix me! get_arc_requests returned tuple/list')
            import pdb; pdb.set_trace()
            req_list_T = ret[0]
            req_list_P = ret[1]
        T_data = []  # move, measure
        for i, req in enumerate(req_list_T):
            self.logger.info(f'Measuring theta arc point {i+1} of '
                             f'{len(req_list_T)}...')
            T_data.append(self.move_measure(req, match_radius=match_radius))
            if i+1 < len(req_list_T):  # no pause after the last iteration
                self.pause()
        P_data = []
        for i, req in enumerate(req_list_P):
            self.logger.info(f'Measuring phi arc point {i+1} of '
                             f'{len(req_list_P)}...')
            if i+1 < len(req_list_T):  # pause before first iteration
                self.pause()
            P_data.append(self.move_measure(req, match_radius=match_radius))
        # put all arc measurement data in one dataframe
        T_arc = pd.concat(T_data, keys=range(self.data.n_pts_T))
        P_arc = pd.concat(P_data, keys=range(self.data.n_pts_P))
        data_arc = pd.concat([T_arc, P_arc], keys=['T', 'P'],
                             names=['axis', 'target_no', 'DEVICE_ID'])
        data_arc.to_pickle(os.path.join(self.data.dir, 'data_arc.pkl.gz'),
                           compression='gzip')
        # run fitting
        fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                 printfunc=self.logger.info)
        self.data.movedf, calib_fit = fit.calibrate_from_arc_data(data_arc)
        calib_new = self.collect_calib(self.posids)
        self.data.write_calibdf(calib_old, calib_fit, calib_new)

    def run_grid_calibration(self, match_radius=50,
                             interactive=False):
        if interactive:
            # commit = self._parse_yn(input(
            #             'Automatically update calibration? (y/n): '))
            match_radius = float(input(
                    'Please provide a spotmatch radius: '))
            return self.run_grid_calibration(match_radius=match_radius)
        self.data.test_cfg['match_radius'] = match_radius
        calib_old = self.collect_calib(self.posids)
        self.logger.info(
            f'Running grid calibration, n_pts_T = {self.data.n_pts_T}, '
            f'n_pts_P = {self.data.n_pts_P}, with no automatic DB commit')
        # req_list = self.ptl.get_grid_requests(ids=self.posids,
        #                                       n_points_T=self.data.n_pts_T,
        #                                       n_points_P=self.data.n_pts_P)
        ret = self.ptlm.get_grid_requests(ids=self.posids,
                                          n_points_T=self.n_points_T,
                                          n_points_P=self.n_points_P)
        if isinstance(ret, dict):
            print('fix me! get_grid_requests returned dict')
            import pdb; pdb.set_trace()
            req_list = []
            for i in range(self.n_points_P*self.n_points_T):
                dflist = []
                for df in ret.values():
                    dflist.append(df[i])
                req_list.append(pd.concat(dflist))
        else:
            print('fix me! get_grid_requests returned request list')
            import pdb; pdb.set_trace()
            req_list = ret
        grid_data = []  # move, measure
        for i, request in enumerate(req_list):
            self.logger.info(
                f'Measuring grid point {i+1} of {len(req_list)}...')
            grid_data.append(self.move_measure(request,
                                               match_radius=match_radius))
            if i+1 < len(req_list):  # no pause after the last iteration
                self.pause()
        data_grid = pd.concat(grid_data, keys=range(len(req_list)),
                              names=['target_no', 'DEVICE_ID'])
        data_grid.to_pickle(os.path.join(self.data.dir, 'data_grid.pkl.gz'),
                            compression='gzip')
        # run fitting
        fit = PosCalibrationFits(petal_alignments=self.petal_alignments,
                                 printfunc=self.logger.info)
        self.data.movedf, calib_fit = fit.calibrate_from_grid_data(data_grid)
        calib_new = self.collect_calib(self.posids)
        self.data.write_calibdf(calib_old, calib_fit, calib_new)

    @property
    def petal_alignments(self):
        return {self._role2pcid(role): ptl.alignment
                for role, ptl in self.ptlm.Petals.items()}

    def move_measure(self, request, match_radius=50):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Returns data merged with request
        '''
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
    path = "/data/focalplane/logs/kpno/20191222/00034382/data_grid.pkl.gz"
    data_grid = pd.read_pickle(path)
    fit = PosCalibrationFits()
    movedf, calib_fit = fit.calibrate_from_grid_data(data_grid)
