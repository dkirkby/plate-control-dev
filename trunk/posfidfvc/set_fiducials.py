import os
import sys
import datetime
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../../../positioner_logs/data_processing_scripts/'))
sys.path.append(os.path.abspath(os.getenv('HOME')+'/focalplane/positioner_logs/data_processing_scripts/'))
sys.path.append(os.path.abspath(os.getenv('HOME')+'/focalplane/pos_utility/'))
#sys.path.remove('/software/products/plate_control-trunk/xytest')
#sys.path.remove('/software/products/plate_control-trunk/posfidfvc')
#sys.path.remove('/software/products/plate_control-trunk/petalbox')
#sys.path.remove('/software/products/plate_control-trunk/petal')

import fvchandler
import petal
import petalcomm
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
from tkinter import *
import googlesheets
import time
import show_detected
import populate_petal_travelers
import populate_busids
import pdb
ptl_id=sys.argv[1]
mode=sys.argv[2]
pcomm=petalcomm.PetalComm(ptl_id)
if mode == 'on':
    fiducial_settings_by_busid = {'can10': {10067:100}, 'can12':{10127:100},'can15':{10059:100},'can22':{15002:100,15008:100}}
else:
    fiducial_settings_by_busid = {'can10': {10067:0}, 'can12':{10127:0},'can15':{10059:0},'can22':{15002:0,15008:0}}
pcomm.pbset('fiducials', fiducial_settings_by_busid)
