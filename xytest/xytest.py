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
import csv
import getpass
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
            self.xytest_conf.filename = pc.xytest_logs_directory + pc.filename_timestamp_str_now() + '_' + os.path.basename(xytest_conf)
            self.new_and_changed_files = set()  # start a set to keep track of all files that need to be added / committed to SVN
            self.track_file(self.xytest_conf.filename)
            self.xytest_conf.final_comment.append('\n\n# *** TEST LOG ***') # just for formatting
            self.xytest_conf.write()
            self.logwrite('Hardware setup file: ' + hwsetup_conf)
            self.logwrite('Test template file: ' + xytest_conf)
            self.logwrite('Test traveler file:' + self.xytest_conf.filename)
        else:
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
        self.pos_ids = self.hwsetup_conf['pos_ids']
        self.pos_notes = self.hwsetup_conf['pos_notes'] # notes for report to add about positioner (reported with positioner in same slot as pos_ids list)
        while len(self.pos_notes) < len(self.pos_ids):
            self.pos_notes.append('')
        fid_ids = self.hwsetup_conf['fid_ids']
        ptl_id = self.hwsetup_conf['ptl_id']
        ptl = petal.Petal(ptl_id, self.pos_ids, fid_ids, simulator_on=self.simulate, printfunc=self.logwrite)
        ptl.anticollision_default = self.xytest_conf['anticollision']
        self.m = posmovemeasure.PosMoveMeasure([ptl],fvc,printfunc=self.logwrite)
        self.pos_ids = self.m.all_pos_ids()
        self.logwrite('Positoners: ' + str(self.pos_ids))
        self.logwrite('Positoner notes: ' + str(self.pos_notes))
        self.logwrite('Fiducials: ' + str(fid_ids))
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
        summarizer_init_data['xytest log file']     = self.xytest_conf.filename
        summarizer_init_data['code version']        = pc.code_version
        user_vals = self.intro_questions()
        for key in user_vals.keys():
            self.logwrite('user-entry: ' + key + ': ' + user_vals[key])
            summarizer_init_data[key] = user_vals[key]
        summarizer_init_data['operator notes'] = self.get_and_log_comments_from_user()
        for pos_id in self.pos_ids:
            state = self.m.petals[0].get(pos_id).state
            self.summarizers[pos_id] = summarizer.Summarizer(state,summarizer_init_data)
            self.track_file(self.summarizers[pos_id].filename)
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

    def run_calibration(self, loop_number):
        """Move positioners through a short sequence to calibrate them.
        """
        n_pts_calib_T = self.xytest_conf['n_points_calib_T'][loop_number]
        n_pts_calib_P = self.xytest_conf['n_points_calib_P'][loop_number]
        if n_pts_calib_T >= 4 and n_pts_calib_P >= 3:
            if self.xytest_conf['should_measure_ranges'][loop_number]:
                start_time = time.time()
                self.logwrite('Starting physical travel range measurement sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
                self.m.measure_range(pos_ids='all', axis='theta')
                self.m.measure_range(pos_ids='all', axis='phi')
                for pos_id in self.pos_ids:
                    state = self.m.state(pos_id)
                    self.track_file(state.unit.filename)
                    for key in ['PHYSICAL_RANGE_T','PHYSICAL_RANGE_P']:
                        self.logwrite(str(pos_id) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
                self.logwrite('Calibration of physical travel ranges completed in ' + self._elapsed_time_str(start_time) + '.')
            self.m.rehome(pos_ids='all')
            start_time = time.time()
            self.logwrite('Starting arc calibration sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            self.m.n_points_full_calib_T = n_pts_calib_T
            self.m.n_points_full_calib_P = n_pts_calib_P
            files = self.m.calibrate(pos_ids='all', mode='full', save_file_dir=pc.xytest_plots_directory, save_file_timestamp=pc.filename_timestamp_str_now())
            for file in files:
                self.track_file(file)
                self.logwrite('Calibration plot file: ' + file)
            for pos_id in self.pos_ids:
                state = self.m.state(pos_id)
                for key in ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P','OFFSET_X','OFFSET_Y']:
                    self.logwrite(str(pos_id) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
            self.logwrite('Calibration with ' + str(n_pts_calib_T) + ' theta points and ' + str(n_pts_calib_P) + ' phi points completed in ' + self._elapsed_time_str(start_time) + '.')
        
    def run_xyaccuracy_test(self, loop_number):
        """Move positioners to a series of xy targets and measure performance.
        """
        
        log_suffix = self.xytest_conf['log_suffix']
        log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
        log_timestamp = pc.filename_timestamp_str_now()
        def move_log_name(pos_id):
            return pc.xytest_data_directory  + pos_id + '_' + log_timestamp + log_suffix + '_movedata.csv'
        def summary_plot_name(pos_id):
            return pc.xytest_plots_directory + pos_id + '_' + log_timestamp + log_suffix + '_xyplot'    

        n_pts_calib_T = self.xytest_conf['n_points_calib_T'][loop_number]
        n_pts_calib_P = self.xytest_conf['n_points_calib_P'][loop_number]
        for pos_id in self.pos_ids:
            self.summarizers[pos_id].update_loop_inits(move_log_name(pos_id), n_pts_calib_T, n_pts_calib_P)

        local_targets = self.generate_posXY_targets_grid(self.xytest_conf['n_pts_across_grid'][loop_number])
        self.logwrite('Number of local targets = ' + str(len(local_targets)))
        self.logwrite('Local target xy positions: ' + str(local_targets))
        
        num_corr_max = self.xytest_conf['num_corr_max'][loop_number]
        submove_idxs = [i for i in range(num_corr_max+1)]
        self.logwrite('Number of corrections max = ' + str(num_corr_max))
        
        # write headers for move data log files
        move_log_header = 'timestamp,cycle,move_log,target_x,target_y'
        submove_fields = ['meas_obsXY','errXY','err2D','posTP']
        for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_x'  + str(i) + ',err_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_xy' + str(i)
        for i in submove_idxs: move_log_header += ',pos_t'  + str(i) + ',pos_p' + str(i)
        move_log_header += '\n'
        for pos_id in self.pos_ids:
            filename = move_log_name(pos_id)
            self.track_file(filename)
            file = open(filename,'w')
            file.write(move_log_header)
            file.close()
        
        # transform test grid to each positioner's global position, and create all the move request dictionaries
        all_targets = []
        for local_target in local_targets:
            these_targets = {}
            for pos_id in self.pos_ids:
                trans = self.m.trans(pos_id)
                these_targets[pos_id] = {'command':'obsXY', 'target':trans.posXY_to_obsXY(local_target)}
            all_targets.append(these_targets)
            
        # initialize some data structures for storing test data
        targ_num = 0
        all_data_by_target = []
        all_data_by_pos_id = {}
        start_cycles = {}
        for pos_id in self.pos_ids:
            all_data_by_pos_id[pos_id] = {'targ_obsXY': []}
            for key in submove_fields:
                all_data_by_pos_id[pos_id][key] = [[] for i in submove_idxs]
            start_cycles[pos_id] = self.m.state(pos_id).read('TOTAL_MOVE_SEQUENCES')
        
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
                for pos_id in these_targets.keys():
                    all_data_by_pos_id[pos_id]['targ_obsXY'].append(these_meas_data[pos_id]['targ_obsXY'])
                    for sub in submove_idxs:
                        for key in submove_fields:
                            all_data_by_pos_id[pos_id][key][sub].append(these_meas_data[pos_id][key][sub])              
                
                # update summary data logs
                for pos_id in self.pos_ids:
                    self.summarizers[pos_id].write_row(all_data_by_pos_id[pos_id]['err2D'])
        
                # update test data log
                for pos_id in these_targets.keys():
                    state = self.m.state(pos_id)
                    self.track_file(state.log_path)
                    self.track_file(state.unit.filename)
                    row = this_timestamp
                    row += ',' + str(state.read('TOTAL_MOVE_SEQUENCES'))
                    row += ',' + str(state.log_basename)
                    row += ',' + str(these_targets[pos_id]['targ_obsXY'][0])
                    row += ',' + str(these_targets[pos_id]['targ_obsXY'][1])
                    for key in submove_fields:
                        for submove_data in these_targets[pos_id][key]:
                            if isinstance(submove_data,list):
                                for j in range(len(submove_data)):
                                    row += ',' + str(submove_data[j])
                            else:
                                row += ',' + str(submove_data)
                    row += '\n'
                    file = open(move_log_name(pos_id),'a')
                    file.write(row)
                    file.close()
            
            # make summary plots showing the targets and measured positions
            if self.xytest_conf['should_make_plots']:
                for pos_id in all_data_by_pos_id.keys():
                    posmodel = self.m.posmodel(pos_id)
                    title = log_timestamp + log_suffix
                    center = [posmodel.state.read('OFFSET_X'),posmodel.state.read('OFFSET_Y')]
                    theta_min = posmodel.trans.posTP_to_obsTP([min(posmodel.targetable_range_T),0])[0]
                    theta_max = posmodel.trans.posTP_to_obsTP([max(posmodel.targetable_range_T),0])[0]
                    theta_range = [theta_min,theta_max]
                    r1 = posmodel.state.read('LENGTH_R1')
                    r2 = posmodel.state.read('LENGTH_R2')
                    filenames = pos_xytest_plot.plot(summary_plot_name(pos_id),pos_id,all_data_by_pos_id[pos_id],center,theta_range,r1,r2,title)
                    self.logwrite(pos_id + ': Summary log file: ' + self.summarizers[pos_id].filename)
                    self.logwrite(pos_id + ': Full data log file: ' + move_log_name(pos_id))
                    for filename in filenames:
                        self.logwrite(pos_id + ': Summary plot file: ' + filename)
                        self.track_file(filename)

            # Test report and email only on certain tests
            if self.xytest_conf['should_email']:
                test_report.do_test_report(self.pos_ids, all_data_by_pos_id, log_timestamp, self.pos_notes, self._elapsed_time_str(start_time), self.xytest_conf['email_list'])
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
            start_time = time.time()
            self.logwrite('Starting unmeasured move sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            for j in range(n_moves):
                status_str = '... now at move ' + str(j+1) + ' of ' + str(n_moves) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops)
                if j % 1000 == 0:
                    for pos_id in self.pos_ids:
                        state = self.m.state(pos_id)
                        self.track_file(state.log_path)
                    self.logwrite(status_str)
                elif j % 50 == 0:
                    print(status_str)
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
            for pos_id in self.pos_ids:
                retract_requests[pos_id] = {'command':'posTP', 'target':[0,90], 'log_note':'retract for hardstop test strike'}
            for j in range(n_strikes):
                print('... now at strike ' + str(j+1) + ' of ' + str(n_strikes) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
                self.m.move(retract_requests)
                self.m.rehome(self.pos_ids)
            self.logwrite(str(n_strikes) + ' hardstop strikes completed in ' + self._elapsed_time_str(start_time) + '.')
    
    def get_svn_credentials(self):
        '''Query the user for credentials to the SVN.'''
        if self.xytest_conf['should_auto_commit_logs'] and not(self.simulate):
            self.logwrite('Querying the user for SVN credentials. These will not be written to the log file.')
            print('')
            print('Enter your svn username and password for committing the logs to the server. These will not be saved to the logfile, but will briefly be clear-text in this script\'s memory while it is running.')
            n_credential_tries = 4
            while n_credential_tries:
                self.svn_user = input('svn username: ')
                self.svn_pass = getpass.getpass('svn password: ')
                err = os.system('svn --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive list')
                if err == 0:
                    self.logwrite('SVN user and pass verified.')
                    n_credential_tries = 0
                else:
                    n_credential_tries -= 1
                    print('SVN user / pass was not verified. This is the same as your DESI user/pass for DocDB and the Wiki.')
                    print(str(n_credential_tries) + ' tries remaining.')
            if err:
                self.logwrite('SVN credential failure. Logs will have to be manually uploaded to SVN after the test. This is very BAD, and needs to be resolved.')
                self.svn_user = ''
                self.svn_pass = ''
                
    def svn_add_commit(self):
        # Commit logs through SVN
        if self.xytest_conf['should_auto_commit_logs'] and not(self.simulate):
            if not(self.svn_user and self.svn_pass):
                self.logwrite('No files were auto-committed to SVN due to lack of user / pass credentials.')
            elif self.new_and_changed_files:
                start_time = time.time()
                print('Will attempt to commit the logs automatically now. This may take a long time. In the messages printed to the screen for each file, a return value of 0 means it was committed to the SVN ok.')
                err1 = []
                err2 = []
                n = 0
                n_total = len(self.new_and_changed_files)
                for file in self.new_and_changed_files:
                    n += 1
                    err1.append(os.system('svn add --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive ' + file))
                    err2.append(os.system('svn commit --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + file))
                    print('SVN upload of file ' + str(n) + ' of ' + str(n_total) + ' (' + os.path.basename(file) + ') returned: ' + str(err1[-1]) + ' (add) and ' + str(err2[-1]) + ' (commit)')
                if any(err2):
                    print('Warning: it appears that not all the log or plot files committed ok to SVN. Check through carefully and do this manually. The files that failed were:')
                    for err in err2:
                        if err:
                            file = self.new_and_changed_files(err2.index(err))
                            print(file)
                del self.svn_user
                del self.svn_pass
                print('SVN uploads completed in ' + self._elapsed_time_str(start_time))
                
    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler config file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        self.xytest_conf.final_comment.append(line)
        self.xytest_conf.write()
        if stdout:
            print(line)

    def set_current_overrides(self, loop_number):
        """If the test config calls for overriding cruise or creep currents to a particular value
        for this loop, this method sets that. It also stores the old setting for later restoration.
        """
        self.old_currents = {}
        for pos_id in self.pos_ids:
            self.old_currents[pos_id] = {}
        for key in ['CURR_CRUISE','CURR_CREEP']:
            if key == 'CURR_CRUISE':
                curr_val = self.xytest_conf['cruise_current_override'][loop_number]
            else:
                curr_val = self.xytest_conf['creep_current_override'][loop_number]
            for pos_id in self.pos_ids:
                state = self.m.state(pos_id)
                self.old_currents[pos_id][key] = state.read(key)
                if curr_val != None:
                    state.write(key,curr_val)
                    self.logwrite(str(pos_id) + ': Set ' + key + ' to ' + str(curr_val))
                else:
                    self.logwrite(str(pos_id) + ': ' + key + ' is ' + str(self.old_currents[pos_id][key]))
                    self.old_currents[pos_id][key] = None # indicates later in clear_current_overrides() method whether to do anything
        
    def clear_current_overrides(self):
        """Restore current settings for each positioner to their original values.
        """
        for key in ['CURR_CRUISE','CURR_CREEP']:
            for pos_id in self.pos_ids:
                if self.old_currents[pos_id][key] != None:
                    state = self.m.state(pos_id)
                    state.write(key, self.old_currents[pos_id][key])
                    self.logwrite(str(pos_id) + ': Restored ' + key + ' to ' + str(self.old_currents[pos_id][key]))

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
            for pos_id in sorted(self.pos_ids):
                these_targets[pos_id] = {'command':'posXY', 'target':local_target}
            requests.append(these_targets)
        return requests

    def track_file(self,filename):
        """Use this to put new filenames into the list of new and changed files we keep track of.
        This list gets put into the log later, and is also used for auto-updating of the SVN.
        """
        self.new_and_changed_files.add(filename)
        self.xytest_conf['new_and_changed_files'] = self.new_and_changed_files

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

if __name__=="__main__":
    test = XYTest()
    test.get_svn_credentials()
    test.logwrite('Start of positioner performance test.')
    for loop_num in range(test.starting_loop_number, test.n_loops):
        test.xytest_conf['current_loop_number'] = loop_num
        test.xytest_conf.write()
        test.logwrite('Starting xy test in loop ' + str(loop_num + 1) + ' of ' + str(test.n_loops))
        test.set_current_overrides(loop_num)
        test.run_calibration(loop_num)
        test.run_xyaccuracy_test(loop_num)
        test.run_unmeasured_moves(loop_num)
        test.run_hardstop_strikes(loop_num)
        test.clear_current_overrides()
    test.logwrite('All test loops complete.')
    test.m.park(pos_ids='all')
    test.logwrite('Moved positioners into \'parked\' position.')
    test.logwrite('Test complete.')
    test.logwrite('Files changed or generated: ' + str(test.new_and_changed_files))
    test.svn_add_commit()
