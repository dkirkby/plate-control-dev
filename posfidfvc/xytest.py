import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import fvchandler
import petal
import posmovemeasure
import posconstants as pc
import numpy as np
import time
import pos_xytest_plot
import um_test_report as test_report
import traceback
import configobj
import tkinter
import tkinter.filedialog
import csv


class XYTest(object):
    """XYTest handles running a fiber positioner xy accuracy test. It supports being called
    repeatedly in a loop, with variable settings for each loop in terms of number of calibration
    moves, number of test moves, number of unmeasured life moves, number of hardstop slams, etc.
    The idea is that we can really tailor a robust test suite into a single automated setup.
    """

    def __init__(self,configfile=''):
        """For the input 'configfile', you typically would leave it as the default empty string. This causes
        a gui file picker to come up. For debug purposes, if you want to short-circuit the gui because it is
        annoying, then you could argue a filename here. Templates for configfiles are found in the DESI svn at
        https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        
        # set up configuration traveler file that goes with this test, and begin logging
        os.makedirs(pc.test_logs_directory, exist_ok=True)
        if not(configfile):
            gui_root = tkinter.Tk()
            configfile = tkinter.filedialog.askopenfilename(initialdir=pc.test_settings_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title="Select the configuration file for this test run.")
            gui_root.destroy()
        self.config = configobj.ConfigObj(configfile,unrepr=True)
        initial_timestamp = pc.timestamp_str_now() 
        config_traveler_name = pc.test_logs_directory + initial_timestamp + '_' + os.path.basename(configfile)
        self.config.filename = config_traveler_name
        self.config.write()
        self.new_and_mod_files = [self.config.filename] # start a list to keep track of all files that need to be added / committed to SVN
        self.logwrite('File ' + str(configfile) + ' selected as template for test settings.')
        self.logwrite('Test will be run from a uniquely-generated traveler config file located at ' + str(self.config.filename) + ' which was based off the template.')
        
        # verifications of config file
        self.n_loops = self._calculate_and_check_n_loops()
        
        # set up fvc and platemaker
        fvc = fvchandler.FVCHandler(self.config['fvc_type'])       
        if self.config['platemaker_type'] == 'BUILT-IN':
            fvc.rotation = self.config['rotation']  # deg
            fvc.scale =  self.config['scale'] # mm/pixel
        self.logwrite('FVC initialized.')
        
        # set up positioners, fiducials, and petals
        self.pos_ids = self.config['pos_ids']
        self.pos_notes = self.config['pos_notes'] # notes for report to add about positioner (reported with positioner in same slot as pos_ids list)
        while len(self.pos_notes) < len(self.pos_ids):
            self.pos_notes.append('')
        fid_ids = self.config['fid_ids']
        ptl_ids = self.config['ptl_ids']
        petals = [petal.Petal(ptl_ids[0], self.pos_ids, fid_ids)] # single-petal placeholder for generality of future implementations, where we could have a list of multiple petals, and need to correlate pos_ids and fid_ids to thier particular petals
        for ptl in petals:
            ptl.anticollision_default = self.config['anticollision']
        self.m = posmovemeasure.PosMoveMeasure(petals,fvc)
        self.logwrite('posmovemeasure initialized.')

        # set up lookup table for random targets
        self.rand_xy_targs_idx = 0 # where we are in the random targets list
        self.rand_xy_targs_list = []
        targs_file = self.config['rand_xy_targs_file']
        with open(targs_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            header_rows_remaining = 1
            for row in reader:
                if header_rows_remaining:
                    header_rows_remaining -= 1
                else:
                    self.rand_xy_targs_list.append([float(row[0]),float(row[1])])
        self.logwrite('Read in ' + str(len(self.rand_xy_targs_list)) + ' xy targets from file ' + targs_file + ' and formed move requests.')

    def intro_questions(self):
        user_vals = []
        print('Please enter the name of who is running the test.',end=' ')
        user_vals.append('TEST OPERATOR: ' + input('your name: '))
        print('')
        
        print('Please enter the name of the test station.',end=' ')
        user_vals.append('TEST STATION: ' + input('station name: '))
        print('')
        
        print('Please enter the current temperature at the test stand (degrees Celsius). Leave blank if not measured.',end=' ')
        user_vals.append('TEMPERATURE (CELSIUS): ' + input('temperature: '))
        print('')
        
        print('Please enter the current relative humidity at the test stand. Leave blank if not measured.',end=' ')
        user_vals.append('RELATIVE HUMIDITY: ' + input('relative humidity: '))
        print('')
        
        print('You entered:')
        for s in user_vals:
            print('  ' + s)
        try_again = input('If this is ok, hit enter to continue. Otherwise, type any character and enter to start over: ')
        if try_again:
            self.intro_questions()
        else:
            for s in user_vals:
                self.logwrite('user-entry: ' + s)
        
    def get_and_log_comments_from_user(self):
        print('\nPlease enter any specific observations or notes about this test. These will be recorded into the test log. You can keep on entering notes until you hit enter on a blank line.',end=' ')
        thanks_msg = False
        note = input('observation/note: ')
        while note:
            self.logwrite('user-entry: OBSERVATION/NOTE: ' + note)
            note = input('observation/note: ')
            thanks_msg = True
        if thanks_msg:
            print('Thank you, notes entered into log at ' + self.config.filename)        

    def run_calibration(self, loop_number):
        """Move positioners through a short sequence to calibrate them.
        """
        n_pts_calib_T = self.config['n_points_calib_T'][loop_number]
        n_pts_calib_P = self.config['n_points_calib_P'][loop_number]
        if n_pts_calib_T >= 4 and n_pts_calib_P >= 3:
            if self.config['should_measure_ranges'][loop_number]:
                start_time = time.time()
                self.logwrite('Starting physical travel range measurement sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
                self.m.measure_range(pos_ids='all', axis='theta')
                self.m.measure_range(pos_ids='all', axis='phi')
                self.m.rehome(pos_ids='all')
                for pos_id in self.pos_ids:
                    state = self.m.state(pos_id)
                    for key in ['PHYSICAL_RANGE_T','PHYSICAL_RANGE_P']:
                        self.logwrite(str(pos_id) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
                self.logwrite('Calibration of physical travel ranges completed in ' + self._elapsed_time_str(start_time) + '.')
            start_time = time.time()
            self.logwrite('Starting arc calibration sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            self.m.n_points_full_calib_T = n_pts_calib_T
            self.m.n_points_full_calib_P = n_pts_calib_P
            self.m.calibrate(pos_ids='all', mode='full', save_file_dir=pc.test_logs_directory, save_file_timestamp=pc.timestamp_str_now())
            for pos_id in self.pos_ids:
                state = self.m.state(pos_id)
                for key in ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P','OFFSET_X','OFFSET_Y']:
                    self.logwrite(str(pos_id) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
            self.logwrite('Calibration with ' + str(n_pts_calib_T) + ' theta points and ' + str(n_pts_calib_P) + ' phi points completed in ' + self._elapsed_time_str(start_time) + '.')
        
    def run_xyaccuracy_test(self, loop_number):
        """Move positioners to a series of xy targets and measure performance.
        """
        
        log_suffix = self.config['log_suffix']
        log_suffix = ('_' + log_suffix) if log_suffix else '' # automatically add an underscore if necessary
        log_timestamp = pc.timestamp_str_now()
        def path_prefix(pos_id):
            return log_directory + os.path.sep + pos_id + '_' + log_timestamp + log_suffix
        def move_log_name(pos_id):
            return path_prefix(pos_id) + '_movedata.csv'
        def summary_log_name(pos_id):
            return path_prefix(pos_id) + '_summary.csv'
        def summary_plot_name(pos_id):
            return path_prefix(pos_id) + '_xyplot'    

        local_targets = self.generate_posXY_targets_grid(self.config['npoints_across_grid'][loop_number])
        
        submove_idxs = [i for i in range(self.num_corr_max+1)]
        
        # write headers for move data log files
        move_log_header = 'timestamp,cycle,move_log,target_x,target_y'
        submove_fields = ['meas_obsXY','errXY','err2D','posTP']
        for i in submove_idxs: move_log_header += ',meas_x' + str(i) + ',meas_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_x'  + str(i) + ',err_y' + str(i)
        for i in submove_idxs: move_log_header += ',err_xy' + str(i)
        for i in submove_idxs: move_log_header += ',pos_t'  + str(i) + ',pos_p' + str(i)
        move_log_header += '\n'
        for pos_id in self.pos_ids:
            file = open(move_log_name(pos_id),'w')
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
        start_timestamp = pc.timestamp_str_now()
        
        # run the test
        try:  
            start_time = time.time()
            for these_targets in all_targets:
                targ_num += 1
                print('')
                self.logwrite('MEASURING TARGET ' + str(targ_num) + ' OF ' + str(len(all_targets)))
                self.logwrite('Local target (posX,posY)=(' + format(local_targets[targ_num-1][0],'.3f') + ',' + format(local_targets[targ_num-1][1],'.3f') + ') for each positioner.')
                this_timestamp = pc.timestamp_now_str()
                these_meas_data = self.m.move_and_correct(these_targets, num_corr_max=self.num_corr_max)
                
                # store this set of measured data
                all_data_by_target.append(these_meas_data)
                for pos_id in these_targets.keys():
                    all_data_by_pos_id[pos_id]['targ_obsXY'].append(these_meas_data[pos_id]['targ_obsXY'])
                    for sub in submove_idxs:
                        for key in submove_fields:
                            all_data_by_pos_id[pos_id][key][sub].append(these_meas_data[pos_id][key][sub])              
                
                # update summary data log
                for pos_id in self.pos_ids:
                    summary_log_data =  'pos_id,' + str(pos_id) + '\n'
                    summary_log_data += 'log_suffix,' + str(log_suffix) + '\n'
                    summary_log_data += 'cycles at start,' + str(start_cycles[pos_id]) + '\n'
                    summary_log_data += 'cycles at finish,' + str(self.m.state(pos_id).read('TOTAL_MOVE_SEQUENCES')) + '\n'
                    summary_log_data += 'start time,' + start_timestamp + '\n'
                    summary_log_data += 'finish time,' + this_timestamp + '\n'
                    summary_log_data += 'num targets measured,' + str(len(all_data_by_target)) + '\n'
                    summary_log_data += 'num corrections max,' + str(self.num_corr_max) + '\n'
                    summary_log_data += 'submove index -->'
                    for i in submove_idxs: summary_log_data += ',' + str(i)
                    summary_log_data += '\n'
                    for calc in ['max','min','mean','rms']:
                        summary_log_data += calc + '(um)'
                        for i in submove_idxs:
                            this_submove_data = all_data_by_pos_id[pos_id]['err2D'][i]
                            if calc == 'max':    summary_log_data += ',' + str(np.max(this_submove_data) * pc.um_per_mm)
                            elif calc == 'min':  summary_log_data += ',' + str(np.min(this_submove_data) * pc.um_per_mm)
                            elif calc == 'mean': summary_log_data += ',' + str(np.mean(this_submove_data) * pc.um_per_mm)
                            elif calc == 'rms':  summary_log_data += ',' + str(np.sqrt(np.mean(np.array(this_submove_data)**2)) * pc.um_per_mm)
                            else: pass
                            if i == submove_idxs[-1]: summary_log_data += '\n'
                    file = open(summary_log_name(pos_id),'w')
                    file.write(summary_log_data)
                    file.close()
        
                # update test data log
                for pos_id in these_targets.keys():
                    state = self.m.state(pos_id)
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
            for pos_id in all_data_by_pos_id.keys():
                posmodel = self.m.posmodel(pos_id)
                title = log_timestamp + log_suffix
                center = [posmodel.state.read('OFFSET_X'),posmodel.state.read('OFFSET_Y')]
                theta_min = posmodel.trans.posTP_to_obsTP([min(posmodel.targetable_range_T),0])[0]
                theta_max = posmodel.trans.posTP_to_obsTP([max(posmodel.targetable_range_T),0])[0]
                theta_range = [theta_min,theta_max]
                r1 = posmodel.state.read('LENGTH_R1')
                r2 = posmodel.state.read('LENGTH_R2')
                pos_xytest_plot.plot(summary_plot_name(pos_id),pos_id,all_data_by_pos_id[pos_id],center,theta_range,r1,r2,title)

            # Test report and email only on certain tests
            if self.config['should_email']:
                test_report.do_test_report(self.pos_ids, all_data_by_pos_id, log_timestamp, self.pos_notes, self._elapsed_time_str(start_time), self.config['email_list'])
             
            

        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            #Email traceback to alert that test failed and why
            if self.config['should_email']:
                test_report.email_error(traceback.format_exc(),log_timestamp)
            raise
            
        
        self.logwrite(str(NTARGETS) + ' targets measured in ' + self._elapsed_time_str(start_time) + '.')

    def run_unmeasured_moves(self, loop_number):
        """Exercise positioners to a series of target positions without doing FVC measurements in-between.
        """
        n_moves = self.config['n_unmeasured_moves_between_loops']
        if loop_number < self.n_loops - 1 and n_moves > 0: # the last loop does not have unmeasured moves after it
            start_time = time.time()
            self.logwrite('Starting unmeasured move sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            for j in range(n_moves):
                status_str = '... now at move ' + str(j+1) + ' of ' + str(n_moves) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops)
                if j % 1000 == 0:
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
        n_strikes = self.config['n_hardstop_strikes_between_loops']
        if loop_number < self.n_loops - 1 and n_strikes > 0: # the last loop does not have hardstop strikes after it
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

    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler config file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        filehandle = open(self.config.filename,'a')
        filehandle.write('\n' + line)
        filehandle.close()
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
                curr_val = self.config['cruise_current_override'][loop_number]
            else:
                curr_val = self.config['creep_current_override'][loop_number]
            for pos_id in self.pos_ids:
                state = self.m.state(pos_id)
                self.old_currents[pos_id][key] = state.read(key)
                if curr_val != None:
                    state.write(key,curr_val)
                    self.logwrite(str(pos_id) + ': Set ' + key + ' to ' + str(curr_val))
        
    def clear_current_overrides(self):
        """Restore current settings for each positioner to their original values.
        """
        for key in ['CURR_CRUISE','CURR_CREEP']:
            for pos_id in self.pos_ids:
                state = self.m.state(pos_id)
                state.write(key, self.old_currents[pos_id][key])
                self.logwrite(str(pos_id) + ': Restored ' + key + ' to ' + str(self.old_currents[pos_id][key]))

    def generate_posXY_targets_grid(self, npoints_across_grid):
        """Make rectilinear grid of local (x,y) targets. Returns a list.
        """
        r_max = self.config['targ_max_radius']
        line = np.linspace(-r_max,r_max,npoints_across_grid)
        targets = [[x,y] for x in line for y in line]
        for i in range(len(targets)):
            if not(self.target_within_limits(targets[i])):
                targets.pop(i)
        return targets

    def target_within_limits(self, xytarg):
        """Check whether [x,y] target is within the patrol limits.
        """
        r_min = self.config['targ_min_radius']
        r_max = self.config['targ_max_radius']
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

    def _calculate_and_check_n_loops(self):
        """Returns total number of loops in test configuration.
        (Also checks that all params in config file are consistent.)
        """
        keys = ['n_pts_across_grid','n_points_calib_T','n_points_calib_P','num_corr_max','should_measure_ranges','cruise_current_override','creep_current_override']
        all_n = [len(self.config[key]) for key in keys]
        n = max(all_n) # if all lengthss are same, then they must all be as long as the longest one
        all_same = True
        for i in range(len(keys)):
            if all_n(i) != n:
                self.logwrite('Error: ' + keys[i] + ' has only ' + str(all_n(i)) + ' entries (expected ' + str(n) + ')')
                all_same = False
        if not(all_same):
            sys.exit('Not all loop lengths the same in config file ' + self.config.filename)
        else:
            return n
    
    def _elapsed_time_str(self,start_time):
        """Standard string for elapsed time.
        """
        return format((time.time()-start_time)/60/60,'.2f') + ' hrs'
    
    def svn_add_commit(self):
        # Commit logs through SVN
        if self.config['should_auto_commit_logs']:
            all_files = ''
            for file in self.new_and_mod_files:
                all_files += ' ' + file
            if all_files:
                self.logwrite('The following files were generated or modified during the test and need to be added / committed to svn:' + all_files)
                print('')
                print('Enter you svn username and password for committing the logs to the server. These will not be saved to the logfile, but will briefly be clear-text in this script''s memory while it is running.')
                svn_user = input('svn username: ')
                svn_pass = input('svn password: ')
                print('Will attemp to commit the logs automatically now. This may take a few minutes...')
                os.system('svn add --username j' + svn_user + ' --password ' + svn_pass + ' --non-interactive' + all_files)
                err = os.system('svn commit --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive -m "autocommit from xytest script"' + all_files)
                del svn_user
                del svn_pass
                if err == 0:
                    print('...automatic svn commit appears to have worked.')
                else:
                    print('...automatic svn commit may have failed. We''ll need to check manually and make sure all files uploaded properly. A list of the files needing upload is in the traveler conf file.')

if __name__=="__main__":
    test = XYTest()
    test.logwrite('Start of positioner performance test.')
    test.logwrite('Code version: ' + pc.code_version)
    test.intro_questions()
    test.get_and_log_comments_from_user()

    for loop_num in range(test.n_loops):
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
    test.get_and_log_comments_from_user()
    test.logwrite('Test complete.')    
    test.svn_add_commit()
