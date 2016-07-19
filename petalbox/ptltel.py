#!/usr/local/bin/python3.4
# 
# Class for communication with Beaglebone GPIO headers
# 
# modification history:
# 160617 created (igershko, UM)
# 160719 changed error handling, added functions for reading back GPIO pin state, reading feadback from power supplies,
#        and reading tachometers

import os
import time
import Adafruit_BBIO.GPIO as GPIO
import numpy as np

class PetalTelemetry(object):
	"""	Class for communicating with the DESI petalbox telemetry electronics 
	"""

	def __init__(self):
		
		try:
			os.system('sudo config-pin "P8.13" pwm')
			os.system('sudo config-pin "P8.19" pwm')
			
			GPIO.cleanup()
			
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
			self.pins["CANBRD1_EN"] = "P8_9"
			self.pins["CANBRD2_EN"] = "P8_11"			

			#Inputs
			self.pins["GFA_TACH1"] = "P8_16"
			self.pins["GFA_TACH2"] = "P8_18"
			self.pins["GFAPWR_OK"] = "P8_17"
			self.pins["PS1_OK"] = "P9_14"	#needed to be re-routed or re-multiplexed
			self.pins["PS2_OK"] = "P9_15"	#needed to be re-routed or re-multiplexed

			#PWM
			self.pins["GFA_PWM1"] = "P8_13"
			self.pins["GFA_PWM2"] = "P8_19"

			#Setup
			GPIO.setup(self.pins["SYNC"], GPIO.OUT)
			GPIO.setup(self.pins["PS1_EN"], GPIO.OUT)
			GPIO.setup(self.pins["PS2_EN"], GPIO.OUT)
			GPIO.setup(self.pins["GFA_FAN1"], GPIO.OUT)
			GPIO.setup(self.pins["GFA_FAN2"], GPIO.OUT)
			GPIO.setup(self.pins["GFAPWR_EN"], GPIO.OUT)
			GPIO.setup(self.pins["CANBRD1_EN"], GPIO.OUT)
			GPIO.setup(self.pins["CANBRD2_EN"], GPIO.OUT)			

			GPIO.setup(self.pins["GFA_TACH1"], GPIO.IN)
			GPIO.setup(self.pins["GFA_TACH2"], GPIO.IN)
			GPIO.setup(self.pins["GFAPWR_OK"], GPIO.IN)
			GPIO.setup(self.pins["PS1_OK"], GPIO.IN)
			GPIO.setup(self.pins["PS2_OK"], GPIO.IN)			
			return

		except Exception as e:
			return e
		

	def __cleanup__(self):
		try:
			GPIO.cleanup()
			return
		except Exception as e:
			return e

	def read_GPIOstate(self, pin):
		"""
		Input - pin name
		Returns direction ('in' or 'out') and value of GPIO pin eg. ('out', 1)
		"""

		try:
			state = os.popen('sudo config-pin -q ' + self.pins[pin]).readlines()
			value = state[0].split('Value: ')
			value = int(value[-1].replace('\n',''))			
			direction = state[0].split('Direction: ')
			direction = direction[1][0:3].replace(' ','')  
			return direction, value

		except Exception as e:
			return e

	def read_temp_sensors(self):
		"""
		Returns dict of temperature sensor serial numbers/readings in degrees Celcius
		eg. {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}, number of entries depends 
		on the number of 1-wire devices detected on P8_07
		"""
		try:
			temp_sensors = {}

			#list of all 1-wire ids detected on the bus (P8_07)
			ids = os.popen('cat /sys/devices/w1_bus_master1/w1_master_slaves').readlines()		

			for id in ids:
				id = id.replace('\n', '')
				w1 = '/sys/devices/w1_bus_master1/' + id + '/w1_slave'
				raw = open(w1, 'r').read()
				temp_sensors[id] = float(raw.split("t=")[-1])/1000 		

			return temp_sensors

		except Exception as e:
			return e

	def control_pwm(self, fan= 'GFA_FAN1', duty=50):
		"""
		Change duty cycle (speed control)
		"""

		try: 
			period = 40000   #period in ns (corresponds to 25 KHz fan pwm specification)
			duty = int(400.*duty) #on-time in ns

		
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
				return('FAILED')
	
			return

		except Exception as e:
			return e
 
	def switch(self, pin = "SYNC", state = 0):
		"""
		Switch power to load switches
		"""
		try:
			if state == 1:
				GPIO.output(self.pins[pin], GPIO.HIGH)
			else:
				GPIO.output(self.pins[pin], GPIO.LOW)
			return
			
		except Exception as e:
			return e
		
   
	def read_PSOK(self):
		"""
		Read "DC-OK" signals from HRPG-600 series power supplies.  Returns dictionary, eg: {"PS1_OK" : True, "PS2_OK" : True, "GFAPWR_OK" : True}
		True = Power supply on
		False = Powers supply off
		"""

		PSOK = {}

		try:
			if GPIO.input(self.pins["PS1_OK"]):
				PSOK["PS1_OK"] = True
			else:
				PSOK["PS1_OK"] = False

			if GPIO.input(self.pins["PS2_OK"]):
				PSOK["PS2_OK"] = True
			else:
				PSOK["PS2_OK"] = False

			if GPIO.input(self.pins["GFAPWR_OK"]):
				PSOK["GFAPWR_OK"] = True
			else:
				PSOK["GFAPWR_OK"] = False
			return PSOK
			
		except Exception as e:
			return e

	def read_tach(self, samples):
		"""
		input - samples (int), number of rising edges to wait for
		returns speeds for inflow and outflow fans as dict, eg. {'inlet' : 5000, 'outlet' : 5000}
		"""
		speed_rpm = {}

		try:
			#inlet
			#check if fan is enabled
			fan_state = os.popen('sudo config-pin -q ' + self.pins["GFA_FAN1"]).readlines()
			fan_state = int(fan_state[0][fan_state[0].index('\n')-1])

			t=[]
			
			if fan_state:
				for edge in range(samples):
					GPIO.wait_for_edge(self.pins["GFA_TACH1"], GPIO.RISING)
					t.append(time.time())		

				t=np.array(t)
				diff = np.ediff1d(t)
				
				diff = diff[abs(diff - np.mean(diff) < 1*np.std(diff))]
				diff = np.mean(diff)
				rpm = 60./(diff*2)
				speed_rpm["inlet"] = int(rpm)

			else:
				speed_rpm["inlet"] = 'fan_off'
			

			#outlet
			#check if fan is enabled
			fan_state = os.popen('sudo config-pin -q ' + self.pins["GFA_FAN2"]).readlines()
			fan_state = int(fan_state[0][fan_state[0].index('\n')-1])

			t=[]

			if fan_state:
				for edge in range(samples):
					GPIO.wait_for_edge(self.pins["GFA_TACH2"], GPIO.RISING)
					t.append(time.time())

				t=np.array(t)
				diff = np.ediff1d(t)

				diff = diff[abs(diff - np.mean(diff) < 1*np.std(diff))]
				diff = np.mean(diff)
				rpm = 60./(diff*2)
				speed_rpm["outlet"] = int(rpm)

			else:
				speed_rpm["outlet"] = 'fan_off'

			return speed_rpm

		except Exception as e:
			return e
	



 

