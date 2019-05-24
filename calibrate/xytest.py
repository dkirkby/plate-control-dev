import os
import sys
import numpy as np
import math
import time
from astropy.io import ascii
from configobj import ConfigObj
import csv
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))
import posmovemeasure
import fvchandler
import petal
import posconstants as pc
import summarizer
import pos_xytest_plot
from fptestdata import FPTestData


class XYTest(object):
    """XYTest handles running a fiber positioner xy accuracy test for a petal.
    It supports being called repeatedly in a loop, with variable settings for
    each loop in terms of number of number of test moves,
    number of unmeasured life moves, number of hardstop slams, etc.
    The idea is that we can really tailor a robust test suite into
    a single automated setup.
    """

    def __init__(self, test_name, hwsetup_conf, xytest_conf):
        """For the inputs hwsetup_conf and xytest_conf, you typically would
        leave these as the default empty string. This causes a gui file picker
        to come up. For debug purposes, if you want to short-circuit the
        gui because it is annoying, then you could argue a filename here.
        Templates for configfiles are found
        in the DESI svn at
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """

        self.test_name = test_name
        # load config and traveler files, begin logging
        self.hwsetup_conf = ConfigObj(hwsetup_conf, unrepr=True,
                                      encoding='utf-8')
        self.xytest_conf = ConfigObj(xytest_conf, unrepr=True,
                                     encoding='utf-8')
        petal_id = self.hwsetup_conf['ptl_id']
        # set up debugging data storage and logger
        self.data = FPTestData(test_name, petal_id)
        self.logger = self.data.logger  # use this logger to write to logs
        
        
        
        # The status file is used to maintain current status of the test in case of test disruption.
        self.xytest_conf.filename = pc.dirs['temp_files'] + 'xytest_status.conf'
        self.xytest_logfile = pc.dirs['xytest_logs'] + pc.filename_timestamp_str_now() + '_' + os.path.splitext(os.path.basename(xytest_conf))[0] + '.log'
        self.xytest_conf['logfile']=self.xytest_logfile
        self.xytest_conf.write()
        self.track_file(self.xytest_logfile, commit='always')
        self.logwrite(' *** BEGIN TEST LOG ***',False) # just for formatting
        self.logwrite('HARDWARE SETUP FILE: ' + hwsetup_conf)
        self.logwrite_conf(hwsetup_conf)
        self.logwrite('TEST TEMPLATE FILE: ' + xytest_conf)
        self.logwrite_conf(xytest_conf)
        self.logwrite('Test traveler file:' + self.xytest_conf.filename)
        self.logwrite('Total number of test loops: ' + str(self.n_loops))
        self.logwrite('Code version: ' + pc.code_version)
                
        # simulation mode
        self.simulate = self.xytest_conf['simulate']
        self.logwrite('Simulation mode on: ' + str(self.simulate))        
        
        # set up fvc and platemaker
        if self.simulate:
            fvc_type = 'simulator'
        else:
            fvc_type = self.hwsetup_conf['fvc_type']
        if fvc_type == 'FLI' and 'pm_instrument' in self.hwsetup_conf:
            fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite,save_sbig_fits=self.hwsetup_conf['save_sbig_fits'], platemaker_instrument = self.hwsetup_conf['pm_instrument'],fvc_role=self.hwsetup_conf['fvc_role'])       
        else:
            fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite,save_sbig_fits=self.hwsetup_conf['save_sbig_fits'])
        fvc.rotation = self.hwsetup_conf['rotation']
        fvc.scale = self.hwsetup_conf['scale']
        fvc.translation = self.hwsetup_conf['translation']
        fvc.exposure_time = self.hwsetup_conf['exposure_time']
        self.logwrite('FVC type: ' + str(fvc_type))
        self.logwrite('FVC rotation: ' + str(fvc.rotation))
        self.logwrite('FVC scale: ' + str(fvc.scale))
        
        # set up positioners, fiducials, and petals
        self.pos_notes = self.hwsetup_conf['pos_notes'] # notes for report to add about positioner (reported with positioner in same slot as posids list)
        db_commit_on = False
        if 'store_mode' in self.hwsetup_conf and self.hwsetup_conf['store_mode'] == 'db':
            db_commit_on = True
        ptl_id=self.hwsetup_conf['ptl_id']
        shape = 'asphere' #if self.hwsetup_conf['plate_type'] == 'petal' else 'flat'
        ptl = petal.Petal(ptl_id, 
                          posids=[],
                          fidids=[],
                          simulator_on=self.simulate,
                          sched_stats_on=True,
                          printfunc=self.logwrite,
                          collider_file=self.xytest_conf['collider_file'],
                          db_commit_on=db_commit_on, 
                          anticollision=self.xytest_conf['anticollision'])#, petal_shape=shape)
        posids=self.posids=ptl.posids
        fidids=self.fidids=ptl.fidids
        
        while len(self.pos_notes) < len(self.posids):
            self.pos_notes.append('')

        self.m = posmovemeasure.PosMoveMeasure([ptl],fvc,printfunc=self.logwrite)
        self.m.rehome(posids='all')
        self.posids = self.m.all_posids
        self.logwrite('Positoners: ' + str(self.posids))
        self.logwrite('Positoner notes: ' + str(self.pos_notes))
        self.logwrite('Fiducials: ' + str(fidids))
        self.logwrite('Petal: ' + str(ptl_id))
        self.m.make_plots_during_calib = self.xytest_conf['should_make_plots']
        self.logwrite('PosMoveMeasure initialized.')
        fid_settings_done = self.m.set_fiducials('on')
        self.logwrite('Fiducials turned on: ' + str(fid_settings_done))

        # set up the test summarizers
        self.summarizers = {}
        summarizer_init_data = {}
        summarizer_init_data['test loop data file'] = ''
        summarizer_init_data['num pts calib T']     = None
        summarizer_init_data['num pts calib P']     = None
        summarizer_init_data['calib mode']          = None
        summarizer_init_data['ranges remeasured']   = None
        summarizer_init_data['xytest log file']     = os.path.basename(self.xytest_logfile)
        summarizer_init_data['code version']        = pc.code_version
        for posid in self.posids:
            state = self.m.state(posid)
            self.summarizers[posid] = summarizer.Summarizer(state,summarizer_init_data)
            self.track_file(self.summarizers[posid].filename, commit='always')
        self.logwrite('Data summarizers for all positioners initialized.')

    def run_xyaccuracy_test(self, loop_number):
        """Move positioners to a series of xy targets and measure performance.
        """
        
        log_suffix = self.xytest_conf['log_suffix']
        log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
        log_timestamp = pc.filename_timestamp_str_now()
        def movedata_name(posid):
            return pc.dirs['xytest_data']  + posid + '_' + log_timestamp + log_suffix + '_movedata.csv'
        def summary_plot_name(posid):
            return pc.dirs['xytest_plots'] + posid + '_' + log_timestamp + log_suffix + '_xyplot'    

        n_pts_calib_T = self.xytest_conf['n_points_calib_T'][loop_number]
        n_pts_calib_P = self.xytest_conf['n_points_calib_P'][loop_number]
        calib_mode = self.xytest_conf['calib_mode'][loop_number]
        should_measure_ranges = self.xytest_conf['should_measure_ranges'][loop_number]
        for posid in self.posids:
            self.summarizers[posid].update_loop_inits(movedata_name(posid), n_pts_calib_T, n_pts_calib_P, calib_mode, should_measure_ranges)

        local_targets = self.generate_posXY_targets_grid(self.xytest_conf['n_pts_across_grid'][loop_number])
        self.logwrite('Number of local targets = ' + str(len(local_targets)))
        self.logwrite('Local target xy positions: ' + str(local_targets))
        
        num_corr_max = self.xytest_conf['num_corr_max'][loop_number]
        submove_idxs = [i for i in range(num_corr_max+1)]
        self.logwrite('Number of corrections max = ' + str(num_corr_max))
        
        # write headers for move data files
        move_log_header = 'timestamp,cycle,move_log,target_x,target_y'
        submove_fields = ['meas_obsXY','errXY','err2D','posTP']
        for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_x'  + str(i) + ',err_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_xy' + str(i)
        for i in submove_idxs: move_log_header += ',pos_t'  + str(i) + ',pos_p' + str(i)
        move_log_header += '\n'
        for posid in self.posids:
            filename = movedata_name(posid)
            self.track_file(filename, commit='once')
            file = open(filename,'w')
            file.write(move_log_header)
            file.close()
        
        # transform test grid to each positioner's global position, and create all the move request dictionaries
        all_targets = []
        
        if self.xytest_conf['input_targs_file']:
            targ_list=ascii.read(pc.dirs['test_settings']+self.xytest_conf['input_targs_file'])
            targ_list=targ_list['filename']
            n_targets=len(targ_list)
            for i in range(n_targets):
                these_targets = {}
                file_targ_this=pc.dirs['test_settings']+'move_request_sets/'+targ_list[i]
                data=ascii.read(file_targ_this)
                data.add_index('DEVICE_LOC')
                for posid in self.posids:
                    ptl = self.m.petal(posid)
                    deviceloc_this=ptl.get_posfid_val(posid,'DEVICE_LOC')
                    enabled_this=ptl.get_posfid_val(posid,'CTRL_ENABLED')
                    posT_this=ptl.get_posfid_val(posid,'POS_T')
                    posP_this=ptl.get_posfid_val(posid,'POS_P')
                    data_this=data.loc[deviceloc_this]
                    trans = self.m.trans(posid)
                    if enabled_this:
                        these_targets[posid] = {'command':'obsXY', 'target':trans.posXY_to_obsXY([data_this['u'],data_this['v']])}
                    else:
                        these_targets[posid] = {'command':'obsXY','target':trans.posTP_to_obsXY([posT_this,posP_this])} 

                all_targets.append(these_targets)
        else:
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
        start_cycles = {}
        for posid in self.posids:
            all_data_by_posid[posid] = {'targ_obsXY': []}
            for key in submove_fields:
                all_data_by_posid[posid][key] = [[] for i in submove_idxs]
            start_cycles[posid] = self.m.state(posid).read('TOTAL_MOVE_SEQUENCES')
        
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
                    filenames = pos_xytest_plot.plot(summary_plot_name(posid),posid,all_data_by_posid[posid],center,theta_range,r1,r2,title)
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

    def logwrite(self,text,stdout=True,):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.xytest_logfile,'a',encoding='utf8') as fh:            
            fh.write(line + '\n')
        if stdout:
            print(line)

    def logwrite_conf(self,conf_file):
        """Standard function for copying a config file's contents to the test traveler log file.
        """
        with open(conf_file, 'r', newline='') as file:
            for line in file:
                if line[0] != '#' and line[0] != '\n': # skip blank or comment lines
                    line = line[:-1] if line[-1] == '\n' else line
                    all_blank = sum([1 for x in line if x == ' ']) == len(line)
                    if not all_blank:
                        self.logwrite(line)

    def set_current_overrides(self, loop_number):
        """If the test config calls for overriding cruise or creep currents to a particular value
        for this loop, this method sets that. It also stores the old setting for later restoration.
        """
        self.old_currents = {}
        for posid in self.posids:
            self.old_currents[posid] = {}
        for key in ['CURR_CRUISE','CURR_CREEP']:
            if key == 'CURR_CRUISE':
                curr_val = self.xytest_conf['cruise_current_override'][loop_number]
            else:
                curr_val = self.xytest_conf['creep_current_override'][loop_number]
            for posid in self.posids:
                state = self.m.state(posid)
                ptl = self.m.petal(posid)
                self.track_file(state.log_path, commit='once')
                self.old_currents[posid][key] = state.read(key)
                if curr_val != None:
                    ptl.set_posfid_val(posid, key, curr_val)
                    self.logwrite(str(posid) + ': Setting ' + key + ' to ' + str(curr_val))
                else:
                    self.logwrite(str(posid) + ': ' + key + ' is ' + str(self.old_currents[posid][key]))
                    self.old_currents[posid][key] = None # indicates later in clear_current_overrides() method whether to do anything
        self.m.set_motor_parameters()
        
    def clear_current_overrides(self):
        """Restore current settings for each positioner to their original values.
        """
        for key in ['CURR_CRUISE','CURR_CREEP']:
            for posid in self.posids:
                if self.old_currents[posid][key] != None:
                    state = self.m.state(posid)
                    ptl = self.m.petal(posid)
                    self.track_file(state.log_path, commit='once')
                    ptl.set_posfid_val(posid, key, self.old_currents[posid][key])
                    self.logwrite(str(posid) + ': Restoring ' + key + ' to ' + str(self.old_currents[posid][key]))
        self.m.set_motor_parameters()

    def generate_posXY_targets_grid(self, npoints_across_grid):
        """Make rectilinear grid of local (x,y) targets. Returns a list.
        """
        r_max = self.xytest_conf['targ_max_radius']
        line = np.linspace(-r_max,r_max,npoints_across_grid)
        targets = [[x,y] for x in line for y in line]
        for i in range(len(targets)-1,-1,-1): # go backwards thru list for popping so indices always work 
            if not(self.target_within_limits(targets[i])):
                targets.pop(i)
        return targets

    def target_within_limits(self, xytarg):
        """Check whether [x,y] target is within the patrol limits.
        """
        r_min = self.xytest_conf['targ_min_radius']
        r_max = self.xytest_conf['targ_max_radius']
        x = xytarg[0]
        y = xytarg[1]
        r = math.sqrt(x**2 + y**2)
        if r > r_min and r < r_max:
            return True
        return False
    
    def generate_posXY_move_requests(self, xytargets_list):
        """For a list of local xy targets, make a list of move request dictionaries.
        Each dictionary contains the move requests to move all the positioners to that
        location in their respective patrol disks.
        """
        requests = []
        for local_target in xytargets_list:
            these_targets = {}
            for posid in sorted(self.posids):
                these_targets[posid] = {'command':'posXY', 'target':local_target}
            requests.append(these_targets)
        return requests


if __name__ == "__main__":
    hwsetup_conf_path = os.path.join(pc.dirs['hwsetups'],
                                     'xytest_template.conf')
    xytest_conf_path = os.path.join(pc.dirs['test_settings'],
                                    'xytest_template.conf')
    test = XYTest(hwsetup_conf=hwsetup_conf_path, xytest_conf=xytest_conf_path)
    test.logwrite('Start of positioner performance test.')
    test.m.park(posids='all')

    test.xytest_conf['current_loop_number'] = loop_num
    test.xytest_conf.write()
    test.logwrite('Starting xy test in loop ' + str(loop_num + 1) + ' of ' + str(test.n_loops))
    test.set_current_overrides(loop_num)
    test.run_xyaccuracy_test(loop_num)
    test.clear_current_overrides()
    test.logwrite('All test loops complete.')
    test.m.park(posids='all')
    test.logwrite('Moved positioners into \'parked\' position.')
    for petal in test.m.petals:
        petal.schedule_stats.save()
    test.logwrite('Test complete.')
