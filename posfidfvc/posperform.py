import numpy as np
import configobj
import sys, os
sys.path.append(os.path.abspath('../petal/'))
import petal
import posconstants as pc
import xytest
import datetime



# set seed for random generator ... DOES THIS NEED TO BE IN HERE?
SEED=123456
np.random.seed(SEED)


# initialize the test handler
test = xytest.XYTest(config,logwrite)



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