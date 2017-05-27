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
import select

class PtlTelemetry(object):
	"""	Class for communicating with the DESI petalbox telemetry electronics 
	"""

	def __init__(self):
		
		modulename=self.__init__.__name__+": "
		try:
			os.system('sudo config-pin "P8.13" pwm')
			os.system('sudo config-pin "P8.19" pwm')

			self.gfa_tach1 = '/sys/class/gpio/gpio46/'
			self.gfa_tach2 = '/sys/class/gpio/gpio65/'
			
			GPIO.cleanup()
			
			self.pins = {}
			self.PWM1 = 0
			self.PWM2 = 0
 
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
			self.pins["BUFF_EN1"] = "P8_10"
			self.pins["BUFF_EN2"] = "P8_8"

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
			GPIO.setup(self.pins["BUFF_EN1"], GPIO.OUT)
			GPIO.setup(self.pins["BUFF_EN2"], GPIO.OUT)			

			GPIO.setup(self.pins["GFA_TACH1"], GPIO.IN)
			GPIO.setup(self.pins["GFA_TACH2"], GPIO.IN)
			GPIO.setup(self.pins["GFAPWR_OK"], GPIO.IN)
			GPIO.setup(self.pins["PS1_OK"], GPIO.IN)
			GPIO.setup(self.pins["PS2_OK"], GPIO.IN)
			
			return

		except Exception as e:
			rstring = modulename + 'Error initializing petal telemetry: %s' %  str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring
		
	def __cleanup__(self):
		modulename=self.__cleanup__.__name__+": "
		try:
			GPIO.cleanup()
			return
		except Exception as e:
			rstring = modulename + 'Error running GPIO cleanup: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring

	def get_GPIO_names(self):
		"""
		Function that returns a dictionary of pin names and descriptions
		"""

		modulename=self.get_GPIO_names.__name__+": "
		try:
			pin_info = {}
			pin_info["W1"] = 'Input (1-wire) pin to which all temperature sensors are connected'
			pin_info["SYNC"] = 'Output pin for sending synchronization signal to positioners'
			pin_info["PS1_EN"] = 'Output pin that enables positioner power supply 1 when set high'
			pin_info["PS2_EN"] = 'Output pin that enables positioner power supply 1 when set high'
			pin_info["GFA_FAN1"] = 'Output for enabling power to GFA fan 1'
			pin_info["GFA_FAN2"] = 'Output for enabling power to GFA fan 2'
			pin_info["GFAPWR_EN"] = 'Output for enabling GFA power supply'
			pin_info["PS1_OK"] = 'Input for reading back feedback signal from positioner power supply 1'
			pin_info["PS2_OK"] = 'Input for reading back feedback signal from positioner power supply 2'
			pin_info["GFAPWR_OK"] = 'Input for reading back feedback signal from GFA power supply'
			pin_info["CANBRD1_EN"] = 'Output for switching power to SYSTEC CAN board 1'
			pin_info["CANBRD2_EN"] = 'Output for switching power to SYSTEC CAN board 2'
			pin_info["GFA_PWM1"] = 'Output (PWM) for controlling GFA_FAN1 speed'
			pin_info["GFA_PWM2"] = 'Output (PWM) for controlling GFA_FAN2 speed'
			pin_info["GFA_TACH1"] = 'Input (pulsed) connected to GFA_FAN1 tachometer sensor'
			pin_info["GFA_TACH2"] = 'Input (pulsed) connected to GFA_FAN2 tachometer sensor'
			pin_info["BUFF_EN1"] = 'Output (active low) for enabling the hardware SYNC'
			pin_info["BUFF_EN2"] = 'Output (active low) for enabling the hardware SYNC'
			return pin_info

		except Exception as e:
			rstring = modulename + 'Error reading pin info: %s' % str(e)
			return 'FAILED: ' + rstring

	def read_pwm(self, device):
		"""
		Function that returns pwm duty cycles on pins "GFA_PWM1" and "GFA_PWM2" as dictionary, eg. {"GFA_PWM1" : 50, "GFA_PWM2" : 20}
		"""
		modulename=self.read_pwm.__name__+": "

		try:
			if device == 'GFA_FAN1':
				pwm = self.PWM1
			elif device == 'GFA_FAN2':
				pwm = self.PWM2
			else:
				rstring = modulename + 'Invalid fan name: %s' % str(device)
				#self.error(rstring)
				return 'FAILED: ' + rstring

			return pwm

		except Exception as e:
			rstring = modulename + 'Error reading PWM state: %s' % str(e)
			return 'FAILED: ' + rstring

	def read_switch(self):
		"""
		Returns dictionary of output pin states
		"""
		modulename=self.read_switch.__name__+": "
		try:
			states = {}
			outputs = ['SYNC', 'GFA_FAN1', 'GFA_FAN2', 'PS1_EN', 'PS2_EN', 'GFAPWR_EN', 'CANBRD1_EN', 'CANBRD2_EN']
			for p in outputs:
				state = os.popen('sudo config-pin -q ' + self.pins[p]).readlines()
				value = state[0].split('Value: ')
				value = int(value[-1].replace('\n',''))			
				#direction = state[0].split('Direction: ')
				#direction = direction[1][0:3].replace(' ','')
				states[p] = value
				  
			return states

		except Exception as e:
			rstring = modulename + 'Error reading GPIO state: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring

	def read_temp_sensors(self):
		"""
		Returns dict of temperature sensor serial numbers/readings in degrees Celcius
		eg. {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}, number of entries depends 
		on the number of 1-wire devices detected on P8_07
		"""
		modulename=self.read_temp_sensors.__name__+": "
		
		temp_sensors = {}

		try:
			#list of all 1-wire ids detected on the bus (P8_07)
			ids = os.popen('cat /sys/devices/w1_bus_master1/w1_master_slaves').readlines()		
		except Exception as e:
			rstring = modulename + 'Error opening 1-wire file: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring

		try:    
			for id in ids:
				id = id.replace('\n', '')
				w1 = '/sys/devices/w1_bus_master1/' + id + '/w1_slave'
				raw = open(w1, 'r').read()
				temp_sensors[id] = float(raw.split("t=")[-1])/1000 		

			return temp_sensors

		except Exception as e:
			rstring = modulename + 'Error reading temp sensors: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring


	def control_pwm(self, fan= 'GFA_FAN1', duty_cycle=50):
		"""
		Change duty cycle (speed control)
		"""
		modulename=self.control_pwm.__name__+": "
 
		period = 40000   #period in ns (corresponds to 25 KHz fan pwm specification)
		duty = int(400.*duty_cycle) #on-time in ns

		try:
			#find path to P8_13, P8_19 pwmchip
			pwmchip = os.popen('ls /sys/devices/platform/ocp/48304000.epwmss/48304200.ehrpwm/pwm/').readlines()
			pwmchip_path = '/sys/devices/platform/ocp/48304000.epwmss/48304200.ehrpwm/pwm/' + pwmchip[0].replace('\n','')
		except Exception as e:
			rstring = modulename + 'Error locating pwmchip: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring
   	

		if fan == 'GFA_FAN1':		#P8_13

			try:
				os.system('sudo chmod -R a+rwx ' + pwmchip_path)
				check_export = os.popen('ls ' + pwmchip_path).readlines()
				if 'pwm1\n' not in check_export:
					os.system('echo 1 > '+ pwmchip_path + '/export')  #create pwm1

				os.system('sudo chmod -R a+rwx ' + pwmchip_path) 
				os.system('echo ' + str(period)+ ' > ' + pwmchip_path + '/pwm1/period')
				os.system('echo ' + str(duty) + ' > ' + pwmchip_path + '/pwm1/duty_cycle')
				os.system('echo ' + str(1) +' > ' + pwmchip_path + '/pwm1/enable')
				self.PWM1 = duty_cycle			
			except Exception as e:
				rstring = modulename + 'Error GFA fan1 control: %s' % str(e)
				#self.error(rstring)
				return 'FAILED: ' + rstring
			
		elif fan == 'GFA_FAN2':		#P8_19

			try:
				os.system('sudo chmod -R a+rwx ' + pwmchip_path)

				check_export = os.popen('ls ' + pwmchip_path).readlines()
				if 'pwm0\n' not in check_export:
					os.system('echo 0 > '+ pwmchip_path + '/export')  #create pwm0
				os.system('sudo chmod -R a+rwx ' + pwmchip_path)
				os.system('echo ' + str(period)+ ' > ' + pwmchip_path + '/pwm0/period')
				os.system('echo ' + str(duty) + ' > ' + pwmchip_path + '/pwm0/duty_cycle')
				os.system('echo ' + str(1) +' > ' + pwmchip_path + '/pwm0/enable')
				self.PWM2 = duty_cycle
			except Exception as e:
				rstring = modulename + 'Error GFA fan2 control: %s' % str(e)
				#self.error(rstring)
				return 'FAILED: ' + rstring

		else:
			rstring = modulename + 'Invalid fan name: %s' % str(fan)
			#self.error(rstring)
			return 'FAILED: ' + rstring

		return 'SUCCESS'

 
	def switch(self, pin = "SYNC", state = 0):
		"""
		Switch power to load switches
		"""
		modulename=self.switch.__name__+": "
		try:
			if state == 1:
				GPIO.output(self.pins[pin], GPIO.HIGH)
			else:
				GPIO.output(self.pins[pin], GPIO.LOW)
		except Exception as e:
			string = modulename + 'Error switch power to load switches: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring
		return 'SUCCESS'
   
	def read_HRPG600(self):
		"""
		Read "DC-OK" signals from HRPG-600 series power supplies.  Returns dictionary, eg: {"PS1_OK" : True, "PS2_OK" : True, "GFAPWR_OK" : True}
		True = Power supply on
		False = Powers supply off
		"""
		modulename=self.read_HRPG600.__name__+": "
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
			string = modulename + 'Error reading HPPG power supply: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring

	def read_fan_tach(self):
		"""
		Returns speeds for inflow and outflow fans as dict, eg. {'GFA_FAN1' : 5000, 'GFA_FAN2' : 5000}
		"""
		modulename=self.read_fan_tach.__name__+": "
		speed_rpm = {}

		if not self.read_switch()['GFA_FAN1']:
			return 'FAILED: Fans must be on.'

		if not self.read_switch()['GFA_FAN2']:
			return 'FAILED: Fans must be on.'

		with open(os.path.join(self.gfa_tach1, 'edge'), 'w') as f:
			f.write('both')

		with open(os.path.join(self.gfa_tach2, 'edge'), 'w') as f:
			f.write('both')
		
		self.ftach1 = open(os.path.join(self.gfa_tach1, 'value'), 'r')
		self.ftach2 = open(os.path.join(self.gfa_tach2, 'value'), 'r')
		self.po1 = select.poll()
		self.po1.register(self.ftach1, select.POLLPRI)
		self.po2 = select.poll()
		self.po2.register(self.ftach2, select.POLLPRI)

		try:
			#GFA_FAN1
			t=[]
			start=time.time()
			end = time.time()
			while abs(start-end) < 1:
				events = self.po1.poll(.5)
				if not events:
					pass
				else:
					t.append(time.time())
					self.ftach1.seek(0)
					pstate = self.ftach1.read()
				end = time.time()
			if len(t) > 1:
				tdiff = np.mean(np.diff(np.array(t)))
				rpm1 = int(60./(4*tdiff))

			else: 
				rpm1 = 'None'

			#GFA_FAN2
			t2=[]
			start=time.time()
			end = time.time()
			while abs(start-end) < 1:
				events2 = self.po2.poll(.5)
				if not events2:
					pass
				else:
					t2.append(time.time())
					self.ftach2.seek(0)
					pstate = self.ftach2.read()
				end = time.time()
			if len(t2) > 1:
				t2diff = np.mean(np.diff(np.array(t2)))
				rpm2 = int(60./(4*t2diff))
			else:
				rpm2 = 'None'

			speed_rpm['GFA_FAN1'] = rpm1
			speed_rpm['GFA_FAN2'] = rpm2

			self.po1.unregister(self.ftach1)
			self.po2.unregister(self.ftach2)

			with open(os.path.join(self.gfa_tach1, 'edge'), 'w') as f:
				f.write('none')

			with open(os.path.join(self.gfa_tach2, 'edge'), 'w') as f:
				f.write('none')

			self.ftach2.close()
			self.ftach1.close()
			
			return speed_rpm

		except Exception as e:
			rstring = modulename + 'Error reading fan speed: %s' % str(e)
			#self.error(rstring)
			return 'FAILED: ' + rstring
	



 

