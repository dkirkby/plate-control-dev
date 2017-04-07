# boardtest.py
# This is a script that the FIPOS quality control test interfaces to.  It performs the following functions based on the command sent:
#'python3 boardtest.py <can_id> program_canid': programs given can_id into the board, returns can_id, sid_short, sid_upper, sid_lower
#'python3 boardtest.py <can_id> read_temp': read temperature sensor of board with given can_id
#'python3 boardtest.py <can_id> test_sync': sends move table to given can_id, checks for when sync is set (move table executed)
#'python3 boardtest.py <can_id> led_seq': sends out led flashing pattern
#'python3 boardtest.py <can_id> test_seq': sends out command that toggles between normal motor opertion mode and test sequence mode


import posfidcan
import sys
import time
import math
import struct
import string
import os,sys


def hex_to_int(barray):
	"""
	Converts byte array to integer
	"""
	i=0
	for j,byte in enumerate(reversed(barray)):
		i=i+byte*2**(j*8)		
	return i

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

	def check_sid_short(self, spid, sid):
		pid=spid
		status=self.scan.send_command_byte(pid,24,sid)
		return status

	def write_can_address(self, pid, new_canid):
		new_canid = str(hex(new_canid).replace('0x','')).zfill(4)
		status=self.scan.send_command(pid,20,new_canid)
		return status 

	def get_can_address(self, spid):
		pid=spid
		posid,data=self.scan.send_command_recv(pid,21, '')
		return posid,data

	def get_firmware_version(self, spid):
		pid=spid
		revision,data=self.scan.send_command_recv(pid,11, '')
		return revision,data


	def set_reset_led(self,id, select):
		if select.lower()=='on':
			state=1
		if select.lower()=='off':
			state=0 
		self.scan.send_command(id,5,str(state).zfill(2))	
	
	def switch_test_mode(self, pid):
		self.scan.send_command(pid, 6, '')

	def get_temperature(self, pid):
		posid, data = self.scan.send_command_recv(pid, 9, '')	
		return data

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

				#print('Data sent is: %s (in hex)'%(str(ex_code + select_flags + amount + pause)))
				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))


				if(ex_code=='1'):

					#print(str(hex(int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4).replace('0x','').zfill(8)))  
					self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
					#print('Bitsum =', self.bitsum)

				return 0

			except:

				#print ("Sending command 4 failed")
				return 1
		else:
                        #Send both last command and bitsum, reset bitsum for next move table    
			try:
				#print('Data sent is: %s (in hex)'%(str(ex_code + select_flags + amount + pause)))
				self.scan.send_command(pid,4, str(ex_code + select_flags  + amount + pause))
				self.bitsum += int(ex_code + select_flags,16) + int(amount,16) + int(pause,16) + 4
				#print('Bitsum =', self.bitsum)
				
				posid, bitsum_response = self.scan.send_command_recv(pid,8, str(hex(self.bitsum).replace('0x','').zfill(8)))
				self.execute_move_table(20000)#TEMP
				posid, bitsum_response = self.scan.send_command_recv(pid,8, str(hex(self.bitsum).replace('0x','').zfill(8)))
				self.bitsum=0
				return bitsum_response
			except:
				#print ("Sending command 4 or 8 failed")
				return 1


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


		print('CAN_ID, S_ID, S_ID upper, S_ID lower: ', read_back_canid, sid_str, sid_upper, sid_lower)

	elif command == 'test_seq':
		pmc.switch_test_mode(canid)

	elif command == 'led_seq':
		for count in range(0,5):
			pmc.set_reset_led(canid, 'on')
			time.sleep(.5)

	elif command == 'test_sync':
		pmc.load_rows(canid, 1, 'cw_cruise_0', 45, 0)
		pmc.load_rows(canid, 1, 'cw_cruise_1', 45, 0)
		checksum = pmc.load_rows(canid, 2, 'cw_creep_1', 0, 0)
		print(checksum[4])		

	elif command == 'read_temp':
		temp = pmc.get_temperature(canid)
		print(int.from_bytes(temp, byteorder = 'little'))
