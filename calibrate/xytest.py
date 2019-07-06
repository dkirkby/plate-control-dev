# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong (dyt@physics.bu.edu)
"""
import os
import sys
import numpy as np
import pandas as pd
import posconstants as pc
from configobj import ConfigObj
sys.path.append('../pecs')
from pecs import PECS
from fptestdata import FPTestData
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
        self.data.posids_ptl    dict with ptlid as key, list of posids as value
                                posids are sorted
        self.data.posdf         dataframe with DEVICE_ID as index and columns:
                                ptlid, PETAL_LOC, DEVICE_LOC, calibration
                                constants and posmodel properties
                                for lookup and coordinate conversion
                                every petal block is contiguous and records
                                within are sorted by posid
        self.data.movedf        dataframe for positioner move data, with
                                (target_no, DEVICE_ID) as index and
                                conventional columns found in previous csv
        self.data.targets_pos   targets dictionary by DEVICE_ID
    """

    def __init__(self, xytest_name, xytest_cfg):
        """Templates for config are found on svn
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        # self.data.test_cfg = xytest_cfg
        self.data = FPTestData(xytest_name, xytest_cfg)
        self.loggers = self.data.loggers  # use these loggers to write to logs
        self.logger = self.data.logger
        # petalids are just ints now, DB and DOS have forced the conversion
        printfuncs = {pid: self.loggers[pid].info for pid in self.data.ptlids}
        PECS.__init__(self, ptlids=self.data.ptlids, printfunc=printfuncs)
        self.enable_debugg_log()
        self._get_pos_info()
        self.generate_targets()  # generate local targets or load from file
        self.logger.info([
            f'PlateMaker instrument: {self.platemaker_instrument}',
            f'FVC role: {self.fvc_role}',
            f'Max num of corrections: {self.data.num_corr_max}',
            f'Num of local targets: {len(self.data.targets)}'])
        self.logger.debug(f'Local targets xy positions:\n{self.data.targets}')
        self.data.initialise_movedata(self.data.posids, self.data.ntargets)
        self.run_xyaccuracy_test(disable_unmatched=True)
        self.data.save_test_products()

    def enable_debugg_log(self):
        # for ptlid in self.data.ptlids:
        #     self.ptls[ptlid].enable_debug_products
        pass

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
        props = ['targetable_range_T']  # posT to be converted to obsT
        self.data.posids = []
        self.data.posids_ptl = {}
        dfs = []
        for ptlid in self.data.ptlids:  # TODO: parallelise this?
            mode = self.data.test_cfg[ptlid]['mode']
            ptl = self.ptls[ptlid]  # use as a PetalApp instance, ptlid is int
            if mode == 'all':
                l0 = ptl.get_positioners(enabled_only=False)
                l1 = ptl.get_positioners(enabled_only=True)
            elif mode == 'pos':
                l0 = self.data.test_cfg[ptlid]['posids']
                l1 = ptl.get_positioners(enabled_only=True, posids=l0)
            elif mode == 'can':
                busids = self.data.test_cfg[ptlid]['busids']
                l0 = ptl.get_positioners(enabled_only=False, busids=busids)
                l1 = ptl.get_positioners(enabled_only=True, busids=busids)
            Nr = len(l0)  # number of requested positioners
            Ne = len(l1)  # nubmer of returned enabled postiioners
            Nd = Nr - Ne  # number of disabled positioners, inferred
            self.loggers[ptlid].info(f'Number of requested positioners: {Nr}')
            self.loggers[ptlid].info(
                'Numbers of enabled, disabled, and total positioners: '
                f'{Ne} + {Nd} = {Ne + Nd}')
            l1 = l1.set_index('DEVICE_ID').sort_index()  # sorted within ptl
            self.data.posids_ptl[ptlid] = posids = l1.index.tolist()
            self.data.posids += posids
            # add to existing positioner index table, first calibration values
            l1['PETAL_ID'] = ptlid  # add petal id as string column
            ret1 = (self.ptls[ptlid].get_pos_vals(keys, posids)
                    .set_index('DEVICE_ID'))
            self.loggers[ptlid].debug(f'Calibration read:\n{ret1.to_string()}')
            # read posmodel properties, for now just targetable_range_T
            ret2 = (self.ptls[ptlid].get_posmodel_prop(props, posids)
                    .set_index('DEVICE_ID'))
            self.loggers[ptlid].debug(f'PosModel properties read:\n'
                                      f'{ret2.to_string()}')
            dfs.append(l1.join(ret1).join(ret2))
        self.data.posdf = pd.concat(dfs)

    @staticmethod
    def _generate_posXY_targets_grid(rmin, rmax, npts):
        x, y = np.mgrid[-rmax:rmax:npts*1j, -rmax:rmax:npts*1j]  # 1j is step
        r = np.sqrt(np.square(x) + np.square(y))
        mask = (rmin < r) & (r < rmax)
        return np.array([x[mask], y[mask]])  # return 2 x N array of targets

    def generate_targets(self):
        path = self.data.test_cfg['input_targs_file']
        if path is None:  # no targets supplied, create local targets in posXY
            tgt = self._generate_posXY_targets_grid(
                self.data.test_cfg['targ_min_radius'],
                self.data.test_cfg['targ_max_radius'],
                self.data.test_cfg['n_pts_across_grid']).T  # shape (N, 2)
        else:  # input target table shoud have two colummns (posX, posY)
            assert os.path.isfile(path), f'Invald target file path: {path}'
            tgt = np.genfromtxt(path, delimiter=',')  # load csv file
            assert tgt.shape[1] == 2, 'Targets should be of dimension (N, 2)'
        self.data.targets = tgt
        self.data.ntargets = tgt.shape[0]  # shape (N_targets, 2)
        if self.data.test_cfg['shuffle_targets']:  # target shuffling logic
            if self.data.test_cfg['shuffle_seed'] is None:  # posid as seed
                self.data.targets_pos = {}  # different targets for each pos
                for posid in self.data.posids:
                    np.random.seed(int(posid[1:]))  # only the numeral part
                    np.random.shuffle(tgt)  # numpy shuffles in place
                    self.data.targets_pos[posid] = tgt  # shape (N, 2)
            else:  # use the same given seed for all posids
                np.random.seed(self.data.test_cfg['shuffle_seed'])
                np.random.shuffle(tgt)  # same shuffled target list for all
                self.data.targets_pos = {pid: tgt for pid in self.data.posids}
        else:  # same targets for all positioners
            self.data.targets_pos = {pid: tgt for pid in self.data.posids}

    def _add_device_id_col(self, df, ptlid):
        '''when df only has DEVICE_LOC, add DEVICE_ID column and use as index
           this method may not be needed anymore after PetalApp updatp
        '''
        df0 = self.data.posdf[self.data.posdf['PETAL_ID'] == ptlid]
        return df.merge(df0, on=['PETAL_LOC', 'DEVICE_LOC'],
                        left_index=True).sort_index()

    def _update(self, newdf, i):
        '''newdf is single-index on posid only'''
        newdf = newdf.set_index(pd.MultiIndex.from_product([[i], newdf.index]))
        self.data.movedf.update(newdf)  # write to movedf

    def run_xyaccuracy_test(self, disable_unmatched=True):
        # led_initial = self.illuminator.get('led')  # no illuminator ctrl yet
        # self.illuminator.set(led='ON')  # turn on illuminator
        t_i = self.data.now
        for i in range(self.data.ntargets):  # test loop over all test targets
            self.logger.info(f'Target {i+1} of {self.data.ntargets}')
            self.record_basic_move_data(i)  # for each target, record basics
            for n in range(self.data.num_corr_max + 1):
                self.logger.info(
                    f'Target {i+1} of {self.data.ntargets}, '
                    f'submove {n} of {self.data.num_corr_max}')
                measured_QS = self.move_measure(i, n)  # includes 10 petals
                self.check_unmatched(measured_QS, disable_unmatched)
                self.update_calibrations(measured_QS)
                self.record_measurement(measured_QS, i, n)
                self.calculate_xy_errors(i, n)
        t_f = self.data.now
        self.logger.info(f'Test complete, duration {t_f - t_i}. Plotting...')
        for ptlid in self.data.ptlids:
            self.ptls[ptlid].schedule_stats.save()
        # self.illuminator.set(led=led_initial)  # restore initial LED state

    def record_basic_move_data(self, i):
        self.logger.info('Recording basic move data for new xy target...')
        movedf = self.data.movedf
        # before moving for each target, write time cycle etc. for all posids
        movedf.loc[idx[i, :], 'timestamp'] = self.data.now
        movedf.loc[idx[i, :], 'move_log'] = \
            'local posmove csv log deprecated; check posmoveDB instead.'
        for ptlid in self.data.ptlids:
            ptl, posids = self.ptls[ptlid], self.data.posids_ptl[ptlid]
            cycles = (ptl.get_pos_vals(['TOTAL_MOVE_SEQUENCES'], posids)
                      .rename(columns={'TOTAL_MOVE_SEQUENCES': 'cycle'}))
            # store other posstate values here
            self._update(cycles.set_index('DEVICE_ID'), i)

    def move_measure(self, i, n):
        '''one complete iteration: move ten petals once, measure once
        ith target, nth move'''
        movedf = self.data.movedf
        # move ten petals
        expected_QS_list = []  # each item is a dataframe for one petal
        for ptlid in self.data.ptlids:  # TODO: parallelise this
            posids = self.data.posids_ptl[ptlid]  # all records obey this order
            ptl = self.ptls[ptlid]
            # device_loc = self.data.posdf.loc[posids, 'DEVICE_LOC']
            if n == 0:  # blind move
                posXY = np.vstack(   # shape (N_posids, 2)
                    [self.data.targets_pos[posid][i, :] for posid in posids])
                movetype, cmd = 'blind', 'obsXY'
                offXY = self.data.posdf.loc[posids, ['OFFSET_X', 'OFFSET_Y']]
                tgt = posXY + offXY.values  # convert to obsXY, shape (N, 2)
                movedf.loc[idx[i, posids], ['target_x', 'target_y']] = tgt
            else:
                movetype, cmd = 'corrective', 'dXdY'
                tgt = - movedf.loc[idx[i, posids],  # note minus sign
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
            self.loggers[ptlid].debug(f'Move requests:\n{req.to_string()}')
            ptl.prepare_move(req, anticollision=self.data.anticollision)
            expected_QS = ptl.execute_move(return_coord='QS')
            self.loggers[ptlid].debug('execute_move() returns expected QS:\n'
                                      + expected_QS.to_string())
            expected_QS_list.append(expected_QS)
            # # get expected posTP from petal and write to movedf after move
            ret_TP = (ptl.get_positions(posids=posids, return_coord='posTP')
                      .set_index('DEVICE_ID'))
            self.loggers[ptlid].debug(f'Expected posTP after move {n}:\n'
                                      + ret_TP.to_string())
            # write posTP for a petal to movedf
            new = pd.DataFrame({f'pos_t_{n}': ret_TP['X1'],
                                f'pos_p_{n}': ret_TP['X2']},
                               dtype=np.float32, index=ret_TP.index)
            self._update(new, i)
        # combine expected QS list for all petals to form a single dataframe
        expected_QS = pd.concat(expected_QS_list)
        # measure ten petals with FVC at once, FVC after all petals have moved
        measured_QS = (pd.DataFrame(self.fvc.measure(expected_QS))
                       .rename(columns={'id': 'DEVICE_ID'})
                       .set_index('DEVICE_ID'))
        measured_QS.columns = measured_QS.columns.str.upper()  # rename upper
        self.logger.debug(f'FVC measured_QS:\n{measured_QS.to_string()}')
        return measured_QS

    def check_unmatched(self, measured_QS, disable_unmatched):
        for ptlid in self.data.ptlids:  # check unmatched positioners
            posids = self.data.posids_ptl[ptlid]
            if not set(posids).issubset(set(measured_QS.index)):
                matched = set(posids).intersection(set(measured_QS.index))
                unmatched = set(posids) - matched
                self.logger.warning(
                    'Please check the numbers: # unmatched spots = '
                    '# broken fibres + 2 ETC fibres + # unmatched fibres\n'
                    f'{len(unmatched)} of {len(posids)} requested devices '
                    f'are missing in FVC measurement, '
                    'possibly including two dark ETC fibres:'
                    f':\n{unmatched}')
                for posid in unmatched:  # log unmatched
                    self.loggers[ptlid].debug(
                        f'Missing posid: {posid}, pos details:\n'
                        f'{self.data.posdf.loc[posid].to_string()}')
                if disable_unmatched:  # log unmatched and disable them
                    # if anticolliions is on, disable positioner and neighbours
                    self.loggers[ptlid].info(
                        f'Disabling unmatched fibres and their neighbours:\n'
                        f'{unmatched}')
                    disabled = self.ptls[ptlid].disable_pos_and_neighbors(
                        list(unmatched))
                    self.loggers[ptlid].info(
                        f'Disabled {len(disabled)} positioners:\n{disabled}')
                    assert set(unmatched).issubset(set(disabled))
                    # remove disabled posids from self attributes
                    self.data.posids = [posid for posid in self.data.posids
                                        if posid not in disabled]
                    self.data.posids_ptl[ptlid] = [posid for posid in posids
                                                   if posid not in disabled]
            else:
                self.loggers[ptlid].info(
                    f'All {len(posids)} requested fibres measured by FVC.')

    def update_calibrations(self, measured_QS):  # test and update TP here
        self.logger.info('Testing and updating posTP...')
        for ptlid in self.data.ptlids:
            posids = set(self.data.posids_ptl[ptlid]).intersection(
                set(measured_QS.index))  # only update measured, valid posid
            df = measured_QS.loc[posids].reset_index()
            assert ('Q' in df.columns and 'S' in df.columns), f'df.columns'
            updates = self.ptls[ptlid].test_and_update_TP(df)
            assert type(updates) == pd.core.frame.DataFrame, (
                f'Exception calling test_and_update_TP, returned:\n'
                f'{updates}')
            self.loggers[ptlid].debug(f'test_and_update_TP returned:\n'
                                      f'{updates.to_string()}')

    def record_measurement(self, measured_QS, i, n):
        # calculate below measured obsXY from measured QS and write to movedf
        q_rad = np.radians(measured_QS['Q'])
        r = pc.S2R_lookup(measured_QS['S'])
        new = pd.DataFrame({f'meas_x_{n}': r * np.cos(q_rad),
                            f'meas_y_{n}': r * np.sin(q_rad)},
                           dtype=np.float32, index=measured_QS.index)
        self._update(new, i)

    def calculate_xy_errors(self, i, n):  # calculate xy error columns in df
        movedf = self.data.movedf
        # convenience functin c returns a column of the movedf for all pos
        def c(col_name): return movedf.loc[idx[i], [col_name]].values
        movedf.loc[idx[i], [f'err_x_{n}']] = c(f'meas_x_{n}') - c('target_x')
        movedf.loc[idx[i], [f'err_y_{n}']] = c(f'meas_y_{n}') - c('target_y')
        movedf.loc[idx[i], [f'err_xy_{n}']] = np.linalg.norm(
                np.hstack([c(f'err_x_{n}'), c(f'err_y_{n}')]), axis=1)
        for ptlid in self.data.ptlids:  # log of error after each move
            err = (movedf.loc[idx[i, self.data.posids_ptl[ptlid]],
                              [f'err_x_{n}', f'err_y_{n}', f'err_xy_{n}']]
                   .sort_values(f'err_xy_{n}', ascending=False))
            errXY = err[f'err_xy_{n}'].values * 1000  # to microns
            self.loggers[ptlid].info(
                f'\nSUBMOVE: {n}, errXY for all positioners:\n'
                f'    max: {np.max(errXY):6.1f} μm\n'
                f'    rms: {np.sqrt(np.mean(np.square(errXY))):6.1f} μm\n'
                f'    avg: {np.mean(errXY):6.1f} μm\n'
                f'    min: {np.min(errXY):6.1f} μm')
            self.loggers[ptlid].info('Worst 10 positioners:\n'
                                     f'{err.iloc[:10].to_string()}')


if __name__ == "__main__":
    path = os.path.join(pc.dirs['test_settings'], 'xytest_ptl3_debug.cfg')
    xytest_cfg = ConfigObj(path, unrepr=True, encoding='utf_8')  # read cfg
    xytest_name = input('Please name this test: ')
    test = XYTest(xytest_name, xytest_cfg)
