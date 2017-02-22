#!/usr/bin/env python3.4
#
#Script to control the PC side of bootloader operation
#

import struct
import string
import time
import sys
import posfidcan
import math
from intelhex import IntelHex

class BootLoadControl(object):
	""" Class for facilitationg firmware update via CAN messages
		from hex file
	"""

	def __init__(self):
		try:
			self.verbose = True
			self.scan=posfidcan.PosFidCAN('can0')		
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

		try:
			verification = {}
			for can_id in can_ids:
				time.sleep(.1)
				id, data = self.scan.send_command_recv(can_id, self.ver_comnr, '')
				data = ''.join("{:02x}".format(c) for c in data)
				
				verification[can_id] = int(data[1])
				if verification[can_id]:
					verification[can_id] = 'OK'
				else:
					verification[can_id] = 'ERROR'
			return verification

		except Exception as e:
			return 'FAILED: Error requesting bootloader verification: %s' % str(e)

	def send_packet(self, pid, partn = 1, packetn = 1, packet = '01234567'):
		
		try:
			checksum = str(bin(int(packet, 16))).replace('0b','').count('1')
			checksum = str(hex(checksum).replace('0x','')).zfill(2)
			partn = str(partn).zfill(2)
			packetn = str(hex(packetn).replace('0x','')).zfill(4)
			self.scan.send_command(pid, self.data_comnr, str(partn + packetn + packet + checksum))
			return 'SUCCESS'

		except Exception as e:
			return 'FAILED: Error sending firmware packet: %s' % str(e)

	#retrieve packet for given part number and packet number from hex file
	def get_packet(self, partn = 1, packetn = 0):

		try:
			packet_addr = self.hexfile.minaddr()+(partn-1)*self.part_size  + 4*packetn		#start address of 4 byte packet
			packet=''
			packet_byte=[0,0,0,0]

			if partn == self.nparts and packetn > self.get_packets_in_n(partn):
				packet = '00000000'
	
			else:
				for i in range(0,4):
					packet_byte[i] = str(hex(self.hexfile[packet_addr + i]).replace('0x','')).zfill(2)	
					packet = packet + packet_byte[i]
				
			return packet

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
			
					packet_np = self.get_packet(n,p)
					packet_array.append(packet_np)
					self.send_packet(pid, n, p, packet_np)
					time.sleep(pause)
	
			return 'SUCCESS'
		
		except Exception as e:
			return 'FAILED: Error with bootloader programming: %s' % str(e)


if __name__ == '__main__':
	

	hex_file_name = str(sys.argv[2]) #'fw31.hex'
	bc=BootLoadControl()
	print('Programming ' + hex_file_name + '.....')
	bc.program(int(sys.argv[1]), hex_file_name)
	print(bc.request_verification([int(sys.argv[1])]))
	print('Done!')
