# boardtest.py
# This is a petalbox script that the FIPOS quality control test interfaces to.  It performs the following functions based on the system arguments supplied:
#'python3 boardtest.py <can_id> program_canid': programs given can_id into the board, returns read back can_id, sid_short, sid_upper, and sid_lower
#'python3 boardtest.py <can_id> read_temp': read temperature sensor of board with given can_id
#'python3 boardtest.py <can_id> test_sync': sends move table to given can_id, checks sync signal
#'python3 boardtest.py <can_id> led_seq': sends out led flashing pattern
#'python3 boardtest.py <can_id> test_seq': sends out command that toggles between normal motor opertion mode and test sequence mode

import posfidcan
import sys
import time
import math
import struct
import string
import os,sys

def flip_byteorder(barray):
	"""
	Flips the byte order (LSB-> MSB etc)
	"""
	newbarray=[]
	for byte in reversed(barray):
		newbarray.append(byte)
	return bytearray(newbarray)
	
class PositionerControl(object):
	def __init__(self,canchan):
		self.scan=posfidcan.PosFidCAN(str(canchan).lower())
		self.bitsum=0
		self.Gear_Ratio=337
	def get_sid(self, posid):		
		sid,data=self.scan.send_command_recv(posid,19,'')
		return sid,data

	def get_sid_upper(self, pid):
		posid, data = self.scan.send_command_recv(pid, 18, '')
		return data

	def get_sid_lower(self, pid):
		posid, data = self.scan.send_command_recv(pid, 17, '')
		return data		

	def check_sid_short(self, pid, sid):
		status=self.scan.send_command_byte(pid,24,sid)
		return status

	def write_can_address(self, pid, new_canid):
		new_canid = str(hex(new_canid).replace('0x','')).zfill(4)
		status=self.scan.send_command(pid,20,new_canid)
		return status 

	def get_can_address(self, pid):
		posid,data=self.scan.send_command_recv(pid,21, '')
		return posid,data

	def get_firmware_version(self, pid):
		revision,data=self.scan.send_command_recv(pid,11, '')
		return revision,data

	def set_reset_led(self,pid, select):
		if select.lower()=='on':
			state=1
		if select.lower()=='off':
			state=0 
		self.scan.send_command(pid,5,str(state).zfill(2))	
	
	def switch_test_mode(self, pid):
		self.scan.send_command(pid, 6, '')

	def get_temperature(self, pid):
		posid, data = self.scan.send_command_recv(pid, 9, '')	
		return data

	def load_rows(self,pid, ex_code,select_flags,amount,pause,readback=True):
		checksum_match = False
		sync_check = False
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
				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))
				if(ex_code=='1'):
					self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
				return 'SUCCESS'
			except:
				return 'FAILED'
		else:
                        #Send both last command and bitsum, reset bitsum for next move table    
			try:
				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))
				self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
				
				posid, bitsum_response = self.scan.send_command_recv(pid,8, str(hex(self.bitsum).replace('0x','').zfill(8)))
				if bitsum_response[4] == 1:
					checksum_match = True
				time.sleep(.2)
				os.system('sudo config-pin "P9_12" 1')
				time.sleep(.2)
				posid, bitsum_response = self.scan.send_command_recv(pid,8, str(hex(self.bitsum).replace('0x','').zfill(8)))
				if bitsum_response[4] == 3:
					sync_check = True
				self.bitsum=0
				if checksum_match and sync_check:
					return 0
				elif not checksum_match:
					return 2
				else:
					return 1
			except:
				return 'FAILED'

	def execute_move_table(self, pid):
		self.scan.send_command(pid, 7, '')

if __name__ == '__main__':
	canchan='can0'
	brdcast_id=20000
	canid = int(sys.argv[1])
	pmc=PositionerControl(canchan)
	
	command = sys.argv[2]

	if command == 'program_canid':
		posid,sid=pmc.get_sid(brdcast_id)
		sid_str= "".join("{:02x}".format(c) for c in sid)
		sid=flip_byteorder(sid)
		pmc.check_sid_short(brdcast_id,sid)
		pmc.write_can_address(brdcast_id, canid)

		posid,read_back_canid = pmc.get_can_address(canid)
		read_back_canid = int.from_bytes(read_back_canid, byteorder = 'little')
		
		sid_upper = pmc.get_sid_upper(brdcast_id)
		sid_upper= "".join("{:02x}".format(c) for c in sid_upper)

		sid_lower = pmc.get_sid_lower(brdcast_id)
		sid_lower= "".join("{:02x}".format(c) for c in sid_lower)

		print('CAN_ID: %d, SID_short: %s, SID_upper: %s, SID_lower: %s'%(read_back_canid, sid_str, sid_upper, sid_lower))

	elif command == 'test_seq':
		pmc.switch_test_mode(canid)

	elif command == 'led_seq':
		for count in range(0,5):
			pmc.set_reset_led(canid, 'on')
			time.sleep(.5)
			pmc.set_reset_led(canid, 'off')
			time.sleep(.5)

	elif command == 'test_sync':
		os.system('sudo config-pin "P9_12" 0')
		pmc.load_rows(canid, 1, 'cw_cruise_0', 45, 0)
		pmc.load_rows(canid, 1, 'cw_cruise_1', 45, 0)
		status = pmc.load_rows(canid, 2, 'cw_creep_1', 0, 0)
		print(status)

	elif command == 'read_temp':
		temp = pmc.get_temperature(canid)
		print(int.from_bytes(temp, byteorder = 'little'))
