# posfid_utility.py
# This script provides some utility and maintenance functions
# for positioners and fiducials
# 
# Revision History
# 
# 160418 created MS based on mvtest.py (by IG)
# testted with FW 1.0


import socketcan
import sys
import time
import math
import struct
import string

can_frame_fmt = "=IB3x8s"


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
	Flips the byte order (LSB-> MSB etc
	"""
	newbarray=[]
	for byte in reversed(barray):
		newbarray.append(byte)
	return bytearray(newbarray)
	
class PositionerControl(object):
	def __init__(self,canchan):
		self.Gear_Ratio=337                          #gear ratio of Namiki motor
		self.scan=socketcan.SocketCAN(str(canchan).lower())
		self.bitsum=0

	def get_sid(self, posid):		
		sid=self.scan.send_command_recv(posid,19,'')
		return sid

	def check_sid_short(self, spid, sid):
		pid=spid
		status=self.scan.send_command_byte(pid,24,sid)
		return status

	def write_can_address(self, spid, sid):
		pid=spid
		status=self.scan.send_command(pid,20,sid)
		return status 

	def get_can_address(self, spid):
		pid=spid
		posid=self.scan.send_command_recv(pid,21, '')
		return posid


	def get_firmware_version(self, spid):
		pass


	def get_device_type(self, spid):
		pass


	def set_reset_led(self,spid, select):
		pid=spid
		self.scan.send_command(pid,5, str(select).zfill(2))	

	
	def run_test_seq(self,spid):
		pid=spid
		self.scan.send_command(pid,6,'')


if __name__ == '__main__':
	
	print(" ID programming requires a single positioner or fiducial on the CAN bus")
	print("")
	print("Select:")
	print("[B]link LED (using broadcast address)")
	print("[R]ead current CAN address")
	sel=input("Select: ")

	
	canchan=sys.argv[1]
	print('CAN channel selected: '+canchan)
	brdcast_id=20000
	 
	pmc=PositionerControl(canchan)
	
	sleepytime=.2
	
	if sel=='B':
		for i in range(8):
			set_reset_led(brdcast_id,'on')
			time.sleep(0.1)
			set_reset_led(brdcast_id,'off')

	sys.exit()		

	readback=False
	initialize=False
	execute_now=True
	program_CAN_address=False
#	setcan=True

	if(program_CAN_address):

		print(" Sending command 19 - read sid short")
		sid=pmc.get_sid(20000)
		print (" sid: ", sid)

		print (" Sending command 21 - read CAN address")
		posid=pmc.get_can_address(20000)
		print (" posid: ", posid)

		print (" Sending command 24 - check sid short")

		sid=flip_byteorder(sid[1])
		pmc.check_sid_short(20000,sid)
		print (" check sid short okay ")
#---
		print (" Sending command 20 - write CAN address")
		can_address='000E' 
		pmc.write_can_address(20000,can_address)
		print (" write CAN address okay ")

		print (" Sending command 21 - read CAN address")
		posid=pmc.get_can_address(20000)
		print (" posid: ", posid)

	if(initialize):
		#currents: spin current, cruise current, creep current, hold current (for m0 and m1)
		pmc.set_currents(1004, 70, 70, 30, 5, 70, 70, 30, 5)

		#periods: m0 creep period, m1 creep period, spin steps
		pmc.set_periods(1004, 1, 1, 12)

	#recv_id, sel, temperature = pmc.get_data(pid1, 'temperature')
	#print("Temperature reading from positioner %d is: %d" % (recv_id, temperature))
	
	time.sleep(.2)

#	pmc.load_rows(pid1, 1, 'pause_only', 0, 1000)
#	time.sleep(sleepytime)
	pmc.load_rows(pid1, 1, 'ccw_cruise_0', 90, 0)
	time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'ccw_cruise_1', 390, 2000)
	#time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'cw_cruise_0', 45, 1000)
	#time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'cw_cruise_1', 45, 1000)
	#time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'cw_cruise_0', 130, 0)
	#time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'ccw_cruise_1', 345, 1000)
	#time.sleep(sleepytime)
	#pmc.load_rows(pid1, 1, 'ccw_cruise_0', 90, 0)
	time.sleep(sleepytime)
	pmc.load_rows(pid1, 2, 'cw_cruise_1', 90, 0)	

	if(execute_now):
		pmc.execute_move_table(pid1)	

		

	
