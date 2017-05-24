#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
#    Title:       gtorque_test.py
#    Date:        05/11/2017
#    Author:      cad
#    Sysnopsis:   GUI to run torque tests on theta and phi motors
#    Description:
#	python3 gtorque_test.py [ debug | info | warning | error | critical ]
#	the optional arguments (case-insensitive) set the logging level for the logging package
#	the default logging level is warning
#
#    Revisions:
#    mm/dd/yyyy who        description
#    ---------- --------   -----------
#    05/24/2017 cad        Version 1.02.  Changed to individual constants for cool down time, and
#                          torque angle. Removed Torque Moves.  Restructured code to allow multiple
#                          CW and CCW torques.
#                          The "Next Motor" button saves the last results and aborts the current
#                          wait for cool down (if any)
#                          Changed get_gui_results to return 1 on error, 0 otherwise
#    05/18/2017 cad        Changed to version 1.01, deal with changes to 'other_settings' 
#                          in posconstants.py
#    05/17/2017 cad        Added prog_version, display it in the Title Bar
#    05/16/2017 cad        Minor UI changes, added test to prevent multiple instances from running,
#                          Fixed the code which wrote a header to CSV file if the file didn't exist.
#                          Change any commas in user notes to "_"
#    05/12/2017 cad        Fixed set_currents and move commands to use single ints, 
#                          not lists, just like in test_torque.py
#                          Disable manual control buttons during cool-down.
#                          Validate user inputs
# 
# ****************************************************************************

# To do: set defaults, allow user override, check PC, canbus, and can_id setting

from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
from tkinter.ttk import *

import os
import sys
import fcntl
import time
import datetime # for the filename timestamp
import logging
import configobj

# This is a hack to get the folder with petalcomm.py into the path
sys.path.append('../../petal')
# print(sys.path)

import petalcomm
import posconstants as pc

prog_name="Torque Test"
prog_version="1.02"

# Configuration Values

TTConfFile="./torque_test.conf"
TTLogFile="./torque_test.log"
TTCSVFile="./torque_test.csv"
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

torque_angle=65		# degrees
torque_cool_down=90	# seconds
torque_mode='creep'

# indices into MoveTable list
iMotor=0     # 'phi' or 'theta'
iMode=1      # 'cruise' or 'creep'
iDirection=2 # 'cw' or 'ccw
iAngle=3     # angle in degrees
iCoolSecs=4  # seconds to cool down

class Torque_Test_GUI:
    """Class for Torque Test GUI"""

    # 
    def __init__(self,tkroot,logging_level):
        self.parent = tkroot
        self.logging_level = logging_level

        logging.basicConfig(filename=TTLogFile,level=logging_level)

        self.gui_initialized=0
        self.logprint("Logging level set to "+str(logging_level))
        
        self.initVars()
        self.initUI()
        self.gui_initialized=1
        return

    def initVars(self):
        global TTConfFile
        global TTLogFile
        global TTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type

        self.max_torque=0.0
        self.res_torque=0.0
        self.tt_state=0
        self.move_count=0
        self.cool_countdown=0
        self.simulate=0         # 1 for simulation, 0 for the real thing
        self.delay=1000         # 1000 ms = 1 sec
        self.sVoltage=""	# string version of Voltage saved by get_gui_results
        self.move_direction="ccw"
        self.torque_angle=torque_angle
        self.cool_down_sec=torque_cool_down
        self.torque_mode=torque_mode

        # define internal variables connected to GUI
        self.config_file=StringVar()
        self.log_file=StringVar()
        self.csv_file=StringVar()

        self.petal_controller=StringVar()
        self.canbus=StringVar()
        self.canid=StringVar()
        self.motor_type=IntVar()
        self.operator_name=StringVar()
        self.motor_sn=StringVar()
        self.voltage=StringVar()
        self.maxTorque=StringVar()
        self.settledTorque=StringVar()
        self.user_notes=StringVar()
        self.status_str=StringVar()
        self.progress_val=IntVar()

        # Now set the default values
        self.config_file.set(TTConfFile)
        self.log_file.set(TTLogFile)
        self.csv_file.set(TTCSVFile)
        self.petal_controller.set(str(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(str(CanID))
        self.motor_type.set(Initial_Motor_Type)	# 0 for phi, 1 for theta
        self.progress_val.set(0)
        return;


    def initUI(self):
        self.parent.title(prog_name+" - Vers. "+prog_version)

        self.top_fr=Frame(self.parent)
        self.top_fr.pack(fill=BOTH, expand=True)
        
        # 4 Frames defining the overall geometry

        # Hardware settings and Connection button
        self.frame_top_left=Frame(self.top_fr)
        self.frame_top_left.grid(column=0,row=0,rowspan=3,sticky="ns",padx=2,pady=2)
        self.frame_hw = Frame(self.frame_top_left,relief="groove",borderwidth=2)
        self.frame_hw.pack(fill=BOTH,expand=True)

        # Test settings and Apply Torque button
        self.frame_top_mid=Frame(self.top_fr)
        self.frame_top_mid.grid(column=1,row=0,rowspan=3,sticky="n",padx=2,pady=2)
        self.frame_tst = Frame(self.frame_top_mid,relief="groove",borderwidth=2)
        self.frame_tst.pack(fill=BOTH,expand=True)
        
        # Tweak Motor Position
        self.frame_top_right=Frame(self.top_fr)
        self.frame_top_right.grid(column=2,row=0,rowspan=3,sticky="ns",padx=2,pady=2)
        self.frame_twk = Frame(self.frame_top_right,relief="groove",borderwidth=2)
        self.frame_twk.pack(fill=BOTH,expand=True)
        
        # Quit button and Status
        self.frame_bot_right=Frame(self.top_fr)
        self.frame_bot_right.grid(column=0,row=3,columnspan=3,sticky="ew",padx=2,pady=2)
        self.frame_qst = Frame(self.frame_bot_right,relief="groove",borderwidth=2)
        self.frame_qst.pack(fill=BOTH,expand=True,ipadx=2,ipady=2)

        
#       ************ HW Frame **********************
        self.frame_hw_1 = Frame(self.frame_hw)
        self.frame_hw_1.pack(fill=X)
        self.label_PC = Label(self.frame_hw_1, text="PetalController", width=11)
        self.label_PC.pack(side=LEFT, padx=5, pady=5)        
        self.entry_PC = Entry(self.frame_hw_1)
        self.entry_PC["textvariable"]=self.petal_controller
        self.entry_PC.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_2 = Frame(self.frame_hw)
        self.frame_hw_2.pack(fill=X)
        self.label_CB = Label(self.frame_hw_2, text="Can Bus", width=11)
        self.label_CB.pack(side=LEFT, padx=5, pady=5)        
        self.entry_CB = Entry(self.frame_hw_2)
        self.entry_CB["textvariable"]=self.canbus
        self.entry_CB.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_3 = Frame(self.frame_hw)
        self.frame_hw_3.pack(fill=X)
        self.label_CI = Label(self.frame_hw_3, text="Can ID", width=11)
        self.label_CI.pack(side=LEFT, padx=5, pady=5)        
        self.entry_CI = Entry(self.frame_hw_3)
        self.entry_CI["textvariable"]=self.canid
        self.entry_CI.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_4 = Frame(self.frame_hw)
        self.frame_hw_4.pack(fill=X, padx=5, pady=3)
        self.frame_rb = Frame(self.frame_hw_4,relief="groove",borderwidth=2)
        self.frame_rb.pack(side=RIGHT,fill=X,pady=3)
        self.button_Phi = Radiobutton(self.frame_rb, width=7, text="Phi", variable=self.motor_type, value=0).pack(side=LEFT,padx=2)
        self.button_Theta = Radiobutton(self.frame_rb, width=7, text="Theta", variable=self.motor_type, value=1).pack(side=RIGHT,padx=2)
        self.motor_type.set(Initial_Motor_Type)
        
        self.frame_hw_6 = Frame(self.frame_hw)
        self.frame_hw_6.pack(fill=X)
        self.label_CF = Label(self.frame_hw_6, text="Config File", width=11)
        self.label_CF.pack(side=LEFT, padx=5, pady=5)        
        self.entry_CF = Entry(self.frame_hw_6)
        self.entry_CF["textvariable"]=self.config_file
        self.entry_CF.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_7 = Frame(self.frame_hw)
        self.frame_hw_7.pack(fill=X)
        self.label_LF = Label(self.frame_hw_7, text="Log File", width=11)
        self.label_LF.pack(side=LEFT, padx=5, pady=5)        
        self.entry_LF = Entry(self.frame_hw_7)
        self.entry_LF["textvariable"]=self.log_file
        self.entry_LF.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_8 = Frame(self.frame_hw)
        self.frame_hw_8.pack(fill=X)
        self.label_DF = Label(self.frame_hw_8, text="Data File", width=11)
        self.label_DF.pack(side=LEFT, padx=5, pady=5)        
        self.entry_DF = Entry(self.frame_hw_8)
        self.entry_DF["textvariable"]=self.csv_file
        self.entry_DF.pack(fill=X, padx=5, expand=True)
        
        self.frame_hw_5 = Frame(self.frame_hw)
        self.frame_hw_5.pack(fill=X,padx=5,pady=3,side=RIGHT)

        self.frame_hw_5a = Frame(self.frame_hw_5,relief="groove",borderwidth=2)
        self.frame_hw_5b = Frame(self.frame_hw_5)

        self.button_LoadConf = Button(self.frame_hw_5a, width=9, text="Load Config")
        self.button_LoadConf["command"]=self.load_config
        self.button_SaveConf = Button(self.frame_hw_5a, width=9, text="Save Config")
        self.button_SaveConf["command"]=self.save_config

        self.label_nada = Label(self.frame_hw_5b, text=" ", width=4)

        self.button_Connect = Button(self.frame_hw_5, width=9, text="Connect")
        self.button_Connect["command"]=self.Connect_to_PC

        self.frame_hw_5a.grid(column=0,row=0,sticky="w",padx=2,pady=2)
#       self.frame_hw_5a.pack(fill=X,side=LEFT)
        self.button_LoadConf.grid(column=0,row=0,sticky="w",padx=2,pady=2)
        self.button_SaveConf.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.frame_hw_5b.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.label_nada.pack(fill=X)
#       self.frame_hw_5b.pack(fill=X)
        self.button_Connect.grid(column=2,row=0,sticky="e",padx=2,pady=2)
#       self.button_Connect.pack(fill=X,side=RIGHT)

#       ********************** TST Frame *****************

        self.frame_op = Frame(self.frame_tst)
        self.frame_op.pack(fill=X,pady=1)
        self.label_op = Label(self.frame_op, text="Operator", width=11)
        self.label_op.pack(side=LEFT, padx=5, pady=5)           
        self.entry_op = Entry(self.frame_op)
        self.entry_op["textvariable"]=self.operator_name
        self.entry_op.pack(fill=X, padx=5, expand=True)
        
        self.frame_sn = Frame(self.frame_tst)
        self.frame_sn.pack(fill=X,pady=1)
        self.label_sn = Label(self.frame_sn, text="Motor S/N", width=11)
        self.label_sn.pack(side=LEFT, padx=5, pady=5)           
        self.entry_sn = Entry(self.frame_sn)
        self.entry_sn["textvariable"]=self.motor_sn
        self.entry_sn.pack(fill=X, padx=5, expand=True)
        
        self.frame_vlt = Frame(self.frame_tst)
        self.frame_vlt.pack(fill=X,pady=1)
        self.label_vlt = Label(self.frame_vlt, text="Voltage", width=11)
        self.label_vlt.pack(side=LEFT, padx=5, pady=5)           
        self.entry_vlt = Entry(self.frame_vlt)
        self.entry_vlt["textvariable"]=self.voltage
        self.entry_vlt.pack(fill=X, padx=5, expand=True)
        
        self.frame_note = Frame(self.frame_tst)
        self.frame_note.pack(fill=X)
        self.label_note = Label(self.frame_note, text="Notes", width=11)
        self.label_note.pack(side=LEFT, anchor=N, padx=5, pady=5)        
        self.entry_note = Entry(self.frame_note)
        self.entry_note["textvariable"]=self.user_notes
        self.entry_note.pack(fill=BOTH, pady=5, padx=5, expand=True)           

        self.frame_Tmax = Frame(self.frame_tst)
        self.frame_Tmax.pack(fill=X)
        self.label_Tmax = Label(self.frame_Tmax, text="Max Torque", width=11)
        self.label_Tmax.pack(side=LEFT, anchor=N, padx=5, pady=5)        
        self.entry_Tmax = Entry(self.frame_Tmax)
        self.entry_Tmax["textvariable"]=self.maxTorque
        self.entry_Tmax.pack(fill=BOTH, pady=5, padx=5, expand=True)           

        self.frame_Tstl = Frame(self.frame_tst)
        self.frame_Tstl.pack(fill=X)
        self.label_Tstl = Label(self.frame_Tstl, text="Settled Torque", width=11)
        self.label_Tstl.pack(side=LEFT, anchor=N, padx=5, pady=5)        
        self.entry_Tstl = Entry(self.frame_Tstl,
                          textvariable=self.settledTorque)
#       self.entry_Tstl["textvariable"]=self.settledTorque
        self.entry_Tstl.pack(fill=BOTH, pady=5, padx=5, expand=True)           

        self.frame_prog = Frame(self.frame_tst)
        self.frame_prog.pack(fill=X)
        self.label_Tstl = Label(self.frame_prog, text="Cool Down", width=11)
        self.label_Tstl.pack(side=LEFT, anchor=N, padx=5, pady=5)        
        self.progress = Progressbar(self.frame_prog, orient="horizontal", 
                                    length=200, mode="determinate", value=0, 
                                    variable=self.progress_val)
        self.progress.pack(fill=BOTH, pady=5, padx=5, expand=True)           
#       self.progress.pack(fill=X,padx=5)

        self.frame_tst_btn = Frame(self.frame_tst)
        self.frame_tst_btn.pack(fill=X,pady=9)

        self.button_CCW = Button(self.frame_tst_btn, width=10, state=DISABLED,
                          command=self.do_ccw_torque,
                          text="CCW Torque")
        self.button_CW  = Button(self.frame_tst_btn, width=10, state=DISABLED,
                          command=self.do_cw_torque,
                          text="CW Torque")
        self.label_nada2 = Label(self.frame_tst_btn, text=" ", width=3)
        self.button_Nxt = Button(self.frame_tst_btn, width=9, state=DISABLED,
                          command=self.do_next_motor,
                          text="Next Motor")

        self.button_CCW.grid(column=0,row=0,sticky="w",padx=2,pady=2)
        self.button_CW.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.label_nada2.grid(column=2,row=0,sticky="w",padx=2,pady=2)
        self.button_Nxt.grid(column=3,row=0,sticky="e",padx=2,pady=2)
        
#       **************** TWK Frame *****************
        self.frame_twk1 = Frame(self.frame_twk)
        self.frame_twk1.pack(fill=X,pady=1,expand=True)
        self.label_ManTwk=Label(self.frame_twk1, text="  Manual Control", width=13)
        self.label_ManTwk.grid(padx=6,pady=2)

        self.frame_twk2 = Frame(self.frame_twk)
        self.frame_twk2.pack(fill=BOTH,expand=True,pady=1)

#       self.label_ManTwk1=Label(self.frame_twk2, text=" Manual", width=7)
#       self.label_ManTwk2=Label(self.frame_twk2, text="Control", width=7)

        self.Lrg_CCW_button = Button(self.frame_twk2, width=4, text="<<<",
                                     state=DISABLED,command=self.ccw_big)
        self.Med_CCW_button = Button(self.frame_twk2, width=4, text="<< ",
                                     state=DISABLED,command=self.ccw_med)
        self.Sml_CCW_button = Button(self.frame_twk2, width=4, text="<  ",
                                     state=DISABLED,command=self.ccw_sml)
        self.Sml_CW_button  = Button(self.frame_twk2, width=4, text=">  ",
                                     state=DISABLED,command=self.cw_sml)
        self.Med_CW_button  = Button(self.frame_twk2, width=4, text=">> ",
                                     state=DISABLED,command=self.cw_med)
        self.Lrg_CW_button  = Button(self.frame_twk2, width=4, text=">>>",
                                     state=DISABLED,command=self.cw_big)

        self.label_LCCW = Label(self.frame_twk2, text="CCW 10deg", width=9)
        self.label_MCCW = Label(self.frame_twk2, text="CCW   5deg", width=9)
        self.label_SCCW = Label(self.frame_twk2, text="CCW   1deg", width=9)
        self.label_SCW  = Label(self.frame_twk2, text="CW     1deg", width=9)
        self.label_MCW  = Label(self.frame_twk2, text="CW     5deg", width=9)
        self.label_LCW  = Label(self.frame_twk2, text="CW   10deg", width=9)

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

#       **************** QST Frame *****************
        self.frame_quit = Frame(self.frame_qst)
        self.frame_quit.pack(fill=X,padx=10,pady=3)
        self.quitButton = Button(self.frame_quit, text="Quit",command=self.quit)
        self.quitButton.pack(side=RIGHT, pady=5, padx=5)

        self.label_status  = Label(self.frame_quit, text="Status", width=9)
        self.label_status.pack(fill=X,side=LEFT,padx=5,pady=5)

        self.frame_stat = Frame(self.frame_qst)
        self.frame_stat.pack(fill=X,padx=10,pady=3)
        self.frame_status = Frame(self.frame_stat)
        self.frame_status.pack(fill=X)
        self.entry_status = Entry(self.frame_status, textvariable=self.status_str, state="readonly")
        self.entry_status.pack(fill=BOTH, pady=5, padx=5, expand=True)           

        self.top_fr.pack()
        self.center_top_window()
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
        debug_msg='geometry='+'%dx%d+%d+%d' % (width, height, x, y)
#       logging.info(debug_msg)
        return

    # load the configuration from a file
    def load_config(self):
        global TTLogFile
        global TTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type
        # read_config reads into the global values
        if(0==read_config(self.config_file.get())):
            return
        # Now set GUI values to be the same as the global values
        self.log_file.set(TTLogFile)
        self.csv_file.set(TTCSVFile)
        self.petal_controller.set(str(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(str(CanID))
        self.motor_type.set(Initial_Motor_Type)	# 0 for phi, 1 for theta
        self.logprint("Configuration loaded from "+self.config_file.get())
        return

    # save the current configuration
    def save_config(self):
        global TTConfFile
        global TTLogFile
        global TTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type

        retval=0
        try:
            lPC_num=int(self.petal_controller.get())
            lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix Entry", ve )
            return retval

        # Set globals to the values of their GUI counterparts
        Petal_Controller_Number=lPC_num
        CanID=lCanID
        TTConfFile=self.config_file.get()
        TTLogFile=self.log_file.get()
        TTCSVFile=self.csv_file.get()
        CanBusID=self.canbus.get()
        Initial_Motor_Type=self.motor_type.get()	# 0 for phi, 1 for theta
        # Now, save in config file
        my_config = configobj.ConfigObj(unrepr=True,encoding='utf-8')
        if(0==Initial_Motor_Type):
        	my_config['MotorType']='phi'
        else:
        	my_config['MotorType']='theta'
        my_config['Logfile']=TTLogFile 
        my_config['CSVfile']=TTCSVFile 
        my_config['Petal_Controller_Number']=Petal_Controller_Number 
        my_config['CanBusID']=CanBusID 
        my_config['CanID']=CanID 
        my_config.filename=TTConfFile
        my_config.write()
        self.logprint("Configuration saved to "+self.config_file.get())
        retval=1
        return retval

    # if anything has changed since the last load/save, return 1 otherwise 0
    def check_config_changed(self):
        global TTConfFile
        global TTLogFile
        global TTCSVFile
        global Petal_Controller_Number
        global CanBusID
        global CanID
        global Initial_Motor_Type
        retval=0	# assume no changes
        if(TTConfFile!=self.config_file.get()):
            retval=1
        if(TTLogFile!=self.log_file.get()):
            retval=1
        if(TTCSVFile!=self.csv_file.get()):
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
            messagebox.showerror(prog_name+" - Fix Entry", ve )
            return 
        lCanBusID=self.canbus.get()
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
        return

    # return 1 on fail, 0 on success
    def get_gui_results(self):
        retval=1	# assume failure
        sVoltage=self.voltage.get()
        sMaxTorque=self.maxTorque.get()
        sSettledTorque=self.settledTorque.get()
        if(""==sMaxTorque or ""==sSettledTorque): # no value?
            messagebox.showerror(prog_name, 'Please enter both Maximum and Settled Torque values')
        else:
            if(""==str(self.motor_sn.get()) or ""==str(self.operator_name.get()) or ""==sVoltage):
                messagebox.showerror(prog_name, 'Please enter Operator Name, Motor Serial Number, and Voltage')
            else:
                try:
                    dVoltage=float(self.voltage.get())
                    dMaxTorque=float(self.maxTorque.get())
                    dSettledTorque=float(self.settledTorque.get())
                except ValueError as ve:
                    messagebox.showerror(prog_name+" - Fix Entry", ve )
                    return retval
                if(0.0>=dMaxTorque or 0.0>=dSettledTorque or 0.0>=dVoltage):
                    messagebox.showerror(prog_name, "Please enter only positive values" )
                    return retval
                if(3.0<dMaxTorque):
                    messagebox.showerror(prog_name, "Max Torque value is out of range" )
                    return retval
                if(3.0<dSettledTorque):
                    messagebox.showerror(prog_name, "Res Torque value is out of range" )
                    return retval
                if(15.0<dVoltage):
                    messagebox.showerror(prog_name, "Test Voltage value is out of range" )
                    return retval

                self.max_torque=dMaxTorque
                self.res_torque=dSettledTorque
                self.sVoltage=sVoltage
                self.maxTorque.set("")
                self.settledTorque.set("")
                retval=0
        return retval

    def disable_Run_button(self):
        self.button_CCW.config(state=DISABLED)
        self.button_CW.config(state=DISABLED)
#       self.button_Nxt.config(state=DISABLED)
        self.Lrg_CCW_button.config(state=DISABLED)
        self.Med_CCW_button.config(state=DISABLED)
        self.Sml_CCW_button.config(state=DISABLED)
        self.Sml_CW_button.config(state=DISABLED)
        self.Med_CW_button.config(state=DISABLED)
        self.Lrg_CW_button.config(state=DISABLED)
        return

    def enable_Run_button(self):
        self.button_CCW.config(state=NORMAL)
        self.button_CW.config(state=NORMAL)
        self.button_Nxt.config(state=NORMAL)
        self.Lrg_CCW_button.config(state=NORMAL)
        self.Med_CCW_button.config(state=NORMAL)
        self.Sml_CCW_button.config(state=NORMAL)
        self.Sml_CW_button.config(state=NORMAL)
        self.Med_CW_button.config(state=NORMAL)
        self.Lrg_CW_button.config(state=NORMAL)
        return

    def do_ccw_torque(self):
        self.tt_state=0
        self.move_direction="ccw"
        self.tt_state_machine()
        return

    def do_cw_torque(self):
        self.tt_state=0
        self.move_direction="cw"
        self.tt_state_machine()
        return

    def do_next_motor(self):
#       self.tt_state=5
#       self.tt_state_machine()
        if(self.get_gui_results()):
            return
        if(self.save_results()):
            return
        # Reset indexes and values so user can run another motor test
        self.reset_torque_test_state()
        self.enable_Run_button()
        return

    def tt_state_machine(self):
        self.disable_Run_button()
        if(0==self.tt_state):
            if(0 != self.move_count):   #   First must save the previous results, if any
                if(self.get_gui_results()):
                    self.enable_Run_button()
                    return
                if(self.save_results()):
                    self.enable_Run_button()
                    return
            if(self.wait_for_FIPOS_ready()):
                self.tt_state+=1	# set currents next
            else:
                self.reset_torque_test_state()
                messagebox.showerror(prog_name, "Aborting Torque Test" )
                return
        if(1==self.tt_state):
            if(self.set_FIPOS_currents()):
                self.tt_state+=1	# apply torque next
            else:
                self.reset_torque_test_state()
                messagebox.showerror(prog_name, "Aborting Torque Test" )
                return
        if(2==self.tt_state):
            if(self.apply_FIPOS_torque()):
                self.tt_state+=1	# wait for cool-down next
                self.move_count=self.move_count
            else:
                self.reset_torque_test_state()
                messagebox.showerror(prog_name, "Aborting Torque Test" )
                return
        if(3==self.tt_state):
            self.cool_down()
            # cool_down determines the next state
        if(4==self.tt_state):
            self.tt_state=0    # wait for user to apply next torque in sequence
            self.enable_Run_button()
            return
        if(5==self.tt_state):	# State 5 is no longer used -cad 05/24/2017
            if(self.get_gui_results()):
                self.enable_Run_button()
                return
            if(self.save_results()):
                self.enable_Run_button()
                return
            # Reset indexes and values so user can run another motor test
            self.reset_torque_test_state()
            return  # wait for user to run test again, or to quit
        if(6==self.tt_state):
            self.enable_Run_button()
            return  # wait for user to run test again, or to quit

        self.parent.after(self.delay,self.tt_state_machine)
        return

    def reset_torque_test_state(self):
        self.tt_state=6	# abort state machine
        self.move_count=0
        self.max_torque=0.0
        self.res_torque=0.0
        self.maxTorque.set("")
        self.settledTorque.set("")
        self.motor_sn.set("")
        self.user_notes.set("")
        self.cool_countdown=0
        self.progress_val.set(self.cool_countdown)
        self.enable_Run_button()
        return

    def cool_down(self):
        self.cool_countdown=self.cool_countdown-1
        cool_msg="Waiting "+str(int(self.cool_countdown))+" seconds to cool down"
        self.status_str.set(cool_msg)
#       self.logprint(cool_msg)
        self.progress_val.set(self.cool_countdown)
        if(self.cool_countdown <= 0):
            self.status_str.set("")
            self.tt_state+=1

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
            bool_val=True
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

    # returns 0 on failure, 1 on success
    def apply_FIPOS_torque(self):
        retval=0	# assume failure
        try:
           lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return retval
        lCanBusID=self.canbus.get()
        pt=self.motor_type_to_str(self.motor_type.get())
        self.move_count+=1
        move_str="Moving: CanID="+str(lCanID)
        move_str+=" "+pt+" "+str(self.move_direction)
        move_str+=" "+str(self.torque_angle)+" deg at "
        move_str+=str(self.torque_mode)
        self.logprint(move_str)
        if(self.simulate):
            error=0
        else:
            error = self.pcomm.move(lCanBusID, lCanID,
                                    self.move_direction,
                                    self.torque_mode,
                                    pt,
                                    self.torque_angle)
        self.cool_countdown=self.cool_down_sec
        self.progress["maximum"]=self.cool_countdown
        self.progress_val.set(self.cool_countdown)
        cool_msg="Waiting "+str(int(self.cool_countdown))+" seconds to cool down"
        self.logprint(cool_msg)
        self.status_str.set(cool_msg)
        retval=1	# success
        return retval;

    def my_cruise(self,direction,angle):
        try:
           lCanID=int(self.canid.get())
        except ValueError as ve:
            messagebox.showerror(prog_name+" - Fix CanID", ve )
            return
        lCanBusID=self.canbus.get()
        pt=self.motor_type_to_str(self.motor_type.get())
        move_str="Moving: CanID="+str(lCanID)
        move_str+=" "+pt+" "+direction+" "+str(angle)+" deg at cruise"
        self.logprint(move_str)
        if(self.simulate):
            error=0
        else:
            error = self.pcomm.move(lCanBusID, lCanID, direction, "cruise", pt, angle)
        return

    def cw_big(self):
        self.my_cruise("CW",10)
        return

    def cw_med(self):
        self.my_cruise("CW",5)
        return

    def cw_sml(self):
        self.my_cruise("CW",1)
        return

    def ccw_big(self):
        self.my_cruise("CCW",10)
        return

    def ccw_med(self):
        self.my_cruise("CCW",5)
        return

    def ccw_sml(self):
        self.my_cruise("CCW",1)
        return

    def getCSVheader(self):
        header_str ="Time,"
        header_str+="Motor_SN,Operator,Test_Voltage,MotorType,Speed,"
        header_str+="Direction,Torque_Angle,Cooldown_Sec,"
        header_str+="Max_Torque_(oz-in),Max_Torque_(n-mm),"
        header_str+="Settled_Torque_(oz-in),Settled_Torque_(n-mm),"
        header_str+="Notes"
        return header_str

    # return 1 on fail, 0 on success
    def save_results(self):
        retval=0	# assume success
        spreadsheet_str =str(self.motor_sn.get())+"," 		   # motor serial number
        spreadsheet_str+=str(self.operator_name.get())+","         # operator id
        spreadsheet_str+=str(self.sVoltage)+","                    # test_voltage
        pt=self.motor_type_to_str(self.motor_type.get())
        spreadsheet_str+=pt+","                                    # phi or theta
        spreadsheet_str+=str(self.torque_mode)+","                 # creep or cruise
        spreadsheet_str+=str(self.move_direction)+","              # ccw or cw
        spreadsheet_str+=str(self.torque_angle)+","                # torque angle
        spreadsheet_str+=str(self.cool_down_sec)+","               # cooldown seconds
        spreadsheet_str+=str(self.max_torque)+","               # max ccw torque in oz-in
        spreadsheet_str+=str(format(float(self.max_torque)/n_mm_to_oz_in,'.3f'))+","	# max ccw torque in n-mm
        spreadsheet_str+=str(self.res_torque)+","		   # settled ccw torque in oz-in
        spreadsheet_str+=str(format(float(self.res_torque)/n_mm_to_oz_in,'.3f'))+","	# settled ccw torque in n-mm

        # Make sure not to add any extra commas to the CSV file
        spreadsheet_str+=str(self.user_notes.get()).replace(",","_")
        self.log(spreadsheet_str,which=1)
        self.logprint(spreadsheet_str)
        return retval


    def logfile(self,themessage,which):
        if(0==which):
            try:
                logf= open( TTLogFile, 'a+' )	# if log file exists, open for appending
            except FileNotFoundError:		# no, it doesn't
                logf=open( TTLogFile, 'w+')	# create it
        else:
            try:
                logf=open( TTCSVFile, 'r')	# See if csv file exists
                logf.close()			# yes, it does
            except IOError:			# no, it doesn't
                logf=open( TTCSVFile, 'w')	# create it
                logf.write(self.getCSVheader() + "\n")	# write the header
                logf.close()			# yes, it does
            logf= open( TTCSVFile, 'a' )
        logf.write( themessage + "\n" )
        logf.close()			# This will flush out the log after every line
        return

    # which is 0 for TTLogFile, and 1 for TTCSVFile
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

    # which is 0 for TTLogFile, and 1 for TTCSVFile
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
    global TTConfFile
    global TTLogFile
    global TTCSVFile
    global Petal_Controller_Number
    global CanBusID
    global CanID
    global Initial_Motor_Type
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
        TTLogFile = my_config['Logfile']
        TTCSVFile = my_config['CSVfile']
        Petal_Controller_Number = int(my_config['Petal_Controller_Number'])
        CanBusID = my_config['CanBusID']
        CanID = int(my_config['CanID'])
        TTConfFile=cfg_fname
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
    root = Tk()
    if(not another_instance()):
        TTConfFile = filedialog.askopenfilename(initialdir=pc.dirs["other_settings"], filetypes=(("Config file","*.conf"),("All Files","*")), title="Select Torque Test Config File")
        if(""==TTConfFile):
            messagebox.showerror(prog_name, 'Cannot run without a config file')
            root.quit()
            sys.exit(0)
        if(0==read_config(TTConfFile)):
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
                torque_cool_down=20
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

