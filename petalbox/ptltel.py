#!/usr/local/bin/python3.4
# 
# Class for communication with Beaglebone GPIO headers
# 
# modification history:
# 160617 created (igershko, UM)

import os
import time
import Adafruit_BBIO.GPIO as GPIO

class PtlTel(object):
	"""	Class for communicating with the DESI petalbox telemetry electronics 
	"""

	def __init__(self):
		
		try:
			os.system('sudo config-pin "P8.13" pwm')
			os.system('sudo config-pin "P8.19" pwm')

			self.pins = {}
			#1-Wire
			self.pins["W1"] = "P8_07"

			#Outputs
			self.pins["SYNC"] = "P9_12"
			self.pins["PS1_EN"] = "P9_11"
			self.pins["PS2_EN"] = "P9_13"
			self.pins["GFA_FAN1"] = "P8_12"
			self.pins["GFA_FAN2"] = "P8_14"
			self.pins["GFAPWR_EN"] = "P8_15"
			
			#Inputs
			self.pins["GFA_TACH1"] = "P8_16"
			self.pins["GFA_TACH2"] = "P8_18"

			#PWM
			self.pins["GFA_PWM1"] = "P8_13"
			self.pins["GFA_PWM2"] = "P8_19"

			GPIO.setup(self.pins["SYNC"], GPIO.OUT)
			GPIO.setup(self.pins["PS1_EN"], GPIO.OUT)
			GPIO.setup(self.pins["PS2_EN"], GPIO.OUT)
			GPIO.setup(self.pins["GFA_FAN1"], GPIO.OUT)
			GPIO.setup(self.pins["GFA_FAN2"], GPIO.OUT)
			GPIO.setup(self.pins["GFAPWR_EN"], GPIO.OUT)

			GPIO.setup(self.pins["GFA_TACH1"], GPIO.IN)
			GPIO.setup(self.pins["GFA_TACH2"], GPIO.IN)
		except:
			print('Error initializing')
		return		

	def __cleanup__(self):
		GPIO.cleanup()
		return
	
	def read_temp_sensors(self):
		"""
		Returns dict of temperature sensor serial numbers/readings in degrees Celcius
		eg. {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}, number of entries depends 
		on the number of 1-wire devices detected on P8_07
		"""
		temp_sensors = {}

		#list of all 1-wire ids detected on the bus (P8_07)
		ids = os.popen('cat /sys/devices/w1_bus_master1/w1_master_slaves').readlines()		

		for id in ids:
			id = id.replace('\n', '')
			w1 = '/sys/devices/w1_bus_master1/' + id + '/w1_slave'
			raw = open(w1, 'r').read()
			temp_sensors[id] = float(raw.split("t=")[-1])/1000 		

		return temp_sensors

	def control_pwm(self, fan= 'GFA_FAN1', duty=50):
		"""
		Change duty cycle (speed control)
		"""

		period = 40000   #period in ns (corresponds to 25 KHz fan pwm specification)
		duty = int(400.*duty) #on-time in ns

		#enable/disable P8_12
		#find path to P8_13, P8_19 pwmchip
		pwmchip = os.popen('ls /sys/devices/platform/ocp/48304000.epwmss/48304200.ehrpwm/pwm/').readlines()
		pwmchip_path = '/sys/devices/platform/ocp/48304000.epwmss/48304200.ehrpwm/pwm/' + pwmchip[0].replace('\n','')

		if fan == 'GFA_FAN1':		#P8_13

			os.system('sudo chmod -R a+rwx ' + pwmchip_path)
			check_export = os.popen('ls ' + pwmchip_path).readlines()
			if 'pwm1\n' not in check_export:
				os.system('echo 1 > '+ pwmchip_path + '/export')  #create pwm1

			os.system('sudo chmod -R a+rwx ' + pwmchip_path) 
			os.system('echo ' + str(period)+ ' > ' + pwmchip_path + '/pwm1/period')
			os.system('echo ' + str(duty) + ' > ' + pwmchip_path + '/pwm1/duty_cycle')
			os.system('echo ' + str(1) +' > ' + pwmchip_path + '/pwm1/enable')			
			
		elif fan == 'GFA_FAN2':		#P8_19

			os.system('sudo chmod -R a+rwx ' + pwmchip_path)

			check_export = os.popen('ls ' + pwmchip_path).readlines()
			if 'pwm0\n' not in check_export:
				os.system('echo 0 > '+ pwmchip_path + '/export')  #create pwm0
			os.system('sudo chmod -R a+rwx ' + pwmchip_path)
			os.system('echo ' + str(period)+ ' > ' + pwmchip_path + '/pwm0/period')
			os.system('echo ' + str(duty) + ' > ' + pwmchip_path + '/pwm0/duty_cycle')
			os.system('echo ' + str(1) +' > ' + pwmchip_path + '/pwm0/enable')
		else:
			print('Error applying fan settings, check arguments!')
	
		return
	
 
	def switch(self, pin = "SYNC", state = 0):
		"""
		Switch power to load switches
		"""
		print(self.pins[pin])
		try:
			if state == 1:
				GPIO.output(self.pins[pin], GPIO.HIGH)
			else:
				GPIO.output(self.pins[pin], GPIO.LOW)
		except:
			print('Error switching power')
		return
   

	def read_tach(self):
		"""
		returns speeds for inflow and outflow fans as dict, eg. {'inflow' : 5000, 'outflow' : 5000}
		"""

		#TODO
		try:
			print('Reading tachometers')
		except:
			print('Error reading tachometers')
		return 

	



 

