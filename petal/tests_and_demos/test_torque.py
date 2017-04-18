#    Title:       test_torque.py
#    Date:        04/11/2017
#    Author:      cad
#    Sysnopsis:   Code to run torque tests on theta and phi motors
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
print(sys.path)

import petalcomm

# Edit the values below before each test
Petal_Controller_Number=10
CanBusID='can0'
CanID=27
Currents=[100,100,100,0]    # percentages for spin-up,cruise,creep,hold
Torque_Moves=[
    #'motor','speed','direction','angle','cool_down_seconds'
    ['phi'  ,'creep' ,'cw'  ,90,  120],
    ['phi'  ,'creep' ,'ccw' ,90,  120]
]

# End of normally edited section


TTLogFile="torque_test.csv"

# indices into MoveTable list
iMotor=0     # 'phi' or 'theta'
iMode=1      # 'cruise' or 'creep'
iDirection=2 # 'cw' or 'ccw
iAngle=3     # angle in degrees
iCoolSecs=4  # seconds to cool down

class Operator_Torque_Test:
    """Class for Torque Test by human Operator"""

    # 
    def __init__(self,tkroot,PCnum):
        self.pcomm=petalcomm.PetalComm(PCnum)
        self.pcnum=PCnum
        self.tkroot=tkroot

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


    def torque_moves(self,CanID,CurrentList,MoveTable):
        err,errmsg = self.check_MoveTable(MoveTable)
        if(err):
            print(errmsg)
            return 1
        if(4!=len(CurrentList)):
            print("CurrentList should be a list of 4 values!")
            return 1
        print("CanID=",int(CanID))
        can_ids=[CanID]
        can_bus_ids=[CanBusID]
        print("Checking ready_for_tables, can_bus_ids="+str(can_bus_ids)+", can_ids="+str(can_ids)) 
        bool_val=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
        print("ready_for_tables returned "+str(bool_val))
        if(bool_val):
            print("Setting current: CanBusID="+str(CanBusID)+", CanID="+str(CanID))
            self.pcomm.set_currents(CanBusID,CanID,Currents,Currents)
            for i in range(len(MoveTable)):
                print("Moving: CanID="+str(CanID))
                self.pcomm.move(CanID,MoveTable[i][iDirection],MoveTable[i][iMode],MoveTable[i][iMotor],MoveTable[i][iAngle])
                ready=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
                while(not ready):
                    time.sleep(1)
                    ready=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
                max_torque=input("Enter Max Torque: ")
                res_torque=input("Enter Residual Torque: ")
                self.logprint(str(MoveTable[i][iMotor])+","+str(MoveTable[i][iMode])+","+str(MoveTable[i][iDirection])+","+str(MoveTable[i][iAngle])+","+str(MoveTable[i][iCoolSecs])+","+str(max_torque)+","+str(res_torque))
                print("Waiting "+str(MoveTable[i][iCoolSecs])+" seconds for cool down")
                time.sleep(int(MoveTable[i][iCoolSecs]))
                if(i+1<len(MoveTable)):
                    response=input("Press Enter when ready for next move: ")
                else:
                    print("Finished")
        else:
            print("PC"+int(self.pcnum)+" not ready, try again later")
        return 0

    def logit(self,themessage):
        logfile= open( TTLogFile, 'a' )
        logfile.write( time.strftime( "%x %X," ) + themessage + "\n" )
        logfile.close()			# This will flush out the log after every line

    def logprint(self,themessage):
        self.logit(themessage)
        print(time.strftime( "%x %X," )+themessage)



if __name__ == '__main__':
    verbose=True
    if len(sys.argv) >=1:
        if len(sys.argv) == 2:
            if sys.argv[1].lower() == 'false':
                verbose=False
    
    
    root =Tk()
    ott = Operator_Torque_Test(root,Petal_Controller_Number)
    if(ott.pcomm.is_connected()):
        ott.torque_moves(CanID,Currents,Torque_Moves)
    else:
        print("Not connected to petal controller")


