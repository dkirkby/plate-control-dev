# posfid_utility.py
# This script provides some utility and maintenance functions
# for positioners and fiducials
# 
# Revision History
# 
# 160418 created MS based on mvtest.py (by IG)
# tested with FW 2.1

import posfidcan
import sys
import time
import math
import struct
import string
import os


can_frame_fmt = "=IB3x8s"
os.system('cansend ' + str(sys.argv[1]) + ' 004e2080#00')
sleept = 0.5

class _read_key:
    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
	
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
		self.scan=posfidcan.PosFidCAN(str(canchan).lower())
		self.bitsum=0

	def set_mode(self, pid):
		status=self.scan.send_command(pid,128,'00')

	def get_sid(self, posid):		
		sid,data=self.scan.send_command_recv(posid,19,'')
		return sid,data

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
		posid,data=self.scan.send_command_recv(pid,21, '')
		return posid,data

	def get_firmware_version(self, spid):
		pid=spid
		revision,data=self.scan.send_command_recv(pid,11, '')
		return revision,data
		pass

	def get_device_type(self, spid):
		pass

	def set_reset_led(self,id, select):
		if select.lower()=='on':
			state=1
		if select.lower()=='off':
			state=0 
		self.scan.send_command(id,5,str(state).zfill(2))	
	
if __name__ == '__main__':
	canchan=sys.argv[1]
	can_id=int(sys.argv[2])
 
	pmc=PositionerControl(canchan)
	pmc.set_mode(can_id)
	time.sleep(sleept)
	try:
		posid, data=pmc.get_can_address(can_id)
	except:
		posid = 'READ ERROR'	
	print ("   CAN ID: ", posid)
	try:
		posid,sid=pmc.get_sid(can_id)
		sid_str= ":".join("{:02x}".format(c) for c in sid)
	except:
		sid_str='READ ERROR'
	print ("    Si ID: ",sid_str)
	try:
		posid,fw=pmc.get_firmware_version(can_id)
		if len(fw) == 1:
			fw=str(int(ord(fw))/10)
		else:			
			fw=str(int(str(fw[1]),16))+"."+str(int(str(fw[0]),16))
	except:
		fw='unknown'
	print ("  FW rev.: ", fw)

		