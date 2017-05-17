# pf_utility.py
# This script provides some utility and maintenance functions
# for positioners and fiducials
# 
# Revision History
# 
# 160418 created MS based on mvtest.py (by IG)

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

	def send_command(self, pid, command, data):
		self.scan.send_command(pid, command, data)
		
	def set_reset_led(self,id, select):
		if select.lower()=='on':
			state=1
		if select.lower()=='off':
			state=0 
		self.scan.send_command(id,5,str(state).zfill(2))	
	
	def get_from_all(self, id, command):
		data = self.scan.send_command_recv_multi(20000, command, '')
		return data

	def format_sids(self, sid_dict):
		for key,value in sid_dict.items():
			sid_dict[key] = ":".join("{:02x}".format(c) for c in value)			
		return sid_dict

	def format_versions(self, vr_dict):
		for key,value in vr_dict.items():
			if len(value) == 1:
				vr_dict[key] = fw=str(int(ord(value))/10)
			else:
				vr_dict[key] = str(int(str(value[1]),16))+"."+str(int(str(value[0]),16))
		return vr_dict

if __name__ == '__main__':
	canchan=sys.argv[1]
	_sel=_read_key()
	print("")
	print(" ID programming requires a single positioner or fiducial on the CAN bus, or a known silicon ID")
	print("")	
	print(" (Using CANbus "+str(canchan)+")")
	print("")	

	loop=True
	while loop:
		print("\n\n")
		print("[b]link LED (using broadcast address)")
		print("[r]ead CAN address, silicon ID and software revision")
		print("[e]xit")
		print("[p]rogram new CAN address")
		print("[l]ist all silicon IDs, software revision numbers, and CAN ids found on the CAN bus. If more than one device on bus FW vr >= 4.0 needed.")
		print("[s]id programming - type in silicon ID, then program new CAN id into the corresponding device")
		print("[i]ndividually address a pos/fid by CAN address and ask for its fw version and silicon ID")
		print("Select: \n")
		
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
			pmc.set_mode(brdcast_id)
			time.sleep(sleept)	
			for i in range(8):
				pmc.set_reset_led(brdcast_id,'on')
				time.sleep(0.1)
				pmc.set_reset_led(brdcast_id,'off')

		if sel=='r':
		#print (" Sending command 21 - read CAN address")
			pmc.set_mode(brdcast_id)
			time.sleep(sleept)
			posid, data=pmc.get_can_address(20000)
			print ("   CAN ID: ", posid)
		#print(" Sending command 19 - read sid short")
			posid,sid=pmc.get_sid(20000)
			sid_str= ":".join("{:02x}".format(c) for c in sid)
			print ("    Si ID: ",sid_str)
			try:
				posid,fw=pmc.get_firmware_version(20000)
				if len(fw) == 1:
					fw=str(int(ord(fw))/10)
				else:
					
					fw=str(int(str(fw[1]),16))+"."+str(int(str(fw[0]),16))
		
			except:
				fw='unknown'
			print ("  FW rev.: ", fw)

		if sel=='p':
			pmc.set_mode(brdcast_id)
			time.sleep(sleept)
			new_id=input("Enter new CAN address (in decimal): ")
			new_id=int(new_id)
			new_id=(hex(new_id)).replace('0x','')			
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


		if sel=='l':	#list fw versions, sid64, sid96, by can id
			print("\n\n**Note: CAN ids of the devices on the bus must be unique for this to work properly**\n")
			fw_vr = pmc.get_from_all(brdcast_id, 11)
			fw_vr = pmc.format_versions(fw_vr)		
	
			bl_vr = pmc.get_from_all(brdcast_id, 15)
			bl_vr = pmc.format_versions(bl_vr)

			sid64 = pmc.get_from_all(brdcast_id, 19)
			sid64 = pmc.format_sids(sid64)

			sidupper = pmc.get_from_all(brdcast_id, 18)
			sidupper = pmc.format_sids(sidupper)

			sidlower = pmc.get_from_all(brdcast_id, 17)
			sidlower = pmc.format_sids(sidlower)

			sidfull = {}
			for key,value in sidupper.items():
				sidfull[key] = sidupper[key] + ':' + sidlower[key]					
			print('CAN_ID| FW Version| BL Version|' + 'Silicon ID (64-bit)|  '.rjust(27) +'Silicon ID (full)|  '.rjust(37))
			for key, value in sid64.items():
				try:
					bl = bl_vr[key]
				except:
					bl = 'too old'
				print(str(key).rjust(6) + '| ' + fw_vr[key].rjust(10) + '| ' + bl.rjust(10) + '| ' + sid64[key] + '| ' + sidfull[key] + '|')
			print('\n')

		if sel=='s':   #enter sid, then send new can_id to positioner with this sid
			sid = input('Enter 64-bit silicon id (xx:xx:xx:xx:xx:xx:xx:xx): ')
			sid = (sid.split(':'))
			sid.reverse()
			sid = "".join(sid)
			print(sid)
			pmc.send_command(brdcast_id, 24, sid)
			id = input('Enter new can id (it will be programmed into the device with the matching silicon id): ')
			id = (hex(int(id))).replace('0x','').zfill(4)
			pmc.write_can_address(brdcast_id, id)
		
		if sel=='i':   #individially read back pos/fid info, loops but breaks out if non-numeric entry is given
			while loop:
				id = input('Enter numeric CAN id of the device that you would like to read and press enter (or just press enter to return to main menu): ')
				if not id.isdigit():
					print('CAN id must be a number, returning to main menu')
					break

				if id.isdigit():
					can_id = int(id)
					posid, data=pmc.get_can_address(can_id)
					print ("   CAN ID: ", posid)
					posid,sid=pmc.get_sid(can_id)
					sid_str= ":".join("{:02x}".format(c) for c in sid)
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
					print('\n')
	
	
				
	
