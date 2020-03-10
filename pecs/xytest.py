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
        self.data.posids_pc     dict with pcid as key, list of posids as value
                                posids are sorted
        self.data.posdf         dataframe with DEVICE_ID as index and columns:
                                pcid, PETAL_LOC, DEVICE_LOC, calibration
                                constants and posmodel properties for records
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
        self.logger = self.data.logger
        self.logger.info(f'Starting Test at {self.data.t_i}')
        super().__init__(
            printfunc={p: self.loggers[p].info for p in self.data.pcids},
            interactive=False)
        self.ptlm.participating_petals = [
            self._pcid2role(pcid) for pcid in self.data.pcids]
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
        pos_all = self.ptlm.get_positioners(enabled_only=False)
        pos_en = self.ptlm.get_positioners(enabled_only=True)
        l1s = {}
        for pcid in self.data.pcids:
            self.data.posids_disabled_pc[pcid] = set()
            mode = self.data.test_cfg[pcid]['mode']
            role = self._pcid2role(pcid)  # petalman returns dict keyed by role
            if mode == 'all':
                l0 = pos_all[role]
                l1 = pos_en[role]
            elif mode == 'pos':
                l0 = self.data.test_cfg[pcid]['posids']
                l1 = pos_en[role][pos_en[role]['DEVICE_ID'].isin(l0)]
            elif mode == 'can':
                busids = self.data.test_cfg[pcid]['busids']
                l0 = pos_all[role][pos_all[role]['BUS_ID'].isin(busids)]
                l1 = pos_en[role][pos_en[role]['BUS_ID'].isin(busids)]
            Nr = len(l0)  # number of requested positioners
            Ne = len(l1)  # nubmer of returned enabled postiioners
            Nd = Nr - Ne  # number of disabled positioners, inferred
            self.logger.info(
                f'{Nr} positioners requested, # enabled, '
                f'disabled, and total: {Ne:3} + {Nd:3} = {Ne + Nd:3}', pcid)
            l1 = l1.set_index('DEVICE_ID').sort_index()  # sorted within ptl
            self.data.posids_pc[pcid] = l1.index.tolist()
            self.data.posids += self.data.posids_pc[pcid]
            # add to existing positioner index table, first calibration values
            l1['PCID'] = pcid  # add pcid as a column
            l1s[pcid] = l1
        ret1 = self.ptlm.get_pos_vals(keys, self.data.posids)
        # read posmodel properties, for now just targetable_range_T
        ret2 = self.ptlm.get_posmodel_prop(props, self.data.posids)
        dfs = []
        for pcid in self.data.pcids:
            role = self._pcid2role(pcid)
            calib = ret1[role].set_index('DEVICE_ID')
            posprop = ret2[role].set_index('DEVICE_ID')
            self.logger.debug([f'Calibration read:', calib.to_string(),
                               f'PosModel properties read:',
                               posprop.to_string()], pcid)
            dfs.append(l1s[pcid].join(calib).join(posprop))
        self.data.posdf = pd.concat(dfs)
        # add columns from self.posinfo, if not already in posdf
        cols = self.posinfo.columns.difference(self.data.posdf.columns)
        self.data.posdf = self.data.posdf.join(self.posinfo[cols])

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
            acceptable_types = ['poslocTP', 'poslocXY', 'obsXY']
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
                    i = self.posinfo.loc[posid, 'DEVICE_LOC']
                    if f'{col1}_{i}' in df.columns:
                        self.data.targets_pos[posid] = (
                            df[[f'{col1}_{i}', f'{col2}_{i}']].values)
                    else:
                        self.logger.warning(
                            'Missing target assignment for device_loc '
                            f'{i}, posid {posid}', pcid)
        assert self.data.ntargets > 0, 'Empty target list, exiting...'

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
        self.set_schedule_stats(enabled=self.schedule_stats)
        self.logger.info(f'Parking {len(self.data.posids)} positioners...')
        ret = self.ptlm.park_positioners(self.data.posids)
        ret = pd.concat(list(ret.values()))
        mask = ret['FLAG'] != 4
        ret['STATUS'] = pc.decipher_posflags(ret['FLAG'])
        retry_list = list(ret.loc[mask, 'DEVICE_ID'])
        if len(retry_list) > 0:
            self.logger.info(f'{len(retry_list)} unsucessful: {retry_list}\n\n'
                             f'{ret[mask].to_string()}')
        for i in range(self.data.ntargets):  # test loop over all test targets
            self.record_basic_move_data(i)  # for each target, record basics
            if i > 0:  # don't pause for the 1st target
                self.pause()
            for n in range(self.data.num_corr_max + 1):
                self.logger.info(f'Target {i+1} of {self.data.ntargets}, '
                                 f'submove {n} of {self.data.num_corr_max}')
                self.expected_QS_list = []
                _, meapos, matched, unmatched = self.move_measure_petals(i, n)
                self.record_expected_positions(i, n)
                self.check_unmatched(meapos, matched, unmatched,
                                     disable_unmatched=disable_unmatched)
                self.update_calibrations(meapos)
                self.record_measurement(meapos, i, n)
                self.calculate_xy_errors(i, n)
        self.data.t_f = pc.now()
        self.data.delta_t = self.data.t_f - self.data.t_i
        self.logger.info(f'Test complete, duration {self.data.delta_t}.')
        self.logger.info('Disabling positioner schedule stats...')
        self.set_schedule_stats(enabled=False)
        self.fvc_collect()

    def record_basic_move_data(self, i):
        self.logger.info(f'Recording move metadata for target {i+1}...')
        movedf = self.data.movedf
        # before moving for each target, write time cycle etc. for all posids
        movedf.loc[idx[i, :], 'timestamp'] = pc.now()
        movedf.loc[idx[i, :], 'move_log'] = (
            f'xytest: {i}th target; check posmoveDB.')
        cycles_dict = self.ptlm.get_pos_vals(['TOTAL_MOVE_SEQUENCES'],
                                             self.data.posids)
        for pcid in self.data.pcids:
            cycles = (cycles_dict[self._pcid2role(pcid)]
                      .rename(columns={'TOTAL_MOVE_SEQUENCES': 'cycle'}))
            # store other posstate values here
            self._update(cycles.set_index('DEVICE_ID'), i)

    def move_measure_petals(self, i, n):
        '''move ten petals once, measure once for the ith target, nth move'''
        self.move_petals(i, n)
        # measure ten petals with FVC at once, FVC after all petals have moved
        ret = self.fvc_measure()
        self.logger.debug([f'FVC measured_QS:',
                           ret[1].reset_index().to_string()])
        return ret

    def move_petals(self, i, n):
        movedf = self.data.movedf
        posids = self.data.posids  # all records obey this order
        if n == 0:  # blind move, issue cmd in obsXY for easy check with FVC
            self.logger.info(f'Setting up target {i+1} in poslocXY...')
            movetype, cmd = 'blind', 'poslocXY'
            for posid in posids:  # write targets to move df
                # No need to ask all petals to transform one pos
                pcid = self.pcid_lookup(posid)
                role = self.ptl_role_lookup(posid)
                if posid not in self.data.targets_pos.keys():
                    continue
                tgt = self.data.targets_pos[posid][i, :]  # two elements
                if self.data.target_type == 'poslocTP':
                    tgt = self.ptlm.postrans(
                        posid, 'poslocTP_to_poslocXY', tgt,
                        participating_petals=role)
                    posintTP, unreachable = self.ptlm.postrans(
                        posid, 'poslocXY_to_posintTP', tgt, 'targetable',
                        participating_petals=role)
                    if unreachable:
                        self.logger.warning(f'{posid} unreachable: {posintTP}',
                                            pcid=pcid)
                    else:
                        self.logger.debug(f'{posid} reachable: {posintTP}',
                                          pcid=pcid)
                elif self.data.target_type == 'obsXY':
                    tgt = self.ptlm.postrans(
                        posid, 'obsXY_to_poslocXY', tgt,
                        participating_petals=role)
                elif self.data.target_type == 'poslocXY':
                    pass
                else:
                    self.logger.error(
                        f'Bad Target type: {self.data.target_type}', pcid=pcid)
                    raise ValueError('Bad Target type.')
                movedf.loc[idx[i, posid], ['tgt_x', 'tgt_y']] = tgt
                movedf.loc[idx[i, posid], ['tgt_q', 'tgt_s']] = (
                    self.ptlm.postrans(posid, 'poslocXY_to_QS', tgt,
                                       participating_petals=role))
            tgt = movedf.loc[idx[i, posids], ['tgt_x', 'tgt_y']].values  # Nx2
        else:
            movetype, cmd = 'corrective', 'poslocdXdY'
            tgt = - movedf.loc[idx[i, posids],  # note minus sign, last move
                               [f'err_x_{n-1}', f'err_y_{n-1}']].values
            tgt = np.nan_to_num(tgt)  # replace NaN with zero for unmatched
        # build move request dataframe for a petal
        note = (f'xytest: {self.data.test_name}; '  # same for all
                f'target {i+1} of {self.data.ntargets}; '
                f'move {n} ({movetype}); expid {self.exp.id}')
        req = pd.DataFrame(
            {'DEVICE_ID': posids,
             'PETAL_LOC': self.posinfo.loc[posids, 'PETAL_LOC'],
             'DEVICE_LOC': self.posinfo.loc[posids, 'DEVICE_LOC'],
             'COMMAND': cmd, 'X1': tgt[:, 0], 'X2': tgt[:, 1],
             'LOG_NOTE': note})
        self.logger.debug([f'Move requests:', req.to_string()])
        self.logger.info('Calculating move paths...')
        self.ptlm.prepare_move(req, anticollision=self.data.anticollision)
        # Execute move returns dict of all individual execute move calls
        self.logger.info('Executing moves...')
        expected_QS = self.ptlm.execute_move(
            reset_flags=False, return_coord='QS', control={'timeout': 120})
        for pcid in self.data.pcids:
            self.logger.debug(['Target {i}, submove {n}, '
                               'execute_move() returns expected QS:',
                               expected_QS[self._pcid2role(pcid)].to_string()],
                              pcid)
        return expected_QS

    def record_expected_positions(self, i, n):
        coords = ['posintTP', 'poslocTP', 'poslocXY']
        # get expected posintTP from petal and write to movedf after move
        # Positions are concatenated in petalman
        for coord in coords:
            x = self.ptlm.get_positions(return_coord=coord).sort_values(
                'DEVICE_ID')
            for pcid in self.data.pcids:
                self.logger.debug(['Target {i}, submove {n}, '
                                   f'Expected {coord}:\n',
                                   x[x.PETAL_LOC == pcid].to_string()], pcid)
            try:  # record per-move data to movedf for a petal
                new[f'{coord[:-1]}_{n}'] = x['X1']
                new[f'{coord[:-2]+coord[-1]}_{n}'] = x['X2']
            except NameError:
                new = pd.DataFrame(
                    {f'{coord[:-1]}_{n}': x['X1'],
                     f'{coord[:-2]+coord[-1]}_{n}': x['X2'],
                     f'flag_{n}': x['FLAGS'],
                     f'status_{n}': pc.decipher_posflags(x['FLAGS']),
                     f'DEVICE_ID': x['DEVICE_ID']})
        self._update(new.set_index('DEVICE_ID'), i)

    def check_unmatched(self, measured_QS, matched, unmatched,
                        disable_unmatched=True):
        for pcid in self.data.pcids:  # check unmatched positioners
            posids = self.data.posids_pc[pcid]
            if not set(posids).issubset(matched):
                # matched_pc = set(posids) & matched
                unmatched_pc = set(posids) & unmatched
                for posid in unmatched_pc:  # log unmatched fibres to logger
                    self.loggers[pcid].warning(
                        ['Missing {posid}:',
                         self.posinfo.loc[posid].to_string()])
                if disable_unmatched:  # disable unmatched fibre positioners
                    # if anticolliions is on, disable positioner and neighbours
                    self.loggers[pcid].info(
                        f'Disabling unmatched fibres and their neighbours:\n'
                        f'{unmatched_pc}')
                    role = self._pcid2role(pcid)
                    disabled = self.ptlm.disable_positioner_and_neighbors(
                                  list(unmatched_pc),
                                  participating_petals=role)[role]
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
                    # add disabled to disabled sets for bookeeping
                    self.data.posids_disabled |= set(disabled)
                    self.data.posids_disabled_pc[pcid] |= set(disabled)
            else:
                self.loggers[pcid].info(f'All {len(posids)} requested '
                                        'positioners measured by FVC.')

    def update_calibrations(self, measured_QS):  # test and update TP here
        self.logger.info('Testing and updating posintTP...')
        posids = set(self.data.posids) & set(measured_QS.index)
        df = measured_QS.loc[posids].reset_index()
        assert ('Q' in df.columns and 'S' in df.columns), f'{df.columns}'
        updates = self.ptlm.test_and_update_TP(df)
        for pcid in self.data.pcids:
            self.loggers[pcid].debug(
                ['test_and_update_TP returned:',
                 updates[self._pcid2role(pcid)].to_string()])

    def record_measurement(self, measured_QS, i, n):
        measured_QS = measured_QS[measured_QS.index.isin(self.data.posids)]
        for posid in measured_QS.index:
            if self.ptl_role_lookup(posid) is None:  # only selected posids
                measured_QS.drop(posid, inplace=True)
        QS = measured_QS[['Q', 'S']].values.T  # 2 x N array
        poslocXY = np.zeros(QS.shape)  # empty array
        for j, posid in enumerate(measured_QS.index):
            role = self.ptl_role_lookup(posid)
            poslocXY[:, j] = self.ptlm.postrans(
                posid, 'QS_to_poslocXY', QS[:, j], participating_petals=role)
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
        err = (movedf.loc[idx[i, :],
                          [f'err_x_{n}', f'err_y_{n}', f'err_xy_{n}',
                           f'status_{n}']]
               .sort_values(f'err_xy_{n}', ascending=False))
        errXY = err[f'err_xy_{n}'].values * 1000  # to microns
        self.logger.info([
            f'\nSUBMOVE: {n}, errXY for all positioners:',
            f'    max: {np.max(errXY):6.1f} μm',
            f'    rms: {np.sqrt(np.mean(np.square(errXY))):6.1f} μm',
            f'    avg: {np.mean(errXY):6.1f} μm',
            f'    min: {np.min(errXY):6.1f} μm'])
        self.logger.info(['Worst 20 positioners:', err.iloc[:20].to_string()])


if __name__ == '__main__':
    path = os.path.join(pc.dirs['test_settings'], 'xytest_7ptl.cfg')
    print(f'Loading test config: {path}')
    xytest_cfg = ConfigObj(path, unrepr=True, encoding='utf_8')  # read cfg
    xytest_name = input(r'Please name this test (xytest-{test_name}): ')
    test = XYTest('xytest-'+xytest_name, xytest_cfg)
    test.run_xyaccuracy_test(
        disable_unmatched=test.data.test_cfg['disable_unmatched'])
    test.data.generate_data_products()
