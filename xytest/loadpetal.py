#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 23:10:49 2017

@author: zhangkai
"""
import os
import sys
import datetime
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
	sys.path.append(os.path.abspath(basepath+'/posfidfvc/SBIG'))
	sys.path.append(os.path.abspath(os.environ['TEST_BASE_PATH']+'/positioner_logs/data_processing_scripts/'))
else:
	sys.path.append(os.path.abspath('../petal/'))
	sys.path.append(os.path.abspath('../posfidfvc/SBIG'))
	sys.path.append(os.path.abspath('../../positioner_logs/data_processing_scripts/'))
import time

import fvchandler
import petal
import petalcomm
import posmovemeasure
import posschedule
import posconstants as pc
import poscollider
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

class LoadPetal(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
#        global gui_root
#        gui_root = tkinter.Tk()
#        gui_root.title='Move Controll for Petal '+str(self.ptl_id)

        self.simulate = False
        self.logfile='LoadPetal.log'
        fvc_type='simulator'

        self.ptl_id=13
        fidids=['F021']
        self.pcomm=petalcomm.PetalComm(self.ptl_id)
        self.mode = 0
	#petalcomm.
   #     info=self.petalcomm.get_device_status()
        canbus='can0'
        self.bus_id=canbus
        self.info = self.pcomm.get_posfid_info(canbus)
        self.posids = []
        print(self.info)
        for key in sorted(self.info.keys()):
            if len(str(key))==2:
                self.posids.append('M000'+str(key))
            elif len(str(key))==3:
                self.posids.append('M00'+str(key))
            elif len(str(key))==4:
                self.posids.append('M0'+str(key))
            elif len(str(key))==5:
                self.posids.append('M'+str(key))
        self.ptl = petal.Petal(self.ptl_id, self.posids, fidids, simulator_on=self.simulate, printfunc=self.logwrite)
        self.fvc = fvchandler.FVCHandler(fvc_type,printfunc=self.logwrite,save_sbig_fits=False)
        self.m = posmovemeasure.PosMoveMeasure([self.ptl],self.fvc,printfunc=self.logwrite)

#        self.posschedule=posschedule.PosSchedule(self.ptl)
       # Add target for each positioner
        self.posmodels=self.ptl.posmodels
        for posid in self.posids:
            print('\n',posid)
            self.ptl.schedule.request_target(posid, 'posTP', 0., 180., log_note='') # extend every positioner
            print(len(self.ptl.schedule.get_requests()))
        # rotate one positioner, check if it can avoid the obstacle?
        for i in range(36): # cannot request more than one target per positioner in a given schedule
            self.ptl.schedule.request_target('M00100', 'posTP', (i+1)*10., 180., log_note='')
        print(self.ptl.schedule.get_requests())
        self.ptl.schedule._schedule_with_anticollision() # Make move_tables

        move_tables=self.ptl.schedule.move_tables

#        self.ptl.send_move_tables()

#        # Make an animation
#        self.ptl.collider.add_positioners(self.posmodels)
#        self.ptl.collider.posmodels=self.posmodels
#        possweep=poscollider.PosSweep()
#        possweep.fill_exact(init_obsTP,move_tables)


    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.logfile,'a') as fh:
            fh.write(line + '\n')
        if stdout:
            print(line)

