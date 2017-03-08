#
#
# Script for creating a DESI fiber positioner control (FPC) test sequence
# that calls on the SocketCAN class to generate CAN commands 
#
# Revision History
# 150619 created (igershko, UM)
# 151202 restructured to communicate with V1.0 firmware (igershko, UM)
# 

import socketcanf
import sys
import time
import math
import socket
import struct
import string

can_frame_fmt = "=IB3x8s"

class PositionerMoveControl(object):
	def __init__(self):

		self.Gear_Ratio=337                          #gear ratio of Namiki motor
		self.scan=socketcanf.SocketCAN('can0')
		self.bitsum=0

	#still needs to be redone
	def get_data(self, spid, data_select):			
		pid=spid
		select=dict(temperature = 1, positioner_id = 2, firmware_version = 3, movement_status=4, current_monitor_1 = 5, current_monitor_2 = 6)
		data_select = str(select[data_select]).zfill(2)

		received_id, data=self.scan.send_command_recv(pid,5,str(data_select))
		requested_data=16777216*data[1]+65536*data[2]+256*data[3]+data[4];
		select=int(data[0]);

		return received_id, select, requested_data
	

	def set_reset_leds(self,spid, select):
		pid=spid
		self.scan.send_command(pid,6, str(select).zfill(2))	

	
	def run_test_seq(self,spid):
		pid=spid
		self.scan.send_command(pid,7,'')


	def execute_move_table(self,spid):
		pid=spid
		self.scan.send_command(pid,8,'')

	def legacy_mode(self,spid):
		pid=spid
		self.scan.send_command(pid,10,'')
	
	def set_currents(self,spid, spin_current_m0, cruise_current_m0, creep_current_m0, hold_current_m0, spin_current_m1, cruise_current_m1, creep_current_m1, hold_current_m1):
		pid=spid
		
		spin_current_m0 = str(hex(spin_current_m0).replace('0x','')).zfill(2)
		cruise_current_m0 = str(hex(cruise_current_m0).replace('0x','')).zfill(2)
		creep_current_m0 = str(hex(creep_current_m0).replace('0x','')).zfill(2)
		hold_current_m0 = str(hex(hold_current_m0).replace('0x','')).zfill(2)	

		spin_current_m1 = str(hex(spin_current_m1).replace('0x','')).zfill(2)
		cruise_current_m1 = str(hex(cruise_current_m1).replace('0x','')).zfill(2)
		creep_current_m1 = str(hex(creep_current_m1).replace('0x','')).zfill(2)
		hold_current_m1 = str(hex(hold_current_m1).replace('0x','')).zfill(2)			
	
		try:
			self.scan.send_command(pid,2,spin_current_m0 + cruise_current_m0 + creep_current_m0 + hold_current_m0 + spin_current_m1 + cruise_current_m1 + creep_current_m1 + hold_current_m1)
			return 0

		except:
			return 1

	def set_periods(self,spid, creep_period_m0, creep_period_m1, spin_steps):
		pid=spid
		
		
		creep_period_m0=str(creep_period_m0).zfill(2)
		creep_period_m1=str(creep_period_m1).zfill(2)
		spin_steps=str(hex(spin_steps).replace('0x','')).zfill(4)
		
		print("Data sent: %s" % creep_period_m0+creep_period_m1+spin_steps)
		try:
			self.scan.send_command(pid,3,creep_period_m0 + creep_period_m1 + spin_steps)
			return 0

		except:
			print ("Sending command 2 failed")
			return 1



	def load_rows(self,spid, ex_code,select_flags,amount,pause,readback=True):
		
		
		pid=spid
		ex_code=str(ex_code)
		select_flags=str(select_flags)
		pause = str(hex(pause).replace('0x','')).zfill(4)

		select=dict(cw_cruise_0 = 2, ccw_cruise_0 = 3, cw_cruise_1 = 6, ccw_cruise_1 = 7, cw_creep_0 = 0, ccw_creep_0 = 1, cw_creep_1 = 4,  ccw_creep_1 = 5, pause_only = 8)
		
		if(select[select_flags] == 0 or select[select_flags] == 4 or select[select_flags] == 1 or select[select_flags] == 5):
			amount=amount*self.Gear_Ratio/.1

		else:
			amount=amount*self.Gear_Ratio/3.3
			
		
		amount=str(hex(int(amount)).replace('0x','').zfill(6))
		select_flags=str(select[select_flags])
	
		if(ex_code == '0' or ex_code == '1'):		

			try:
			
				print('Data sent is: %s (in hex)'%(str(ex_code + select_flags + amount + pause)))
				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))
				

				if(ex_code=='1'):	
					
					print(str(hex(int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4).replace('0x','').zfill(8)))				 						
					self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
					print('Bitsum =', self.bitsum)

				return 0
	
			except:

				print ("Sending command 4 failed")
				return 1
		else:
			#Send both last command and bitsum, reset bitsum for next move table	
		
			try:
			
				print('Data sent is: %s (in hex)'%(str(ex_code + select_flags + amount + pause)))

				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))
				self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
				print('Bitsum =', self.bitsum)
				
				self.scan.send_command(pid,9, str(hex(self.bitsum).replace('0x','').zfill(8)))
				self.bitsum=0
				
				return 0
	
			except:
				print ("Sending command 4 or 9 failed")
				return 1	

if __name__ == '__main__':
	
	pid1=1004   
	 
	pmc=PositionerMoveControl()
	
	sleepytime=.2
	
	readback=False
	initialize=True
	execute_now=False
	
	if(initialize):
		#currents: spin current, cruise current, creep current, hold current (for m0 and m1)
		pmc.set_currents(1004, 70, 70, 30, 5, 70, 70, 30, 5)

		#periods: m0 creep period, m1 creep period, spin steps
		pmc.set_periods(1004, 1, 1, 378)

	recv_id, sel, temperature = pmc.get_data(pid1, 'temperature')
	print("Temperature reading from positioner %d is: %d" % (recv_id, temperature))
	
	time.sleep(1)

	pmc.load_rows(pid1, 1, 'pause_only', 0, 5000)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'ccw_cruise_0', 200, 0)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'ccw_cruise_1', 390, 3000)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'cw_cruise_0', 45, 2000)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'cw_cruise_1', 45, 3000)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'cw_creep_0', 130,0)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 2, 'cw_creep_1', 345,0)
	time.sleep(sleepytime)

	if(execute_now):

		pmc.execute_move_table(pid1)	

		

	
