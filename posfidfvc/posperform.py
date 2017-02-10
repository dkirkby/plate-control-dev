import numpy as np
import configobj
import sys, os
sys.path.append(os.path.abspath('../petal/'))
import petal
import posconstants as pc
import xyaccuracy_test
import datetime
import Tkinter
import tkFileDialog

# set up logging of the high-level actions of posperform.py
initial_timestamp = pc.timestamp_str_now() 
posperf_logfile_name = pc.test_logs_directory + initial_timestamp + '_posperform.log'
def logwrite(text,stdout=True):
    """convinience function; writes log info to file and optionally to screen"""
    line = pc.timestamp_str_now() + ': ' + text
    filehandle = open(posperf_logfile_name)
    filehandle.write('\n' + line)
    filehandle.close()
    if stdout: print(line)

# set seed for random generator
SEED=123456
np.random.seed(SEED)

# select configuration file for test
configfile = '' # For debug purposes, if you want to short-circuit the gui because it is annoying, you could hard-code a filename here, for any file located in the standard test_settings directory.
if configfile:
    configfile = pc.test_settings_directory + configfile
else:
    gui_root = tk.Tk()
    configfile = tk.filedialog.askopenfilename(initialdir=pc.test_settings_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title="Select the configuration file for this test run.")
    gui_root.destroy()
logwrite('File ' + str(settings_filename) + ' selected as template for test settings.')
config = configobj.ConfigObj(configfile,unrepr=True)
config_traveler_name = pc.test_logs_directory + initial_timestamp + '_' + os.path.basename(configfile)
config.filename = config_traveler_name
config.write()

# gather up some values from the config file
ptl_ids = config['petal']['petal_id']
pos_ids = config['positioners']['ids']
fid_ids = []


logwrite('Petal IDs: ' + str(ptl_ids))
logwrite('Fid IDs: ' + str(fid_ids))
logwrite('Pos IDs: ' + str(pos_ids))


ptl = petal.Petal(petal_id, pos_ids, fid_ids)

# initialize the test handler
acc_test = xyaccuracy_test.AccuracyTest()
acc_test.enable_logging()

# create all the move request dictionaries
life_moves = []
targets_list = acc_test.generate_posXY(config['n_unmeasured_moves_between_loops'])
for local_target in targets_list:
	these_targets = {}
	for pos_id in sorted(pos_ids):
		these_targets[pos_id] = {'command':'posXY', 'target':local_target}
	life_moves.append(these_targets)



logwrite('Start of positioner performance test.')
total_loops = len(config['sequence']['n_pts_across_per_loop'])
n_between_loops = config['sequence']['n_unmeasured_moves_between_loops']
for i in range(total_loops):
    logwrite('Starting xy test in loop ' + str(i+1) + ' of ' + str(total_loops))
    acc_test.update_loop_settings(i)
    acc_test.run_xyaccuracy_test()
    if i >= total_loops - 1:
        break # the last loop does not have unmeasured moves
    logwrite('Starting unmeasured move sequence in loop ' + str(i+1) + ' of ' + str(total_loops))
    for j in range(n_between_loops):
		if j % 100 == 0:
			print('... now at cycle ' + str(j+1) + ' of ' + str(n_between_loops) + ' within loop ' + str(i+1) ' of ' + str(total_loops))
		m.move(life_moves[j+i*NMOVES])
	print("MOVES"+str(life_moves[j+i*NMOVES]))	

	logwrite('Finished move loop '+str(i+1)+' of '+str(LOOPS))

	# 10 hardstop strikes
	logwrite('Start '+str(NSTRIKES)+' hardstop strikes')

	#turn off anti-backlash & creep move to save time 
	ptl.set(key='ANTIBACKLASH_ON', value=False)
	ptl.set(key='FINAL_CREEP_ON', value=False)

	for k in range(NSTRIKES):

		theta=np.random.uniform(0, trange_h) # this was hard coded at 375
		phi=np.random.uniform(0, prange_h) # this was hard coded at 185
		print("PHI "+str(phi))
		#move theta and phi to random positions
		requests={}
		for pos_id in pos_ids:
			requests[pos_id] = {'target': [theta, -phi]}  #theta and phi move in opposite directions (away from hard stops)

		if not TESTING:	
			ptl.request_direct_dtdp(requests)
			ptl.schedule_send_and_execute_moves()

			#slam into hard stops after moving to random positions
			ptl.request_homing(pos_ids_slam)
			ptl.schedule_send_and_execute_moves()
		else:
			print('slamming')
	
	#turn anti-backlash and creep on prior to running accuracy test
	ptl.set(key='ANTIBACKLASH_ON', value=True)
	ptl.set(key='FINAL_CREEP_ON', value=True)

	# 28 point test

	if not TESTING:
		m=acc_test.run_xyaccuracy_test()
	else:
		print ('RUNNING XY TEST 28 poins')

	logwrite('Finished xyaccuracy test '+str(i+1)+' of '+str(LOOPS))

# switch back to full calibration 
# 198 point test (n=17)
config['mode']['should_calibrate_full'] = 'True'
config['grid']['n_pts_across'] = '17'
config.write()
acc_test.update_config()
logwrite('Starting final xyaccuracy test - 198 poins')

if not TESTING:
	acc_test.run_xyaccuracy_test()
else:
	print ('RUNNING XY TEST 198 poins')

logwrite('End of performance test')