import os
import sys
sys.path.append(os.path.abspath('../petal/'))
sys.path.append(os.path.abspath('../posfidfvc/'))
sys.path.append(os.path.abspath('../xytest/'))

import petal
import posmovemeasure
import fvchandler
import posconstants as pc
import instrmaker
import tkinter
import tkinter.filedialog
import tkinter.messagebox
import tkinter.simpledialog
from tkinter import *
import configobj
import csv

class Generate_Platemaker_Pars(object):
    def __init__(self):
        global gui_root
        gui_root = tkinter.Tk()

        # get the station config info
        message = 'Pick hardware setup file.'
        hwsetup_conf = tkinter.filedialog.askopenfilename(initialdir=pc.dirs['hwsetups'], filetypes=(("Config file","*.conf"),("All Files","*")), title=message)
        hwsetup = configobj.ConfigObj(hwsetup_conf,unrepr=True)

        # software initialization and startup
        if hwsetup['fvc_type'] == 'FLI' and 'pm_instrument' in hwsetup:
            fvc=fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'],platemaker_instrument=hwsetup['pm_instrument'])
        else:
            fvc = fvchandler.FVCHandler(fvc_type=hwsetup['fvc_type'],save_sbig_fits=hwsetup['save_sbig_fits'])    
        fvc.rotation = hwsetup['rotation'] # this value is used in setups without fvcproxy / platemaker
        fvc.scale = hwsetup['scale'] # this value is used in setups without fvcproxy / platemaker
        fvc.translation = hwsetup['translation']

        ptl = petal.Petal(petal_id = hwsetup['ptl_id'],
                  simulator_on = False,
                  user_interactions_enabled = True,
                  db_commit_on = False,
                  local_commit_on = True,
                  local_log_on = True,
                  printfunc = print,
                  verbose = False,
                  collider_file = None,
                  sched_stats_on = False,
                  anticollision = None) # valid options for anticollision arg: None, 'freeze', 'adjust'
        posids=ptl.posids
        fidids=ptl.fidids
        m = posmovemeasure.PosMoveMeasure([ptl],fvc)
        m.n_extradots_expected = hwsetup['num_extra_dots']


        # calibration routines
        m.rehome() # start out rehoming to hardstops because no idea if last recorded axis position is true / up-to-date / exists at all
        w=800
        h=600
        ws=gui_root.winfo_screenwidth()
        hs=gui_root.winfo_screenheight()
        x=(ws/2)-(w/2)
        y=(hs/2)-(h/2)
        gui_root.geometry('%dx%d+%d+%d' % (w,h,x,y))

        self.listbox1 = Listbox(gui_root, width=20, height=20,selectmode='multiple',exportselection=0)
        self.listbox1.grid(row=6, column=0,rowspan=10,pady=4,padx=15)
        Button(gui_root,text='OK',width=10,command=self.ok).grid(row=0,column=4,sticky=W,pady=4)
        yscroll_listbox1 = Scrollbar(command=self.listbox1.yview, orient=tkinter.VERTICAL)
        yscroll_listbox1.grid(row=6, column=0, rowspan=10,sticky=tkinter.E+tkinter.N+tkinter.S,pady=5)
        self.listbox1.configure(yscrollcommand=yscroll_listbox1.set)
        self.listbox1.insert(tkinter.END,'ALL')
        for key in sorted(posids):
            self.listbox1.insert(tkinter.END,str(key))
        self.listbox1.bind('<ButtonRelease-1>', self.get_list)

#       Load the information
        Label(gui_root,text="You selected").grid(row=3,column=5)
        self.e_selected=Entry(gui_root)
        self.e_selected.grid(row=3,column=6)

        mainloop()

        m.identify_many_enabled_positioners(self.selected_posids)

        instr = instrmaker.InstrMaker(ptl,m,fvc,hwsetup,m.enabled_posids)
        instr.make_instrfile()
        instr.push_to_db()
        m.identify_disabled_positioners()

    def ok(self):
        gui_root.destroy()

    def get_list(self,event):
        # get selected line index
        index = self.listbox1.curselection()
        # get the line's text
        self.selected=[]
        self.selected_posids=[]
        self.selected_can=[]
        for i in range(len(index)):
            self.selected.append(self.listbox1.get(index[i]))
            if 'ALL' in self.selected:
                self.selected_posids=self.posids
                self.selected_can=[20000]
            else:
                self.selected_posids.append(self.selected[i])
                self.selected_can.append(int(str(self.selected[i][1:6])))
        self.e_selected.delete(0,END)
        self.e_selected.insert(0,str(self.selected_can))


    
if __name__=="__main__":
    gui = Generate_Platemaker_Pars()

