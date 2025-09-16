import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
    basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
    sys.path.append(os.path.abspath(basepath+'/petal/'))
    sys.path.append(os.path.abspath(basepath+'/posfidfvc/'))
else:
    sys.path.append(os.path.abspath('../petal/'))
    sys.path.append(os.path.abspath('../posfidfvc/'))

import fvchandler
import petal
import posmovemeasure
import posconstants as pc
import summarizer
import numpy as np
import math
import time
import pos_xytest_plot
#import um_test_report as test_report
import traceback
import configobj
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
import csv
import collections
import getpass
from astropy.io import ascii

class _read_key:
    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

class XYTest(object):
    """XYTest handles running a fiber positioner xy accuracy test. It supports being called
    repeatedly in a loop, with variable settings for each loop in terms of number of calibration
    moves, number of test moves, number of unmeasured life moves, number of hardstop slams, etc.
    The idea is that we can really tailor a robust test suite into a single automated setup.
    """

    def __init__(self,hwsetup_conf='',xytest_conf='',USE_LOCAL_PRESETS=False):
        """For the inputs hwsetup_conf and xytest_conf, you typically would leave these as the default empty
        string. This causes a gui file picker to come up. For debug purposes, if you want to short-circuit the
        gui because it is annoying, then you could argue a filename here. Templates for configfiles are found
        in the DESI svn at
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/hwsetups/
            https://desi.lbl.gov/svn/code/focalplane/fp_settings/test_settings/
        """
        # set up configuration and traveler files that goes with this test, and begin logging
        if not USE_LOCAL_PRESETS:
            gui_root = tkinter.Tk()
            if not(hwsetup_conf):
                message = "Select hardware setup file."
                hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
            if not(xytest_conf):
                message = "Select test configuration file."
                xytest_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['test_settings'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
            if not(hwsetup_conf) or not(xytest_conf):
                tkinter.messagebox.showwarning(title='Files not found.',message='Not all configuration files specified. Exiting program.')
                gui_root.withdraw()
                sys.exit(0)
            gui_root.withdraw()


        if USE_LOCAL_PRESETS:
            self.presets={}
            try:
                presets_file=os.environ['TEST_PRESETS_CONFIG']
                presets = configobj.ConfigObj(presets_file,unrepr=True)
                self.presets['supply voltage']=presets['supply_voltage']
                self.presets['relative humidity']=presets['relative_humidity']
                self.presets['test station']=os.environ['TEST_STAND_NAME']
            except:
                USE_LOCAL_PRESETS=False


        self.use_local_presets=    USE_LOCAL_PRESETS
        self.hwsetup_conf = configobj.ConfigObj(hwsetup_conf,unrepr=True,encoding='utf-8')
        self.xytest_conf = configobj.ConfigObj(xytest_conf,unrepr=True,encoding='utf-8')
        self.starting_loop_number = self.xytest_conf['current_loop_number']
        self.n_loops = self._calculate_and_check_n_loops()
        if self.starting_loop_number == 0:
            # The status file is used to maintain current status of the test in case of test disruption.
            self.xytest_conf.filename = pc.dirs['temp_files'] + 'xytest_status.conf'
            self.xytest_logfile = pc.dirs['xytest_logs'] + pc.filename_timestamp_str_now() + '_' + os.path.splitext(os.path.basename(xytest_conf))[0] + '.log'
            self.xytest_conf['logfile']=self.xytest_logfile
            self.xytest_conf.write()
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
        ptl_id=self.hwsetup_conf['ptl_id']
        shape = 'asphere' if self.hwsetup_conf['plate_type'] == 'petal' else 'flat'

        try:
            db_commit_on = self.hwsetup_conf['db_commit_on']
        except:
            db_commit_on = False

        try:
            petal_proxy = self.hwsetup_conf['use_petal_proxy']
            from DOSlib.proxies import Petal
        except:
            petal_proxy = False

        if petal_proxy:
            ptl = Petal(ptl_id)
        else:
            ptl = petal.Petal(ptl_id,
                posids=[],
                fidids=[],
                simulator_on=self.simulate,
                sched_stats_on=True,
                printfunc=self.logwrite,
                collider_file=self.xytest_conf['collider_file'],
                db_commit_on=db_commit_on,
                anticollision=self.xytest_conf['anticollision']) # petal_shape=shape)
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
        self.m.n_extradots_expected = self.hwsetup_conf['num_extra_dots']
        self.logwrite('Number of extra fiducial dots: ' + str(self.m.n_extradots_expected))
        extradots_filename = pc.dirs['temp_files'] + os.path.sep + 'extradots.csv'
        if self.m.n_extradots_expected > 0 and os.path.isfile(extradots_filename):
            with open(extradots_filename,'r',newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    self.m.extradots_fvcXY.append([float(row['x_pix']),float(row['y_pix'])])
                self.logwrite('Read ' + str(len(self.m.extradots_fvcXY)) + ' from csv file.')
        else:
            self.logwrite('Re-identifying fiducial locations.')
            self.m.identify_fiducials()
        self.logwrite('Petal: ' + str(ptl_id))
        self.m.make_plots_during_calib = self.xytest_conf['should_make_plots']
        self.logwrite('Automatic generation of calibration and submove plots is turned ' + ('ON' if self.xytest_conf['should_make_plots'] else 'OFF') + '.')
        self.logwrite('PosMoveMeasure initialized.')
        fid_settings_done = self.m.set_fiducials('on')
        self.logwrite('Fiducials turned on: ' + str(fid_settings_done))
        if self.m.fvc.fvcproxy: #Remind FVC that it needs to look for all dots, not all dots without a fiducial
            self.m.fvc.fvcproxy.send_fvc_command('make_targets',len(self.posids) + self.m.n_ref_dots)

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
        user_vals = self.intro_questions()
        for key in user_vals.keys():
            self.logwrite('user-entry: ' + key + ': ' + user_vals[key])
            summarizer_init_data[key] = user_vals[key]
        summarizer_init_data['operator notes'] = None #self.get_and_log_comments_from_user()
        #import pdb; pdb.set_trace()
        for posid in self.posids:
            state = self.m.state(posid)
            self.summarizers[posid] = summarizer.Summarizer(state,summarizer_init_data)
            self.track_file(self.summarizers[posid].filename, commit='always')
        self.logwrite('Data summarizers for all positioners initialized.')

        # set up lookup table for random targets
        self.rand_xy_targs_idx = 0 # where we are in the random targets list
        self.rand_xy_targs_list = []
        targs_file = pc.dirs['test_settings'] + self.xytest_conf['rand_xy_targs_file']
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
            if self.use_local_presets and key in self.presets:
                user_vals[key]=self.presets[key]
            else:
                user_vals[key] = input(key + ': ')
        print('')
        print('You entered:')
        nchar = max([len(key) for key in user_vals.keys()])
        for key in user_vals.keys():
            print('  ' + format(key + ':',str(nchar + 2) + 's') + user_vals[key])
        print('')
        try_again = input('If this is ok, hit enter to continue. Otherwise, type any character and enter to start over: ')
        if try_again:
            self.use_local_presets=False
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
                self.track_file(state.conf.filename, commit='always')
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
        try:
            keepR1R2 = self.xytest_conf['keep_arm_old_armlengths'][loop_number]
        except:
            keepR1R2 = False
        params = ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P','OFFSET_X','OFFSET_Y']
        if n_pts_calib_T >= 4 and n_pts_calib_P >= 3:
            if not(set_as_defaults):
                self.collect_calibrations()
            elif keepR1R2:
                self.collect_calibrations()
                params = ['OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P','OFFSET_X','OFFSET_Y']
            start_time = time.time()
            self.logwrite('Starting arc calibration sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            self.m.n_points_calib_T = n_pts_calib_T
            self.m.n_points_calib_P = n_pts_calib_P
            self.m.calibrate(posids='all', mode='rough')
            files = self.m.calibrate(posids='all', mode=calib_mode, save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=pc.filename_timestamp_str_now())
            for file in files:
                self.track_file(file, commit='once')
                self.logwrite('Calibration plot file: ' + file)
            for posid in self.posids:
                self.summarizers[posid].update_loop_calibs(summarizer.meas_suffix, params)
            if not(set_as_defaults):
                self.restore_calibrations()
            else:
                if keepR1R2:
                    self.restore_calibrations(keys = ['LENGTH_R1','LENGTH_R2'])
                for posid in self.posids:
                    state = self.m.state(posid)
                    self.track_file(state.log_path, commit='once')
                    for key in params:
                        self.logwrite(str(posid) + ': Set ' + str(key) + ' = ' + format(state.read(key),'.3f'))
            self.logwrite('Calibration with ' + str(n_pts_calib_T) + ' theta points and ' + str(n_pts_calib_P) + ' phi points completed in ' + self._elapsed_time_str(start_time) + '.')
        else:
            self.m.one_point_calibration(posids='all', mode='posTP')
        for posid in self.posids:
            self.summarizers[posid].update_loop_calibs(summarizer.used_suffix, params)


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
                import pdb; pdb.set_trace()

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

            # Test report and email only on certain tests
            if self.xytest_conf['should_email']:
                pass
                #test_report.do_test_report(self.posids, all_data_by_posid, log_timestamp, self.pos_notes, self._elapsed_time_str(start_time), self.xytest_conf['email_list'])
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            # Email traceback to alert that test failed and why
            if self.xytest_conf['should_email']:
                pass
                #test_report.email_error(traceback.format_exc(),log_timestamp)
            raise
        self.logwrite(str(len(all_data_by_target)) + ' targets measured in ' + self._elapsed_time_str(start_time) + '.')

    def run_unmeasured_moves(self, loop_number):
        """Exercise positioners to a series of target positions without doing FVC measurements in-between.
        """
        n_moves = self.xytest_conf['n_unmeasured_moves_after_loop'][loop_number]
        if n_moves > 0:
            self.track_all_poslogs_once()
            arbitrary_posid = next(iter(self.posids))
            max_log_length = self.m.state(arbitrary_posid).max_log_length
            start_time = time.time()
            self.logwrite('Starting unmeasured move sequence in loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops))
            status_str = lambda j : 'move ' + str(j + 1) + ' of ' + str(n_moves) + ' within loop ' + str(loop_number + 1) + ' of ' + str(self.n_loops)
            for j in range(n_moves):
                this_status_str = status_str(j)
                if j % max_log_length == 0:
                    self.track_all_poslogs_once()
                if j % 1000 == 0:
                    self.logwrite('... now at ' + this_status_str)
                elif j % 50 == 0:
                    print(status_str(j))
                targ_xy = [np.Inf,np.Inf]
                while not(self.target_within_limits(targ_xy)):
                    targ_xy = self.rand_xy_targs_list[self.rand_xy_targs_idx]
                    self.rand_xy_targs_idx += 1
                    if self.rand_xy_targs_idx >= len(self.rand_xy_targs_list):
                        self.rand_xy_targs_idx = 0
                requests = self.generate_posXY_move_requests([targ_xy])[0]
                for posid in requests.keys():
                    requests[posid]['log_note'] = 'unmeasured ' + this_status_str
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
        if not self.simulate:
            self.logwrite('Querying the user for SVN credentials. These will not be written to the log file.')
            print('')
            if self.use_local_presets:
                [svn_user, svn_pass, err] = self.simple_svn_creds()
            else:
                [svn_user, svn_pass, err] = XYTest.ask_user_for_creds(should_simulate=self.simulate)

            if err:
                self.logwrite('SVN credential failure. Logs will have to be manually uploaded to SVN after the test. This is very BAD, and needs to be resolved.')
                self.svn_user = ''
                self.svn_pass = ''
            else:
                self.logwrite('SVN user and pass verified.')
                self.svn_user = svn_user
                self.svn_pass = svn_pass
        else:
            self.logwrite('Skipped querying user for SVN credentials in simulation mode.')

    def svn_add_commit(self, keep_creds=False):
        '''Commit logs through SVN.

        Optional keep_creds parameter instructs to *not* delete SVN user/pass after
        this commit is complete. Otherwise they get automatically deleted.
        '''
        self.logwrite('Files changed or generated: ' + str(list(self.new_and_changed_files.keys())))
        if not self.simulate:
            if not(self.svn_user and self.svn_pass):
                self.logwrite('No files were auto-committed to SVN due to lack of user / pass credentials.')
            elif self.new_and_changed_files:
                start_time = time.time()
                print('Will attempt to commit the logs automatically now. This may take a while.')
                n_total = 0
                these_files_to_commit = ''
                for file in self.new_and_changed_files.keys():
                    should_commit = self.new_and_changed_files[file]
                    if should_commit == 'always' or should_commit == 'once':
                        these_files_to_commit += ' ' + file
                        n_total += 1
                print("these_files_to_commit")
                print(these_files_to_commit)
                print("")
                self.logwrite('Beginning add + commit of ' + str(n_total) + ' data files to SVN.')
                err_add = os.system('svn add --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive ' + these_files_to_commit)
                err_commit = os.system('svn commit --username ' + self.svn_user + ' --password ' + self.svn_pass + ' --non-interactive -m "autocommit from xytest script" ' + these_files_to_commit)
                print('SVN upload attempt of ' + str(n_total) + ' data files returned: ' + str(err_add) + ' for ADD and ' + str(err_commit) + ' for COMMIT. (Return value of 0 means it was added/committed to the SVN ok.)')
                for file in self.new_and_changed_files.keys():
                    should_commit = self.new_and_changed_files[file]
                    if should_commit == 'once' and err_add == 0 and err_commit == 0:
                        self.new_and_changed_files[file] = 'do not commit'
                if err_add != 0:
                    print('Warning: not all data files ADDED correctly to SVN. Check through carefully and do this manually.')
                if err_commit != 0:
                    print('Warning: not all data files COMMITTED correctly to SVN. Check through carefully and do this manually.')
                if not(keep_creds):
                    del self.svn_user
                    del self.svn_pass
                print('SVN uploads completed in ' + self._elapsed_time_str(start_time))
        else:
            self.logwrite('Skipped committing files to SVN in simulation mode.')

    def logwrite(self,text,stdout=True):
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

    def track_file(self, filename, commit='always'):
        """Use this to put new filenames into the list of new and changed files we keep track of.
        This list gets put into the log later, and is also used for auto-updating of the SVN.

          commit ... 'always'        --> always commit this file to the SVN upon svn_add_commit
                 ... 'once'          --> only commit this file to the SVN upon the next svn_add_commit
                 ... 'do not commit' --> do not commit this file (anymore) to the SVN
        """
        self.new_and_changed_files[filename] = commit
        self.xytest_conf['new_and_changed_files'] = self.new_and_changed_files
        self.xytest_conf.write()

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
                self.calib_store[posid][calib_key] = ptl.get_posfid_val(posid,calib_key)

    def restore_calibrations(self, keys = None):
        '''Restore all the calibration values previously stored with the
        collect_calibrations() method. Can argue which calib keys to reset.
        '''
        if not(keys):
            keys = pc.nominals.keys()
        for posid in self.posids:
            for calib_key in keys:
                ptl = self.m.petal(posid)
                ptl.set_posfid_val(posid, calib_key, self.calib_store[posid][calib_key])
        for ptl in self.m.petals:
            ptl.commit(log_note='xytest restoring old calibration values (if necessary)')

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


    def simple_svn_creds(self):
        try:
            svn_user=input("Please enter your SVN username: ")
            svn_pass=getpass.getpass("Please enter your SVN password: ")
            svn_auth_err=False
        except:
            svn_auth_err=True
        return svn_user, svn_pass, svn_auth_err

    @staticmethod
    def ask_user_for_creds(should_simulate=False):
        '''General function to gather SVN username and password from operator.
        '''
        gui_root = tkinter.Tk()
        intro = 'Enter your svn username and password for committing the logs'
        intro += '\nto the server. These will not be saved to the logfile, but will briefly'
        intro += '\nbe clear-text in this script\'s memory while it is running.'
        n_credential_tries = 4
        while n_credential_tries:
            svn_user = tkinter.simpledialog.askstring(title='SVN authentication',prompt=intro + '\n\n' + 'svn username:' + ' (' + str(n_credential_tries) + ' tries remaining)')
            svn_pass = tkinter.simpledialog.askstring(title='SVN authentication',prompt='svn password:',show="*")
            if should_simulate:
                err = 0
            elif svn_user and svn_pass:
                err = os.system('svn --username ' + svn_user + ' --password ' + svn_pass + ' --non-interactive list')
            else:
                err = 'no name/pass entered'
            if err == 0:
                n_credential_tries = 0
            else:
                n_credential_tries -= 1
        gui_root.withdraw()
        return svn_user, svn_pass, err

if __name__=="__main__":
    # added optional use of local presets
    USE_LOCAL_PRESETS=False
    CONTINUE_TEST=False
    arguments = sys.argv[1:]

    try:
        if len(arguments) > 0:
            if arguments[0].lower()=='uselocal': USE_LOCAL_PRESETS=True

        if len(arguments) > 1:
            if arguments[1].lower()[0:4]=='cont': CONTINUE_TEST=True
    except:
        pass
    hwsetup_conf=''
    xytest_conf=''

    if USE_LOCAL_PRESETS:
        try:
            presets_file=os.environ['TEST_PRESETS_CONFIG']
            test_base_path=os.environ['TEST_BASE_PATH']
            temp_file_path=os.environ['TEST_TEMP_PATH']
            presets = configobj.ConfigObj(presets_file,unrepr=True)
            hwsetup_conf=presets['hwsetup_conf']
            if CONTINUE_TEST:
                xytest_conf=presets['xytest_continue_conf']
            else:
                xytest_conf=presets['xytest_conf']
            #should_update_from_svn=presets['should_update_from_svn']
            #should_commit_to_svn=presets['should_commit_to_svn']
            #should_identify_fiducials = presets['should_identify_fiducials']
            #should_identify_positioners = presets['should_identify_positioners']
        except:
            print("Can not use local presets.")
            USE_LOCAL_PRESETS=False


    if USE_LOCAL_PRESETS:
        print("")
        print("The following presets will be used:")
        print("")
        print("  Hardware setup file: "+str(hwsetup_conf))
        print("  XYtest config file: "+str(xytest_conf))
        print("")
        print("  Is this correct? (hit 'y' for yes or any key otherwise)")
        sel=_read_key().__call__()
        if sel.lower() !='y':
            USE_LOCAL_PRESETS=False
            hwsetup_conf=''
            xytest_conf=''
        else:
            print("Local presets will be used")
            hwsetup_conf=test_base_path+'/fp_settings/hwsetups/'+hwsetup_conf
            if not CONTINUE_TEST:
                xytest_conf=test_base_path+'/fp_settings/test_settings/'+xytest_conf
            else:
                xytest_conf=temp_file_path+'/'+xytest_conf

    test = XYTest(hwsetup_conf=hwsetup_conf,xytest_conf=xytest_conf,USE_LOCAL_PRESETS=USE_LOCAL_PRESETS)
    test.get_svn_credentials()
    test.logwrite('Start of positioner performance test.')
    test.m.park(posids='all')
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
    for petal in test.m.petals:
        petal.schedule_stats.save()
        #petal.generate_animation()
    test.logwrite('Test complete.')
    test.track_all_poslogs_once()
    test.svn_add_commit(keep_creds=False)
