#!/usr/local/bin/python3.4
# 
# Class for CANbus communication via SocketCAN
# 
# modification history:
# 150619 created (igershko, UM)

from __future__ import print_function
import os
import socket
import struct
import string
import time

class PosFidCAN(object):
	"""Class for communicating with the DESI fiber positioner control (FPC) electronics
		through Systec module via SocketCAN.
	"""

	can_frame_fmt = "=IB3x8s"
	#Create CAN socket and bind to interface channel='canX'
	def __init__(self, channel='can0'):
		
		try:	
			self.s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)		
			self.s.bind((channel,))	
		
		except socket.error:
			print('Error creating and/or binding socket')
		return		

	def __close__(self):
		self.s.close()
	
	#CAN frame packing/unpacking (see `struct can_frame` in <linux/can.h>)	
	def build_can_frame(self, can_id, data):
		can_dlc = len(data)
		data = data.ljust(8, b'\x00')
		return struct.pack(self.can_frame_fmt, can_id, can_dlc, data)

	def dissect_can_frame(self, frame):
		can_id, can_dlc, data = struct.unpack(self.can_frame_fmt , frame)
		return (can_id, can_dlc, data[:can_dlc])
    
	#Send a command, but do not wait to receive a response    
	def send_command(self, posID= 4321, ccom=8, data=''):
		try:

			ext_id_prefix = '8'		
			
			posID2 = ext_id_prefix + (hex(posID).replace('0x','')+hex(ccom).replace('0x','').zfill(2)).zfill(7)			
			posID2 = int(posID2,16)
			data=data.replace(',','')
			
			self.s.send(self.build_can_frame(posID2, bytearray.fromhex(data)))
			
			time.sleep(.2)
			
		except socket.error:
			print('Error sending CAN frame')
		return
   

	#Send a command and wait to receive a response from the positioner
	def send_command_recv(self, posID= 4321, ccom=8, data=''):
		try:

			ext_id_prefix = '8'						#this is the extended id prefix
			
			posID2 = ext_id_prefix + (hex(posID).replace('0x','')+hex(ccom).replace('0x','').zfill(2)).zfill(7)			
			posID2 = int(posID2,16)
			data=data.replace(',','')
			
			self.s.send(self.build_can_frame(posID2, bytearray.fromhex(data)))
			
			time.sleep(.2)
			
			
			cf, addr = self.s.recvfrom(24)
					
			can_id, can_dlc, data = self.dissect_can_frame(cf)
			can_id=can_id-0x80000000				#remove extended id prefix to give just a can id
			intid=str(can_id)
			
			return (int(intid) , data)
			
		except socket.error:
			print('Error sending CAN frame')
		return 
   






	



 

