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
	"""	Class for communicating with the DESI fiber positioner control (FPC) electronics
		through Systec module via SocketCAN.
	"""
	__sleeptime = 0.	# sleep time after sending CAN command (in seconds) -- Joe found needed 0.2 sec here for consistent operation 2016-04-14
						# For FW 2.1 and later the sleep time can be safely set to 0 (MS 2016-
	can_frame_fmt = "=IB3x8s"
	#Create CAN socket and bind to interface channel='canX'
	def __init__(self, channel='can0'):
		
		try:	
			self.channel = channel
			self.s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)		
			self.s.bind((channel,))
			self.s.settimeout(10)	#give up on receiving resonse from positioner ater this amount of time in seconds	
		except socket.error:
			print('Error creating and/or binding socket')
		return		

	def __close__(self):
		self.s.close()
	
	def build_can_frame(self, can_id, data):
		"""
		Convinience function for CAN frame packing/unpacking (see `struct can_frame` in <linux/can.h>)
		"""
		can_dlc = len(data)
		data = data.ljust(8, b'\x00')
		return struct.pack(self.can_frame_fmt, can_id, can_dlc, data)

	def dissect_can_frame(self, frame):
		"""
		Convinience function for CAN frame packing/unpacking (see `struct can_frame` in <linux/can.h>)
		"""
		can_id, can_dlc, data = struct.unpack(self.can_frame_fmt , frame)
		return (can_id, can_dlc, data[:can_dlc])
	 
	def send_command(self, posID = 0, ccom=8, data=''):
		"""
		Sends a CAN command. Does not wait to receive a response
		"""
		ext_id_prefix='8'
		try:
			posID = ext_id_prefix+(hex(posID).replace('0x','')+hex(ccom).replace('0x','').zfill(2)).zfill(7)
			posID = int(posID,16)
			data=data.replace(',','')		
			self.s.send(self.build_can_frame(posID, bytearray.fromhex(data)))			
			time.sleep(self.__sleeptime)
			return 'SUCCESS'
		except socket.error:
			print('Error sending CAN frame in send_command')
			return 'FAILED' 
   
	def send_command_byte(self, posID = 0, ccom=8, data=''):
		"""
		Sends a CAN command. Does not wait to receive a response
		"""
		ext_id_prefix='8'
		try:
			posID = ext_id_prefix+(hex(posID).replace('0x','')+hex(ccom).replace('0x','').zfill(2)).zfill(7)
			posID = int(posID,16)
#			data=data.replace(',','')
			self.s.send(self.build_can_frame(posID, data))
			time.sleep(self.__sleeptime)
			return 'SUCCESS'
		except socket.error:
			print('Error sending CAN frame in send_command_byte')
			return 'FAILED'

	def send_command_recv(self, posID= 4321, ccom=8, data=''):
		"""
		Sends a CAN command. Does wait to receive a response from the positioner
		"""

		try:
			posID_int = posID
			ext_id_prefix = '8'						#this is the extended id prefix			
			posID = ext_id_prefix + (hex(posID).replace('0x','')+hex(ccom).replace('0x','').zfill(2)).zfill(7)			
			posID = int(posID,16)
			data=data.replace(',','')
			
			self.s.send(self.build_can_frame(posID, bytearray.fromhex(data)))
			
			time.sleep(self.__sleeptime)
			try:			
				cf, addr = self.s.recvfrom(24)
			except socket.timeout:
				print('Socket timeout error: positioner probably did not respond.  Check that it is connected, power is on, and the CAN id is correct.  Problem with canid, busid: ', posID_int, self.channel)
				return('FAILED: can_id, bus_id: ', posID_int, self.channel)
			can_id, can_dlc, data = self.dissect_can_frame(cf)
			can_id=can_id-0x80000000				#remove extended id prefix to give just a can id
			intid=str(can_id)			
			return (int(intid) , data)
		except socket.error:
			
			print('Error sending CAN frame in send_command_recv')
			return 'FAILED' 






	



 

