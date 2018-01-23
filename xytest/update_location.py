"""
update_location.py

#A GUI to update positioner locations in Travellers.
# History: V1.0   Kai Zhang @LBNL  2018-01-05   Contact: zkdtckk@gmail.com
# Implemented on Beyonce on 2017-10-17, just change the data_processing_scripts relative location to work. 


"""
import os
import sys
import datetime
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../../positioner_logs/data_processing_scripts/'))
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


class Update_Location(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
        global gui_root
        gui_root = tkinter.Tk()
        

        # Load Travellers
        url1='https://docs.google.com/spreadsheets/d/1lJ9GjhUUsK2SIvXeerpGW7664OFKQWAlPqpgxgevvl8/edit#gid=0' # PosID, SiID database
        self.sheet1=googlesheets.connect_by_url(url1,credentials = '../../positioner_logs/data_processing_scripts/google_access_account.json')
     
        url2='https://docs.google.com/spreadsheets/d/19Aq-28qgODaaX9wH-NMsX_GiuNyXG_6rjIjPVLb8aYw/edit#gid=795996596' # Acceptance Traveller
        self.sheet2=googlesheets.connect_by_url(url2,credentials = '../../positioner_logs/data_processing_scripts/google_access_account.json')

        url3='https://docs.google.com/spreadsheets/d/1LDH-YTH3_d0EZX_DgvkUFZKj9_fAauDjfeW79V2N-Hk/edit#gid=754786657' 
        self.positionerLocDatabase = googlesheets.connect_by_url(url3,credentials = '../../positioner_logs/data_processing_scripts/google_access_account.json')       
        self.existingPositionerIDs = googlesheets.read_col(self.positionerLocDatabase, 3, ID_col_with_data = False)
        self.simulate = False
        self.logfile='Update_Location.log'
        fvc_type='simulator'
        fidids=['F021']   
        gui_root.title='Update Location'
        self.mode = 0
        canbus='can0'
        self.bus_id=canbus
        self.posids = []
        
# GUI input       
        w=1200
        h=500
        ws=gui_root.winfo_screenwidth()
        hs=gui_root.winfo_screenheight()
        x=(ws/2)-(w/2)
        y=(hs/2)-(h/2)
        gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))
        
        column_entry=0 
        row_entry=1

        Label(gui_root,text="Tech Name Init").grid(row=row_entry,column=column_entry)
        self.e1=Entry(gui_root)
        self.e1.grid(row=row_entry,column=column_entry+1)
        Label(gui_root,text="Petal # Installed").grid(row=row_entry+1,column=column_entry)
        self.e2=Entry(gui_root)
        self.e2.grid(row=row_entry+1,column=column_entry+1)
        Label(gui_root,text="Time Stamp").grid(row=row_entry+2,column=column_entry)
        self.e3=Entry(gui_root)
        self.e3.insert(END,'{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
        self.e3.grid(row=row_entry+2,column=column_entry+1)
        Label(gui_root,text="PosID").grid(row=row_entry+3,column=column_entry)
        self.e4=Entry(gui_root)
        self.e4.grid(row=row_entry+3,column=column_entry+1)
        Label(gui_root,text="Previous PosID").grid(row=row_entry+4,column=column_entry)
        self.e5=Entry(gui_root)
        self.e5.grid(row=row_entry+4,column=column_entry+1)
        

        yscroll_text1 = Scrollbar(gui_root, orient=tkinter.VERTICAL)
        yscroll_text1.grid(row=6, column=4, rowspan=20,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.text1=Text(gui_root,height=30,width=90,wrap=WORD)
        self.text1.grid(row=1,column=3,columnspan=4,rowspan=20,sticky=W,pady=4,padx=15)
        self.text1.configure(yscrollcommand=yscroll_text1.set)
        yscroll_text1.config(command=self.text1.yview)

        
#        Button(gui_root,text='Plot List',width=10,command=click_plot_list).grid(row=4,column=2,sticky=W,pady=4)
        Button(gui_root,text='Refresh/Restart',width=15,command=self.restart).grid(row=0,column=8,sticky=W,pady=4)
        Button(gui_root,text='Write Traveller',width=20,command=self.write_traveller).grid(row=row_entry+5,column=column_entry,sticky=W,pady=4)
        
        photo = PhotoImage(file='desi_logo.gif')
        photo=photo.subsample(8)
        label = Label(image=photo,width=20,height=100)
        label.image = photo # keep a reference!
        label.grid(row=16, column=0, columnspan=1, rowspan=20,sticky=W+E+N+S, padx=5, pady=5)
        

        mainloop()
        
        
    def posidnum_to_posid(self,posidnum):
        if len(str(posidnum))==2:
            str_out='M000'+str(posidnum)
        elif len(str(posidnum))==3:
            str_out='M00'+str(posidnum)
        elif len(str(posidnum))==4:
            str_out='M0'+str(posidnum)
        elif len(str(posidnum))==5:
            str_out='M'+str(posidnum)
        return str_out

    def write_traveller(self):
        initials=self.e1.get()
        positionerLocation='Petal '+str(int(self.e2.get()))+' (77-141A)'
        self.e3.delete(0, END)
        self.e3.insert(END,'{:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
        posid_input=self.e4.get()
        self.posidnum=posid_input.upper().lstrip('M').lstrip('0')
        self.posid=self.posidnum_to_posid(self.posidnum)
        self.e4.delete(0,END)
        self.e5.delete(0,END)
        self.e5.insert(0,str(self.posidnum))

        # Find the column we want first
        indices = [i for i, x in enumerate([y.strip() for y in self.existingPositionerIDs]) if x == str(self.posidnum).strip()]
        if len(indices) > 1:
#            self.text1.delete('0.0', END)
            self.text1.insert('0.0','There are duplicates of this positioner in the database! Please set the positioner aside and alert Todd or Jessica!\n')
        elif len(indices) == 0:
#            self.text1.delete('0.0', END)
            self.text1.insert('0.0','This positioner is not already in the database! Please set the positioner aside and alert Todd or Jessica!\n')
        else:
            index = indices[0] + 1
            colID1 = 1
            colID2 = 5
            toWriteDatabase = [initials, str(self.e3.get()), str(self.posidnum), 'LBNL', positionerLocation]
            googlesheets.write_row_range(self.positionerLocDatabase, index, colID1, colID2, toWriteDatabase)
#            self.text1.delete('0.0', END)
            self.text1.insert('0.0','The Current Location of '+self.posid+' is '+positionerLocation+'\n')
    
    
    def restart(self):
        gui_root.destroy()
        MoveGUI()
    def clear1(self):
        self.text1.delete('0.0', END)
    def clear2(self):
        self.text2.delete('0.0', END)
        
    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.logfile,'a') as fh:
            fh.write(line + '\n')
        if stdout:
            print(line)
            
if __name__=="__main__":
    gui = Update_Location()
