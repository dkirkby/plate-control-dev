# dlptemp.py
# provides a class for communicating with the DLP-TEMP-G daq board.
# This board can read 3 temperatures via the Dallas Semiconductor
# DS18B20 sensor.
# Please note that two pairs of wires in the Category 5 cable are
# required for the connection. One pair is for power and ground, and
# the other pair is for data and ground.
# For more information and data sheet: http://www.dlpdesign.com
#
# Author: Michael Schubnell, University of Michigan
#
# revision history:
# 140215.MS	created
#
# requires python version: developed under python 2.6 
#
# requires:
# PX_HWCONFPATH must be set to the path for the configuration file
# read by the parser (pxhwserial.conf).
# known issues:
# none
#
from enhancedserial import EnhancedSerial
from enhancedserial import SerialException
import sys
import os
#from configobj import ConfigObj
class DlpTemp(object):	
	def __init__(self,port='/dev/serial/by-id/usb-DLP_Design_DLP-TEMP_01234567-if00-port0',baudrate=9600):
		
		if True: #(instrument != None):			
#			configpath=os.environ.get('PSC_HWCONFPATH')
#			config = ConfigObj(configpath+'hwserial.conf')
			
#			iclass = config[instrument]['iclass']
#			if iclass != 'ReadDlptemp':
#				raise ValueError("The instrument needs to be of class 'dlptemp'")
#			port = config[instrument]['port']
			self.port=port
			self.baudrate=baudrate
#			baudrate = config[instrument]['baudrate']
		try:
			self.esp = EnhancedSerial(self.port,self.baudrate)
		except(SerialException):
			raise IOError("Can't open serial port %s for DLP-TEMP G board" % self.esp.port)
	def __del__(self):
		self.close()
	def __exit__(self):
		self.close()
	def close(self):
		self.esp.close()

	def ping(self):
		self.esp.write('P')
		if self.esp.readline()=='Q':
			return True
		return False

	def read_temp(self,sens):
		sel={'1':'S','2':'T','3':'U'}
		sens=str(sens)
		if sens not in ['1','2','3']:
			return None
		try:
			self.esp.write(sel[sens])
			r=self.esp.readline()
			#print r.encode('hex')
			#print r[0].encode('hex')
			#print int(r[0].encode('hex'),16)
			a=int(r[0].encode('hex'),16)+256*int(r[1].encode('hex'),16)
			#print a
			# need to test msb for neg temperature!!
			if a & 0x8000: # neg. temp 
				a=0x800-a
			temp=float(a)/16.
			if temp==0.0: temp=temp+0.01
		except:
			temp=999.
		return temp


if __name__ == "__main__":
	#print "=== Temperature measurement test ==="
	#a=raw_input("Enter USB port: ")
	#print "Starting temperature measurement on port ",a
	#baudrate=9600
	#port=a
	dlp=DlpTemp() #,port,baudrate)
	
	a=dlp.ping()
	#print "Pinging DLP-TEMP-G board ",a
	

	if a:
		while True:
			x = raw_input('S/s to stop, any key to continue: ')
			if x.upper()=='S':
				sys.exit()
			r=dlp.read_temp(2)	
			print "Temperature S2: ",r
			r=dlp.read_temp(1)	
			print "Temperature S1: ",r
	else:
		print "Can't find temperature sensor module :( "
		sys.exit()

