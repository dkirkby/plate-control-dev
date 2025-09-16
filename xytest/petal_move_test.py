account='msdos'
import os
import sys
import datetime
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../../../positioner_logs/data_processing_scripts/'))
sys.path.append(os.path.abspath('/home/'+account+'/focalplane/positioner_logs/data_processing_scripts/'))

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

ptl_id=input('Input PC Number: ')
canlist=['can10','can11','can13','can12','can22','can23','can15','can16','can17','can14']
pcomm=petalcomm.PetalComm(ptl_id)
info = pcomm.pbget('posfid_info')
print(info.keys())
fidids=['F021']
posids=[]
for can in canlist:
    print('Loading '+can)
    if can in info.keys():
        info = info[can]
        print('info:',info)
    else:
        info={}
    if not isinstance(info, str):
        for key in sorted(info.keys()):
            if len(str(key))==2:
                posids.append('M000'+str(key))
            elif len(str(key))==3:
                posids.append('M00'+str(key))
            elif len(str(key))==4:
                posids.append('M0'+str(key))
            elif len(str(key))==5:
                posids.append('M'+str(key))
print('posids:',posids)
ptl = petal.Petal(ptl_id, posids, fidids, simulator_on=False, user_interactions_enabled=True)
dtdp=[50,0]
ptl.quick_direct_dtdp(posids,dtdp,should_anneal=True)  # positive is ccw

