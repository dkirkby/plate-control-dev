"""
============
Petal Build XY Test GUI
============
Author: P. Fagrelius
Date: June 18, 2019

This GUI is meant to help the XY Testing of positioners during the Petal 0 and Petal 1 buildup

It is expected that 10-15 positioners will be tested at a time.

To complete the XY test for these positioners, the following must be complete:
* The positioners, their CAN Bus and device location need to be identified and updated in the pos config file
* The hwsetup file needs to be update with positioners used for the test
* Initialization of the hwsetup needs to be complete, which identifies the fiducials and positioners and runs a calibration
* Then, the XY test can be complete
* At the end of the XY test, a grade will be give to each positioner.

Version History:
v1: June 18, 2019 PAF:  Intial version with pos conf, hwsetup file, init hwsetup, xytest, and grading. 

"""
import os
import sys
import numpy as np
import pandas as pd
import configobj
import tkinter
import tkinter.filedialog
import tkinter.messagebox
from tkinter import *
from configobj import ConfigObj
from datetime import datetime
import ptl_build_xytest as build

POS_SETTINGS_PATH = ('/home/msdos/focalplane/fp_settings/pos_settings/')
HWSETUP_PATH = ('/home/msdos/focalplane/fp_settings/hwsetups/')

class PtlTestGUI(object):
    def __init__(self, hwsetup_file='hwsetup_petal0_xytest.conf'):
        global gui_root
        self.hwsetup_file = hwsetup_file

        #Init the GUI
        gui_root = tkinter.Tk()
        self.logfile = 'PtlTestGUI.log'
        gui_root.title("Petal Build XY Test GUI")
        
        #Set Petal and PetalBox
        self.get_petal = Entry(gui_root, width=8, justify='right')
        self.get_petal.grid(row=0, column=0)
        self.get_petal.insert(0, 'PETAL')
        self.get_pc = Entry(gui_root, width=8, justify='right')
        self.get_pc.grid(row=1, column=0)
        self.get_pc.insert(0, 'PC')
        Button(gui_root, width=10, text='PETAL + PC', command=lambda: self.set_petal_no()).grid(row=0, column=1)

        #Set Scale
        self.scale_conf = ConfigObj('b141_scale.conf', unrepr=True, encoding='utf-8')
        self.scale = float(self.scale_conf['SCALE'])
        self.get_scale = Entry(gui_root, width=8, justify='right')
        self.get_scale.grid(row=0, column=2)
        self.get_scale.insert(0, str(self.scale))
        Button(gui_root, width=10, text='SCALE', command=lambda: self.update_scale()).grid(row=1, column=2)

        #Set svn username and call for password
        self.svnuser = None
        self.svnpass = None
        self.get_svnuser = Entry(gui_root, width=8, justify='right')
        self.get_svnuser.grid(row=0, column=3)
        Button(gui_root, width=10, text='SVN INFO', command=lambda: self.svn_info()).grid(row=1, column=3)

        #Entry for CAN, BUS, DEV      
        self.pos_info = {'CAN':[], 'BUS':[], 'DEV':[]}

        Label(gui_root, text='CAN ID (int)').grid(row=3, column = 0)
        self.get_canid = Entry(gui_root, width=8, justify='right')
        self.get_canid.grid(row=4, column=0)
        self.get_canid.insert(0, str('CAN ID')) 

        Label(gui_root, text='BUS ID (int)').grid(row=3, column=1)
        self.get_busid = Entry(gui_root, width=8, justify='right')
        self.get_busid.grid(row=4, column=1)
        self.get_busid.insert(0, str('BUS ID')) 

        Label(gui_root, text = 'DEV LOC (int)').grid(row=3, column=2)
        self.get_devloc = Entry(gui_root, width=8, justify='right')
        self.get_devloc.grid(row=4, column=2)
        self.get_devloc.insert(0, str('DEV LOC'))   

        Button(gui_root, width=10, text='ADD POS', command=lambda: self.get_pos()).grid(row=4, column=3)   

        #Write Pos .conf file
        Label(gui_root, text='Write CONF files').grid(row=1, column=4)
        Button(gui_root, width=10, text='POS Conf', command=lambda: self.pos_conf()).grid(row=2, column=4)
        Button(gui_root, width=10, text='HWSETUP', command=lambda: self.hwsetup_conf()).grid(row=3, column=4)

        #Run Tests
        Label(gui_root, text = 'Tests').grid(row=1, column=5)
        Button(gui_root, width=10, text='Init HW', command=lambda: self.run_init_hwsetup()).grid(row=2, column=5)
        Button(gui_root, width=10, text='GRID', command=lambda: self.run_grid()).grid(row=3, column=5)
        Button(gui_root, width=10, text='XYTEST', command=lambda: self.run_xytest()).grid(row=4, column=5)
        Button(gui_root, width=10, text='Get RESULTS', command=lambda: self.test_results()).grid(row=5, column=5)
     
        #Quit Button
        Button(gui_root, width=10, text='QUIT', command=lambda: self.quit()).grid(row=0, column=6)

        #Main print screen
        yscroll_main = Scrollbar(gui_root, orient=tkinter.VERTICAL)
        yscroll_main.grid(row=6, column=4, rowspan=20, sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.main=Text(gui_root, height=30, width=90, wrap=WORD)
        self.main.grid(row=6, column=1, columnspan=4, rowspan=20, sticky=W,pady=4, padx=15)
        self.main.configure(yscrollcommand=yscroll_main.set)
        self.main.tag_configure('bold_italics', font=('Arial', 12, 'bold', 'italic'))
        self.main.tag_configure('big', font=('Verdana', 12, 'bold','bold'))
        self.main.tag_configure('green', foreground='#476042', font=('Tempus Sans ITC', 12, 'bold'))
        self.main.tag_configure('red', foreground='#ff0000', font=('Tempus Sans ITC', 12, 'bold'))
        self.main.tag_configure('yellow', background='#ffff00', font=('Tempus Sans ITC', 12, 'bold'))
        yscroll_main.config(command=self.main.yview)

        #Positioner List Box
        self.listbox1 = Listbox(gui_root, width=15, height=15,selectmode='multiple',exportselection=0)
        self.listbox1.grid(row=6, column=0, rowspan=8, pady=4, padx=15)
        yscroll_listbox1 = Scrollbar(command=self.listbox1.yview, orient=tkinter.VERTICAL)
        yscroll_listbox1.grid(row=6, column=0, rowspan=10, sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.listbox1.configure(yscrollcommand=yscroll_listbox1.set)
        #self.listbox1.insert(tkinter.END,'ALL')
        Button(gui_root, width=10, text='REMOVE', command=lambda: self.remove_pos()).grid(row=15, column=0)

        #Logo Image 
        photo = PhotoImage(file='desi_logo.gif')
        photo=photo.subsample(7)
        label = Label(image=photo,width=20,height=100)
        label.image = photo # keep a reference!
        label.grid(row=16, column=0, columnspan=1, rowspan=20, sticky=W+E+N+S, padx=5, pady=5)
        
        mainloop()
        
    def set_petal_no(self):
        """
        Uses input for petal number and petal controller. These are necessary for running the tests.
        """
        try:
            self.petal = int(self.get_petal.get())
        except:
            self.main.insert(END, "Input an integer for the Petal number" +'\n')
         
        try:
            self.pc = int(self.get_pc.get())
        except:
            self.main.insert(END, "Input an integer for the Petal Controller number" +'\n')

        if (isinstance(self.petal,int)) and (isinstance(self.pc,int)):
            self.main.insert(END, "Testing to proceed with Petal #%d, PetalController PC%s \n" % (self.petal, str(self.pc).zfill(2))) 

    def update_scale(self):
        """
        Currently the scale needs to be measured independently and input here. The hwsetup file will be updated
        with whichever number is in the box. The scale numbers is saved in a conf file when updated. The last used
        scale number will be used if not updated.
        """
        try:
            self.scale = float(self.get_scale.get())
            self.scale_conf['SCALE'] = self.scale
            self.scale_conf.write()
            self.main.insert(END, "Scale resaved as %f \n" % self.scale)
        except:
            self.main.insert(END, "Input a float for the scale" +'\n')

    def get_pos(self):
        """
        Takes info from the inputs available and adds them to a list. 
        For a positioner to be added a CAN ID, BUS ID and device location must be entered.
        All values should be entered as int()
        """
        self.canid = self.get_canid.get()
        self.busid = self.get_busid.get()
        self.devloc = self.get_devloc.get()

        try:
            self.canid = int(self.canid)
            self.canid = 'M' + str(self.canid).zfill(5)
        except:
            self.main.insert(END, 'Need to input CAN ID as an integer'+'\n')
        try:
            self.busid = int(self.busid)
        except:
            self.main.insert(END, 'Need to input BUS ID as an integer'+'\n')
        try:
            self.devloc = int(self.devloc)
        except:
            self.main.insert(END, 'Need to input DEV LOC as an integer'+'\n')

        if (isinstance(self.canid, str)) and (isinstance(self.busid, int)) and (isinstance(self.devloc, int)):
            self.pos_info['CAN'].append(self.canid)
            self.pos_info['BUS'].append(self.busid)
            self.pos_info['DEV'].append(self.devloc)
            self.print_pos_info()

        else:
            return

    def print_pos_info(self):
        """
        Shows the list of positioners input. This will be updated any time a positioner is added or removed.
        """
        self.listbox1.delete(0, tkinter.END)
        this_pos_info = np.asarray([self.pos_info['CAN'], self.pos_info['BUS'], self.pos_info['DEV']]).T
        #self.listbox1.insert(tkinter.END,'ALL')
        self.listbox1.insert(tkinter.END, 'CAN BUS DEV')
        for pos in this_pos_info:
            self.listbox1.insert(tkinter.END, pos)

    def pos_conf(self):
        """
        This reads the list of positioners and updates their pos configuration files
        """
        df = pd.DataFrame.from_dict(self.pos_info)
        df.to_csv('pos_list.csv',index=False)
        
        self.write_pos_conf()
        

    def hwsetup_conf(self):
        """
        This reads the list of positioners and calls the function to update the hwsetup file with that list
        """
        df = pd.DataFrame.from_dict(self.pos_info)
        df.to_csv('pos_list.csv',index=False)

        self.write_hwsetup_conf()


    def write_pos_conf(self):
        """
        Updates the positioner configuration file with the petal,  device location and bus id
        """
        pos_list = pd.read_csv('pos_list.csv', header=0)
        pos_list = pos_list.to_records(index=False)
        for line in pos_list:
            pos = str(line['CAN']) # str('M' + str(line['CAN']).zfill(5))
            try:
                file_name = POS_SETTINGS_PATH+'unit_%s.conf'%pos
                config = ConfigObj(file_name, unrepr=True, encoding='utf-8')
                bus = line['BUS']
                busid = 'can'+str(bus)
                config['BUS_ID'] = str(busid)
                config['DEVICE_LOC'] = int(line['DEV'])
                config['PETAL_ID'] = int(self.petal)
                config.write()
                self.main.insert(END, "Wrote config file for %s \n" % pos)
            except:
                self.main.insert(END, "Something went wrong with device %s \n "%pos)
        self.main.insert(END, "Done writing POS Conf files \n")

    def write_hwsetup_conf(self):
        """
        Updates the hwsetup file with the new list of positioners, the scale, ptal numer, and time of update
        """
        pos_list = pd.read_csv('pos_list.csv', header=0)
        pos_list = pos_list.to_records(index=False)
        self.main.insert(END, "Will update this hwsetup file: %s \n " % HWSETUP_PATH+self.hwsetup_file)
        hwconfig = ConfigObj(HWSETUP_PATH+self.hwsetup_file, unrepr=True, encoding='utf-8')
        pos_ids = [str(line['CAN']) for line in pos_list]
        time_now = str(datetime.now())
        hwconfig['scale'] = float(self.scale)
        hwconfig['pos_ids'] = pos_ids
        hwconfig['last_updated'] = time_now
        hwconfig['ptl_id'] = int(str(self.petal).zfill(2))
        hwconfig.write()
        self.main.insert(END,"hwsetup file updated with these positioners: \n")
        for pos in pos_ids:
            self.main.insert(END,pos+'\n')

    def check_svn(self):
        """
        Checks if svn credentials have been input before allowing you to proceed. This is not currently used.
        """
        if (self.svnuser is None) | (self.svnpass is None):
            self.main.insert(END, "You must enter your SVN credentials before proceeding"+'\n')


    def svn_info(self):
        """
        When you input your user name, this function will have a popup ask you for your password and check that it is 
        correct
        """
        try:
            self.svnuser = str(self.get_svnuser.get())
            self.svnpass = tkinter.simpledialog.askstring(title='SVN authentication', prompt='svn password:', show="*")
            err = os.system('svn --username ' + self.svnuser + ' --password ' + self.svnpass + ' --non-interactive list')
            if err == 0:
                pass
            else:
                self.main.insert(END, "Something wrong with the SVN credentials"+'\n')
        except:
            self.main.insert(END, "Please put in your SVN credentials"+'\n')


    def run_init_hwsetup(self):
        self.main.insert(END, "You selected to run the Initialize HWSetup. This will identify positioners and run calibration \n")
        test = build.InitHwSetup(self.svnuser, self.svnpass)
        test.init_hwsetup()

    def run_xytest(self):
        self.main.insert(END, "You selected to run the XYTest \n")
        test = build.XYTest(self.svnuser, self.svnpass)
        test.run()

    def run_grid(self):
        self.main.insert(END, "You selected to run a Grid calibration \n")
        test = build.XYTest(self.svnuser, self.svnpass, opt = 'grid')
        test.run()

    def test_results(self):
        """
        This function reads the most recent summary files from XY tests and then gives a grade for 
        each positioner in the hwsetup file. This can be called even if a list of positioners isn't
        on the GUI
        """
        if len(self.pos_info['CAN']) == 0:
            hwconfig = ConfigObj(HWSETUP_PATH+self.hwsetup_file, unrepr=True, encoding='utf-8')
            pos_list = hwconfig['pos_ids']
        else:
            pos_list = self.pos_info['CAN']

        Data = {}
        for pos in pos_list:
            try:
                self.main.insert(END, "Getting data for positioner %s \n" % pos)
                filen = "/home/msdos/focalplane/positioner_logs/xytest_summaries/%s_summary.csv" % pos
                df = pd.read_csv(filen)
                d = df.iloc[[-1]]
                Data[pos] = d
            except:
                self.main.insert(END, "Didnt have a summary file for %s \n" % pos)
        Grades = {}
        for pos, df in Data.items():
            rms_corr = float(df['corr rms (um) all targets with 5.0 um threshold'])
            max_corr = float(df['corr max (um) all targets with 5.0 um threshold'])
            max_blind = float(df['blind max (um) all targets'])
            max_corr_95 = float(df['corr max (um) best 95% with 5.0 um threshold'])
            rms_corr_95 = float(df['corr rms (um) best 95% with 5.0 um threshold'])

            grade = self.grade_pos(max_blind, max_corr, rms_corr, max_corr_95, rms_corr_95)
            Grades[pos] = grade

        self.main.insert(END, "Here are the final grades for each positioner in the last test: \n") 
        for pos, grade in Grades.items():
            self.main.insert(END, "%s: %s \n" % (pos, grade))
       

    def grade_pos(self,max_blind, max_corr, rms_corr, max_corr_95, rms_corr_95):
        """
        Gives grade to a positioner based on its XY Test performance according to DESI-XXXX
        """
        if (max_blind <= 100) & (max_corr <=15) & (rms_corr <=5):
            grade = 'A'
        elif (max_blind <= 250) & (max_corr <=25) & (max_corr_95 <=15) & (rms_corr <=10) & (rms_corr <=5):
            grade = 'B'
        elif (max_blind <= 250) & (max_corr <=50) & (max_corr_95 <=25) & (rms_corr <=20) & (rms_corr <=10):
            grade = 'C'
        elif (max_blind <= 500) & (max_corr <=50) & (max_corr_95 <=25) & (rms_corr <=20) & (rms_corr <=10):
            grade = 'D'
        else:
            grade = 'F'
        
        return grade
 
    def quit(self):
        sys.exit()

    def remove_pos(self):
        """
        Remove positioner from the list and return an updated list
        """ 
        index = self.listbox1.curselection()
        if len(index) == 0:
            self.main.insert(END, "You haven't selected any positioners to remove")
            return

        selected = []
        for i in range(len(index)):
            selected.append(self.listbox1.get(index[i]))

        remove_these_pos = [str(s[2:8]) for s in selected]
        self.main.insert(END, "You have selected to remove the following positioners: \n")
        for pos in remove_these_pos:
            self.main.insert(END, pos + '\n')
        for pos in remove_these_pos:
            idx = np.where(np.array(self.pos_info['CAN']) == str(pos))
            del self.pos_info['CAN'][idx[0][0]]
            del self.pos_info['BUS'][idx[0][0]]
            del self.pos_info['DEV'][idx[0][0]]
        self.print_pos_info()

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
        self.main.insert(END,str(len(self.info.keys())).strip()+' Pos+Fid are found \n')
        for key in sorted(self.info.keys()):
            self.main.insert(END,str(key)+' '+str(self.info[key])+'\n')
        
        
    def logwrite(self,text,stdout=True):
        """Standard logging function for writing to the test traveler log file.
        """
        line = '# ' + pc.timestamp_str_now() + ': ' + text
        with open(self.logfile,'a') as fh:
            fh.write(line + '\n')
        if stdout:
            self.main.insert(END,line)


if __name__ == "__main__":
    gui = PtlTestGUI()
