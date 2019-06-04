"""
MoveGUI

"""
import os
import sys
import datetime
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../../../positioner_logs/data_processing_scripts/'))
sys.path.append(os.path.abspath(os.getenv('HOME')+'/focalplane/positioner_logs/data_processing_scripts/'))
sys.path.append(os.path.abspath(os.getenv('HOME')+'/focalplane/pos_utility/'))
#sys.path.remove('/software/products/plate_control-trunk/xytest')
#sys.path.remove('/software/products/plate_control-trunk/posfidfvc')
#sys.path.remove('/software/products/plate_control-trunk/petalbox')
#sys.path.remove('/software/products/plate_control-trunk/petal')

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
import time
import show_detected
import pdb
import write_conf_files as wc

class PtlTestGUI(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
        global gui_root
        gui_root = tkinter.Tk()

        w=200
        h=100
        ws=gui_root.winfo_screenwidth()
        hs=gui_root.winfo_screenheight()
        x=(ws/2)-(w/2)
        y=(hs/2)-(h/2)
        gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))

        self.e1=Entry(gui_root,width=5)
        self.e1.grid(row=0,column=1)
        Label(gui_root,text="Petal ID:").grid(row=0)
        self.e_can=Entry(gui_root,width=5)
        self.e_can.grid(row=1,column=1)
        self.e_can.insert(0,'0')
        Label(gui_root,text="Petal ID:").grid(row=0)
        Button(gui_root,text='OK',width=10,command=self.set_ptl_id).grid(row=1,column=2,sticky=W,pady=4)

        
        mainloop()

        gui_root = tkinter.Tk()
        self.logfile='PtlTestGUI.log'
        self.fvc_type='simulator'
        self.fidids=['F021']   
        gui_root.title='Petal Build GUI'
        self.pcomm=petalcomm.PetalComm(self.ptl_id)
        self.mode = 0
        #petalcomm.
   #     info=self.petalcomm.get_device_status()
        canbus=self.canbus
        self.bus_id=canbus
        #self.info = self.pcomm.get_posfid_info(canbus)
        info_temp=self.pcomm.pbget('posfid_info')
        if isinstance(info_temp, (list,)):
            self.info = self.pcomm.pbget('posfid_info')[0]
        else:
            self.info=self.pcomm.pbget('posfid_info')[canbus]
        print(self.info)
        self.posids = []
        for key in sorted(self.info.keys()):
            if len(str(key))==2:
                self.posids.append('M000'+str(key)) 
            elif len(str(key))==3:
                self.posids.append('M00'+str(key))
            elif len(str(key))==4:
                self.posids.append('M0'+str(key))
            elif len(str(key))==5:
                self.posids.append('M'+str(key))
        print(self.posids)
        self.ptl = petal.Petal(self.ptl_id, self.posids, self.fidids, simulator_on=self.simulate, printfunc=self.logwrite,user_interactions_enabled=True)
        print('Finish loading petal')

        for posid in self.ptl.posids:
            self.ptl.set_posfid_val(posid, 'CTRL_ENABLED', True)
            self.ptl.set_posfid_val(posid, 'BUS_ID', self.canbus)
        self.fvc = fvchandler.FVCHandler(self.fvc_type,printfunc=self.logwrite,save_sbig_fits=False)               
        self.m = posmovemeasure.PosMoveMeasure([self.ptl],self.fvc,printfunc=self.logwrite)
        
# GUI input       
        w=1600
        h=700
        ws=gui_root.winfo_screenwidth()
        hs=gui_root.winfo_screenheight()
        x=(ws/2)-(w/2)
        y=(hs/2)-(h/2)
        gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))
        
        Button(gui_root,text='Set',width=10,command=self.set_fiducial).grid(row=0,column=4,sticky=W,pady=4)
        
        Label(gui_root,text="Rotation Angel").grid(row=0,column=0)
        self.e1=Entry(gui_root)
        self.e1.grid(row=0,column=1)
        self.e1.insert(0,'50')
        
        Label(gui_root,text="Set Fiducial").grid(row=0,column=2)
        self.e2=Entry(gui_root)
        self.e2.grid(row=0,column=3)

        self.e_can=Entry(gui_root,width=10)
        self.e_can.grid(row=5,column=0,sticky=E)
        self.e_can.insert(0,self.canbus.strip('can'))
        Label(gui_root,text="CAN Bus:").grid(row=5,column=0,sticky=W,padx=10)

        Button(gui_root,text='Theta CW',width=10,command=self.theta_cw_degree).grid(row=3,column=1,sticky=W,pady=4)
        Button(gui_root,text='Theta CCW',width=10,command=self.theta_ccw_degree).grid(row=4,column=1,sticky=W,pady=4)
        self.mode=IntVar(gui_root)
        self.mode.set(1)
        Checkbutton(gui_root, text='CAN', variable=self.mode).grid(row=3,column=1,sticky=E,pady=4)
        self.syncmode=IntVar(gui_root)
        self.sync_mode_value=self.ptl.sync_mode
        if self.ptl.sync_mode == 'hard':
            self.syncmode.set(1)
        else:
            self.syncmode.set(0)
        Checkbutton(gui_root, text='SYNC hard', variable=self.syncmode,command=self.sync_mode).grid(row=3,column=2,sticky=W,pady=4)

        Button(gui_root,text='Phi CW',width=10,command=self.phi_cw_degree).grid(row=3,column=0,sticky=W,pady=4)
        Button(gui_root,text='Phi CCW',width=10,command=self.phi_ccw_degree).grid(row=4,column=0,sticky=W,pady=4)
        Button(gui_root,text='Show INFO',width=10,command=self.show_info).grid(row=5,column=2,sticky=W,pady=4)
        Button(gui_root,text='Reload CANBus',width=12,command=self.reload_canbus).grid(row=5,column=1,sticky=W,pady=4)
        Button(gui_root,text='1 Write SiID',width=15,command=self.write_siid).grid(row=3,column=3,sticky=W,pady=4)
        #Button(gui_root,text='Sync Test',width=15,command=self.sync_test).grid(row=3,column=4,sticky=W,pady=4)
        Button(gui_root,text='Movement Check',width=15,command=self.movement_check).grid(row=4,column=4,sticky=W,pady=4)
        Button(gui_root,text='3 Populate Busids',width=15,command=self.populate_can).grid(row=5,column=3,sticky=W,pady=4)# Call populate_busids.py under pos_utility/ 
        Button(gui_root,text='2 Write DEVICE_LOC',width=15,command=self.populate_petal_travelers).grid(row=4,column=3,sticky=W,pady=4)# Call populate_travellers.py under pos_utility/ to read from installation traveler and write to positioner 'database' and ID map
        Button(gui_root,text='Aliveness Test',width=10,command=self.aliveness_test).grid(row=4,column=5,sticky=W,pady=4)# Call show_detected.py under pos_utility/ to do aliveness test.

        Button(gui_root,text='Center',width=10,command=self.center).grid(row=4,column=2,sticky=W,pady=4)                

        yscroll_text1 = Scrollbar(gui_root, orient=tkinter.VERTICAL)
        yscroll_text1.grid(row=6, column=4, rowspan=20,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.text1=Text(gui_root,height=30,width=90,wrap=WORD)
        self.text1.grid(row=6,column=1,columnspan=4,rowspan=20,sticky=W,pady=4,padx=15)
        self.text1.configure(yscrollcommand=yscroll_text1.set)
        self.text1.tag_configure('bold_italics', font=('Arial', 12, 'bold', 'italic'))
        self.text1.tag_configure('big', font=('Verdana', 12, 'bold','bold'))
        self.text1.tag_configure('green', foreground='#476042', font=('Tempus Sans ITC', 12, 'bold'))
        self.text1.tag_configure('red', foreground='#ff0000', font=('Tempus Sans ITC', 12, 'bold'))
        self.text1.tag_configure('yellow', background='#ffff00', font=('Tempus Sans ITC', 12, 'bold'))
        yscroll_text1.config(command=self.text1.yview)

        self.listbox1 = Listbox(gui_root, width=20, height=20,selectmode='multiple',exportselection=0)
        self.listbox1.grid(row=6, column=0,rowspan=10,pady=4,padx=15)
        # create a vertical scrollbar to the right of the listbox
        yscroll_listbox1 = Scrollbar(command=self.listbox1.yview, orient=tkinter.VERTICAL)
        yscroll_listbox1.grid(row=6, column=0, rowspan=10,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.listbox1.configure(yscrollcommand=yscroll_listbox1.set)
        self.listbox1.insert(tkinter.END,'ALL')
        
        for key in sorted(self.info.keys()):
            if len(str(key))==2:
                self.listbox1.insert(tkinter.END,'M000'+str(key)) 
            elif len(str(key))==3:
                self.listbox1.insert(tkinter.END,'M00'+str(key))
            elif len(str(key))==4:
                self.listbox1.insert(tkinter.END,'M0'+str(key))
            elif len(str(key))==5:
                self.listbox1.insert(tkinter.END,'M'+str(key))
            # FW version check
            if float(self.info[key][0]) < 4.3:
                self.text1.insert(END,str(key)+' has too low a FW ver = '+self.info[key][0]+', BL ver = '+self.info[key][1]+'! Hand it to Jessica. \n','red')

        self.listbox1.bind('<ButtonRelease-1>', self.get_list)


# Right part of the GUI to write to Acceptance Traveller

#       Load the information 
        Label(gui_root,text="You selected").grid(row=3,column=5)
        self.e_selected=Entry(gui_root)
        self.e_selected.grid(row=3,column=6)
        
        yscroll_text2 = Scrollbar(gui_root, orient=tkinter.VERTICAL)
        yscroll_text2.grid(row=6, column=6, rowspan=20,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)     
        self.text2=Text(gui_root,height=30,width=38)
        self.text2.grid(row=6,column=5,columnspan=2,rowspan=20,sticky=W+E+N+S,pady=4,padx=15)
        self.text2.tag_configure('bold_italics', font=('Arial', 12, 'bold', 'italic'))
        self.text2.tag_configure('big', font=('Verdana', 12, 'bold','bold'))
        self.text2.tag_configure('green', foreground='#476042', font=('Tempus Sans ITC', 12, 'bold'))
        self.text2.tag_configure('red', foreground='#ff0000', font=('Tempus Sans ITC', 12, 'bold'))
        self.text2.tag_configure('yellow', background='#ffff00', font=('Tempus Sans ITC', 12, 'bold'))
        self.text2.configure(yscrollcommand=yscroll_text2.set)   
        yscroll_text2.config(command=self.text2.yview)
        

##      checkboxes
        
        self.theta_work=IntVar(gui_root)
        self.phi_work=IntVar(gui_root)
        self.centered=IntVar(gui_root)
        self.theta_work.set(1)
        self.phi_work.set(1)
        self.centered.set(0) 
        column_entry=7
        Checkbutton(gui_root, text='Theta Work?', variable=self.theta_work).grid(row=5,column=column_entry,sticky=W,pady=4)
        Checkbutton(gui_root, text='Phi Work?', variable=self.phi_work).grid(row=6,column=column_entry,sticky=W,pady=4)
        Checkbutton(gui_root, text='Centered?', variable=self.centered).grid(row=7,column=column_entry,sticky=W,pady=4)
 
        #Label(gui_root,text="Note").grid(row=8,column=column_entry)
        #self.e3=Entry(gui_root)
        #self.e3.grid(row=8,column=column_entry+1)
        Label(gui_root,text="Send PFA Date").grid(row=9,column=column_entry)
        self.e4=Entry(gui_root)
        self.e4.insert(END,'{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
        self.e4.grid(row=9,column=column_entry+1)
        #Label(gui_root,text="Send PFA Name").grid(row=10,column=column_entry)
        #self.e5=Entry(gui_root)
        #self.e5.grid(row=10,column=column_entry+1)
        #Label(gui_root,text="Tote").grid(row=11,column=column_entry)
        #self.box_options = [    "GREY TOTE\n---------\nREADY FOR PFA INSTALL",    "GREY TOTE\n---------\nINCOMING INSPECTION IN PROGRESS",    "LARGE TOTE\n--------\nFAIL REVIEW LATER", "LARGE TOTE\n--------\nFAIL PERMANENT"]
        #self.box_goto = StringVar(gui_root)
        #self.box_goto.set("Where will you put me?") # default value
        #self.drop1 = OptionMenu(gui_root, self.box_goto, *self.box_options)
        #self.drop1.grid(row=11,column=column_entry+1)

        Label(gui_root,text="Your init").grid(row=12,column=column_entry)
        self.e6=Entry(gui_root)
        self.e6.grid(row=12,column=column_entry+1)
        

        
#        Button(gui_root,text='Plot List',width=10,command=click_plot_list).grid(row=4,column=2,sticky=W,pady=4)
        Button(gui_root,text='Refresh/Restart',width=15,command=self.restart).grid(row=0,column=8,sticky=W,pady=4)
        self.pwr_button = Button(gui_root,text='POSPWR is ON', width=15, command=self.toggle, bg='green')
        self.pwr_button.grid(row=1, column=8, sticky=W,pady=4)

        Button(gui_root,text='Clear',width=15,command=self.clear1).grid(row=5,column=4,sticky=W,pady=4)
        Button(gui_root,text='Clear',width=15,command=self.clear2).grid(row=5,column=6,sticky=W,pady=4)
        
        photo = PhotoImage(file='desi_logo.gif')
        photo=photo.subsample(7)
        label = Label(image=photo,width=20,height=100)
        label.image = photo # keep a reference!
        label.grid(row=16, column=0, columnspan=1, rowspan=20,sticky=W+E+N+S, padx=5, pady=5)
        

        mainloop()
        
    def set_ptl_id(self):
        self.ptl_id=self.e1.get()
        self.canbus='can'+self.e_can.get().strip()        
        print('Loading Petal'+self.ptl_id+', canbus:'+self.canbus)
        gui_root.destroy()

 
    def get_list(self,event):
        # get selected line index
        index = self.listbox1.curselection()
        # get the line's text
        self.selected=[]
        self.selected_posid=[]
        self.selected_can=[]
        for i in range(len(index)):
            self.selected.append(self.listbox1.get(index[i]))
            if 'ALL' in self.selected:
                self.selected_posid=self.posids
                self.selected_can=[20000]
            else:
                self.selected_posid.append(self.selected[i])
                self.selected_can.append(int(str(self.selected[i][1:6])))
        self.e_selected.delete(0,END)
        self.e_selected.insert(0,str(self.selected_can))

            
    def show_info(self):
        self.text1.insert(END,str(len(self.info.keys())).strip()+' Pos+Fid are found \n')
        for key in sorted(self.info.keys()):
            self.text1.insert(END,str(key)+' '+str(self.info[key])+'\n')
        

        
    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.logfile,'a') as fh:
            fh.write(line + '\n')
        if stdout:
            print(line)





if __name__=="__main__":
    gui = MoveGUI()
