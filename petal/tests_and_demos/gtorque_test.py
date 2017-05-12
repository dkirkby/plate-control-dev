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
# 
# ****************************************************************************

# To do: set defaults, allow user override, check PC, canbus, and can_id setting

from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
from tkinter.ttk import *

import os
import sys
import time
import datetime # for the filename timestamp
import logging
import configobj

# This is a hack to get the folder with petalcomm.py into the path
cwd = os.getcwd()
sys.path.append(cwd + '/../')
# print(sys.path)

import petalcomm
import posconstants as pc

prog_name="Torque Test"

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
Torque_Moves=[
    #'motor','speed','direction','angle','cool_down_seconds'
    ['phi'  ,'creep' ,'ccw' ,90,  120],
    ['phi'  ,'creep' ,'cw'  ,90,    0]
]

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

        self.max_torque=[]
        self.res_torque=[]
        self.tt_state=0
        self.move_count=0
        self.cool_countdown=0
        self.simulate=1         # 1 for simulation, 0 for the real thing
        self.delay=1000         # 1000 ms = 1 sec

        # define internal variables connected to GUI
        self.config_file=StringVar()
        self.log_file=StringVar()
        self.csv_file=StringVar()

        self.petal_controller=IntVar()
        self.canbus=StringVar()
        self.canid=IntVar()
        self.motor_type=IntVar()
        self.operator_name=StringVar()
        self.motor_sn=StringVar()
        self.voltage=DoubleVar()
        self.maxTorque=DoubleVar()
        self.settledTorque=DoubleVar()
        self.user_notes=StringVar()
        self.Connect_Button_Text=StringVar()
        self.Run_Button_Text=StringVar()
        self.status_str=StringVar()
        self.progress_val=IntVar()

        # Now set the default values
        self.config_file.set(TTConfFile)
        self.log_file.set(TTLogFile)
        self.csv_file.set(TTCSVFile)
        self.petal_controller.set(int(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(int(CanID))
        self.motor_type.set(Initial_Motor_Type)	# 0 for phi, 1 for theta
        self.Connect_Button_Text.set("Connect")
        self.Run_Button_Text.set("Apply Torque")
        self.progress_val.set(0)
        return;


    def initUI(self):
        self.parent.title(prog_name)

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
        self.button_LoadConf = Button(self.frame_hw_5, width=9, text="Load Config", command=self.load_config)
        self.button_SaveConf = Button(self.frame_hw_5, width=9, text="Save Config", command=self.save_config)
        self.button_Connect = Button(self.frame_hw_5, width=9)
        self.button_Connect["command"]=self.Connect_to_PC
        self.button_Connect["textvariable"]=self.Connect_Button_Text

        self.button_LoadConf.grid(column=0,row=0,sticky="w",padx=2,pady=2)
        self.button_SaveConf.grid(column=1,row=0,sticky="w",padx=2,pady=2)
        self.button_Connect.grid(column=2,row=0,sticky="e",padx=2,pady=2)

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
        self.label_Tstl = Label(self.frame_Tstl, text="Res Torque", width=11)
        self.label_Tstl.pack(side=LEFT, anchor=N, padx=5, pady=5)        
        self.entry_Tstl = Entry(self.frame_Tstl,
                          textvariable=self.settledTorque)
#       self.entry_Tstl["textvariable"]=self.settledTorque
        self.entry_Tstl.pack(fill=BOTH, pady=5, padx=5, expand=True)           

        self.progress = Progressbar(self.frame_tst, orient="horizontal", 
                                    length=200, mode="determinate", value=0, 
                                    variable=self.progress_val)
        self.progress.pack(fill=X,padx=5)

        self.frame_btn_run = Frame(self.frame_tst)
        self.frame_btn_run.pack(fill=X)
        self.button_Run = Button(self.frame_btn_run, width=16, state=DISABLED,
                          command=self.tt_state_machine,
                          textvariable=self.Run_Button_Text)
#       self.button_Run["command"]=self.tt_state_machine
#       self.button_Run["textvariable"]=self.Run_Button_Text
        self.button_Run.pack(padx=5,pady=2,side=RIGHT)
        
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
        logging.info(debug_msg)
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
        if(read_config(self.config_file.get())):
            return
        # Now set GUI values to be the same as the global values
        self.log_file.set(TTLogFile)
        self.csv_file.set(TTCSVFile)
        self.petal_controller.set(int(Petal_Controller_Number))
        self.canbus.set(CanBusID)
        self.canid.set(int(CanID))
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
        # Set globals to the values of their GUI counterparts
        TTConfFile=self.config_file.get()
        TTLogFile=self.log_file.get()
        TTCSVFile=self.csv_file.get()
        Petal_Controller_Number=int(self.petal_controller.get())
        CanBusID=self.canbus.get()
        CanID=int(self.canid.get())
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
        return

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
        if(Petal_Controller_Number!=int(self.petal_controller.get())):
            retval=1
        if(CanBusID!=self.canbus.get()):
            retval=1
        if(CanID!=int(self.canid.get())):
            retval=1
        if(Initial_Motor_Type!=self.motor_type.get()):	# 0 for phi, 1 for theta
            retval=1
        return retval;

    def Connect_to_PC(self):
        lPetal_Controller_Number=self.petal_controller.get()
        lCanBusID=self.canbus.get()
        lCanID=self.canid.get()
        self.pcomm=petalcomm.PetalComm(lPetal_Controller_Number)
        if(self.pcomm.is_connected()):
            print("Connected")
            print("CanBus=",lCanBusID)
            print("CanID =",lCanID)
            self.logprint("Connected")
            err,errmsg = self.check_MoveTable(Torque_Moves)
            if(err):
                messagebox.showerror(prog_name+' Error', errmsg)
                return
            if(4!=len(Currents)):
                messagebox.showerror(prog_name+' Error', 'Currents should be a list of 4 values!')
                return
            # enable button_Run here
            self.enable_Run_button()
        else:
            print("Not Connected")
            self.status_str.set("Not Connected")
        return


    def check_MoveTable(self,MoveTable):
        if(0==len(MoveTable)):
            return 1,"Empty MoveTable"
        prev_lenMT=5    # set to correct value
        for i in range(len(MoveTable)):
            lenMT=len(MoveTable[i])
            if(prev_lenMT!=lenMT):
                return 1,"Wrong length list: "+str(MoveTable[i])
            if('phi'!=MoveTable[i][iMotor] and 'theta'!=MoveTable[i][iMotor]):
                return 1,"Motor must be either 'phi' or 'theta': "+str(MoveTable[i][iMotor])
            if('creep'!=MoveTable[i][iMode] and 'cruise'!=MoveTable[i][iMode]):
                return 1,"Speed must be either 'creep' or 'cruise': "+str(MoveTable[i][iMode])
            if('ccw'!=MoveTable[i][iDirection] and 'cw'!=MoveTable[i][iDirection]):
                return 1,"Direction must be either 'cw' or 'ccw': "+str(MoveTable[i][iDirection])
            if(359<int(MoveTable[i][iAngle]) or 0>MoveTable[i][iAngle]):
                return 1,"Angle must be between 0 and 359"+str(MoveTable[i][iAngle])
            if(600<int(MoveTable[i][iCoolSecs]) or 0>MoveTable[i][iCoolSecs]):
                return 1,"Cool_down_seconds must be between 0 and 600"+str(MoveTable[i][iCoolSecs])
        return 0,"" # all is well

    def get_results(self):
        retval=0
        if(0.0 == self.maxTorque.get() or 0.0 == self.settledTorque.get()): # no value?
            messagebox.showerror(prog_name, 'Please enter both Maximum and Settled Torque values')
        else:
            if(""==str(self.motor_sn.get()) or ""==str(self.operator_name.get()) or 0.0==self.voltage.get()):
                messagebox.showerror(prog_name, 'Please enter Operator Name, Motor Serial Number, and Voltage')
            else:
                self.max_torque.append(self.maxTorque.get())
                self.res_torque.append(self.settledTorque.get())
                self.maxTorque.set(0.0)
                self.settledTorque.set(0.0)
                retval=1
        return retval

    def enable_Run_button(self):
        self.button_Run.config(state=NORMAL)
        self.Lrg_CCW_button.config(state=NORMAL)
        self.Med_CCW_button.config(state=NORMAL)
        self.Sml_CCW_button.config(state=NORMAL)
        self.Sml_CW_button.config(state=NORMAL)
        self.Med_CW_button.config(state=NORMAL)
        self.Lrg_CW_button.config(state=NORMAL)
        return

    def tt_state_machine(self):
        self.button_Run.config(state=DISABLED)
        if(0==self.tt_state):
            if(0 != self.move_count):   #   First must save the previous results
                if(0==self.get_results()):
                    self.enable_Run_button()
                    return
            self.wait_for_FIPOS_ready()
            self.tt_state+=1
        if(1==self.tt_state):
            self.set_FIPOS_currents()
            self.tt_state+=1
        if(2==self.tt_state):
            self.apply_FIPOS_torque(Torque_Moves)
            self.Run_Button_Text.set("Apply Next Torque")
            # apply_FIPOS_torque determines the next state
        if(3==self.tt_state):
            self.cool_down()
            # cool_down determines the next state
        if(4==self.tt_state):
            if(self.move_count < len(Torque_Moves)):
                self.tt_state=0    # wait for user to apply next torque in sequence
#               self.Run_Button_Text.set("Apply Torque")
            else:
                self.tt_state=5    # wait for user to save results
                self.Run_Button_Text.set("Save Results")
            self.button_Run.config(state=NORMAL)
            return
        if(5==self.tt_state):
            if(0==self.get_results()):
                self.button_Run.config(state=NORMAL)
                return
            self.save_results(Torque_Moves)
            # Reset indexes so user can run another test
            self.tt_state=0
            self.move_count=0
            self.max_torque=[]
            self.res_torque=[]
            self.maxTorque.set(0.0)
            self.settledTorque.set(0.0)
            self.motor_sn.set("")
            self.Run_Button_Text.set("Apply Torque")
            self.button_Run.config(state=NORMAL)
            answer=messagebox.askokcancel(prog_name, 'Do you want to test another motor?')
            if(False==answer):
                self.quit()
            return  # wait for user to run test again, or to quit

        self.parent.after(self.delay,self.tt_state_machine)
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

    def wait_for_FIPOS_ready(self):
        can_ids=[self.canbus.get()]
        can_bus_ids=[self.canid.get()]
        if(self.simulate):
            bool_val=True
        else:
            bool_val=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
        print("ready_for_tables returned "+str(bool_val))
        if(bool_val):
            self.tt_state+=1    # go to next state
        return

    def set_FIPOS_currents(self):
        can_ids=[self.canbus.get()]
        can_bus_ids=[self.canid.get()]
        lCanBusID=self.canbus.get()
        lCanID=self.canid.get()
        self.logprint("Setting current: CanBusID="+str(lCanBusID)+", CanID="+str(lCanID))
        if(self.simulate):
            bool_val=True
        else:
            self.pcomm.set_currents(can_bus_ids,can_ids,Currents,Currents)
        self.tt_state+=1        # go to next state
        return;

    def motor_type_to_str(self,motor_type):
        if(0==self.motor_type.get()):
          pt="Phi"
        else:
          pt="Theta"
        return pt

    def apply_FIPOS_torque(self,MoveTable):
        can_ids=[self.canbus.get()]
        can_bus_ids=[self.canid.get()]
        lCanBusID=self.canbus.get()
        lCanID=self.canid.get()
        i=self.move_count
        pt=self.motor_type_to_str(self.motor_type.get())
        if(i < len(MoveTable)):
            self.move_count+=1
            move_str="Moving: CanID="+str(lCanID)
            move_str+=" "+pt+" "+MoveTable[i][iDirection]
            move_str+=" "+str(MoveTable[i][iAngle])+" deg at "
            move_str+=str(MoveTable[i][iMode])
            self.logprint(move_str)
            if(self.simulate):
                error=0
            else:
                error = self.pcomm.move(can_bus_ids, can_ids,
                                        MoveTable[i][iDirection],
                                        MoveTable[i][iMode],
                                        pt,
                                        MoveTable[i][iAngle])
        if(self.move_count < len(MoveTable)):
            self.cool_countdown=MoveTable[i][iCoolSecs]
            self.progress["maximum"]=self.cool_countdown
            self.progress_val.set(self.cool_countdown)
            cool_msg="Waiting "+str(int(self.cool_countdown))+" seconds to cool down"
            self.logprint(cool_msg)
            self.status_str.set(cool_msg)
            self.tt_state+=1    # Wait for Cool Down
        else:
            self.tt_state+=2    # Wait for final values
        return

    def my_cruise(self,direction,angle):
        can_ids=[self.canbus.get()]
        can_bus_ids=[self.canid.get()]
        lCanBusID=self.canbus.get()
        lCanID=self.canid.get()
        pt=self.motor_type_to_str(self.motor_type.get())
        move_str="Moving: CanID="+str(lCanID)
        move_str+=" "+pt+" "+direction+" "+str(angle)+" deg at cruise"
        self.logprint(move_str)
        if(self.simulate):
            error=0
        else:
            error = self.pcomm.move(can_bus_ids, can_ids, direction, "cruise", pt, angle)
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

    def get_csv_header(self):
        header_str ="Time,"
        header_str+="Motor_SN,Operator,Test_Voltage,MotorType,Speed,Cooldown_Sec,"
        header_str+="Max_CCW_Torque_(oz-in),Max_CCW_Torque_(n-mm),"
        header_str+="Settled_CCW_Torque_(oz-in),Settled_CCW_Torque_(n-mm),"
        header_str+="Max_CW_Torque_(oz-in),Max_CW_Torque_(n-mm),"
        header_str+="Settled_CW_Torque_(oz-in),Settled_CW_Torque_(n-mm),"
        header_str+="Notes"
        return header_str

    def save_results(self,MoveTable):
        spreadsheet_str =str(self.motor_sn.get())+"," 		   # motor serial number
        spreadsheet_str+=str(self.operator_name.get())+","         # operator id
        spreadsheet_str+=str(self.voltage.get())+","               # test_voltage
        pt=self.motor_type_to_str(self.motor_type.get())
        spreadsheet_str+=pt+","                                    # phi or theta
        spreadsheet_str+=str(MoveTable[0][iMode])+","              # creep or cruise
        spreadsheet_str+=str(MoveTable[0][iCoolSecs])+","          # cooldown seconds
        if(str(MoveTable[0][iDirection]).lower()=='ccw'):
            spreadsheet_str+=str(self.max_torque[0])+","			# max ccw torque in oz-in
            spreadsheet_str+=str(format(float(self.max_torque[0])/n_mm_to_oz_in,'.3f'))+","	# max ccw torque in n-mm
            spreadsheet_str+=str(self.res_torque[0])+","			# settled ccw torque in oz-in
            spreadsheet_str+=str(format(float(self.res_torque[0])/n_mm_to_oz_in,'.3f'))+","	# settled ccw torque in n-mm
            spreadsheet_str+=str(self.max_torque[1])+","			# max cw torque in oz-in
            spreadsheet_str+=str(format(float(self.max_torque[1])/n_mm_to_oz_in,'.3f'))+","	# max cw torque in n-mm
            spreadsheet_str+=str(self.res_torque[1])+","			# settled cw torque in oz-in
            spreadsheet_str+=str(format(float(self.res_torque[1])/n_mm_to_oz_in,'.3f'))+","	# settled cw torque in n-mm
        else:
            spreadsheet_str+=str(self.max_torque[1])+","			# max ccw torque in oz-in
            spreadsheet_str+=str(format(float(self.max_torque[1])/n_mm_to_oz_in,'.3f'))+","	# max ccw torque in n-mm
            spreadsheet_str+=str(self.res_torque[1])+","			# settled ccw torque in oz-in
            spreadsheet_str+=str(format(float(self.res_torque[1])/n_mm_to_oz_in,'.3f'))+","	# settled ccw torque in n-mm
            spreadsheet_str+=str(self.max_torque[0])+","			# max cw torque in oz-in
            spreadsheet_str+=str(format(float(self.max_torque[0])/n_mm_to_oz_in,'.3f'))+","	# max cw torque in n-mm
            spreadsheet_str+=str(self.res_torque[0])+","			# settled cw torque in oz-in
            spreadsheet_str+=str(format(float(self.res_torque[0])/n_mm_to_oz_in,'.3f'))+","	# settled cw torque in n-mm
        spreadsheet_str+=str(self.user_notes.get())
        self.log(spreadsheet_str,which=1)
        self.logprint(spreadsheet_str)
        return


    def logfile(self,themessage,which):
        if(0==which):
            logf= open( TTLogFile, 'a' )
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
                self.save_config()
                ask_quit=False
        if(ask_quit):
            answer=messagebox.askokcancel(prog_name, 'Do you really want to quit?')
            if(answer):
                self.top_fr.destroy()	# destroy window
                self.parent.quit()
                exit()
        return

    def runGUI(self):
        self.parent.mainloop()
        return


def read_config(cfg_fname):
    global TTConfFile
    global TTLogFile
    global TTCSVFile
    global Petal_Controller_Number
    global CanBusID
    global CanID
    global Initial_Motor_Type
    retval=0	# success is assumed
    my_config = configobj.ConfigObj(cfg_fname,unrepr=True,encoding='utf-8')
    MotorType = my_config['MotorType']
    if('phi' == str(MotorType).lower()):
        Initial_Motor_Type=0
    else:
        if('theta' == str(MotorType).lower()):
            Initial_Motor_Type=1
        else:
            messagebox.showerror(prog_name, 'MotorType in config file is not "phi" or "theta":'+str(MotorType))
            retval=1
    if(0==retval):
        TTLogFile = my_config['Logfile']
        TTCSVFile = my_config['CSVfile']
        Petal_Controller_Number = int(my_config['Petal_Controller_Number'])
        CanBusID = my_config['CanBusID']
        CanID = int(my_config['CanID'])
        TTConfFile=cfg_fname
    return retval

def main(logging_level):
    root = Tk()
    TTConfFile = filedialog.askopenfilename(initialdir=pc.other_settings_directory, filetypes=(("Config file","*.conf"),("All Files","*")), title="Select Torque Test Config File")
    if(""==TTConfFile):
        root.messagebox.showerror(prog_name, 'Cannot run without a config file')
        self.parent.quit()
        sys.exit(0)
    if(read_config(TTConfFile)):
        root.quit()
        sys.exit(0)
    my_ttg = Torque_Test_GUI(root,logging_level)
    my_ttg.runGUI()
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

