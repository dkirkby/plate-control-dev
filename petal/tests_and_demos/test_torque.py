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

# Michigan - Irena test
# Petal_Controller_Number=20
# CanBusID='can0'
# CanID=208

# LBL - CAD test
Petal_Controller_Number=10
CanBusID='can0'
CanID=27

Currents=[100,100,100,0]    # percentages for spin-up,cruise,creep,hold
Torque_Moves=[
    #'motor','speed','direction','angle','cool_down_seconds'
    ['phi'  ,'creep' ,'ccw' ,90,  90],
    ['phi'  ,'creep' ,'cw'  ,90,  90]
]

# End of normally edited section


n_mm_to_oz_in = 0.1416119
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
        operator_id=input("Enter Your Name: ")
        motor_sn=input("Enter Motor SN: ")
        test_voltage=input("Enter Test Voltage: ")
        can_ids=[CanID]
        can_bus_ids=[CanBusID]
        print("Checking ready_for_tables, can_bus_ids="+str(can_bus_ids)+", can_ids="+str(can_ids)) 
        bool_val=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
        print("ready_for_tables returned "+str(bool_val))
        if(bool_val):
            print("Setting current: CanBusID="+str(CanBusID)+", CanID="+str(CanID))
            self.pcomm.set_currents(CanBusID,CanID,Currents,Currents)
            response=input("Press Enter when ready for next move: ")
            max_torque=[]
            res_torque=[]
            for i in range(len(MoveTable)):
                print("Moving: CanID="+str(CanID))
                error = self.pcomm.move(CanBusID, CanID,MoveTable[i][iDirection],MoveTable[i][iMode],MoveTable[i][iMotor],MoveTable[i][iAngle])
                ready=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
                while(not ready):
                    time.sleep(1)
                    ready=self.pcomm.ready_for_tables(can_bus_ids,can_ids)
                max_torque.append(input("Enter Max Torque: "))
                res_torque.append(input("Enter Settled Torque: "))
                print("Waiting "+str(MoveTable[i][iCoolSecs])+" seconds for cool down")
                if(i+1<len(MoveTable)):
                    for j in range(int(MoveTable[i][iCoolSecs])):
                        left=int(MoveTable[i][iCoolSecs])-j
                        if((0!=j) and 0==(left%10)):
                            print("Waiting "+str(left)+" seconds for cool down")
                        time.sleep(1)
                    response=input("Press Enter when ready for next move: ")
                else:
                    print("Finished")
                    operator_notes=input("Enter any notes: ")
                    spreadsheet_str =str(motor_sn)+"," 		   # motor serial number
                    spreadsheet_str+=str(operator_id)+","          # operator id
                    spreadsheet_str+=str(test_voltage)+","         # test_voltage
                    spreadsheet_str+=str(MoveTable[0][iMotor])+"," # phi or theta
                    spreadsheet_str+=str(MoveTable[0][iMode])+","  # creep or cruise
                    spreadsheet_str+=str(MoveTable[i][iCoolSecs])+"," # cooldown seconds
                    if(str(MoveTable[0][iDirection]).lower()=='ccw'):
                        spreadsheet_str+=str(max_torque[0])+","			# max ccw torque in oz-in
                        spreadsheet_str+=str(format(float(max_torque[0])/n_mm_to_oz_in,'.3f'))+","	# max ccw torque in n-mm
                        spreadsheet_str+=str(res_torque[0])+","			# settled ccw torque in oz-in
                        spreadsheet_str+=str(format(float(res_torque[0])/n_mm_to_oz_in,'.3f'))+","	# settled ccw torque in n-mm
                        spreadsheet_str+=str(max_torque[1])+","			# max cw torque in oz-in
                        spreadsheet_str+=str(format(float(max_torque[1])/n_mm_to_oz_in,'.3f'))+","	# max cw torque in n-mm
                        spreadsheet_str+=str(res_torque[1])+","			# settled cw torque in oz-in
                        spreadsheet_str+=str(format(float(res_torque[1])/n_mm_to_oz_in,'.3f'))+","	# settled cw torque in n-mm
                    else:
                        spreadsheet_str+=str(max_torque[1])+","			# max ccw torque in oz-in
                        spreadsheet_str+=str(format(float(max_torque[1])/n_mm_to_oz_in,'.3f'))+","	# max ccw torque in n-mm
                        spreadsheet_str+=str(res_torque[1])+","			# settled ccw torque in oz-in
                        spreadsheet_str+=str(format(float(res_torque[1])/n_mm_to_oz_in,'.3f'))+","	# settled ccw torque in n-mm
                        spreadsheet_str+=str(max_torque[0])+","			# max cw torque in oz-in
                        spreadsheet_str+=str(format(float(max_torque[0])/n_mm_to_oz_in,'.3f'))+","	# max cw torque in n-mm
                        spreadsheet_str+=str(res_torque[0])+","			# settled cw torque in oz-in
                        spreadsheet_str+=str(format(float(res_torque[0])/n_mm_to_oz_in,'.3f'))+","	# settled cw torque in n-mm
                    spreadsheet_str+=str(operator_notes)
                    self.logprint(spreadsheet_str)
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
    
    
#   root =Tk()
    root = 0
    ott = Operator_Torque_Test(root,Petal_Controller_Number)
    if(ott.pcomm.is_connected()):
        ott.torque_moves(CanID,Currents,Torque_Moves)
    else:
        print("Not connected to petal controller")
#   root.withdraw()



