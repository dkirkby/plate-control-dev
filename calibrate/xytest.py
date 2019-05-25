# -*- coding: utf-8 -*-
"""
Created on Fri May 24 17:46:45 2019

@author: Duan Yutong
"""

import os
import sys
from itertools import product
import numpy as np
import math
import time
# from astropy.io import ascii
from configobj import ConfigObj
sys.path.append(os.path.abspath('../petal/'))
# sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))
# import fvchandler
# import petal
import posconstants as pc
from summarizer import Summarizer
import pos_xytest_plot
from pecs import PECS
from fptestdata import FPTestData

db_commit = False


class XYTest(PECS):
    """XYTest handles running a fiber positioner xy accuracy test.
    Does not support input_targs_file now for clarity's sake
    Avoid double inheritance from FPTestData because we want to isolate
    the data class to one attribute for easy pickling, otherwise we would have
    to pickle the entire XYTest class

    Input:
        petal_cfgs:     list of petal config objects, one for each petal
        xytest_cfg:     one config object for xy test settings
    """

    def __init__(self, petal_cfgs, xytest_cfg):
        """Templates for configfiles are found on svn
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        self.data = FPTestData(xytest_cfg.filename, petal_cfgs, xytest_cfg)
        self.loggers = self.data.loggers  # use these loggers to write to logs
        self.logger = self.data.logger
        printfuncs = {pid: self.loggers[pid].info for pid in self.data.ptlids}
        PECS.__init__(self, ptlids=self.data.ptlids, printfunc=printfuncs,
                      simulate=self.data.simulate,
                      db_commit=db_commit, sched_stats_on=True,
                      anticollision=self.xytest_conf['anticollision'],
                      collider_file=self.test_conf['collider_file'])
        self.logger.info([
            'PlateMaker instrument: {self.platemaker_instrument}',
            'PlateMaker role: {self.fvc.pm_role}',
            'FVC instrument: {self.fvc.instrument}',
            'FVC role: {self.fvc.fvc_role}'])
        # TODO: need to calibrate FVC here when setting up fvc and platemaker?
        # TODO: replace this loop with MP?
        self.summarizers = {}
        for ptlid, ptl in self.ptls.items():
            # TODO: rehome or park pos before starting?
            logger = self.loggers[ptlid]
            logger.info(f'Petal: {ptlid}')
            logger.debug(f'Positoners: {ptl.posids}')
            logger.debug(f'Fiducials: {ptl.fidids}')
            fid_settings_done = ptl.set_fiducials(setting='on')
            logger.info(f'Fiducials turned on: {fid_settings_done}')
            # set up the test summarizers
            self.summarizers[ptlid] = {}
            summarizer_init_data = {
                'test loop data file': '',
                'num pts calib T': None,
                'num pts calib P': None,
                'calib mode': None,
                'ranges remeasured': None,
                'xytest log file': self.data.log_paths[ptlid],
                'code version': pc.code_version}
            for posid in ptl.posids:
                self.summarizers[ptlid][posid] = Summarizer(
                        ptl.state(posid), summarizer_init_data)
            logger.info('Data summarizers for all positioners initialized.')

    def run_xyaccuracy_test(self):
        """Move positioners to a series of xy targets and measure performance.
        """
        @staticmethod
        def movedata_path(posid):
            return os.path.join(self.data.dir, f'{posid}_movedata.csv')

        @staticmethod
        def summary_path(posid):
            return os.path.join(self.data.dir, f'{posid}_xyplot')

        local_targets = self.generate_posXY_targets_grid(
            self.data.test_cfg['targ_min_radius'],
            self.data.test_cfg['targ_max_radius'],
            self.data.test_cfg['n_pts_across_grid'])
        self.logger.info(f'Number of local targets: {len(local_targets)}')
        self.logger.debug(f'Local targets xy positions: {local_targets}')
        self.logger.info('Max number of corrections: {num_corr_max}')
        # columns for pandas dataframe
        cols = ['timestamp', 'cycle', 'move_log', 'target_no',
                'target_x', 'target_y']
        fields = ['meas_x', 'meas_y', 'err_x', 'err_y', 'err_xy',
                  'pos_t', 'pos_p']
        num_corr_max = self.data.test_cfg['num_corr_max']
        for field, i in product(fields, range(num_corr_max+1)):
            cols.append(f'{field}_{i}')

        # get enabled posids for each petal
        
        # transform test grid to each positioner's global position, and create all the move request dictionaries
        all_targets = []
        for local_target in local_targets:
            these_targets = {}
            for posid in self.posids:
                ptl = self.m.petal(posid)
                enabled_this=ptl.get_posfid_val(posid,'CTRL_ENABLED')
                posT_this=ptl.get_posfid_val(posid,'POS_T')
                posP_this=ptl.get_posfid_val(posid,'POS_P') 
                trans = self.m.trans(posid)
                if enabled_this:
                    these_targets[posid] = {'command':'obsXY', 'target':trans.posXY_to_obsXY(local_target)}
                else:
                    these_targets[posid] = {'command':'obsXY','target':trans.posTP_to_obsXY([posT_this,posP_this])}
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
                
                # update summary data logs
                for posid in self.posids:
                    self.summarizers[posid].write_row(all_data_by_posid[posid]['err2D'])
        
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
        return np.array([x[mask], y[mask]]).T.tolist()

    def generate_posXY_move_requests(self, xy_list, posids):
        """For a list of local xy targets, make a list of move request
        dictionaries. Each dictionary contains the move requests to move all
        the positioners to that location in their respective patrol disks.
        """
        requests = []
        for xy in xy_list:
            item = {}
            for posid in posids:
                item[posid] = {'command': 'posXY', 'target': xy}
            requests.append(item)
        return requests


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
