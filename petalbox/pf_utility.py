# posfid_utility.py
# This script provides some utility and maintenance functions
# for positioners and fiducials
# 
# Revision History
# 
# 160418 created MS based on mvtest.py (by IG)
# tested with FW 1.0

import posfidcan
import sys
import time
import math
import struct
import string

can_frame_fmt = "=IB3x8s"

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
		pid=spid
		revision=self.scan.send_command_recv(pid,11, '')
		return revision
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

	_sel=_read_key()	
	print(" ID programming requires a single positioner or fiducial on the CAN bus")
	print("")
	loop=True
	while loop:
#		print("Select:")
		print("[b]link LED (using broadcast address)")
		print("[r]ead CAN address, silicon ID and software revision")
		print("[e]xit")
		print("[p]rogram new CAN address")
		print("Select: ")
		sel=_sel.__call__()		
		#print("sel:",sel)

		sel=sel.lower()
		if sel=='e':
			print ("Bye...")
			sys.exit()

		canchan=sys.argv[1]
#		print('CAN channel selected: '+canchan)
		brdcast_id=20000
	 
		pmc=PositionerControl(canchan)

		if sel=='b':
			for i in range(8):
				pmc.set_reset_led(brdcast_id,'on')
				time.sleep(0.1)
				pmc.set_reset_led(brdcast_id,'off')

		if sel=='r':
		#print (" Sending command 21 - read CAN address")
			posid, data=pmc.get_can_address(20000)
			print (" CAN ID: ", posid)
		#print(" Sending command 19 - read sid short")
			posid,sid=pmc.get_sid(20000)
			sid_str= ":".join("{:02x}".format(c) for c in sid)
			print ("  Si ID: ",sid_str)
			try:
				posid,fw=pmc.get_firmware_version(20000,)
			except:
				fw='unknown'
			print (" FW  revision: ", str(fw)	


		if sel=='p':
			new_id=input("Enter new CAN address (in decimal): ")
			new_id=int(new_id)
			new_id=(hex(new_id)).strip('0x')
			new_id=new_id.zfill(4)
			posid,sid=pmc.get_sid(20000)
			sid=flip_byteorder(sid)
			pmc.check_sid_short(20000,sid)
			#print (" check sid short okay ")
			#print (" Sending command 20 - write CAN address")
			can_address=new_id # '000E' 
			print ("Writing new CAN address ...")
			try:
				pmc.write_can_address(20000,can_address)
				print ("Writing new CAN address okay ")
			except:
				print ("Writing new CAN address failed ...")
