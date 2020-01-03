# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import numpy as np
import pandas as pd
from configobj import ConfigObj
import posconstants as pc
from pecs import PECS
from fptestdata import XYTestData
idx = pd.IndexSlice  # pandas slice for selecting slice using multiindex


class XYTest(PECS):
    """Class for running fiber positioner xy accuracy test.
    Avoiding double inheritance from FPTestData as we want to isolate the data
    class for easy pickling, which would otherwise be rather difficult.
    All data go under self.data; self.attribute only for test methods.

    if input_targs_file is given in the test config, the ordering of targets
    strictly follows the list, no check of the sweep pattern or shuffling.

    To run tests in simulation mode, one has to first initiliase petal and fvc
    in simulation mode as DOS apps using architect. Then this test script will
    connect to these apps via proxies.
    Also need to check PECS default cfg has the correct platemaker_instrument
    and fvc_role that work for all ten petals.

    Input:
        xytest_name:    string, name of the test for folder creation
        xytest_cfg:     one config object for xy test settings

    Useful attributes:
        self.data.posids        list of posids for all petals
        self.data.posids_pc    dict with pcid as key, list of posids as value
                                posids are sorted
        self.data.posdf         dataframe with DEVICE_ID as index and columns:
                                pcid, PETAL_LOC, DEVICE_LOC, calibration
                                constants and posmodel properties
                                for lookup and coordinate conversion
                                every petal block is contiguous and records
                                within are sorted by posid
        self.data.movedf        dataframe for positioner move data, with
                                (target_no, DEVICE_ID) as index and
                                conventional columns found in previous csv
        self.data.targets_pos   targets dictionary by DEVICE_ID
    """

    def __init__(self, test_name, test_cfg):
        """Templates for config are found on svn
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        self.data = XYTestData(test_name, test_cfg=test_cfg)
        self.loggers = self.data.loggers  # use these loggers to write to logs
        self.logger = self.data.logger  # broadcast to all petals
        super().__init__(
            printfunc={p: self.loggers[p].info for p in self.data.pcids})
        self.data.t_i = pc.now()  # set initial time before setting dirs
        self.exp_setup()  # set up exposure ID and product directory
        if 'pause_interval' in test_cfg:  # override default pecs settings
            self.logger.info(
                f"Overriding default pause interval {self.pause_interval} s "
                f"with {test_cfg['pause_interval']} s")
            self.pause_interval = test_cfg['pause_interval']
        self._get_pos_info()
        self.generate_targets()  # generate local targets or load from file
        self.logger.info([
            f'PlateMaker instrument: {self.pm_instrument}',
            f'FVC role: {self.fvc_role}',
            f'Max num of corrections: {self.data.num_corr_max}',
            f'Num of local targets: {self.data.ntargets}'])
        self.logger.debug(f'Test targets:\n{self.data.targets_pos}')
        self.data.initialise_movedata(self.data.posids, self.data.ntargets)
        for ptl in self.ptls:
            ptl.set_schedule_stats(enabled=True)

    def _lookup_pcid(self, posid):
        for pcid, posids in self.data.posids_pc.items():
            if posid in posids:
                return pcid
            else:
                pass
        return None

    def _get_pos_info(self):
        '''get enabled positioners, according to given posids or busids
        also load pos calibration values for each positioner
        which are not expected to change during the test.
        read them before test so transform can be more efficient
        unfortunately all positioner states are stored completely separately,
        but still we can sort of vectorise the XY and TP transformations
        which are particularly simple and should been vectorised
        '''
        keys = ['LENGTH_R1', 'LENGTH_R2', 'OFFSET_X', 'OFFSET_Y',
                'OFFSET_T', 'OFFSET_P']
        props = ['targetable_range_T', 'targetable_range_P']
        self.data.posids = []
        self.data.posids_pc = {}
        self.data.posids_disabled = set()
        self.data.posids_disabled_pc = {}
        dfs = []
        for pcid in self.data.pcids:  # fast enough, no need to parallelise
            self.data.posids_disabled_pc[pcid] = set()
            mode = self.data.test_cfg[pcid]['mode']
            ptl = self.ptls[pcid]  # use as a PetalApp instance, pcid is int
            if mode == 'all':
                l0 = ptl.get_positioners(enabled_only=False)
                l1 = ptl.get_positioners(enabled_only=True)
            elif mode == 'pos':
                l0 = self.data.test_cfg[pcid]['posids']
                l1 = ptl.get_positioners(enabled_only=True, posids=l0)
            elif mode == 'can':
                busids = self.data.test_cfg[pcid]['busids']
                l0 = ptl.get_positioners(enabled_only=False, busids=busids)
                l1 = ptl.get_positioners(enabled_only=True, busids=busids)
            Nr = len(l0)  # number of requested positioners
            Ne = len(l1)  # nubmer of returned enabled postiioners
            Nd = Nr - Ne  # number of disabled positioners, inferred
            self.loggers[pcid].info(f'Number of requested positioners: {Nr}')
            self.loggers[pcid].info(
                'Numbers of enabled, disabled, and total positioners: '
                f'{Ne} + {Nd} = {Ne + Nd}')
            l1 = l1.set_index('DEVICE_ID').sort_index()  # sorted within ptl
            self.data.posids_pc[pcid] = posids = l1.index.tolist()
            self.data.posids += posids
            # add to existing positioner index table, first calibration values
            l1['PCID'] = pcid  # add pcid as a column
            ret1 = (self.ptls[pcid].get_pos_vals(keys, posids)
                    .set_index('DEVICE_ID'))
            self.loggers[pcid].debug(f'Calibration read:\n{ret1.to_string()}')
            # read posmodel properties, for now just targetable_range_T
            ret2 = (self.ptls[pcid].get_posmodel_prop(props, posids)
                    .set_index('DEVICE_ID'))
            self.loggers[pcid].debug(f'PosModel properties read:\n'
                                     f'{ret2.to_string()}')
            dfs.append(l1.join(ret1).join(ret2))
        self.data.posdf = pd.concat(dfs)

    @staticmethod
    def _generate_poslocXY_targets_grid(rmin, rmax, npts):
        x, y = np.mgrid[-rmax:rmax:npts*1j, -rmax:rmax:npts*1j]  # 1j is step
        r = np.sqrt(np.square(x) + np.square(y))
        mask = (rmin < r) & (r < rmax)
        return np.array([x[mask], y[mask]])  # return 2 x N array of targets

    def generate_targets(self, ntargets=None):
        fn = self.data.test_cfg['input_targs_file']
        if fn is None:  # no targets supplied, create local targets in posXY
            tgt = self._generate_poslocXY_targets_grid(
                self.data.test_cfg['targ_min_radius'],
                self.data.test_cfg['targ_max_radius'],
                self.data.test_cfg['n_pts_across_grid']).T  # shape (N, 2)
            if self.data.test_cfg['shuffle_targets']:  # target shuffling logic
                if self.data.test_cfg['shuffle_seed'] is None:  # posid as seed
                    self.data.targets_pos = {}  # keyed by posid
                    for posid in self.data.posids:
                        np.random.seed(int(posid[1:]))  # only the numeral part
                        np.random.shuffle(tgt)  # numpy shuffles in place
                        self.data.targets_pos[posid] = tgt  # shape (N, 2)
                else:  # use the same given seed for all posids
                    np.random.seed(self.data.test_cfg['shuffle_seed'])
                    np.random.shuffle(tgt)  # same shuffled target list for all
            if ntargets is not None:
                tgt = tgt[:ntargets, :]
            self.data.targets = tgt
            self.data.targets_pos = {posid: tgt for posid in self.data.posids}
            self.data.ntargets = tgt.shape[0]  # shape (N_targets, 2)
            self.data.target_type = 'poslocXY'
        else:  # use input target table, see xytest_psf.csv as an exampl
            path = os.path.join(pc.dirs['test_settings'], fn)
            assert os.path.isfile(path), f'Invald target file path: {path}'
            self.data.targets = path
            # set move command according to target type
            self.data.target_type = self.data.test_cfg['target_type']
            acceptable_types = ['poslocTP', 'obsXY']
            if self.data.target_type not in acceptable_types:
                self.logger.error('Bad target type')
                raise ValueError(
                    f'Bad target type, acceptable: {acceptable_types}')
            col1 = self.data.target_type[:-1]
            col2 = self.data.target_type[:-2] + self.data.target_type[-1]
            self.data.targets_pos = {}
            df = pd.read_csv(path, index_col='target_no')
            if ntargets is not None:
                df = df.iloc[:ntargets]
            self.data.ntargets = len(df)  # set number of targets
            for pcid in self.data.pcids:  # set targets for each positioner
                for posid in self.data.posids_pc[pcid]:
                    i = self.data.posdf.loc[posid]['DEVICE_LOC']
                    if f'{col1}_{i}' in df.columns:
                        self.data.targets_pos[posid] = (
                            df[[f'{col1}_{i}', f'{col2}_{i}']].values)
                    else:
                        self.logger.warning(
                            'Missing target assignment for device_loc '
                            f'{i}, posid {posid}')
        assert self.data.ntargets > 0, 'Empty target list, exiting...'

    def _add_device_id_col(self, df, pcid):
        '''when df only has DEVICE_LOC, add DEVICE_ID column and use as index
           this method may not be needed anymore after PetalApp update
        '''
        df0 = self.data.posdf[self.data.posdf['PCID'] == pcid]
        return df.merge(df0, on=['PETAL_LOC', 'DEVICE_LOC'],
                        left_index=True).sort_index()

    def _update(self, newdf, i):
        '''input newdf is single-index on posid only'''
        newdf = newdf.set_index(pd.MultiIndex.from_product([[i], newdf.index]))
        self.data.movedf.update(newdf)  # write to movedf

    def run_xyaccuracy_test(self, disable_unmatched=None):
        if disable_unmatched is None:
            if 'disable_unmatched' in self.data.test_cfg:
                disable_unmatched = self.data.test_cfg['disable_unmatched']
            else:
                disable_unmatched = True  # do disable by default
        self.logger.info(f'Starting Test at {self.data.t_i}')
        for i in range(self.data.ntargets):  # test loop over all test targets
            self.logger.info(f'Target {i+1} of {self.data.ntargets}')
            self.record_basic_move_data(i)  # for each target, record basics
            for n in range(self.data.num_corr_max + 1):
                self.logger.info(
                    f'Target {i+1} of {self.data.ntargets}, '
                    f'submove {n} of {self.data.num_corr_max}')
                self.expected_QS_list = []
                _, meapos, matched, unmatched = self.move_measure_petals(i, n)
                self.check_unmatched(meapos, matched, unmatched,
                                     disable_unmatched=disable_unmatched)
                self.update_calibrations(meapos)
                self.record_measurement(meapos, i, n)
                self.calculate_xy_errors(i, n)
            if i+1 < self.data.ntargets:  # no pause after the last target
                self.pause()
        self.data.t_f = pc.now()
        self.data.delta_t = self.data.t_f - self.data.t_i
        self.logger.info(f'Test complete, duration {self.data.delta_t}.')
        try:
            for pcid in self.data.pcids:
                self.data.schedstats[pcid] = (
                    self.ptls[pcid].schedule_stats.generate_table())
                self.ptls[pcid].set_schedule_stats(enabled=False)
        except Exception:
            self.logger.debug('Failed to generate schedule stats table')

    def record_basic_move_data(self, i):
        self.logger.info('Recording basic move data for new xy target...')
        movedf = self.data.movedf
        # before moving for each target, write time cycle etc. for all posids
        movedf.loc[idx[i, :], 'timestamp'] = pc.now()
        movedf.loc[idx[i, :], 'move_log'] = (
            f'xytest: {i}th target; check posmoveDB.')
        for pcid in self.data.pcids:
            ptl, posids = self.ptls[pcid], self.data.posids_pc[pcid]
            cycles = (ptl.get_pos_vals(['TOTAL_MOVE_SEQUENCES'], posids)
                      .rename(columns={'TOTAL_MOVE_SEQUENCES': 'cycle'}))
            # store other posstate values here
            self._update(cycles.set_index('DEVICE_ID'), i)

    def move_measure_petals(self, i, n):
        '''move ten petals once, measure once for the ith target, nth move'''
        [self.move_petal(pcid, i, n) for pcid in self.data.pcids]
        # combine expected QS list for all petals to form a single dataframe
        # measure ten petals with FVC at once, FVC after all petals have moved
        _, meapos, matched, unmatched = self.fvc_measure()
        self.logger.debug(f'FVC measured_QS:\n'
                          f'{meapos.reset_index().to_string()}')
        return meapos, matched, unmatched

    def move_petal(self, pcid, i, n):
        movedf = self.data.movedf
        posids = self.data.posids_pc[pcid]  # all records obey this order
        ptl = self.ptls[pcid]
        if n == 0:  # blind move, issue cmd in obsXY for easy check with FVC
            self.logger.info(f'Setting up target {i} in poslocXY...')
            movetype, cmd = 'blind', 'poslocXY'
            for posid in posids:  # write targets to move df
                if posid not in self.data.targets_pos.keys():
                    continue
                tgt = self.data.targets_pos[posid][i, :]  # two elements
                if self.data.target_type == 'poslocTP':
                    tgt = ptl.postrans(posid, 'poslocTP_to_poslocXY', tgt)
                    posintTP, unreachable = ptl.postrans(
                        posid, 'poslocXY_to_posintTP', tgt, 'targetable')
                    if unreachable:
                        self.logger.warning(f'{posid} unreachable: {posintTP}')
                    else:
                        self.logger.info(f'{posid} reachable: {posintTP}')
                elif self.data.target_type == 'obsXY':
                    tgt = ptl.postrans(posid, 'obsXY_to_poslocXY', tgt)
                elif self.data.target_type == 'poslocXY':
                    pass
                else:
                    self.logger.error('Bad Target type.')
                    raise ValueError('Bad Target type.')
                movedf.loc[idx[i, posid], ['tgt_x', 'tgt_y']] = tgt
                movedf.loc[idx[i, posid], ['tgt_q', 'tgt_s']] = (
                    ptl.postrans(posid, 'poslocXY_to_QS', tgt))
            tgt = movedf.loc[idx[i, posids], ['tgt_x', 'tgt_y']].values  # Nx2
        else:
            movetype, cmd = 'corrective', 'poslocdXdY'
            tgt = - movedf.loc[idx[i, posids],  # note minus sign, last move
                               [f'err_x_{n-1}', f'err_y_{n-1}']].values
            tgt = np.nan_to_num(tgt)  # replace NaN with zero for unmatched
        # build move request dataframe for a petal
        note = (f'xytest: {self.data.test_name}; '  # same for all
                f'target {i+1} of {self.data.ntargets}; '
                f'move {n} ({movetype})')
        req = pd.DataFrame({'DEVICE_ID': posids,
                            'COMMAND': cmd,
                            'X1': tgt[:, 0],  # shape (N_posids, 1)
                            'X2': tgt[:, 1],  # shape (N_posids, 1)
                            'LOG_NOTE': note})
        self.loggers[pcid].debug(f'Move requests:\n{req.to_string()}')
        self.loggers[pcid].info(f'Moving positioners...')
        ptl.prepare_move(req, anticollision=self.data.anticollision)
        expected_QS = ptl.execute_move(reset_flags=False, return_coord='QS')
        self.loggers[pcid].debug('execute_move() returns expected QS:\n'
                                 + expected_QS.to_string())
        # get expected posintTP from petal and write to movedf after move
        ret_TP = ptl.get_positions(return_coord='posintTP')
        ret_TP['STATUS'] = ptl.decipher_posflags(ret_TP['FLAG'])
        self.loggers[pcid].debug(f'Expected posintTP after move {n}:\n'
                                 + ret_TP.to_string())
        # record per-move data to movedf for a petal
        new = pd.DataFrame({f'posintT_{n}': ret_TP['X1'],
                            f'posintP_{n}': ret_TP['X2'],
                            f'flag_{n}': ret_TP['FLAG'],
                            f'status_{n}': ret_TP['STATUS'],
                            f'DEVICE_ID': ret_TP['DEVICE_ID']})
        self._update(new.set_index('DEVICE_ID'), i)
        return expected_QS

    def check_unmatched(self, measured_QS, matched, unmatched,
                        disable_unmatched=True):
        for pcid in self.data.pcids:  # check unmatched positioners
            posids = self.data.posids_pc[pcid]
            if not set(posids).issubset(matched):
                matched_pc = set(posids) & matched
                unmatched_pc = set(posids) & unmatched
                self.logger.warning(
                    'Please check the numbers: # unmatched spots = '
                    '# broken fibres + 2 ETC fibres + # unmatched fibres\n'
                    f'{len(unmatched_pc)} of {len(posids)} requested devices '
                    f'are missing in FVC measurement, '
                    'possibly including two dark ETC fibres:'
                    f':\n{unmatched_pc}')
                for posid in unmatched_pc:  # log unmatched fibres to logger
                    self.loggers[pcid].debug(
                        f'Missing posid: {posid}, pos details:\n'
                        f'{self.data.posdf.loc[posid].to_string()}')
                if disable_unmatched:  # disable unmatched fibre positioners
                    # if anticolliions is on, disable positioner and neighbours
                    self.loggers[pcid].info(
                        f'Disabling unmatched fibres and their neighbours:\n'
                        f'{unmatched_pc}')
                    disabled = (
                        self.ptls[pcid].disable_positioner_and_neighbors(
                            list(unmatched_pc)))
                    if disabled is None:
                        disabled = []
                    self.loggers[pcid].info(
                        f'Disabled {len(disabled)} positioners:\n{disabled}')
                    assert unmatched_pc.issubset(set(disabled))
                    # remove disabled posids from self attributes
                    self.data.posids = [posid for posid in self.data.posids
                                        if posid not in disabled]
                    self.data.posids_pc[pcid] = [posid for posid in posids
                                                 if posid not in disabled]
                    # add disabled to disabled sets for bookkeeping
                    self.data.posids_disabled |= set(disabled)
                    self.data.posids_disabled_pc[pcid] |= set(disabled)
            else:
                self.loggers[pcid].info(f'All {len(posids)} requested '
                                        'positioners measured by FVC.')

    def update_calibrations(self, measured_QS):  # test and update TP here
        self.logger.info('Testing and updating posintTP...')
        for pcid in self.data.pcids:
            posids = set(self.data.posids_pc[pcid]) & set(measured_QS.index)
            df = measured_QS.loc[posids].reset_index()
            assert ('Q' in df.columns and 'S' in df.columns), f'{df.columns}'
            updates = self.ptls[pcid].test_and_update_TP(df)
            assert isinstance(updates, pd.core.frame.DataFrame), (
                f'Exception calling test_and_update_TP, returned:\n'
                f'{updates}')
            self.loggers[pcid].debug(f'test_and_update_TP returned:\n'
                                     f'{updates.to_string()}')

    def record_measurement(self, measured_QS, i, n):
        for posid in measured_QS.index:
            if self._lookup_pcid(posid) is None:  # keep only selected posids
                measured_QS.drop(posid, inplace=True)
        QS = measured_QS[['Q', 'S']].values.T  # 2 x N array
        poslocXY = np.zeros(QS.shape)  # empty array
        for j, posid in enumerate(measured_QS.index):
            poslocXY[:, j] = self.ptls[self._lookup_pcid(posid)].postrans(
                posid, 'QS_to_poslocXY', QS[:, j])
        new = pd.DataFrame({f'mea_q_{n}': QS[0, :],
                            f'mea_s_{n}': QS[1, :],
                            f'mea_x_{n}': poslocXY[0, :],
                            f'mea_y_{n}': poslocXY[1, :]},
                           dtype=np.float64, index=measured_QS.index)
        self._update(new, i)

    def calculate_xy_errors(self, i, n):  # calculate xy error columns in df
        movedf = self.data.movedf
        # convenience functin c returns a column of the movedf for all pos
        def c(col_name): return movedf.loc[idx[i], [col_name]].values
        movedf.loc[idx[i], [f'err_x_{n}']] = c(f'mea_x_{n}') - c('tgt_x')
        movedf.loc[idx[i], [f'err_y_{n}']] = c(f'mea_y_{n}') - c('tgt_y')
        movedf.loc[idx[i], [f'err_xy_{n}']] = np.linalg.norm(
                np.hstack([c(f'err_x_{n}'), c(f'err_y_{n}')]), axis=1)
        for pcid in self.data.pcids:  # log of error after each move
            err = (movedf.loc[idx[i, self.data.posids_pc[pcid]],
                              [f'err_x_{n}', f'err_y_{n}', f'err_xy_{n}',
                               f'pos_status_{n}']]
                   .sort_values(f'err_xy_{n}', ascending=False))
            errXY = err[f'err_xy_{n}'].values * 1000  # to microns
            self.loggers[pcid].info(
                f'\nSUBMOVE: {n}, errXY for all positioners:\n'
                f'    max: {np.max(errXY):6.1f} μm\n'
                f'    rms: {np.sqrt(np.mean(np.square(errXY))):6.1f} μm\n'
                f'    avg: {np.mean(errXY):6.1f} μm\n'
                f'    min: {np.min(errXY):6.1f} μm')
            self.loggers[pcid].info('Worst 10 positioners:\n'
                                    f'{err.iloc[:10].to_string()}')


if __name__ == '__main__':
    path = os.path.join(pc.dirs['test_settings'], 'xytest_cmx_psf.cfg')
    print(f'Loading test config: {path}')
    xytest_cfg = ConfigObj(path, unrepr=True, encoding='utf_8')  # read cfg
    xytest_name = input(r'Please name this test (xytest-{test_name}): ')
    test = XYTest('xytest-'+xytest_name, xytest_cfg)
    test.run_xyaccuracy_test(
        disable_unmatched=test.data.test_cfg['disable_unmatched'])
    test.fvc_collect(destination=test.data.dir)
    test.data.generate_data_products()
