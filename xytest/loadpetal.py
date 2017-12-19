#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 23:10:49 2017

@author: zhangkai
"""
class LoadPetal(object):
    def __init__(self,hwsetup_conf='',xytest_conf=''):
        global gui_root
        gui_root = tkinter.Tk()
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
       
        