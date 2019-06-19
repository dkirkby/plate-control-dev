# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong
"""
import os
import numpy as np
import pandas as pd
from pecs import PECS
import posconstants as pc
from fptestdata import FPTestData

idx = pd.IndexSlice  # pandas slice for selecting slice using multiindex


class XYTest(PECS):
    """XYTest handles running a fiber positioner xy accuracy test.

    Avoiding double inheritance from FPTestData because we want to isolate
    the data class to one attribute for easy pickling, otherwise we would have
    to pickle the entire XYTest class.

    So self.attribute should be used for only test methods and objects,
    all data variables go under self.data which will be stored

    if input_targs_file is given in the config,
    the ordering of targets strictly follows the list and the test script
    doesn't bother with checking the sweep pattern or shuffling.

    to run tests in simulation mode, one has to first initiliase petal and fvc
    in simulation mode as DOS apps. then this test script will connect to
    these apps which are already in simulation mode. the same goes for changing
    anti-collision/poscollider settings.

    Need to check that PECS default cfg has the correct platemaker_instrument
    and fvc_role that work for all ten petals.

    Input:
        petal_cfgs:     list of petal config objects, one for each petal
        xytest_cfg:     one config object for xy test settings

    Useful attributes:
        self.data.posids        list of posids
        self.data.posids_ptl    dict with ptlid as key, list of posids as value
                                posids are sorted
        self.data.posdf         dataframe with posid as index and columns:
                                ptlid, PETAL_LOC, DEVICE_LOC, calibration
                                constants and posmodel properties
                                for lookup and coordinate conversion
                                every petal block is contiguous and records
                                within are sorted by posid
        self.data.movedf        dataframe for positioner move data, with
                                (target_no, posid) as index and conventional
                                columns
        self.data.targets_pos   targets dictionary by posid
    """

    def __init__(self, petal_cfgs, xytest_cfg):
        """Templates for config are found on svn
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        self.data = FPTestData(xytest_cfg.filename, petal_cfgs, xytest_cfg)
        self.loggers = self.data.loggers  # use these loggers to write to logs
        self.logger = self.data.logger
        printfuncs = {pid: self.loggers[pid].info for pid in self.data.ptlids}
        PECS.__init__(self, ptlids=self.data.ptlids, printfunc=printfuncs,
                      simulate=self.data.simulate)
        self._get_pos_info()
        self.generate_targets()  # generate local targets or load from file
        self.logger.info([
            f'PlateMaker instrument: {self.platemaker_instrument}',
            f'PlateMaker role: {self.fvc.pm_role}',
            f'FVC instrument: {self.fvc.instrument}',
            f'FVC role: {self.fvc.fvc_role}',
            f'Max num of corrections: {self.data.num_corr_max}',
            f'Num of local targets: {len(self.local_targets)}'])
        self.logger.debug(f'Local targets xy positions: {self.local_targets}')
        self.data.initialise_movedata(self.data.posids, self.data.ntargets)
        self.logger.info(f'Move data tables initialised '
                         f'for {len(self.data.posids)} positioners.')
        # TODO: add summarizer functionality if needed?

    def _get_pos_info(self):
        '''get enabled positioners, according to given posids or busids
        also load pos calibration values for each positioner
        which are not expected to change after each move.
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
            mode = self.data.testcfg[ptlid]['mode']
            ptl = self.ptls[ptlid]  # use as a petal app instance
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
                f'Numbers of enabled and disabled positioners: {Ne}, {Nd}')
            l1 = l1.rename(columns={'DEVICE_ID': 'posid'})
            l1 = l1.set_index('posid').sort_index()  # posids sorted within ptl
            self.data.posids_ptl[ptlid] = posids = l1.index.to_list()
            self.data.posids += posids
            # add to existing positioner index table, first calibration values
            l1['ptlid'] = ptlid  # add petal id as string column
            ret1 = self.get_pos_vals(keys, posids).set_index('posid')
            self.loggers[ptlid].debug(f'XY offsets read:\n{ret1.to_string()}')
            # read posmodel properties, for now just targetable_range_T
            ret2 = self.get_posmodel_prop(props, posids).set_index('posid')
            self.loggers[ptlid].debug(f'PosModel properties read:\n'
                                      f'{ret2.to_string()}')
            dfs.append(l1.join(ret1).join(ret2))
        self.data.posdf = pd.concat(dfs)
        # write ptlid column to movedf
        self.data.movedf = self.data.movedf.merge(
            self.data.posdf['ptlid'].reset_index(), on='posid',
            right_index=True)

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

    def _add_posid_col(self, df, ptlid):
        '''when df only has DEVICE_LOC, add posids column and use as index
        '''
        df0 = self.data.posdf[self.data.posdf['ptlid'] == ptlid]
        return df.merge(df0, on=['PETAL_LOC', 'DEVICE_LOC'],
                        left_index=True).sort_index()

    def _update(self, newdf, i):
        '''newdf is single-index on posid only'''
        newdf = newdf.set_index(pd.MultiIndex.from_product([[i], newdf.index]))
        self.data.movedf.update(newdf)  # write to movedf

    def record_basic_move_data(self, i):
        self.logger.info('Recording basic move data for new xy target...')
        movedf = self.data.movedf
        # before moving for each target, write time cycle etc. for all posids
        movedf.loc[idx[i, :], 'timestamp'] = self.data.now
        movedf.loc[idx[i, :], 'move_log'] = \
            'local posmove csv log deprecated; check posmoveDB instead.'
        # self.ptls[ptlid].states[posid].log_basename
        for ptlid in self.data.ptlids:
            ptl, posids = self.ptls[ptlid], self.data.posids_ptl[ptlid]
            cycles = ptl.get_pos_vals(['TOTAL_MOVE_SEQUENCES'], posids) \
                .set_index('posid')
            # TODO: store other posstate stuff here
            self._update(cycles, i)

    def calculate_xy_errors(self, i, n):
        movedf = self.data.movedf
        # convenience functin c returns a column of the movedf for all pos
        def c(col_name): return movedf.loc[idx[i], [col_name]].values
        movedf.loc[idx[i], [f'err_x_{n}']] = c(f'meas_x_{n}') - c('target_x')
        movedf.loc[idx[i], [f'err_y_{n}']] = c(f'meas_y_{n}') - c('target_y')
        movedf.loc[idx[i], [f'err_xy_{n}']] = np.linalg.norm(
                np.hstack([c(f'err_x_{n}'), c(f'err_y_{n}')]), axis=1)

    def run_xyaccuracy_test(self):
        led_initial = self.illuminator.get('led')
        self.illuminator.set(led='ON')  # turn on illuminator
        for i in range(self.data.ntargets):  # test loop over all test targets
            self.logger.info(f'target {i+1} of {self.ntargets}')
            self.record_basic_move_data(i)  # for each target, record basics
            for n in range(self.data.num_corr_max + 1):
                self.move_measure(i, n)
            # TODO: make real-time plots as test runs
        self.illuminator.set(led=led_initial)  # restore initial LED state
        if self.data.test_cfg['make_plots']:
            self.make_summary_plots()  # plot for all positioners by default

    def move_measure(self, i, n):
        '''one complete iteration: move ten petals once, measure once
        ith target, nth move'''
        movedf = self.data.movedf
        # move ten petals
        # TODO: parallelise this and have ten petals run simultaneously
        expected_QS_list = []  # each item is a dataframe for one petal
        for ptlid in self.data.ptlids:
            posids = self.data.posids_ptl[ptlid]  # all records obey this order
            ptl = self.ptls[ptlid]
            device_loc = self.data.posdf.loc[posids, 'DEVICE_LOC']
            if n == 0:  # blind move
                posXY = np.vstack(   # shape (N_posids, 2)
                    [self.data.targets_pos[posid][i, :] for posid in posids])
                movetype, cmd = 'blind', 'obxXY'
                offXY = self.data.posdf.loc[posids, ['OFFSET_X', 'OFFSET_Y']]
                tgt = posXY + offXY.values  # convert to obsXY, shape (N, 2)
                movedf.loc[idx[i, posids], ['target_x', 'target_y']] = tgt
            else:
                movetype, cmd = 'corrective', 'dXdY'
                tgt = - movedf.loc[idx[i, posids],  # note minus sign
                                   [f'err_x_{n-1}', f'err_y_{n-1}']].values
            # build move request dataframe for a petal
            note = (f'xy test: {self.data.test_name}; '  # same for all
                    f'target {i+1} of {self.ntargets}; '
                    f'move {n} ({movetype})')
            req = pd.DataFrame({'DEVICE_LOC': device_loc,
                                'COMMAND': cmd,
                                'TARGET_X1': tgt[:, 0],  # shape (N_posids, 2)
                                'TARGET_X2': tgt[:, 1],  # shape (N_posids, 2)
                                'LOG_NOTE': note})
            # TODO: anti-collision schedule rejection needs to be recorded
            accepted_requests = ptl.prepare_move(
                req, anticollision=self.data.anticollision)
            self.loggers[ptlid].debug(  # already keyed by posids
                'prepare_move() returns accepted requests:\n'
                + pd.DataFrame(accepted_requests).to_string())
            # execute move, make sure return df has proper format for logging
            ret_QS = ptl.execute_move(posids=posids, return_coord='QS')
            # ensure the same set of devices are returned after execution
            assert set(req['DEVICE_LOC']) == set(ret_QS['DEVICE_LOC'])
            ret_QS = self._add_posid_col(ret_QS, ptlid)  # add posid column
            self.loggers[ptlid].debug('execute_move() returns expected QS:\n'
                                      + ret_QS.to_string())
            # build expected QS positions for fvc measure
            # TODO: is the flag below gauranteed to be 4?
            expected_QS = pd.DataFrame(  # this is for only one petal
                {'id': pd.Series(posids, dtype=str),
                 'q': pd.Series(ret_QS['X1'], dtype=np.float64),
                 's': pd.Series(ret_QS['X2'], dtype=np.float64),
                 'flags': pd.Series(4*np.ones(len(posids)),
                                    dtype=np.uint32)})
            expected_QS_list.append(expected_QS)

            # # get expected posTP from petal and write to movedf after move
            ret_TP = ptl.get_positions(posids=posids, return_coord='posTP')
            ret_TP = self._add_posid_col(ret_TP, ptlid)  # add posid column
            self.loggers[ptlid].debug('expected posTP after move:\n'
                                      + ret_TP.to_string())
            # write posTP for a petal to movedf
            new = pd.DataFrame({f'pos_t_{n}': ret_TP['X1'],
                                f'pos_p_{n}': ret_TP['X2']},
                               dtype=np.float32, index=ret_TP.index)
            self._update(new, i)
        # combine expected QS list to form a single dataframe
        expected_QS = pd.concat(expected_QS_list)
        # measure ten petals with FVC after all petals have moved
        measured_QS = self.fvc.measure(expected_QS) \
            .rename(columns={'id': 'posid'}).set_index('posid')
        # TODO: handle spotmatch errors? no return code from FVC proxy?
        # TODO: if measured position is [0, 0], disable positioner?
        # calculate measured obsXY from measured QS and write to movedf
        q_rad = np.radians(measured_QS['q'])
        r = pc.S2R_lookup(measured_QS['s'])
        new = pd.DataFrame({f'meas_x_{n}': r * np.cos(q_rad),
                            f'meas_y_{n}': r * np.sin(q_rad)},
                           dtype=np.float32, index=measured_QS.index)
        self._update(new, i)
        self.calculate_xy_errors(i, n)

    def make_summary_plots(self, posids=None):
        if posids is None:
            posids = self.data.posids
        for posid in posids:
            self.data.make_summary_plot(posid)


if __name__ == "__main__":
    test = XYTest()
    test.run_xyaccuracy_test()
    test.data.export_move_data()
    test.data.dump_as_one_pickle()

# def unit_test(self):
#     num_corr_max = 3
#     i = 0
#     n = 0
#     # return of execute move and get positions
#     posids = ['M01525', 'M01527', 'M01545', 'M01588', 'M01589',
#               'M01625', 'M01662', 'M01699', 'M01704', 'M01945']
#     PETAL_LOC = 3
#     DEVICE_LOC = np.arange(10)
#     X1 = np.random.rand(10)
#     X2 = np.random.rand(10)
#     FLAGS = [4] * 10
#     ptlid = '01'
#     ret = pd.DataFrame({'PETAL_LOC': PETAL_LOC,
#                         'DEVICE_LOC': DEVICE_LOC[::-1],
#                         'X1': X1,
#                         'X2': X2,
#                         'FLAGS': FLAGS})
#     posdf1 = pd.DataFrame({'posid': posids,
#                            'ptlid': '09',
#                            'PETAL_LOC': PETAL_LOC,
#                            'DEVICE_LOC': DEVICE_LOC})
#     posdf2 = pd.DataFrame({'posid': posids,
#                            'ptlid': '01',
#                            'PETAL_LOC': PETAL_LOC,
#                            'DEVICE_LOC': DEVICE_LOC})
#     posdf2 = pd.DataFrame({'posid': posids,
#                            'OFFSET_X': 0.3})
#     posdf = pd.concat([posdf1, posdf2],
#                       ignore_index=True).set_index('posid')
#     df0 = posdf[posdf['ptlid'] == ptlid]
#     ret.merge(df0, left_index=True,
#               on=['PETAL_LOC', 'DEVICE_LOC']).sort_index()
