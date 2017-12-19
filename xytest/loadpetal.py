#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 23:10:49 2017

@author: zhangkai
"""
import os
import sys
import datetime
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../../../positioner_logs/data_processing_scripts/'))
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

class LoadPetal(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
        global gui_root
        gui_root = tkinter.Tk()
        
        self.simulate = False
        self.logfile='MoveGUI.log'
        fvc_type='simulator'

        self.ptl_id=13
        fidids=['F021']   
        gui_root.title='Move Controll for Petal '+str(self.ptl_id)
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
       

    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.logfile,'a') as fh:
            fh.write(line + '\n')
        if stdout:
            print(line)
            