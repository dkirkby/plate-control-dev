import os
import sys
import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import xytest
import configobj
import scipy
import astropy
import csv
import numpy as np
from lmfit import minimize, Parameters
import matplotlib.pyplot as plt
import getpass
import time
from datetime import datetime
import svn.local

sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))

hwsetup_path = ('/home/msdos/focalplane/fp_settings/hwsetups/')

class InitHwSetup(object):
	def __init__(self, svn_user, svn_pass):
		self.svn_user = svn_user
		self.svn_pass = svn_pass
		self.svn_auth_err = False
		self.svn_update_dirs = [pc.dirs[key] for key in ['pos_logs','pos_settings','xytest_logs','xytest_summaries']]

		self.should_limit_range = True

		# unique timestamp
		self.start_filename_timestamp = pc.filename_timestamp_str_now()

		# start set of new and changed files
		self.new_and_changed_files = set()


		self.hwsetup_conf = hwsetup_path + 'hwsetup_petal0_xytest.conf'
		print("Using this configuration file: ", hwsetup_conf)
		self.hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=Trueencoding='utf-8')
		self.add_file(self.hwsetup_conf)

		# software initialization and startup
		if self.hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in self.hwsetup:
    		self.fvc=fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=self.hwsetup['save_sbig_fits'],platemaker_instrument=self.hwsetup['pm_instrument'])
		else:
    		self.fvc=fvchandler.FVCHandler(fvc_type=self.hwsetup['fvc_type'],save_sbig_fits=self.hwsetup['save_sbig_fits']) 

		self.fvc.rotation = self.hwsetup['rotation']
		self.fvc.scale = self.hwsetup['scale']
                self.fvc.translation = self.hwsetup_conf['translation']
                self.fvc.exposure_time = self.hwsetup_conf['exposure_time']
		self.posids = self.hwsetup['pos_ids']
		self.fidids = self.hwsetup['fid_ids']
		shape = 'asphere' if self.hwsetup['plate_type'] == 'petal' else 'flat'
		self.ptl = petal.Petal(self.hwsetup['ptl_id'], posids, fidids, simulator_on=sim, user_interactions_enabled=True, anticollision=None, petal_shape=shape)
		self.m = posmovemeasure.PosMoveMeasure([self.ptl],self.fvc)
		self.m.make_plots_during_calib = True

		print('Automatic generation of calibration plots is turned ' + ('ON' if m.make_plots_during_calib else 'OFF') + '.')
		for ptl in self.m.petals:
			for posmodel in self.ptl.posmodels:
				self.add_file(posmodel.state.conf.filename)
				self.add_file(posmodel.state.log_path)
			for fidstate in self.ptl.fidstates.values():
				self.add_file(fidstate.conf.filename)
				self.add_file(fidstate.log_path)
		print("Initialization Complete")

	def add_file(self, file):
		self.new_and_changed_files.add(file)

	def check_ids(self):
		# check ids with user
		text = '\n\nHere are the known positioners and fiducials:\n\n'
		text += str(len(self.posids)) + ' POSITIONERS:'
		for posid in self.posids:
			text += '\n  ' + format(posid+':','11s') + 'busid = ' + format(str(self.ptl.get_posfid_val(posid,'BUS_ID')),'5s') + '  canid = ' + format(str(self.ptl.get_posfid_val(posid,'CAN_ID')),'5s')
		
		text += '\n\n' + str(len(self.fidids)) + ' FIDUCIALS:'
		for fidid in fidids:
			text += '\n  ' + format(fidid+':','11s') + 'busid = ' + format(str(self.ptl.get_posfid_val(fidid,'BUS_ID')),'5s') + '  canid = ' + format(str(self.ptl.get_posfid_val(fidid,'CAN_ID')),'5s') + '  ndots = ' + str(self.ptl.get_posfid_val(fidid,'N_DOTS'))
		print(text)

		message='A list of all the positioner and fiducials has been printed to the stdout text console.\n\nPlease check each of these carefully.\n\nAre they all correct?'
		message_local='Please check the above list of all the positioners and fiducials carefully.\nAre they all correct?\n'


		#Check how many of these are enabled disabled.
		pos_ids = []
		vals = []
		for ptl in self.m.petals:
			for pos_id in ptl.posids:
				pos_ids.append(pos_id)
				vals.append(ptl.get_posfid_val(posid, 'CTRL_ENABLED'))
		if all(x == True for x in vals):
			print("All positioners are enabled")
		else:
			idx = np.where(vals == False)
			print("These positioners are disabled: ", np.array(pos_ids)[idx])

	def turn_on_fids(self):
		# fire up the fiducials
		fid_settings_done = self.m.set_fiducials('on')
		print('Fiducials turned on: ' + str(fid_settings_done))

	def identification(self): # calibration routines
		print("Rehome")
		self.m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
		print("Identifying Fiducials")
		self.m.identify_fiducials()
		print("Identifying Positioners")
		self.m.identify_positioner_locations()

	def calibration(self):
		print("Starting Calibration")
		self.m.calibrate(mode='rough')
		self.m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=self.start_filename_timestamp)

		#plotfiles = self.m.calibrate(mode='arc', save_file_dir=pc.dirs['xytest_plots'], save_file_timestamp=self.start_filename_timestamp)
		#new_and_changed_files.update(plotfiles)
		self.m.park() # retract all positioners to their parked positions

	def commit_to_svn(self):
		# commit logs and settings files to the SVN
		xtime0=time.time()
		
		commit_message="autocommit from initialize_hwsetup script"
		n_total = len(self.new_and_changed_files)
		flist=list(self.new_and_changed_files)
		n_add = 0
		loc_repo=svn.local.LocalClient('/home/msdos/focalplane/plate_control/trunk',username=svn_user,password=svn_pass)
		for file in flist:
			try:
				loc_repo.add(file)
				n_add=n_add+1
			except:
				pass

		print("Added "+str(n_add)+' files out of '+str(n_total))
		try:	
			loc_repo.commit(commit_message,flist)
		except:
			import datetime
			now = datetime.now()
			datestr= now.strftime('%y%m%d:%H:%M')
			xfer_file=	'svnxfer_'+datestr+'.lst'
			print("Automated SVN commit failed - please transfer files manually.")
			print("The list of files to be transferred was written out to ('"+xfer_file+"').lst')")
			with open(xfer_file,'w') as f:
				f.write(str(flist))
		print("SVN upload took "+str(time.time()-xtime0)+" seconds")
		print("")
		print("Ready to run XYtest")

	def init_hwsetup(self):
		self.check_ids()
		self.turn_on_fids()
		self.identification()
		self.calibration()
		self.commit_to_svn()


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


    


if __name__=="__main__":
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




