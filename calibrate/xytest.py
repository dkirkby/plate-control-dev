# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong
"""

import os
import sys
import numpy as np
import time
# from astropy.io import ascii
from configobj import ConfigObj
sys.path.append(os.path.abspath('../pecs/'))
from pecs import PECS
# sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))
import posconstants as pc
# from summarizer import Summarizer
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
        PECS.__init__(self, ptlids=self.data.ptlids, printfunc=printfuncs)
        self.data.ptl_posids = {}  # enabled posids keyed by petal id
        self.data.posids = []  # all enabled posids for all petals in a list
        for ptlid in self.data.ptlids:
            self.data.ptl_posids[ptlid] = self.get_posids(ptlid)
            self.data.posids += self.data.ptl_posids[ptlid]
        # create local targets in posXY
        # TODO: add support for input target and shuffling
        self.targets = self.generate_posXY_targets_grid(
            self.data.test_cfg['targ_min_radius'],
            self.data.test_cfg['targ_max_radius'],
            self.data.test_cfg['n_pts_across_grid'])
        self.logger.info([
            f'PlateMaker instrument: {self.platemaker_instrument}',
            f'PlateMaker role: {self.fvc.pm_role}',
            f'FVC instrument: {self.fvc.instrument}',
            f'FVC role: {self.fvc.fvc_role}',
            f'Max num of corrections: {self.data.num_corr_max}',
            f'Num of local targets: {len(self.local_targets)}'])
        self.logger.debug(f'Local targets xy positions: {self.local_targets}')
        self.data.initialise_movedata(self.data.posids, len(self.targets))
        self.logger.info(f'Move data tables initialised '
                         f'for {len(self.data.posids)} positioners.')
        # TODO: add summarizer functionality

    def get_posids(self, ptlid):
        mode = self.data.testcfg[ptlid]['mode']
        ptl = self.ptls[ptlid]  # use as a petal app instance
        if mode is None:
            l0 = []  # this case should never happen, as None is filtered out
            l1 = []
        elif mode == 'all':
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
        return sorted(l1)  # always sorted so arrays can use the same ordering

    def run_xyaccuracy_test(self):
        @staticmethod
        def movedata_path(posid):  # return csv path for each posid
            return os.path.join(self.data.dir, f'{posid}_movedata.csv')

        @staticmethod
        def summary_path(posid):  # return positioner directory for each posid
            return os.path.join(self.data.dir, f'{posid}_xyplot')

        requests = []  # each request is for one target
        for i, posXY in enumerate(self.targets):
            request = {}  # include all petals and all positioners
            for ptlid in self.data.ptlids:
                petal_request = {}  # tailor for all positioners in one petal
                for posid in self.data.posids[ptlid]:
                    obsXY = self.ptls[ptlid] \
                        .posmodels[posid].trans.posXY_to_obsXY(posXY)
                    note = (f'xy test: {self.data.test_name}; '
                            f'target {i+1} of {len(self.targets)}')
                    petal_request[posid] = {'command': 'obsXY',
                                            'target': obsXY,
                                            'log_note': note}
                request.update(petal_request)
            requests.append(request)


        # TODO: turn on illuminator        
        # prepare/schedule move
        # execute move
        expected_positions = self.call_petal('execute_move')
        # take FVC measurement
        measured_positions = self.fvc.measure(expected_positions, return_coord='QS')
        
        # transform test grid to each positioner's global position
        # and create all the move request dictionaries
        all_targets = []
        for local_target in local_targets:
            these_targets = {}
            for posid in self.posids:

                trans = self.m.trans(posid)
                these_targets[posid] = {'command':'obsXY', 'target':trans.posXY_to_obsXY(local_target)}

            all_targets.append(these_targets)

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
    def generate_posXY_targets_grid(rmin, rmax, npts):
        x, y = np.mgrid[-rmax:rmax:npts*1j, -rmax:rmax:npts*1j]
        r = np.sqrt(np.square(x) + np.square(y))
        mask = (rmin < r) & (r < rmax)
        return np.array([x[mask], y[mask]]).T.tolist()  # return list of x, y


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




