import numpy as np
import configobj
import sys, os
sys.path.append(os.path.abspath('../petal/'))
import petal
import fvchandler
import posconstants as pc
import posmovemeasure
import xyaccuracy_test
import datetime
from os import environ


def stime():
	# convinience function; returns current date/time as string yymmdd.hhmmss 
	now=datetime.datetime.now().strftime("%y%m%d.%H%M%S")
	return now

def logwrite(fhandle,text,stdout=True):
	# convinience function; writes log info to file and optionally to screen	
	fhandle.write(stime()+text)
	if stdout: print(stime()+text)


def generate_posXY(r_min,r_max,npoints):
	'''Generates uniformly distributed points in circular area
	   Starts with uniformly distributed square then reject points
	   found outside the circle.
	   Returns list.'''

	x = np.random.uniform(-r_max, r_max, npoints*2)
	y = np.random.uniform(-r_max, r_max, npoints*2)
	r = np.sqrt(x**2 + y**2)
	index=np.where(np.logical_and(r < r_max,r > r_min))
	p=zip(x[index],y[index])
	return list(p)[:npoints]


LOOPS =10
NMOVES=1000
NSTRIKES=10
SEED=123456
trange_h=375
prange_h=185

TESTING=True


# set seed for random generator

np.random.seed(SEED)


if len(sys.argv) ==1:
	configfile='accuracy_test.conf'
else:
	configfile=sys.argv[1]

config = configobj.ConfigObj(configfile,unrepr=True)
print(stime())
flog=open('log/posperf_'+stime()+'.log','w')

logwrite(flog,': Start of positioner performance test ')

petal_id = config['petal']['petal_id']
pos_ids = config['positioners']['ids']
fid_ids = []

r_max=config['grid']['grid_max_radius']
r_min=config['grid']['grid_min_radius']

logwrite(flog,': Pos IDs: '+str(pos_ids))

ptl = petal.Petal(petal_id, pos_ids, fid_ids)

log_directory = pc.test_logs_directory
log_timestamp = datetime.datetime.now().strftime(pc.filename_timestamp_format)

move_list = generate_posXY(r_min,r_max,NMOVES*LOOPS)

#create all the move request dictionaries
life_moves = []
for local_target in move_list:
	these_targets = {}
	for pos_id in sorted(pos_ids):
		these_targets[pos_id] = {'command':'posXY', 'target':local_target}
	life_moves.append(these_targets)

acc_test=xyaccuracy_test.AccuracyTest()
acc_test.enable_logging()



# 1) perform xy_accuracy test

acc_test.update_config()

logwrite(flog,': Starting first xyaccuracy test - 198 poins')

if not TESTING:
	m=acc_test.run_xyaccuracy_test()
else:
	print ('RUNNING XY TEST 198 poins')
# 2) repeat 10 x (1000 random moves, 10 hardstop strikes, 28 point xy test w/ quick calibration only)

# quick calibration only during loop 
# 28 point test (n=7)

config['mode']['should_calibrate_full'] = 'False'
config['grid']['n_pts_across'] = '7'
config.write()
acc_test.update_config()

for i in range(LOOPS):
	logwrite(flog,': Starting loop '+str(i+1)+' of '+str(LOOPS))

	# 1000 random moves

	for j in range(NMOVES):
		if j%100 == 0:
			print('Cycle '+str(j+1)+' of '+str(NMOVES))
		if not TESTING:
			m.move(life_moves[j+i*NMOVES])
	print("MOVES"+str(life_moves[j+i*NMOVES]))	

	logwrite(flog,': Finished move loop '+str(i+1)+' of '+str(LOOPS))

	# 10 hardstop strikes
	logwrite(flog,': Start '+str(NSTRIKES)+' hardstop strikes')

	#turn off anti-backlash & creep move to save time 
	ptl.set(key='ANTIBACKLASH_ON', value=False)
	ptl.set(key='FINAL_CREEP_ON', value=False)

	for k in range(NSTRIKES):

		theta=np.random.uniform(0, trange_h)
		phi=np.random.uniform(0, prange_h)
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

	logwrite(flog,': Finished xyaccuracy test '+str(i+1)+' of '+str(LOOPS))

# switch back to full calibration 
# 198 point test (n=17)
config['mode']['should_calibrate_full'] = 'True'
config['grid']['n_pts_across'] = '17'
config.write()
acc_test.update_config()
logwrite(flog,': Starting final xyaccuracy test - 198 poins')

if not TESTING:
	acc_test.run_xyaccuracy_test()
else:
	print ('RUNNING XY TEST 198 poins')

logwrite(flog,': End of performance test')

flog.close()