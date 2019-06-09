# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong
"""

import os
import numpy as np
from datetime import datetime, timezone
import pandas as pd
# import time
from configobj import ConfigObj
from pecs import PECS
# import posconstants as pc
import pos_xytest_plot
from fptestdata import FPTestData


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
        self.data.posids = {}  # enabled posids keyed by petal id
        self.data.device_loc = {}  # dict, corresponding device locations
        self.getloc = {'posids': [], 'loc': []}  # big lists, temporary
        for ptlid in self.data.ptlids:
            self._load_posids(ptlid)
        # re-create self.getloc as posid -> device loc look up dict
        self.getloc = dict(zip(self.getloc['posids'], self.getloc['loc']))
        # create local targets in posXY
        # TODO: add support for input target and shuffling
        self.data.targets = self._generate_posXY_targets_grid(  # shape (2, N)
            self.data.test_cfg['targ_min_radius'],
            self.data.test_cfg['targ_max_radius'],
            self.data.test_cfg['n_pts_across_grid'])
        self.data.ntargets = self.data.targets.shape[1]
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

    def _load_posids(self, ptlid):
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
        Ne = len(l1)  # nubmer of returned, enabled postiioners
        Nd = Nr - Ne  # disabled
        self.loggers[ptlid].info(f'Number of requested positioners: {Nr}')
        self.loggers[ptlid].info(
            f'Numbers of enabled and disabled positioners: {Ne}, {Nd}')
        # always sort by device locations so arrays can use the same ordering
        l1 = l1.sort_values(by='DEVICE_LOC')
        self.data.device_loc[ptlid] = l1['DEVICE_LOC'].tolist()
        self.getloc['loc'] += l1['DEVICE_LOC'].tolist()
        self.data.posids[ptlid] = l1['DEVICE_ID'].tolist()
        self.getloc['posids'] += l1['DEVICE_ID'].tolist()

    @staticmethod
    def _generate_posXY_targets_grid(rmin, rmax, npts):
        x, y = np.mgrid[-rmax:rmax:npts*1j, -rmax:rmax:npts*1j]
        r = np.sqrt(np.square(x) + np.square(y))
        mask = (rmin < r) & (r < rmax)
        return np.array([x[mask], y[mask]])  # return 2 x N array of targets

    def _add_df_col(self, df, ptlid, has_index=False):
        '''has_index:
            True:  df only has device loc, set index name, sort, add posids
            False: df only has posids, add device loc column and use as index
        '''
        index = pd.Series(self.data.device_loc[ptlid], name='device loc')
        df0 = pd.DataFrame({'posid': self.data.posids[ptlid]}, index=index)
        if has_index:
            return df0.merge(df, left_index=True, right_index=True)
        else:
            return df0.merge(df, on='posid', right_index=True)

    def run_xyaccuracy_test(self):
        self.illuminator.set(led='ON')  # turn on illuminator
        for i in range(self.data.ntargets):  # test loop over all test targets
            posXY = self.data.targets[:, i].reshape(2, 1)
            self.logger.info(f'target {i+1} of {self.ntargets}')
            # TODO: parallelise this and have ten petals run simultaneously
            for ptlid in self.data.ptlids:
                posids = self.data.posids[ptlid]
                # transform posXY to obsXY: unfortunately all positioner
                # states are stored comppletely separately, but still we can
                # sort of vectorise posXY_to_obsXY which is particularly
                # simple and should have been vectorised
                offXY = np.zeros((2, len(posids)))  # read xy offsets
                for j, posid in enumerate(posids):
                    t = self.ptls[ptlid].posmodels[posid].trans
                    offXY[:, j] = (t.getval['OFFSET_X'], t.getval['OFFSET_Y'])
                    self.loggers[ptlid].debug(
                        f'Positioner: {posid}, xy offsets read: {offXY[:, j]}')
                obsXY = posXY + offXY  # apply transform, shape (2, N_posids)
                # blind move (n = 0) and 3 corrective moves (n = 1, 2, 3)
                for n in range(self.data.num_corr_max + 1):
                    self.move_measure(ptlid, n, obsXY)

    def move_measure(self, i, ptlid, n_move, obsXY):
        movedf = self.data.movedf  # move dataframe
        if n_move == 0:  # blind move
            movetype = 'blind'
            cmd = 'obxXY'
            target = obsXY  # shape (2, N_posids)
        else:
            movetype = 'corrective'
            cmd = 'dXdY'
            # read last measured obsXY, and calculate errors
            # TODO =======TODO =======TODO =======TODO =======TODO =======TODO
            # from errors make new targets
            target # shape (2, N_posids)

        # before moving positioner, write time and cycle for all positioners
        movedf.loc[idx[i, ptlid, :], 'timestamp_utc'] = \
            datetime.now(timezone.utc)
        for j, posid in enumerate(self.data.posids[ptlid]):
            device_loc = self.getloc[posid]
            movedf.loc[idx[i, ptlid, device_loc], 'cycle'] = \
                self.ptls[ptlid].states[posid].read('TOTAL_MOVE_SEQUENCES')

        # build move request dataframe which includes all positioners on a ptl
        note = (f'xy test: {self.data.test_name}; '  # same for all
                f'target {i+1} of {self.ntargets}; move {n_move} ({movetype})')
        req_dict = {'DEVICE_LOC': self.data.device_loc[ptlid],
                    'COMMAND': cmd,
                    'TARGET_X1': target[0, :],
                    'TARGET_X2': target[1, :],
                    'LOG_NOTE': note}
        requests = pd.DataFrame(data=req_dict)
        # TODO: anti collision schedule rejection needs to be recorded
        accepted_requests = self.ptls[ptlid].prepare_move(
            requests, anticollision=self.data.anticollision)
        self.loggers[ptlid].debug(  # already keyed by posids, print directly
            'prepare_move() returns accepted requests:\n'
            + pd.DataFrame(accepted_requests).to_string())
        # execute move, make sure return df has proper format for logging
        ret = self.ptls[ptlid].execute_move(
            posids=self.data.posids[ptlid], return_coord='QS')
        # ensure the same set of devices are returned
        assert set(req_dict['DEVICE_LOC']) == set(ret['DEVICE_LOC'])
        ret.rename(columns={'DEVICE_LOC': 'device loc',  # loc is the index
                            'X1': 'q', 'X2': 's'}, inplace=True)
        ret = self._add_df_col(ret, ptlid, has_index=True)  # add posid column
        self.loggers[ptlid].debug('execute_move() returns expected positions'
                                  'in QS:\n' + ret.to_string())
        # build expected positions for fvc measure, as this is supposed to be
        # different after each move; still sorted by device loc
        expected_positions = pd.DataFrame(
            {'id': pd.Series(posids, dtype=str),
             'q': pd.Series(ret['X1'], dtype=np.float64),
             's': pd.Series(ret['X2'], dtype=np.float64),
             'flags': pd.Series(4*np.ones(len(posids)),  # gauranteed to be 4?
                                dtype=np.uint32)})
        # measure with FVC after move
        # TODO: handle spotmatch errors? no return code from FVC proxy?
        measured_positions = self.fvc.measure(expected_positions)\
            .rename(columns={'id': 'posid'})
        # this only has posids, also need to add device location
        measured_positions = self._add_df_col(measured_positions, ptlid,
                                              has_index=False)
        # TODO: if measured position is [0, 0], disable positioner?
        # calculate obsXY from measured QS
        q_rad = np.radians(measured_positions['q'])
        r = pc.S2R_lookup(measured_positions['s'])
        measXY = np.array([r * np.cos(q_rad), r * np.cos(q_rad)])
        
        
        
        measured_positions['obsY'] = 
        # 
        
        
        
        
        
        
        # initialize some data structures for storing test data
        targ_num = 0
        all_data_by_target = []
        all_data_by_posid = {}
        for posid in self.posids:
            all_data_by_posid[posid] = {'targ_obsXY': []}
            for key in submove_fields:
                all_data_by_posid[posid][key] = [[] for i in submove_idxs]

        
        # run the test
        try:  
            start_time = time.time()
            for these_targets in all_targets:
                targ_num += 1
                print('')
                self.logwrite('MEASURING TARGET ' + str(targ_num) + ' OF ' + str(len(all_targets)))
                self.logwrite('Local target (posX,posY)=(' + format(local_targets[targ_num-1][0],'.3f') + ',' + format(local_targets[targ_num-1][1],'.3f') + ') for each positioner.')
                this_timestamp = pc.timestamp_str_now()
                these_meas_data = self.m.move_and_correct(these_targets, num_corr_max)
                
                # store this set of measured data
                all_data_by_target.append(these_meas_data)
                for posid in these_targets.keys():
                    all_data_by_posid[posid]['targ_obsXY'].append(these_meas_data[posid]['targ_obsXY'])
                    for sub in submove_idxs:
                        for key in submove_fields:
                            all_data_by_posid[posid][key][sub].append(these_meas_data[posid][key][sub])              
                

                # update move data log
                for posid in these_targets.keys():
                    state = self.m.state(posid)
                    self.track_file(state.log_path, commit='once')
                    self.track_file(state.conf.filename, commit='always')
                    row = this_timestamp
                    row += ',' + str(state.read('TOTAL_MOVE_SEQUENCES'))
                    row += ',' + str(state.log_basename)
                    row += ',' + str(these_targets[posid]['targ_obsXY'][0])
                    row += ',' + str(these_targets[posid]['targ_obsXY'][1])
                    for key in submove_fields:
                        for submove_data in these_targets[posid][key]:
                            if isinstance(submove_data,list):
                                for j in range(len(submove_data)):
                                    row += ',' + str(submove_data[j])
                            else:
                                row += ',' + str(submove_data)
                    row += '\n'
                    file = open(movedata_name(posid),'a')
                    file.write(row)
                    file.close()
            
            # make summary plots showing the targets and measured positions
            if self.xytest_conf['should_make_plots']:
                for posid in all_data_by_posid.keys():
                    posmodel = self.m.posmodel(posid) 
                    title = log_timestamp + log_suffix
                    center = [posmodel.state.read('OFFSET_X'),posmodel.state.read('OFFSET_Y')]
                    theta_min = posmodel.trans.posTP_to_obsTP([min(posmodel.targetable_range_T),0])[0]
                    theta_max = posmodel.trans.posTP_to_obsTP([max(posmodel.targetable_range_T),0])[0]
                    theta_range = [theta_min,theta_max]
                    r1 = posmodel.state.read('LENGTH_R1')
                    r2 = posmodel.state.read('LENGTH_R2')
                    filenames = pos_xytest_plot.plot(summary_path(posid),posid,all_data_by_posid[posid],center,theta_range,r1,r2,title)
                    self.logwrite(posid + ': Summary log file: ' + self.summarizers[posid].filename)
                    self.logwrite(posid + ': Full data log file: ' + movedata_name(posid))
                    for filename in filenames:
                        self.logwrite(posid + ': Summary plot file: ' + filename)
                        self.track_file(filename, commit='once')
        except:
            raise Exception('XYTest error')
        deltat = format((time.time()-start_time)/60/60, '.2f') + ' hrs'
        self.logwrite(str(len(all_data_by_target)) + ' targets measured in '
                      + deltat + '.')



        @staticmethod
        def movedata_path(posid):  # return csv path for each posid
            return os.path.join(self.data.dir, f'{posid}_movedata.csv')

        @staticmethod
        def summary_path(posid):  # return positioner directory for each posid
            return os.path.join(self.data.dir, f'{posid}_xyplot')

if __name__ == "__main__":
    
    if simulate:
        fvc_type = 'simulator'
    else:
        fvc_type = self.hwsetup_conf['fvc_type']
            
    if fvc_type == 'FLI' and 'pm_instrument' in self.hwsetup_conf:
        fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite,save_sbig_fits=self.hwsetup_conf['save_sbig_fits'], platemaker_instrument = self.hwsetup_conf['pm_instrument'],fvc_role=self.hwsetup_conf['fvc_role'])       
    else:
        fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite,save_sbig_fits=self.hwsetup_conf['save_sbig_fits'])
    
    
    hwsetup_path = os.path.join(pc.dirs['hwsetups'], 'hwsetup_sim1.conf')
    xytest_path = os.path.join(pc.dirs['test_settings'],
                               'xytest_template.conf')
    hwsetup_cfg = ConfigObj(hwsetup_path, unrepr=True, encoding='utf-8')
    xytest_cfg = ConfigObj(xytest_path, unrepr=True, encoding='utf-8')
    test = XYTest(test_name='xytest_0',
                  petal_cfgs=[hwsetup_cfg], xytest_cfg=xytest_cfg)
    test.logwrite('Start of positioner performance test.')
    test.m.park(posids='all')

    test.run_xyaccuracy_test(loop_num)
    test.clear_current_overrides()
    test.logwrite('All test loops complete.')
    test.m.park(posids='all')
    test.logwrite('Moved positioners into \'parked\' position.')
    for petal in test.m.petals:
        petal.schedule_stats.save()
    test.logwrite('Test complete.')




