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
from configobj import ConfigObj
import write_conf_files as wc

class PtlTestGUI(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
        global gui_root

        gui_root = tkinter.Tk()
        self.logfile='PtlTestGUI.log'
        self.mode = 0

        # GUI geometry       
        w=800
        h=700
        ws=gui_root.winfo_screenwidth()
        hs=gui_root.winfo_screenheight()
        x=(ws/2)-(w/2)
        y=(hs/2)-(h/2)
        gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))
        
        #Set Petal and PetalBox
        self.get_petal = Entry(gui_root, width = 8, justify = 'right')
        self.get_petal.grid(row=0, column=0)
        self.get_petal.insert(0, 'PETAL')
        self.get_pc = Entry(gui_root, width = 8, justify = 'right')
        self.get_pc.grid(row=1, column=0)
        self.get_pc.insert(0, 'PC')
        Button(gui_root, width = 10, text = 'PETAL + PC', command=lambda: self.set_peta_no()).grid(row=0, column=1)

        #Set Scale

        self.e2=Entry(gui_root)
        self.e2.grid(row=0,column=3)

        self.e_can=Entry(gui_root,width=10)
        self.e_can.grid(row=5,column=0,sticky=E)
        Label(gui_root,text="CAN Bus:").grid(row=5,column=0,sticky=W,padx=10)

        Button(gui_root,text='Theta CW',width=10).grid(row=3,column=1,sticky=W,pady=4)
        Button(gui_root,text='Theta CCW',width=10).grid(row=4,column=1,sticky=W,pady=4)
        self.mode=IntVar(gui_root)
        self.mode.set(1)
        Checkbutton(gui_root, text='CAN', variable=self.mode).grid(row=3,column=1,sticky=E,pady=4)
        self.syncmode=IntVar(gui_root)
        Button(gui_root,text='Reload CANBus',width=12).grid(row=5,column=1,sticky=W,pady=4)
        Button(gui_root,text='1 Write SiID',width=15).grid(row=3,column=3,sticky=W,pady=4)
        #Button(gui_root,text='Sync Test',width=15,command=self.sync_test).grid(row=3,column=4,sticky=W,pady=4)
        Button(gui_root,text='Movement Check',width=15).grid(row=4,column=4,sticky=W,pady=4)
        Button(gui_root,text='3 Populate Busids',width=15).grid(row=5,column=3,sticky=W,pady=4)# Call populate_busids.py under pos_utility/ 
        Button(gui_root,text='2 Write DEVICE_LOC',width=15).grid(row=4,column=3,sticky=W,pady=4)# Call populate_travellers.py under pos_utility/ to read from installation traveler and write to positioner 'database' and ID map
        Button(gui_root,text='Aliveness Test',width=10).grid(row=4,column=5,sticky=W,pady=4)# Call show_detected.py under pos_utility/ to do aliveness test.

        Button(gui_root,text='Center',width=10).grid(row=4,column=2,sticky=W,pady=4)                

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
        column_entry = 7 
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
 
    def set_petal_no(self):
        try:
            self.petal = int(self.get_petal.get())
        except:
            print("Input an integer for the Petal number")
         
        try:
            self.pc = int(self.get_pc.get())
        except:
            print("Input an integer for the Petal Controller number")

 
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
    gui =  PtlTestGUI()
