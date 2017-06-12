#!/usr/bin/env python3.4
#
#Script to control the PC side of bootloader operation
#

import struct
import string
import time
import sys, os
import posfidcan
import math
from intelhex import IntelHex

class BootLoadControl(object):
	""" Class for facilitationg firmware update via CAN messages
		from hex file
	"""

	def __init__(self, canbus):
		try:
			self.verbose = False
			self.scan=posfidcan.PosFidCAN(canbus)
			self.scan.slow_timeout = 0.1		
			#part size in bytes, should fit into 64KB buffer
			self.part_size = 16000 	
			self.broadcast_id=20000

			#CAN command ids
			self.mode_comnr = 128
			self.codesz_comnr=129
			self.nparts_comnr=130
			self.data_comnr=132
			self.ver_comnr = 131
		except Exception as e:
			return 'FAILED: Error initializing bootloader control: %s' % str(e)
			
	def get_packets_in_n(self,partn):	

		try:
			if partn == self.nparts:
				packets_n = self.codesize - (self.nparts-1)*(self.part_size/4)
			else:
				packets_n = self.part_size/4
			return int(packets_n)
		
		except Exception as e:
			return 'FAILED: Error retrieving packets in part n: %s' % str(e)

	def send_codesize(self, pid):	#send size of firmware code in words

		try:
			size = str(hex(self.codesize).replace('0x','')).zfill(8)
			self.scan.send_command(pid,self.codesz_comnr, size)
			return 'SUCCESS'

		except Exception as e:
			return 'FAILED: Error sending code size: %s' % str(e)

	def send_nparts(self, pid):	#send the number of parts that the code has been divided into
		try:
			parts = str(hex(self.nparts).replace('0x','')).zfill(8)
			self.scan.send_command(pid,self.nparts_comnr, parts)
			return 'SUCCESS'

		except Exception as e:
			return 'FAILED: Error sending number of parts in hex file: %s' % str(e)

	def select_mode(self, pid, mode = 'bootloader'):

		try:
			if mode == 'bootloader':
				self.scan.send_command(pid, self.mode_comnr ,'01')
			else:
				self.scan.send_command(pid, self.mode_comnr, '00')
			return 'SUCCESS'

		except Exception as e:
			return 'FAILED: Error selecting between bootloader and normal modes' % str(e)



	def request_verification(self, can_ids):
		id = 0
		try:
			verification = {}
			for can_id in can_ids:
				can_id=int(can_id)
				time.sleep(.1)
				try:
					id, data = self.scan.send_command_recv(int(can_id), self.ver_comnr, '')
					#print('ID, DATA: ', id, data, type(id), type(data))
					data = ''.join("{:02x}".format(c) for c in data)
					verification[int(can_id)] = int(data[1])
				except:
					verification[int(can_id)] = 0					

				if verification[can_id]:
					verification[int(can_id)] = 'OK'
				else:
					verification[int(can_id)] = 'ERROR'
			return verification

		except Exception as e:
			return 'FAILED: Error requesting bootloader verification: %s' % str(e)

	def send_packet(self, pid, partn = 1, packetn = 1, packet = '01234567', chksum = 32):
		
		try:
			chksum = str(hex(chksum).replace('0x','')).zfill(2)
			partn = str(partn).zfill(2)
			packetn = str(hex(packetn).replace('0x','')).zfill(4)
			self.scan.send_command(pid, self.data_comnr, str(partn + packetn + packet + chksum))
			return 'SUCCESS'

		except Exception as e:
			return 'FAILED: Error sending firmware packet: %s' % str(e)

	#retrieve packet for given part number and packet number from hex file
	def get_packet(self, partn = 1, packetn = 0):

		try:
			packet_addr = self.hexfile.minaddr()+(partn-1)*self.part_size  + 4*packetn		#start address of 4 byte packet
			packet=''
			packet_byte=[0,0,0,0]
			checksum_byte=[0,0,0,0]

			if partn == self.nparts and packetn > self.get_packets_in_n(partn):
				packet = '00000000'
				checksum = 0
	
			else:
				for i in range(0,4):
					checksum_byte[i] = int(hex(self.hexfile[packet_addr + i]),16)
					packet_byte[i] = str(hex(self.hexfile[packet_addr + i]).replace('0x','')).zfill(2)	
					packet = packet + packet_byte[i]
				checksum = checksum_byte[0] ^ checksum_byte[1] ^ checksum_byte[2] ^ checksum_byte[3]
			return packet, checksum

		except Exception as e:
			return 'FAILED: Error retrieving packet from hex file: %s' % str(e)


	def program(self, can_id, hex_file = 'fw31.hex'):
	
		try:
			pid = can_id
			pause = 0 

			self.hexfile=IntelHex(hex_file)

	
			self.codesize=int(math.ceil(float(self.hexfile.maxaddr() - self.hexfile.minaddr()+1)/4))                #code size in 32-bit wordshex
			self.nparts=int(math.ceil(float(self.hexfile.maxaddr() - self.hexfile.minaddr()+1)/self.part_size))

			if self.verbose:
				print(self.hexfile.maxaddr())
				print(self.hexfile.minaddr())

				print(int(math.ceil(float(self.hexfile.maxaddr() - self.hexfile.minaddr()+1)/4)))

				print(self.get_packets_in_n(1))
				print(self.get_packets_in_n(2))
				print(self.nparts)

			self.send_codesize(pid)
			time.sleep(1)
			self.send_nparts(pid)
			time.sleep(1)

			#loop through parts
			for n in range(1 , (self.nparts + 1)):
				time.sleep(1)
				for p in range(0,self.get_packets_in_n(n)):	
					packet_array=[]
			
					packet_np, chksum = self.get_packet(n,p)
					packet_array.append(packet_np)
					self.send_packet(pid, n, p, packet_np, chksum)
					time.sleep(pause)
	
			return 'SUCCESS'
		
		except Exception as e:
			return 'FAILED: Error with bootloader programming: %s' % str(e)


if __name__ == '__main__':

	canids = []
	canbus = False
	fw = False
	list_flag = False
	file_flag = False

	for arg in sys.argv:
		if 'can' in arg:
			canbus = arg
		if '.hex' in arg:
			fw = arg
		if arg == '-l':
			canids = sys.argv[-1].split(',')
			list_flag = True
		if arg == '-f':
			file_flag = True

	print('------------------------------------------------')
	print('\n   Welcome to the Firmware Upload Utility   \n')
	print('------------------------------------------------')
	print('\nNOTES: If entering a list of CAN ids on the command line (flag -l), enter them last separated by commas (eg. python3 fw_upload.py -l can0 fw40page4.hex 1,2,3,4,5)')
	print('       If entering CAN ids into file (./fw_upload_canids, flag -f):  python3 fw_upload.py -f can0 fw40page4.hex')
	print('       This script can also be run without command line arguments (just python3 fw_upload.py).  It will then prompt you for the necessary arguments as it runs.')

	if not canbus:
		canbus = input('\nPlease enter the canbus that you are using (eg. can0):  ')
		if canbus not in ['can0', 'can1', 'can2', 'can3', 'can4', 'can5', 'can6', 'can7']:
			print('Invalid can bus name.')
			sys.exit()
	if not fw:
		fw = input('\nEnter name of hex file that you would like to upload: ')

	if not list_flag | file_flag:
		answer = input('\nHave you entered the can ids of the devices that you would like to upload firmware to in ./fw_upload_canids?\nIf not, you will be given a chance to type your list in here. \nType y or n: ')
		if answer == 'y' or answer == 'yes':
			file_flag = True
		else:
                	list = input('\nPlease enter a list of canids separated by commas now (eg. 1, 41, 66): ')
                	canids = list.split(',')


	if file_flag:
		with open('fw_upload_canids', 'r') as file:
			for line in file:
				if line[0] != '#':
					canids.append(line)

		
	bc=BootLoadControl(canbus)
	answer = input('\nIf your power supply is not automated (connected to the BBB), please power cycle your supply and press enter within 2 seconds, otherwise just press enter.  The upload process will begin.')

	os.system('sudo config-pin "P9_11" 0')
	os.system('sudo config-pin "P9_13" 0')
	time.sleep(0.2)
	os.system('sudo config-pin "P9_11" 1')
	os.system('sudo config-pin "P9_13" 1')
	time.sleep(0.2)

	for can_id in canids:
		can_id = int(can_id)
		can_id_str = str(hex(can_id)).replace('0x','').zfill(4)
		os.system('cansend ' + canbus + ' 00' + can_id_str + '80#4d.2e.45.2e.4c.65.76.69')

	hex_file_name = str(fw)
	print('\nProgramming ' + hex_file_name + '.....\n')
	bc.program(20000, hex_file_name)
	verification_dict = (bc.request_verification(canids))

	print('CAN_ID'.rjust(8) + ' | ' + 'RESPONSE')
	for key, value in verification_dict.items():
		print(str(key).rjust(8)+ ' | ' + value.rjust(8))		

	print('\n\n')
