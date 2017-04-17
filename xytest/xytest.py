import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
import fvchandler
import petal
import posmovemeasure
import posconstants as pc
import summarizer
import numpy as np
import time
import pos_xytest_plot
import um_test_report as test_report
import traceback
import configobj
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import csv
import collections


class XYTest(object):
    """XYTest handles running a fiber positioner xy accuracy test. It supports being called
    repeatedly in a loop, with variable settings for each loop in terms of number of calibration
    moves, number of test moves, number of unmeasured life moves, number of hardstop slams, etc.
    The idea is that we can really tailor a robust test suite into a single automated setup.
    """

    def __init__(self,hwsetup_conf='',xytest_conf=''):
        """For the inputs hwsetup_conf and xytest_conf, you typically would leave these as the default empty
        string. This causes a gui file picker to come up. For debug purposes, if you want to short-circuit the
        gui because it is annoying, then you could argue a filename here. Templates for configfiles are found
        in the DESI svn at
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
         
        # set up configuration and traveler files that goes with this test, and begin logging
        os.makedirs(pc.xytest_logs_directory, exist_ok=True)
        gui_root = tkinter.Tk()
        if not(hwsetup_conf):
            message = "Select hardware setup file."
            hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.hwsetups_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
        if not(xytest_conf):
            message = "Select test configuration file."
            xytest_conf = tkinter.filedialog.askopenfilename(initialdir=pc.test_settings_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
        if not(hwsetup_conf) or not(xytest_conf):
            tkinter.messagebox.showwarning(title='Files not found.',message='Not all configuration files specified. Exiting program.')
            gui_root.withdraw()
            sys.exit(0)
        gui_root.withdraw()
        self.hwsetup_conf = configobj.ConfigObj(hwsetup_conf,unrepr=True,encoding='utf-8')
        self.xytest_conf = configobj.ConfigObj(xytest_conf,unrepr=True,encoding='utf-8')
        self.starting_loop_number = self.xytest_conf['current_loop_number']
        self.n_loops = self._calculate_and_check_n_loops()
        if self.starting_loop_number == 0:
            # The status file is used to maintain current status of the test in case of test disruption.
            self.xytest_conf.filename = pc.temp_files_directory + 'xytest_status.conf'
            self.xytest_logfile = pc.xytest_logs_directory + pc.filename_timestamp_str_now() + '_' + os.path.splitext(os.path.basename(xytest_conf))[1]+'.log'
            self.xytest_conf['logfile']=self.xytest_logfile
            self.new_and_changed_files = collections.OrderedDict()  # keeps track of all files that need to be added / committed to SVN
            self.track_file(self.xytest_logfile, commit='always')
            self.logwrite(' *** BEGIN TEST LOG ***',False) # just for formatting
            self.logwrite('HARDWARE SETUP FILE: ' + hwsetup_conf)
            self.logwrite_conf(hwsetup_conf)
            self.logwrite('TEST TEMPLATE FILE: ' + xytest_conf)
            self.logwrite_conf(xytest_conf)
            self.logwrite('Test traveler file:' + self.xytest_conf.filename)
        else:
            self.xytest_logfile=self.xytest_conf['logfile']
            self.logwrite('*** RESTARTING TEST AT ' + pc.ordinal_str(self.starting_loop_number + 1).upper() + ' LOOP *** (index ' + str(self.starting_loop_number) + ')')
            self.new_and_changed_files = self.xytest_conf['new_and_changed_files']
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
        fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite)       
        fvc.rotation = self.hwsetup_conf['rotation']
        fvc.scale = self.hwsetup_conf['scale']
        fvc.exposure_time = self.hwsetup_conf['exposure_time']
        self.logwrite('FVC type: ' + str(fvc_type))
        self.logwrite('FVC rotation: ' + str(fvc.rotation))
        self.logwrite('FVC scale: ' + str(fvc.scale))
        
        # set up positioners, fiducials, and petals
        self.posids = self.hwsetup_conf['pos_ids']
        self.pos_notes = self.hwsetup_conf['pos_notes'] # notes for report to add about positioner (reported with positioner in same slot as posids list)
        while len(self.pos_notes) < len(self.posids):
            self.pos_notes.append('')
        fidids = self.hwsetup_conf['fid_ids']
        ptl_id = self.hwsetup_conf['ptl_id']
        ptl = petal.Petal(ptl_id, self.posids, fidids, simulator_on=self.simulate, printfunc=self.logwrite)
        ptl.anticollision_default = self.xytest_conf['anticollision']
        self.m = posmovemeasure.PosMoveMeasure([ptl],fvc,printfunc=self.logwrite)
        self.posids = self.m.all_posids()
        self.logwrite('Positoners: ' + str(self.posids))
        self.logwrite('Positoner notes: ' + str(self.pos_notes))
        self.logwrite('Fiducials: ' + str(fidids))
        self.logwrite('Petal: ' + str(ptl_id))
        self.m.make_plots_during_calib = self.xytest_conf['should_make_plots']
        self.logwrite('Automatic generation of calibration and submove plots is turned ' + ('ON' if self.xytest_conf['should_make_plots'] else 'OFF') + '.')
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
        summarizer_init_data['xytest log file']     = self.xytest_conf.filename
        summarizer_init_data['code version']        = pc.code_version
        user_vals = self.intro_questions()
        for key in user_vals.keys():
            self.logwrite('user-entry: ' + key + ': ' + user_vals[key])
            summarizer_init_data[key] = user_vals[key]
        summarizer_init_data['operator notes'] = self.get_and_log_comments_from_user()
        for posid in self.posids:
            state = self.m.state(posid)
            self.summarizers[posid] = summarizer.Summarizer(state,summarizer_init_data)
            self.track_file(self.summarizers[posid].filename, commit='always')
        self.logwrite('Data summarizers for all positioners initialized.')
        
        # TEMPORARY HACK until individual fiducial dot locations tracking is properly handled
        self.m.extradots_fid_state = ptl.fidstates[self.hwsetup_conf['extradots_id']]

        # set up lookup table for random targets
        self.rand_xy_targs_idx = 0 # where we are in the random targets list
        self.rand_xy_targs_list = []
        targs_file = pc.test_settings_directory + self.xytest_conf['rand_xy_targs_file']
        with open(targs_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            header_rows_remaining = 1
            for row in reader:
                if header_rows_remaining:
                    header_rows_remaining -= 1
                else:
                    self.rand_xy_targs_list.append([float(row[0]),float(row[1])])
        self.logwrite('Random targets file: ' + targs_file)
        self.logwrite('Random targets file length: ' + str(len(self.rand_xy_targs_list)) + ' targets')
        
    def intro_questions(self):
        print('Please enter the following data. Hit blank if unknown or unmeasured.')
        keys = summarizer.user_data_keys.copy()
        keys.remove('operator notes') # this one is handled separately in get_and_log_comments_from_user()
        user_vals = collections.OrderedDict.fromkeys(keys)
        for key in user_vals.keys():
            user_vals[key] = input(key + ': ')
        print('')
        print('You entered:')
        nchar = max([len(key) for key in user_vals.keys()])
        for key in user_vals.keys():
            print('  ' + format(key + ':',str(nchar + 2) + 's') + user_vals[key])
        print('')
        try_again = input('If this is ok, hit enter to continue. Otherwise, type any character and enter to start over: ')
        if try_again:
            return self.intro_questions()
        else:
            return user_vals
        
    def get_and_log_comments_from_user(self):
        print('\nPlease enter any specific observations or notes about this test. These will be recorded into the test log. You can keep on entering notes until you hit enter on a blank line.',end=' ')
        thanks_msg = False
        notes = []
        note = input('observation/note: ')
        while note:
            self.logwrite('user-entry: OBSERVATION/NOTE: ' + note)
            notes.append(note)
            note = input('observation/note: ')
            thanks_msg = True
        if thanks_msg:
            print('Thank you, notes entered into log at ' + self.xytest_conf.filename)   
        return notes

    def run_range_measurement(self, loop_number):
        set_as_defaults = self.xytest_conf['set_meas_calib_as_new_defaults'][loop_number]
        params = ['PHYSICAL_RANGE_T','PHYSICAL_RANGE_P']
        if self.xytest_conf['should_measure_ranges'][loop_number]:
            if not(set_as_defaults):
                self.collect_calibrations()
            start_time = time.time()
            self.logwrite('Starting physical travel range measurement sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            self.m.measure_range(posids='all', axis='theta')
            self.m.measure_range(posids='all', axis='phi')
            for posid in self.posids:
                state = self.m.state(posid)
                self.track_file(state.log_path, commit='once')
                self.track_file(state.unit.filename, commit='always')
                for key in params:
                    self.logwrite(str(posid) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
            for posid in self.posids:
                self.summarizers[posid].update_loop_calibs(summarizer.meas_suffix, params)
            if not(set_as_defaults):
                self.restore_calibrations()
            self.logwrite('Calibration of physical travel ranges completed in ' + self._elapsed_time_str(start_time) + '.')
        for posid in self.posids:
            self.summarizers[posid].update_loop_calibs(summarizer.used_suffix, params)

    def run_calibration(self, loop_number):
        """Move positioners through a short sequence to calibrate them.
        """
        n_pts_calib_T = self.xytest_conf['n_points_calib_T'][loop_number]
        n_pts_calib_P = self.xytest_conf['n_points_calib_P'][loop_number]
        calib_mode = self.xytest_conf['calib_mode'][loop_number]
        set_as_defaults = self.xytest_conf['set_meas_calib_as_new_defaults'][loop_number]
        if n_pts_calib_T >= 4 and n_pts_calib_P >= 3:
            if not(set_as_defaults):
                self.collect_calibrations()
            start_time = time.time()
            self.logwrite('Starting arc calibration sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            self.m.n_points_calib_T = n_pts_calib_T
            self.m.n_points_calib_P = n_pts_calib_P
            params = ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P','OFFSET_X','OFFSET_Y']
            files = self.m.calibrate(posids='all', mode=calib_mode, save_file_dir=pc.xytest_plots_directory, save_file_timestamp=pc.filename_timestamp_str_now())
            for file in files:
                self.track_file(file, commit='once')
                self.logwrite('Calibration plot file: ' + file)
            for posid in self.posids:
                self.summarizers[posid].update_loop_calibs(summarizer.meas_suffix, params)
            if not(set_as_defaults):
                self.restore_calibrations()
            else:
                for posid in self.posids:
                    state = self.m.state(posid)
                    self.track_file(state.log_path, commit='once')
                    for key in params:
                        self.logwrite(str(posid) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
            for posid in self.posids:
                self.summarizers[posid].update_loop_calibs(summarizer.used_suffix, params)
            self.logwrite('Calibration with ' + str(n_pts_calib_T) + ' theta points and ' + str(n_pts_calib_P) + ' phi points completed in ' + self._elapsed_time_str(start_time) + '.')
        
    def run_xyaccuracy_test(self, loop_number):
        """Move positioners to a series of xy targets and measure performance.
        """
        
        log_suffix = self.xytest_conf['log_suffix']
        log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
        log_timestamp = pc.filename_timestamp_str_now()
        def movedata_name(posid):
            return pc.xytest_data_directory  + posid + '_' + log_timestamp + log_suffix + '_movedata.csv'
        def summary_plot_name(posid):
            return pc.xytest_plots_directory + posid + '_' + log_timestamp + log_suffix + '_xyplot'    

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
                    self.track_file(state.unit.filename, commit='always')
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

            # Test report and email only on certain tests
            if self.xytest_conf['should_email']:
                test_report.do_test_report(self.posids, all_data_by_posid, log_timestamp, self.pos_notes, self._elapsed_time_str(start_time), self.xytest_conf['email_list'])
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            # Email traceback to alert that test failed and why
            if self.xytest_conf['should_email']:
                test_report.email_error(traceback.format_exc(),log_timestamp)
            raise            
        self.logwrite(str(len(all_data_by_target)) + ' targets measured in ' + self._elapsed_time_str(start_time) + '.')

    def run_unmeasured_moves(self, loop_number):
        """Exercise positioners to a series of target positions without doing FVC measurements in-between.
        """
        n_moves = self.xytest_conf['n_unmeasured_moves_after_loop'][loop_number]
        if n_moves > 0:
            self.track_all_poslogs_once()
            max_log_length = test.m.state(test.posids[0]).max_log_length
            start_time = time.time()
            self.logwrite('Starting unmeasured move sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            status_str = lambda j : '... now at move ' + str(j) + ' of ' + str(n_moves) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops)
            for j in range(n_moves):
                if j % max_log_length == 0:
                    self.track_all_poslogs_once()
                if j % 1000 == 0:
                    self.logwrite(status_str(j))
                elif j % 50 == 0:
                    print(status_str(j))
                targ_xy = [np.Inf,np.Inf]
                while not(self.target_within_limits(targ_xy)):
                    targ_xy = self.rand_xy_targs_list[self.rand_xy_targs_idx]
                    self.rand_xy_targs_idx += 1
                    if self.rand_xy_targs_idx >= len(self.rand_xy_targs_list):
                        self.rand_xy_targs_idx = 0
                requests = self.generate_posXY_move_requests([targ_xy])[0]
                self.m.move(requests)
            self.logwrite(str(n_moves) + ' moves completed in ' + self._elapsed_time_str(start_time) + '.')
    
    def run_hardstop_strikes(self, loop_number):
        """Exercise positioners to a series of hardstop strikes without doing FVC measurements in-between.
        """
        n_strikes = self.xytest_conf['n_hardstop_strikes_after_loop'][loop_number]
        if n_strikes > 0:
            start_time = time.time()
            self.logwrite('Starting hardstop strike sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            retract_requests = {}
            for posid in self.posids:
                retract_requests[posid] = {'command':'posTP', 'target':[0,90], 'log_note':'retract for hardstop test strike'}
            for j in range(n_strikes):
                self.logwrite('... now at strike ' + str(j+1) + ' of ' + str(n_strikes) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
                self.m.move(retract_requests)
                self.m.rehome(self.posids)
            self.logwrite(str(n_strikes) + ' hardstop strikes completed in ' + self._elapsed_time_str(start_time) + '.')
    
    def get_svn_credentials(self):
        '''Query the user for credentials to the SVN, and store them.'''
        if self.xytest_conf['should_auto_commit_logs']:
            self.logwrite('Querying the user for SVN credentials. These will not be written to the log file.')
            print('')
            [svn_user, svn_pass, err] = XYTest.ask_user_for_creds(should_simulate=self.simulate)
            if err:
                self.logwrite('SVN credential failure. Logs will have to be manually uploaded to SVN after the test. This is very BAD, and needs to be resolved.')
                self.svn_user = ''
                self.svn_pass = ''
            else:
                self.logwrite('SVN user and pass verified.')
                self.svn_user = svn_user
                self.svn_pass = svn_pass
                
    def svn_add_commit(self, keep_creds=False):
        '''Commit logs through SVN.
        
        Optional keep_creds parameter instructs to *not* delete SVN user/pass after
        this commit is complete. Otherwise they get automatically deleted.
        '''
        self.logwrite('Files changed or generated: ' + str(list(test.new_and_changed_files.keys())))
        if self.xytest_conf['should_auto_commit_logs']:
            if not(self.svn_user and self.svn_pass):
                self.logwrite('No files were auto-committed to SVN due to lack of user / pass credentials.')
            elif self.new_and_changed_files:
                start_time = time.time()
                print('Will attempt to commit the logs automatically now. This may take a long time. In the messages printed to the screen for each file, a return value of 0 means it was committed to the SVN ok.')
                err1 = []
                err2 = []
                files_attempted = []
                n = 0
                n_total = len([x for x in test.new_and_changed_files.values() if x =='once' or x == 'always'])
                for file in self.new_and_changed_files.keys():
                    should_commit = self.new_and_changed_files[file]
                    if should_commit == 'always' or should_commit == 'once':
                        n += 1
                        if self.simulate:
                            err1.append(0)
                            err2.append(0)
                        else:
                            err1.append(os.system('svn add --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive ' + file))
                            err2.append(os.system('svn commit --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + file))
                        print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1[-1]) + ' (add) and ' + str(err2[-1]) + ' (commit)')
                        files_attempted.append(os.path.basename(file))
                    if should_commit == 'once' and not (err2[-1]):
                        self.new_and_changed_files[file] = 'do not commit'
                add_and_commit_errs = [err1[i] and err2[i] for i in range(len(err1))]
                if any(add_and_commit_errs):
                    print('Warning: it appears that not all the log or plot files committed ok to SVN. Check through carefully and do this manually. The files that failed were:')
                    for i in range(len(add_and_commit_errs)):
                        if add_and_commit_errs[i]:
                            print(files_attempted[i])
                if not(keep_creds):
                    del self.svn_user
                    del self.svn_pass
                print('SVN uploads completed in ' + self._elapsed_time_str(start_time))

    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.xytest_logfile,'a') as fh:
            fh.write(line+'\n')
        if stdout:
            print(line)
            
    def logwrite_conf(self,conf_file):
        """Standard function for copying a config file's contents to the test traveler log file.
        """
        with open(conf_file, newline='') as file:
            for line in file:
                if line[0] != '#' and line[0] != '\n': # skip blank or comment lines
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
                    ptl.set(posid, key, curr_val)
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
                    ptl.set(posid, key, self.old_currents[posid][key])
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
        r = np.sqrt(x**2 + y**2)
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

    def track_file(self, filename, commit='always'):
        """Use this to put new filenames into the list of new and changed files we keep track of.
        This list gets put into the log later, and is also used for auto-updating of the SVN.
        
          commit ... 'always'        --> always commit this file to the SVN upon svn_add_commit
                 ... 'once'          --> only commit this file to the SVN upon the next svn_add_commit
                 ... 'do not commit' --> do not commit this file (anymore) to the SVN
        """
        self.new_and_changed_files[filename] = commit
        self.xytest_conf['new_and_changed_files'] = self.new_and_changed_files
        
    def track_all_poslogs_once(self):
        '''Special function to run track_file on all the latest pos logs, since they are kind of
        a moving target. So it's nice to have a convenience function for that.
        '''
        for posid in self.posids:
            state = self.m.state(posid)
            self.track_file(state.log_path, commit='once')

    def collect_calibrations(self):
        '''Store all the current positioner calibration values for future use.
        Restore these with the restore_calibrations() method.
        '''
        self.calib_store = {}
        for posid in self.posids:
            self.calib_store[posid] = {}
            ptl = self.m.petal(posid)
            for calib_key in pc.nominals.keys():
                self.calib_store[posid][calib_key] = ptl.get(posid,calib_key)

    def restore_calibrations(self):
        '''Restore all the calibration values previously stored with the
        collect_calibrations() method.
        '''
        for posid in self.posids:
            for calib_key in pc.nominals.keys():
                ptl = self.m.petal(posid)
                ptl.set(posid, calib_key, self.calib_store[posid][calib_key])
        for ptl in self.m.petals:
            ptl.commit()

    def _calculate_and_check_n_loops(self):
        """Returns total number of loops in test configuration.
        (Also checks that all params in config file are consistent.)
        """
        keys = ['n_pts_across_grid','n_points_calib_T','n_points_calib_P','num_corr_max','should_measure_ranges','cruise_current_override','creep_current_override']
        all_n = [len(self.xytest_conf[key]) for key in keys]
        n = max(all_n) # if all lengthss are same, then they must all be as long as the longest one
        all_same = True
        for i in range(len(keys)):
            if all_n[i] != n:
                self.logwrite('Error: ' + keys[i] + ' has only ' + str(all_n[i]) + ' entries (expected ' + str(n) + ')')
                all_same = False
        if not(all_same):
            sys.exit('Not all loop lengths the same in config file ' + self.xytest_conf.filename)
        else:
            return n
    
    def _elapsed_time_str(self,start_time):
        """Standard string for elapsed time.
        """
        return format((time.time()-start_time)/60/60,'.2f') + ' hrs'

    @staticmethod
    def ask_user_for_creds(should_simulate=False):
        '''General function to gather SVN username and password from operator.
        '''
        gui_root = tkinter.Tk()
        print('Enter your svn username and password for committing the logs to the server. These will not be saved to the logfile, but will briefly be clear-text in this script\'s memory while it is running.')
        n_credential_tries = 4
        while n_credential_tries:
            svn_user = tkinter.simpledialog.askstring(title='SVN authentication',prompt='svn username:')
            svn_pass = tkinter.simpledialog.askstring(title='SVN authentication',prompt='svn password:')
            if should_simulate:
                err = 0
            else:
                err = os.system('svn --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive list')
            if err == 0:
                n_credential_tries = 0
            else:
                n_credential_tries -= 1
                print('SVN user / pass was not verified. This is the same as your DESI user/pass for DocDB and the Wiki.')
                print(str(n_credential_tries) + ' tries remaining.')
        gui_root.withdraw()
        return svn_user, svn_pass, err

if __name__=="__main__":
    test = XYTest()
    test.get_svn_credentials()
    test.logwrite('Start of positioner performance test.')
    for loop_num in range(test.starting_loop_number, test.n_loops):
        test.xytest_conf['current_loop_number'] = loop_num
        test.xytest_conf.write()
        test.logwrite('Starting xy test in loop ' + str(loop_num + 1) + ' of ' + str(test.n_loops))
        test.set_current_overrides(loop_num)
        test.run_range_measurement(loop_num)
        test.run_calibration(loop_num)
        test.run_xyaccuracy_test(loop_num)
        test.run_unmeasured_moves(loop_num)
        test.run_hardstop_strikes(loop_num)
        test.clear_current_overrides()
        test.svn_add_commit(keep_creds=True)
    test.logwrite('All test loops complete.')
    test.m.park(posids='all')
    test.logwrite('Moved positioners into \'parked\' position.')
    test.logwrite('Test complete.')
    test.track_all_poslogs_once()
    test.svn_add_commit(keep_creds=False)
