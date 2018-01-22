import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
	sys.path.append(os.path.abspath(basepath+'/posfidfvc/'))
elif 'USERNAME' in os.environ.keys() and os.environ['USERNAME'] == 'kremin':
	if 'HOME' in os.environ:
		basepath = os.environ['HOME']
	else:
		basepath = os.path.abspath('../')
		os.environ['HOME'] = basepath
	if 'POSITIONER_LOGS_PATH' in os.environ:
		logdir = os.environ['POSITIONER_LOGS_PATH']
	else:
		logdir = os.path.abspath(os.path.join(basepath, 'positioner_logs'))
		os.environ['POSITIONER_LOGS_PATH'] = logdir
	if 'PETAL_PATH' in os.environ:
		pass
	else:
		basepath = os.path.abspath('../')
		os.environ['PETAL_PATH'] = basepath
	if 'FP_SETTINGS_PATH' in os.environ:
		allsetdir = os.environ['FP_SETTINGS_PATH']
	else:
		allsetdir = os.path.abspath(os.path.join(basepath, 'fp_settings'))
		os.environ['FP_SETTINGS_PATH'] = allsetdir

	## Define other useful directories and make them if they don't exist
	outputsdir = os.path.abspath(os.path.join(basepath, 'outputs'))
	figdir = os.path.abspath(os.path.join(basepath, 'figures'))
	tempdir = os.path.join(os.environ['HOME'], 'fp_temp_files', '')
	if not os.path.exists(logdir):
		os.makedirs(logdir)
		for dirname in ['move', 'test', 'pos']:
			fullpath = os.path.join(logdir, '{}_logs'.format(dirname))
			os.makedirs(fullpath)
	for dirname in [allsetdir, tempdir, outputsdir, figdir]:
		if not os.path.exists(dirname):
			os.makedirs(dirname)
	sys.path.append(os.path.abspath('../petal/'))
	sys.path.append(os.path.abspath('../posfidfvc/'))
	os.environ['TEST_PRESETS_CONFIG'] = '../fp_settings/sim_anticol_presets.conf'
	os.environ['TEST_BASE_PATH'] = './'
	os.environ['TEST_TEMP_PATH'] = '../fp_settings'
else:
	sys.path.append(os.path.abspath('../petal/'))
	sys.path.append(os.path.abspath('../posfidfvc/'))

# import fvchandler
# import petal
# import posmovemeasure
# import posconstants as pc
# import summarizer
# import numpy as np
# import time
# import pos_xytest_plot
import configobj

from xytest import XYTest

if __name__=="__main__":
	# added optional use of local presets
	USE_LOCAL_PRESETS = True
	if 'TEST_PRESETS_CONFIF' not in os.environ:
		os.environ['TEST_PRESETS_CONFIG'] = os.path.abspath('../fp_settings/other_settings/defaults_xysim.conf')
	if 'TEST_BASE_PATH' not in os.environ:
		os.environ['TEST_BASE_PATH'] = os.path.abspath('./')
	if 'TEST_TEMP_PATH' not in os.environ:
		os.environ['TEST_TEMP_PATH'] = os.path.abspath('../fp_temp_files/')

	hwsetup_conf = os.path.abspath('../fp_settings/hwsetups/hwsetup_LBNL0_sim.conf')
	xytest_conf = os.path.abspath('../fp_settings/test_settings/xytest_lbnl3_anticol.conf')

	print("")
	print("The following presets will be used:")
	print("")
	print("  Hardware setup file: "+str(hwsetup_conf))
	print("  XYtest config file: "+str(xytest_conf))
	print("")
	print("  Is this correct? (hit 'y' for yes or any key otherwise)")

	test = XYTest(hwsetup_conf=hwsetup_conf,xytest_conf=xytest_conf,USE_LOCAL_PRESETS=USE_LOCAL_PRESETS)
