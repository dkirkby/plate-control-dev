#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
#    Title:       pift.py
#    Date:        05/11/2017
#    Author:      cad
#    Sysnopsis:   GUI to run Positioner Installation Functional Test
#    Description:
#	python3 pift.py [ debug | info | warning | error | critical ]
#	the optional arguments (case-insensitive) set the logging level for the logging package
#	the default logging level is warning
#
#    Revisions:
#    mm/dd/yyyy who        description
#    ---------- --------   -----------
#    08/03/2017 cad        Version 1.01  Added Fiducial control
#    07/25/2017 cad        Version 1.00.  Initial version
# 
# ****************************************************************************

import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
import tkinter.ttk as ttk

import os
import sys
import fcntl
import time
# import datetime # for the filename timestamp
import logging
import configobj

# This is a hack to get the folder with petalcomm.py into the path
sys.path.append('../../petal')
# print(sys.path)

import petalcomm
import posconstants as pc

prog_name="PIFT"
prog_long_name="Positioner Installation Functional Test"
prog_version="1.01"

# Configuration Values

PIFTConfFile="./pift.conf"
PIFTLogFile="./pift.log"
PIFTCSVFile="./pift.csv"
Petal_Controller_Number=43
CanBusID='can0'
CanID=20000
Initial_Motor_Type=0
 
# Michigan - Irena test
# Petal_Controller_Number=20
# CanBusID='can0'
# CanID=208

n_mm_to_oz_in = 0.1416119

Currents=[100,100,100,0]    # percentages for spin-up,cruise,creep,hold

torque_mode='creep'

# indices into MoveTable list
iMotor=0     # 'phi' or 'theta'
iMode=1      # 'cruise' or 'creep'
iDirection=2 # 'cw' or 'ccw
iAngle=3     # angle in degrees
iCoolSecs=4  # seconds to cool down
BigMoveSize=10  # 10 deg for big moves (default)
MedMoveSize=5   # 5 deg for medium moves (default)
SmallMoveSize=1 # 1 deg for small moves (default)

class Torque_Test_GUI:
    """Class for Torque Test GUI"""

    # 
    def __init__(self,tkroot,logging_level):
        self.parent = tkroot
        self.logging_level = logging_level

        logging.basicConfig(filename=PIFTConfFile,level=logging_level)

        self.gui_initialized=0
        self.logprint("Logging level set to "+str(logging_level))
        
        self.initVars()
        self.initUI()
        self.gui_initialized=1
        tkroot.protocol("WM_DELETE_WINDOW", self.quit)
        return

    def initVars(self):
        global PIFTConfFile
        global PIFTLogFile
        global PIFTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type
        global BigMoveSize
        global MedMoveSize
        global SmallMoveSize

        self.move_count=0
        self.cool_countdown=0
        self.simulate=0         # 1 for simulation, 0 for the real thing
        self.delay=1000         # 1000 ms = 1 sec
        self.move_direction="ccw"
        self.torque_mode=torque_mode
        self.big_move=BigMoveSize    # default move sizes (degrees)
        self.med_move=MedMoveSize
        self.small_move=SmallMoveSize

        # define internal variables connected to GUI
        self.config_file=tk.StringVar()
        self.log_file=tk.StringVar()
        self.csv_file=tk.StringVar()

        self.petal_controller=tk.StringVar()
        self.canbus=tk.StringVar()
        self.canid=tk.StringVar()
        self.motor_type=tk.IntVar()
        self.motor_speed=tk.IntVar()
        self.operator_name=tk.StringVar()
        self.motor_sn=tk.StringVar()
        self.user_notes=tk.StringVar()
        self.status_str=tk.StringVar()
        self.fid_pct=tk.IntVar()
    
 
        # Now set the default values
        self.config_file.set(PIFTConfFile)
        self.log_file.set(PIFTLogFile)
        self.csv_file.set(PIFTCSVFile)
        self.petal_controller.set(str(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(str(CanID))
        self.motor_type.set(Initial_Motor_Type)	# 0 for phi, 1 for theta
        self.motor_speed.set(1)	# 0 for creep, 1 for cruise
        return;


    def initUI(self):
        self.parent.title(prog_long_name+" - Vers. "+prog_version)

        self.top_fr=tk.Frame(self.parent)
        self.top_fr.pack(fill=tk.BOTH, expand=True)
        
        # 4 tk.Frames defining the overall geometry

        # Hardware settings and Connection button
        self.frame_top_left=ttk.Frame(self.top_fr)
        self.frame_top_left.grid(column=0,row=0,rowspan=3,sticky="ns",padx=2,pady=2)
        self.frame_hw = ttk.Frame(self.frame_top_left,relief="groove",borderwidth=2)
        self.frame_hw.pack(fill=tk.BOTH,expand=True)

        # Test settings and Apply Torque button
        self.frame_top_mid=ttk.Frame(self.top_fr)
        self.frame_top_mid.grid(column=1,row=0,rowspan=3,sticky="n",padx=2,pady=2)
        self.frame_tst = ttk.Frame(self.frame_top_mid,relief="groove",borderwidth=2)
        self.frame_tst.pack(fill=tk.BOTH,expand=True)
        self.frame_top_fid=ttk.Frame(self.frame_top_mid,relief="groove",borderwidth=2)
        self.frame_top_fid.pack(fill=tk.BOTH,expand=True,pady=10)
        
        # Tweak Motor Position
        self.frame_top_right=ttk.Frame(self.top_fr)
        self.frame_top_right.grid(column=2,row=0,rowspan=3,sticky="ns",padx=2,pady=2)
        self.frame_twk = ttk.Frame(self.frame_top_right,relief="groove",borderwidth=2)
        self.frame_twk.pack(fill=tk.BOTH,expand=True)
        
        # Quit button and Status
        self.frame_bot_right=ttk.Frame(self.top_fr)
        self.frame_bot_right.grid(column=0,row=3,columnspan=3,sticky="ew",padx=2,pady=2)
        self.frame_qst = ttk.Frame(self.frame_bot_right,relief="groove",borderwidth=2)
        self.frame_qst.pack(fill=tk.BOTH,expand=True,ipadx=2,ipady=2)

        
#       ************ HW tk.Frame **********************
        self.frame_hw_1 = ttk.Frame(self.frame_hw)
        self.frame_hw_1.pack(fill=tk.X)
        self.label_PC =ttk.Label(self.frame_hw_1, text="PetalController", width=11)
        self.label_PC.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_PC = ttk.Entry(self.frame_hw_1)
        self.entry_PC["textvariable"]=self.petal_controller
        self.entry_PC.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_2 = ttk.Frame(self.frame_hw)
        self.frame_hw_2.pack(fill=tk.X)
        self.label_CB = ttk.Label(self.frame_hw_2, text="Can Bus", width=11)
        self.label_CB.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_CB = ttk.Entry(self.frame_hw_2)
        self.entry_CB["textvariable"]=self.canbus
        self.entry_CB.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_3 = ttk.Frame(self.frame_hw)
        self.frame_hw_3.pack(fill=tk.X)
        self.label_CI = ttk.Label(self.frame_hw_3, text="Can ID", width=11)
        self.label_CI.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_CI = ttk.Entry(self.frame_hw_3)
        self.entry_CI["textvariable"]=self.canid
        self.entry_CI.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_6 = ttk.Frame(self.frame_hw)
        self.frame_hw_6.pack(fill=tk.X)
        self.label_CF = ttk.Label(self.frame_hw_6, text="Config File", width=11)
        self.label_CF.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_CF = ttk.Entry(self.frame_hw_6)
        self.entry_CF["textvariable"]=self.config_file
        self.entry_CF.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_7 = ttk.Frame(self.frame_hw)
        self.frame_hw_7.pack(fill=tk.X)
        self.label_LF = ttk.Label(self.frame_hw_7, text="Log File", width=11)
        self.label_LF.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_LF = ttk.Entry(self.frame_hw_7)
        self.entry_LF["textvariable"]=self.log_file
        self.entry_LF.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_8 = ttk.Frame(self.frame_hw)
        self.frame_hw_8.pack(fill=tk.X)
        self.label_DF = ttk.Label(self.frame_hw_8, text="Data File", width=11)
        self.label_DF.pack(side=tk.LEFT, padx=5, pady=5)        
        self.entry_DF = ttk.Entry(self.frame_hw_8)
        self.entry_DF["textvariable"]=self.csv_file
        self.entry_DF.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_hw_5 = ttk.Frame(self.frame_hw)
        self.frame_hw_5.pack(fill=tk.X,padx=5,pady=3,side=tk.RIGHT)

        self.frame_hw_5a = ttk.Frame(self.frame_hw_5,relief="groove",borderwidth=2)
        self.frame_hw_5b = ttk.Frame(self.frame_hw_5)

        self.button_LoadConf = ttk.Button(self.frame_hw_5a, width=9, text="Load Config")
        self.button_LoadConf["command"]=self.load_config
        self.button_SaveConf = ttk.Button(self.frame_hw_5a, width=9, text="Save Config")
        self.button_SaveConf["command"]=self.save_config

        self.label_nada = ttk.Label(self.frame_hw_5b, text=" ", width=4)

        self.button_Connect = ttk.Button(self.frame_hw_5, width=9, text="Connect")
        self.button_Connect["command"]=self.Connect_to_PC

        self.frame_hw_5a.grid(column=0,row=0,sticky="w",padx=2,pady=2)
        self.button_LoadConf.grid(column=0,row=0,sticky="w",padx=2,pady=2)
        self.button_SaveConf.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.frame_hw_5b.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.label_nada.pack(fill=tk.X)
        self.button_Connect.grid(column=2,row=0,sticky="e",padx=2,pady=2)

#       ********************** TST tk.Frame *****************

        self.frame_op = ttk.Frame(self.frame_tst)
        self.frame_op.pack(fill=tk.X,pady=1)
        self.label_op = ttk.Label(self.frame_op, text="Operator", width=11)
        self.label_op.pack(side=tk.LEFT, padx=5, pady=5)           
        self.entry_op = ttk.Entry(self.frame_op)
        self.entry_op["textvariable"]=self.operator_name
        self.entry_op.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_sn = ttk.Frame(self.frame_tst)
        self.frame_sn.pack(fill=tk.X,pady=1)
        self.label_sn = ttk.Label(self.frame_sn, text="Positioner", width=11)
        self.label_sn.pack(side=tk.LEFT, padx=5, pady=5)           
        self.entry_sn = ttk.Entry(self.frame_sn)
        self.entry_sn["textvariable"]=self.motor_sn
        self.entry_sn.pack(fill=tk.X, padx=5, expand=True)
        
        self.frame_note = ttk.Frame(self.frame_tst)
        self.frame_note.pack(fill=tk.X)
        self.label_note = ttk.Label(self.frame_note, text="Notes", width=11)
        self.label_note.pack(side=tk.LEFT, anchor=tk.N, padx=5, pady=5)        
        self.entry_note = ttk.Entry(self.frame_note)
        self.entry_note["textvariable"]=self.user_notes
        self.entry_note.pack(fill=tk.BOTH, pady=5, padx=5, expand=True)           

        self.frame_tst_btn = ttk.Frame(self.frame_tst)
        self.frame_tst_btn.pack(fill=tk.X,pady=9)

        self.label_nada2 = ttk.Label(self.frame_tst_btn, text="        ", width=10)
        self.button_next = ttk.Button(self.frame_tst_btn, width=9, text="Next Motor",
                                     state=tk.DISABLED,command=self.do_next_motor)

        self.label_nada2.grid(column=2,row=0,sticky="w",padx=2,pady=2)
        self.button_next.grid(column=3,row=0,sticky="e",padx=2,pady=2)
        
        self.frame_fid = ttk.Frame(self.frame_top_fid)
        self.label_fid = ttk.Label(self.frame_fid, text="Fiducial %", width=11)
        self.entry_fidpct = ttk.Entry(self.frame_fid)
        self.entry_fidpct["textvariable"]=self.fid_pct
        self.button_setfid = ttk.Button(self.frame_fid, width=9, text="Set",
                                     state=tk.DISABLED,command=self.set_fipos_led)
        self.frame_fid.pack(fill=tk.X,pady=10)
        self.label_fid.grid(column=0,row=0,sticky="w",padx=2,pady=2)           
        self.entry_fidpct.grid(column=1,row=0,sticky="ew",padx=2,pady=2)
        self.button_setfid.grid(column=2,row=0,sticky="w",padx=2,pady=2)

        #       **************** TWK tk.Frame *****************
        self.frame_twk1 = ttk.Frame(self.frame_twk)
        self.frame_twk1.pack(fill=tk.X,pady=1,expand=True)
        self.label_ManTwk=ttk.Label(self.frame_twk1, text="  Manual Control", width=13)
        self.label_ManTwk.grid(padx=6,pady=2)

        self.frame_twk_3 = ttk.Frame(self.frame_twk)
        self.frame_twk_3.pack(fill=tk.X, padx=5, pady=3)
        self.frame_rb = ttk.Frame(self.frame_twk_3,relief="groove",borderwidth=2)
        self.frame_rb.pack(side=tk.RIGHT,fill=tk.X,pady=3)
        self.button_Phi = ttk.Radiobutton(self.frame_rb, width=7, text="Phi", variable=self.motor_type, value=0).pack(side=tk.LEFT,padx=2)
        self.button_Theta = ttk.Radiobutton(self.frame_rb, width=7, text="Theta", variable=self.motor_type, value=1).pack(side=tk.RIGHT,padx=2)
        self.motor_type.set(Initial_Motor_Type)
        
        self.frame_twk_4 = tk.Frame(self.frame_twk)
        self.frame_twk_4.pack(fill=tk.X, padx=5, pady=3)
        self.frame_rb = ttk.Frame(self.frame_twk_4,relief="groove",borderwidth=2)
        self.frame_rb.pack(side=tk.RIGHT,fill=tk.X,pady=3)
        self.button_creep = ttk.Radiobutton(self.frame_rb, width=7, text="Creep", variable=self.motor_speed, value=0, state=tk.DISABLED).pack(side=tk.LEFT,padx=2)
        self.button_cruise = ttk.Radiobutton(self.frame_rb, width=7, text="Cruise", variable=self.motor_speed, value=1, state=tk.DISABLED).pack(side=tk.RIGHT,padx=2)
        self.motor_speed.set(1)
        
        self.frame_twk2 = ttk.Frame(self.frame_twk)
        self.frame_twk2.pack(fill=tk.BOTH,expand=True,pady=1)

#       self.label_ManTwk1=tk.Label(self.frame_twk2, text=" Manual", width=7)
#       self.label_ManTwk2=tk.Label(self.frame_twk2, text="Control", width=7)

        self.Lrg_CCW_button = ttk.Button(self.frame_twk2, width=4, text="<<<",
                                     state=tk.DISABLED,command=self.ccw_big)
        self.Med_CCW_button = ttk.Button(self.frame_twk2, width=4, text="<< ",
                                     state=tk.DISABLED,command=self.ccw_med)
        self.Sml_CCW_button = ttk.Button(self.frame_twk2, width=4, text="<  ",
                                     state=tk.DISABLED,command=self.ccw_sml)
        self.Sml_CW_button  = ttk.Button(self.frame_twk2, width=4, text=">  ",
                                     state=tk.DISABLED,command=self.cw_sml)
        self.Med_CW_button  = ttk.Button(self.frame_twk2, width=4, text=">> ",
                                     state=tk.DISABLED,command=self.cw_med)
        self.Lrg_CW_button  = ttk.Button(self.frame_twk2, width=4, text=">>>",
                                     state=tk.DISABLED,command=self.cw_big)

        self.label_LCCW = ttk.Label(self.frame_twk2, text="CCW "+str(self.big_move)+"deg", width=12)
        self.label_MCCW = ttk.Label(self.frame_twk2, text="CCW  "+str(self.med_move)+"deg", width=12)
        self.label_SCCW = ttk.Label(self.frame_twk2, text="CCW  "+str(self.small_move)+"deg", width=12)
        self.label_SCW  = ttk.Label(self.frame_twk2, text="CW    "+str(self.small_move)+"deg", width=12)
        self.label_MCW  = ttk.Label(self.frame_twk2, text="CW    "+str(self.med_move)+"deg", width=12)
        self.label_LCW  = ttk.Label(self.frame_twk2, text="CW   "+str(self.big_move)+"deg", width=12)

#       self.label_ManTwk1.grid(row=0,column=0,pady=2,sticky="e")
#       self.label_ManTwk2.grid(row=0,column=1,pady=2,sticky="w")
        self.label_LCCW.grid(column=0,row=0,padx=2,pady=2)
        self.label_MCCW.grid(column=0,row=1,padx=2,pady=2)
        self.label_SCCW.grid(column=0,row=2,padx=2,pady=2)
        self.label_SCW.grid(column=0,row=3,padx=2,pady=2)
        self.label_MCW.grid(column=0,row=4,padx=2,pady=2)
        self.label_LCW.grid(column=0,row=5,padx=2,pady=2)
        self.Lrg_CCW_button.grid(column=1,row=0,padx=2,pady=2)
        self.Med_CCW_button.grid(column=1,row=1,padx=2,pady=2)
        self.Sml_CCW_button.grid(column=1,row=2,padx=2,pady=2)
        self.Sml_CW_button.grid(column=1,row=3,padx=2,pady=2)
        self.Med_CW_button.grid(column=1,row=4,padx=2,pady=2)
        self.Lrg_CW_button.grid(column=1,row=5,padx=2,pady=2)

#       **************** QST tk.Frame *****************
        self.frame_quit = ttk.Frame(self.frame_qst)
        self.frame_quit.pack(fill=tk.X,padx=10,pady=3)
        self.quitButton = ttk.Button(self.frame_quit, text="Quit",command=self.quit)
        self.quitButton.pack(side=tk.RIGHT, pady=5, padx=5)

        self.label_status  = ttk.Label(self.frame_quit, text="Status", width=9)
        self.label_status.pack(fill=tk.X,side=tk.LEFT,padx=5,pady=5)

        self.frame_stat = ttk.Frame(self.frame_qst)
        self.frame_stat.pack(fill=tk.X,padx=10,pady=3)
        self.frame_status = ttk.Frame(self.frame_stat)
        self.frame_status.pack(fill=tk.X)
        self.entry_status = ttk.Entry(self.frame_status, textvariable=self.status_str, state="readonly")
        self.entry_status.pack(fill=tk.BOTH, pady=5, padx=5, expand=True)           

        self.top_fr.pack()
        self.center_top_window()
        return


    def set_move_labels(self):
        self.label_LCCW.set("CCW "+str(self.big_move)+"deg")
        self.label_MCCW.set("CCW  "+str(self.med_move)+"deg")
        self.label_SCCW.set("CCW  "+str(self.small_move)+"deg")
        self.label_SCW.set("CW    "+str(self.small_move)+"deg")
        self.label_MCW.set("CW    "+str(self.med_move)+"deg")
        self.label_LCW.set("CW   "+str(self.big_move)+"deg")
        return


    def center_top_window(self):
        self.parent.update()

        # get screen width and height
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()

        # get top window size
        width=self.top_fr.winfo_width()
        height=self.top_fr.winfo_height()
        if(625>width):
            width=725
        if(245>height):
            height=345

        # calculate position x and y coordinates
        x = (screen_width/2) - (width/2)
        y = (screen_height/2) - (height/2)
        self.parent.geometry('%dx%d+%d+%d' % (width, height, x, y))
#       debug_msg='geometry='+'%dx%d+%d+%d' % (width, height, x, y)
#       logging.info(debug_msg)
        return

    # load the configuration from a file
    def load_config(self):
        global PIFTConfFile
        global PIFTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type
        global BigMoveSize
        global MedMoveSize
        global SmallMoveSize
        # read_config reads into the global values
        if(0==read_config(self.config_file.get())):
            return
        # Now set GUI values to be the same as the global values
        self.log_file.set(PIFTLogFile)
        self.csv_file.set(PIFTCSVFile)
        self.petal_controller.set(str(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(str(CanID))
        self.motor_type.set(Initial_Motor_Type)	# 0 for phi, 1 for theta

        self.big_move=BigMoveSize
        self.med_move=MedMoveSize
        self.small_move=SmallMoveSize
        self.set_move_labels()

        self.logprint("Configuration loaded from "+self.config_file.get())
        return

    # save the current configuration
    def save_config(self):
        global PIFTConfFile
        global PIFTLogFile
        global PIFTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type

        retval=0
        try:
            lPC_num=int(self.petal_controller.get())
            lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix entry", ve )
            return retval

        # Set globals to the values of their GUI counterparts
        Petal_Controller_Number=lPC_num
        CanID=lCanID
        PIFTConfFile=self.config_file.get()
        PIFTLogFile=self.log_file.get()
        PIFTCSVFile=self.csv_file.get()
        CanBusID=self.canbus.get()
        Initial_Motor_Type=self.motor_type.get()	# 0 for phi, 1 for theta
        # Now, save in config file
        my_config = configobj.ConfigObj(unrepr=True,encoding='utf-8')
        if(0==Initial_Motor_Type):
        	my_config['MotorType']='phi'
        else:
        	my_config['MotorType']='theta'
        my_config['Logfile']=PIFTLogFile 
        my_config['CSVfile']=PIFTCSVFile 
        my_config['Petal_Controller_Number']=Petal_Controller_Number 
        my_config['CanBusID']=CanBusID 
        my_config['CanID']=CanID 
        my_config['BigMoveSize']=BigMoveSize
        my_config['MedMoveSize']=MedMoveSize
        my_config['SmallMoveSize']=SmallMoveSize
        my_config.filename=PIFTConfFile
        my_config.write()
        self.logprint("Configuration saved to "+self.config_file.get())
        retval=1
        return retval

    # if anything has changed since the last load/save, return 1 otherwise 0
    def check_config_changed(self):
        global PIFTConfFile
        global PIFTLogFile
        global PIFTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type
        retval=0	# assume no changes
        if(PIFTConfFile!=self.config_file.get()):
            retval=1
        if(PIFTLogFile!=self.log_file.get()):
            retval=1
        if(PIFTCSVFile!=self.csv_file.get()):
            retval=1
        if(str(Petal_Controller_Number)!=self.petal_controller.get()):
            retval=1
        if(CanBusID!=self.canbus.get()):
            retval=1
        if(str(CanID)!=self.canid.get()):
            retval=1
        if(Initial_Motor_Type!=self.motor_type.get()):	# 0 for phi, 1 for theta
            retval=1
        return retval;

    def Connect_to_PC(self):
        try:
            lPetal_Controller_Number=int(self.petal_controller.get())
            lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix entry", ve )
            return 
        lCanBusID=self.canbus.get()
        try:
            self.pcomm=petalcomm.PetalComm(lPetal_Controller_Number)
            if(self.pcomm.is_connected()):
                print("Connected")
                print("CanBus=",lCanBusID)
                print("CanID =",lCanID)
                self.logprint("Connected")
                if(4!=len(Currents)):
                    messagebox.showerror(prog_name+' Error', 'Currents should be a list of 4 values!')
                    return
                # enable button_Run here
                self.enable_Run_button()
            else:
                print("Not Connected")
                self.status_str.set("Not Connected")
        except:
            print("Not Connected, PetalComm init failed")
            self.status_str.set("Not Connected, PetalComm init failed")
        return

    # return 1 on fail, 0 on success
    def get_gui_results(self):
        retval=0	# assume success
        if(""==str(self.motor_sn.get()) or ""==str(self.operator_name.get())):
            retval=1
            messagebox.showerror(prog_name, 'Please enter Operator Name and Positioner ID')
        return retval

    def disable_Run_button(self):
        self.Lrg_CCW_button.config(state=tk.DISABLED)
        self.Med_CCW_button.config(state=tk.DISABLED)
        self.Sml_CCW_button.config(state=tk.DISABLED)
        self.Sml_CW_button.config(state=tk.DISABLED)
        self.Med_CW_button.config(state=tk.DISABLED)
        self.Lrg_CW_button.config(state=tk.DISABLED)
        self.button_setfid.config(state=tk.DISABLED)
        return

    def enable_Run_button(self):
        self.Lrg_CCW_button.config(state=tk.NORMAL)
        self.Med_CCW_button.config(state=tk.NORMAL)
        self.Sml_CCW_button.config(state=tk.NORMAL)
        self.Sml_CW_button.config(state=tk.NORMAL)
        self.Med_CW_button.config(state=tk.NORMAL)
        self.Lrg_CW_button.config(state=tk.NORMAL)
        self.button_next.config(state=tk.NORMAL)
        self.button_setfid.config(state=tk.NORMAL)
        return

    def do_next_motor(self):
        if(self.get_gui_results()):
            return
#       if(self.save_results()):
#           self.logprint("save failed")
#           return
        # Reset indexes and values so user can run another motor test
        self.reset_torque_test_state()
        self.enable_Run_button()
        return


    def reset_torque_test_state(self):
        self.move_count=0
#       self.logprint("Clearing SN and Notes")
        self.motor_sn.set("")
        self.user_notes.set("")
        self.cool_countdown=0
        self.enable_Run_button()
        return


    # returns 0 on failure, 1 on success
    def wait_for_FIPOS_ready(self):
        retval=0	# assume failure
        try:
           lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return retval
        lCanBusID=self.canbus.get()
        can_bus_ids=[lCanBusID]
        can_ids=[lCanID]
        if(self.simulate):
            bool_val=True
        else:
            bool_val=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
        msg="Ready for Tables: CanBusID="+str(lCanBusID)+", CanID="+str(lCanID)+" returned "+str(bool_val)
        self.logprint(msg)
        if(bool_val):
            retval=1		# success
        return retval

    # returns 0 on failure, 1 on success
    def set_FIPOS_currents(self):
        retval=0	# assume failure
        try:
           lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return retval
        lCanBusID=self.canbus.get()
        self.logprint("Setting current: CanBusID="+str(lCanBusID)+", CanID="+str(lCanID))
        if(self.simulate):
            retval=1
        else:
            self.pcomm.set_currents(lCanBusID,lCanID,Currents,Currents)
            retval=1
        return retval

    def motor_type_to_str(self,motor_type):        
        if(0==self.motor_type.get()):
          pt="Phi"
        else:
          pt="Theta"
        return pt

    def motor_speed_to_str(self,motor_speed):
        if(0==self.motor_speed.get()):
          pt="creep"
        else:
          pt="cruise"
        return pt


    def my_travel(self,direction,angle):
        try:
           lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return
        if(self.get_gui_results()):
            return
        self.set_FIPOS_currents()
        lCanBusID=self.canbus.get()
        pt=self.motor_type_to_str(self.motor_type.get())
        speed=self.motor_speed_to_str(self.motor_speed.get())
        move_str="Moving: CanID="+str(lCanID)
        move_str+=" "+pt+" "+direction+" "+str(angle)+" deg at "+speed
        self.logprint(move_str)
        if(self.simulate):
            error=0
        else:
            error=self.pcomm.move(lCanBusID, lCanID, direction, speed, pt, angle)
        if(0):
            print(error)
        if(self.save_results(speed,direction,angle)):
            self.logprint("save failed")
        return

    def set_fipos_led(self):
        try:
           LED_pct=int(self.fid_pct.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix LED_pct", ve )
            return
        try:
           iCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return
        if(self.get_gui_results()):
            return
        iCanBusID=self.canbus.get()
        lCanID=[iCanID]
        lCanBusID=[iCanBusID]
        LED_pcts=[LED_pct]
        bool_val=self.pcomm.set_fiducials(lCanBusID,lCanID,LED_pcts)
        if(bool_val):
            self.logprint("Success LED_pct="+str(LED_pct))
        else:
            self.logprint("Fail    LED_pct="+str(LED_pct))

    def cw_big(self):
        self.my_travel("CW",self.big_move)
        return

    def cw_med(self):
        self.my_travel("CW",self.med_move)
        return

    def cw_sml(self):
        self.my_travel("CW",self.small_move)
        return

    def ccw_big(self):
        self.my_travel("CCW",self.big_move)
        return

    def ccw_med(self):
        self.my_travel("CCW",self.med_move)
        return

    def ccw_sml(self):
        self.my_travel("CCW",self.small_move)
        return

    def getCSVheader(self):
        header_str ="Time,"
        header_str+="Motor_SN,Operator,MotorType,Speed,Direction,Angle,"
        header_str+="Notes"
        return header_str

    # return 1 on fail, 0 on success
    def save_results(self,speed,direction,angle):
        retval=0	# assume success
        spreadsheet_str =str(self.motor_sn.get())+"," 		# motor serial number
        spreadsheet_str+=str(self.operator_name.get())+","  # operator id
        pt=self.motor_type_to_str(self.motor_type.get())
        spreadsheet_str+=pt+","                             # phi or theta
        spreadsheet_str+=str(speed)+","                     # speed
        spreadsheet_str+=str(direction)+","                 # direction
        spreadsheet_str+=str(angle)+","                     # angle

        # Make sure not to add any extra commas to the CSV file
        spreadsheet_str+=str(self.user_notes.get()).replace(",","_")
        self.log(spreadsheet_str,which=1)
        self.logprint(spreadsheet_str)
        return retval


    def logfile(self,themessage,which):
        if(0==which):
            try:
                logf= open( PIFTLogFile, 'a+' )	# if log file exists, open for appending
            except FileNotFoundError:		# no, it doesn't
                logf=open( PIFTLogFile, 'w+')	# create it
        else:
            try:
                logf=open( PIFTCSVFile, 'r')	# See if csv file exists
                logf.close()			# yes, it does
            except IOError:			# no, it doesn't
                logf=open( PIFTCSVFile, 'w')	# create it
                logf.write(self.getCSVheader() + "\n")	# write the header
                logf.close()			# yes, it does
            logf= open( PIFTCSVFile, 'a' )
        logf.write( themessage + "\n" )
        logf.close()			# This will flush out the log after every line
        return

    # which is 0 for PIFTLogFile, and 1 for PIFTCSVFile
    def log(self,themessage,which=0,printit=0):
        if(0==which):
            timed_msg=time.strftime( "%x %X " )+themessage
        else:
            timed_msg=time.strftime( "%x %X," )+themessage
        if(self.gui_initialized):
            self.status_str.set(timed_msg)
        self.logfile(timed_msg,which)
        if(printit):
            print(timed_msg)
        return

    # which is 0 for PIFTLogFile, and 1 for PIFTCSVFile
    def logprint(self,themessage,which=0):
        self.log(themessage,which,1)
        return


    def quit(self):
        ask_quit=True
        if(self.check_config_changed()):
            answer=messagebox.askyesno(prog_name, 'Configuration has changed, do you want to save it?')
            if(answer):
                if(0==self.save_config()):
                    messagebox.showerror(prog_name, 'Save Config failed, no changes were made')
                ask_quit=False
        if(ask_quit):
            answer=messagebox.askokcancel(prog_name, 'Do you really want to quit?')
            if(answer):
                self.top_fr.destroy()	# destroy window
                self.parent.quit()
                sys.exit(0)
        return

    def runGUI(self):
        self.parent.mainloop()
        return


# return 0 on failure, 1 on success
def read_config(cfg_fname):
    global PIFTConfFile
    global PIFTLogFile
    global PIFTCSVFile
    global Petal_Controller_Number
    global CanBusID
    global CanID
    global Initial_Motor_Type
    global BigMoveSize
    global MedMoveSize
    global SmallMoveSize
    
    retval=1	# success is assumed
    my_config = configobj.ConfigObj(cfg_fname,unrepr=True,encoding='utf-8')
    MotorType = my_config['MotorType']
    if('phi' == str(MotorType).lower()):
        Initial_Motor_Type=0
    else:
        if('theta' == str(MotorType).lower()):
            Initial_Motor_Type=1
        else:
            messagebox.showerror(prog_name, 'MotorType in config file is not "phi" or "theta":'+str(MotorType))
            retval=0
    if(1==retval):
        PIFTLogFile = my_config['Logfile']
        PIFTCSVFile = my_config['CSVfile']
        Petal_Controller_Number = int(my_config['Petal_Controller_Number'])
        CanBusID = my_config['CanBusID']
        CanID = int(my_config['CanID'])
        PIFTConfFile=cfg_fname
        BigMoveSize=float(my_config['BigMoveSize'])
        MedMoveSize=float(my_config['MedMoveSize'])
        SmallMoveSize=float(my_config['SmallMoveSize'])
    return retval

fh=0
def another_instance():
    global fh
    retval=0
    fh=open(os.path.realpath(__file__),'r')
    try:
        fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except:
        retval=1
    return retval

def main(logging_level):
    root = tk.Tk()
    if(not another_instance()):
        PIFTConfFile = filedialog.askopenfilename(initialdir=pc.dirs["other_settings"], filetypes=(("Config file","*.conf"),("All Files","*")), title="Select Torque Test Config File")
        if(""==PIFTConfFile):
            messagebox.showerror(prog_name, 'Cannot run without a config file')
            root.quit()
            sys.exit(0)
        if(0==read_config(PIFTConfFile)):
            root.quit()
            sys.exit(0)
        my_ttg = Torque_Test_GUI(root,logging_level)
        my_ttg.runGUI()
        return
    else:
        messagebox.showerror(prog_name, 'Another instance is already running')
        root.quit()
        sys.exit(0)
    return


if __name__ == '__main__':
    logging_level=logging.WARNING
    print("num args=",len(sys.argv))
    if len(sys.argv) >=1:
        if len(sys.argv) == 2:
            if sys.argv[1].upper() == 'DEBUG':
                logging_level=logging.DEBUG
            if sys.argv[1].upper() == 'INFO':
                logging_level=logging.INFO
            if sys.argv[1].upper() == 'WARNING':
                logging_level=logging.WARNING
            if sys.argv[1].upper() == 'ERROR':
                logging_level=logging.ERROR
            if sys.argv[1].upper() == 'CRITICAl':
                logging_level=logging.CRITICAL
        main(logging_level)
    else:
        print("bad args: ",sys.argv)

