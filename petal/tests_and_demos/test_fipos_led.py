#    Title:       test_fipos_led.py
#    Date:        05/25/2017
#    Author:      cad
#    Sysnopsis:   Code to set fiducial pct
#
#    Revisions:
#    mm/dd/yyyy who        description
#    ---------- --------   -----------
# 
# ****************************************************************************

try:
    from Tkinter import *
except ImportError:
    from tkinter import *

import os
import sys
import time
import datetime # for the filename timestamp

cwd = os.getcwd()
sys.path.append(cwd + '/../')
# print(sys.path)

import petalcomm

# Edit the values below before each test

# LBL - CAD test
Petal_Controller_Number=43
CanBusID='can0'
CanIDs=[1106,9018]
# CanID=9018
# CanID=1106


class Operator_Fiducial_Test:
    """Class for FIPOS LED Test by human Operator"""

    # 
    def __init__(self,tkroot,PCnum):
        self.pcomm=petalcomm.PetalComm(PCnum)
        self.pcnum=PCnum
        self.tkroot=tkroot

    def set_fipos_led(self,LED_pct):
        can_bus_ids=[CanBusID]
        LED_pcts=[LED_pct]
        for x in range(len(CanIDs)):
            my_canids=[CanIDs[x]]
            bool_val=self.pcomm.set_fiducials(can_bus_ids,my_canids,LED_pcts)
            if(bool_val):
                print("Success LED_pct=",str(LED_pct))
            else:
                print("Fail    LED_pct=",str(LED_pct))

    def get_fipos_led(self):
        can_bus_ids=[CanBusID]
        print(self.pcomm.get_fid_status())
        return


if __name__ == '__main__':
    verbose=True
    pct=100
    if len(sys.argv) >=1:
        if len(sys.argv) == 2:
            if sys.argv[1].lower() == 'on':
                pct=100
            else:
                if sys.argv[1].lower() == 'off':
                    pct=0
                else:
                    try:
                       pct=int(sys.argv[1])
                    except ValueError:
                       pct=0
    
    
#   root =Tk()
    root = 0
    ott = Operator_Fiducial_Test(root,Petal_Controller_Number)
    if(ott.pcomm.is_connected()):
        ott.set_fipos_led(pct)
        ott.get_fipos_led()
    else:
        print("Not connected to petal controller")
#   root.withdraw()



