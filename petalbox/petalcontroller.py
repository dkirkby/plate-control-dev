#!/usr/bin/env python3.4

"""
   DOS device application to control the DESI positioner petal
   Features:
	 scan canbus and build posid map  (tpd)
	 implement the functions from petalcomm.py

   Commands:
   get_device_status   ....
   get_fiducial_status
   (complete list)

   Shared Variables:
   none

   Version History
   2/29/2016    MS, KH      Initial version
   1/30/2016    MS, KH      set_led (test) function added
   3/07/2016    MS, IG      added send_tables
   3/08/2016    MS, IG      rewrote load_rows; added load_rows_angle, load_table_rows
   3/24/2016    IG          filled in set_fiducials

"""

from DOSlib.application import Application
import time
import threading
import posfidcan
import ptltel
from configobj import ConfigObj
import sys


def set_bit(value, bit):
	return value | (1<<bit)

def nint(value):
	return int(round(value))

class PetalController(Application):
	"""
	PetalController inherits the DOS (device/application) framework
	init() is called by the framework during initialization
	main() is the runtime loop
	when main returns, the entire calibration exits
	"""
   
	# List of remotely accessible commands
	commands = ['set_led',				# implemented - usefull for testing (of rev 2 positioner boards)
				'set_device',			 
				'get_fid_status',
				'get_device_status', 
				'get_pos_status', 
				'set_fiducials',
				'set_fiducial',  
				'configure',
				'get_positioner_map',
				'move',					# implemented - usefull for testing 
				'execute_sync',			# implemented
				'send_tables',			# implemented
				'set_posid',
				'get_sids',
				'set_periods',
				'set_currents',
				'ready_for_tables',
				'read_temp_ptl',
				'fan_pwm_ptl',
				'switch_en_ptl']

	# Default configuration (can be overwritten by command line or config file)
	defaults = {'default_petal_id' : 1,
				'controller_type' : 'HARDWARE',
				}

	def init(self):
		"""
		Initialize PetalController application. Set up variables, call configure
		"""
		self.info('INITIALIZING Device %s' % self.role)
		self.loglevel('INFO')
		# Get configuration information (add more configuration variables as needed)
		try:
			self.default_petal_id = int(self.config['default_petal_id'])
		except:
			self.default_petal_id = self.default['default_petal_id']
		self.controller_type = self.config['controller_type']
		
		# Bring in the Positioner Move object

		self.pmc=PositionerMoveControl(self.role)
		self.pt = ptltel.PtlTelemetry()

		self.status = 'INITIALIZED'
		self.info('Initialized')
		# call configure to setup the posid map
		retcode = self.configure('constants = DEFAULT')
		self.verbose=True

	def configure(self, constants = 'DEFAULT'):
		"""
		configure petal controller,
		scan canbus to setup posid map
		"""
		print('configuring...')
		self.status = 'READY'
		return self.SUCCESS
	
# PML functions (functions that can be accessed remotely)

	def __get_canbus(self, posid):
		"""
		Maps the positioner ID to a canbus
		For right now we only have one CAN bus (ProtoDESI) and we map
		it to that. Get the CAN bust number from petalcontroller.ini
		"""
		config=ConfigObj('petalcontroller.ini')
		role=config['role']
		config=ConfigObj('petalcontroller.conf')
		canlist=config['CAN'][role]['canlist']
		print("CAN configured...canlist: ",canlist)
		return canlist[0]

	def get_positioner_map(self):
		pass

	def get_sids(self, canbus):
		"""
		Send the command to get silicon IDs
		""" 
		retcode = self.pmc.get_sids(canbus)

		if retcode:
			return self.SUCCESS  
		else:
			return self.FAILED	

	def set_posid(self, canbus, sid, new_posid):
		"""
		Send the command to set positioner ID based on silicon IDs
		""" 
		retcode = self.pmc.set_posid(canbus,sid,posid)

		if retcode:
			return self.SUCCESS  
		else:
			return self.FAILED


	def read_temp_ptl(self):
		"""
		Returns dictionary of temperatures in degrees C, by temp. sensor id.  eg. {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}, number of entries depends
                on the number of 1-wire devices detected on P8_07 		

		"""

		try:	
			temps = self.pt.read_temp_sensors()

		except:
			return self.FAILED

		return temps

	def fan_pwm_ptl(self, pwm_out, percent_duty):
		"""
		Set PWM duty cycle for fan or aux pwm.
	
		INPUTS
			pwm_out		string: 'GFA_FAN1', 'GFA_FAN2', 'PWM_AUX1', or 'PWM_AUX2')
			percent_duty	float 0. to 100., 0. = off

		RETURNS
			SUCCESS OR FAILED	
		
		"""
		try:
			self.pt.control_pwm(str(pwm_out), percent_duty)

		except:
			return self.FAILED

		return self.SUCCESS

	def switch_en_ptl(self, pin_name = "SYNC", state = 0):
		"""
		Switch state of Beaglebone GPIO outputs (power supply enables, fan enables, etc.)

		INPUTS
			pin_name	string, eg. "GFA_FAN1"
			state		int 0, or 1 (0 = off, 1 = on)

		RETURNS
			SUCCESS or FAILED


		PIN NAMES

                        #Outputs
                        "SYNC" = "P9_12"
                        "PS1_EN" = "P9_11"
                        "PS2_EN" = "P9_13"
                        "GFA_FAN1" = "P8_12"
                        "GFA_FAN2" = "P8_14"
                        "GFAPWR_EN" = "P8_15"

		"""
	 
		try:
			self.pt.switch(pin_name, state)
		except:
			return self.FAILED

		return self.SUCCESS



	def set_fiducial(self, posid, percent_duty):
		"""
		Set the ficucial power levels (between 0. and 100.). Inputs less than 0. or
		greater than 100. are automatically set to 0. and 100., respectively.


		INPUT
			ids          	integer fiducial id
			percent_duty 	float (int accepted) 0. to 100.  0.  (or 0) = off
							[note: granularity is 100./65536 = 0.00153]
		RETURNS
			SUCCESS or error message			
		"""

		try:
			if percent_duty < 0.: percent_duty=0.
			if percent_duty > 100.: percent_duty=100.
		except:
			return self.FAILED

		try:
			canbus=self.__get_canbus(posid)
		except:
			return self.FAILED
		
		if not self.pmc.set_fiducial(canbus, posid, percent_duty):
			if self.verbose: print('set_fiducial: Error setting fiducial with id'+str(posid))
			return self.FAILED

		return self.SUCCESS

	def set_fiducials(self, ids, percent_duty):
		"""
		Set the ficucial power levels and period
		Inputs include list with percentages, periods and ids
		Returns SUCCESS or error message.
		canbus	     ... string that specifies the can bus number, eg. 'can2'
		ids          ... list of fiducial ids
		percent_duty ... list of values, 0-100, 0 means off
		
		"""
		if not isinstance(ids, list) or not isinstance(percent_duty,list):
			rstring = 'set_fiducials: Invalid arguments'
			self.error(rstring)
			return 'FAILED: ' + rstring
	
		for id in range(len(ids)):
			# assemble arguments for canbus/firmware function
		
			posid=int(ids[id])
			print(posid)
			canbus=self.__get_canbus(posid)
			print(canbus)
			duty = int(percent_duty[id])
			
		
			if not self.pmc.set_fiducials(canbus, posid, duty):
					if self.verbose: print('set_fiducials: Error')
					return self.FAILED

			if self.verbose:  print('ID: %s, Percent %s' % (ids[id],percent_duty[id]))
		return self.SUCCESS
	
	def send_tables(self, move_tables):
		"""
		Sends move table over CAN to the positioners. 
		See method "hardware_ready_move_tables" in class PosArrayMaster for definition of the
		move_tables format. 

		The definition below was copied over from "hardware_ready_move_tables" for local reference.

		Move table format:
			List of dictionaries.

			Each dictionary is the move table for one positioner.

			The dictionary has the following fields:
				{'posid':'','nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}

			The fields have the following types and meanings:

				posid         ... string                    ... identifies the positioner by 'SERIAL_ID'
				nrows         ... unsigned integer          ... number of elements in each of the list fields (i.e. number of rows of the move table)
				motor_steps_T or
				motor_steps_P ... list of signed integers   ... number of motor steps to rotate
																	... motor_steps_X > 0 ... ccw rotation
																	... motor_steps_X < 0 ... cw rotation
				speed_mode_T or
				speed_mode_P  ... list of strings           ... 'cruise' or 'creep'
				movetime      ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
				postpause     ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
		"""
	 
		# here we need to assemble list of rows and then loop calls to load_rows
		# def load_rows(self, posid, ex_code, mode_select, angle, pause):
		print("*** tables***")
		print(move_tables)
		for table in move_tables:  # each table is a dictionary
			posid=int(table['canid'])
			canbus=self.__get_canbus(posid)
			nrows=table['nrows']
			xcode = '1'
			print("** nrows **"+str(nrows))   #for each table, xcode starts as 1
			for row in range(nrows):
				motor_steps_T=table['motor_steps_T'][row]
				motor_steps_P=table['motor_steps_P'][row]
				speed_mode_T=table['speed_mode_T'][row]
				speed_mode_P=table['speed_mode_P'][row]
				post_pause=nint(table['postpause'][row]) + nint((table['move_time'][row])*1000)

				if (motor_steps_T & motor_steps_P):	#simultaneous movement of theta and phi
					post_pause_T = 0 		#first axis command gets sent with 0 post_pause to make firmware perform simultaneous theta/phi move
				else:
					post_pause_T = post_pause		

 
				if self.verbose: print("send_tables:",  canbus, posid,xcode,'theta',motor_steps_T,speed_mode_T,post_pause)
				if self.pmc.load_table_rows(canbus, posid,xcode,'theta',motor_steps_T,speed_mode_T,post_pause_T):
					if self.verbose: print('send_tables: Error')
					return self.FAILED
				if row == (nrows - 1):  #last row in move table, xcode = 2
					xcode='2'
				if self.pmc.load_table_rows(canbus, posid,xcode,'phi',motor_steps_P,speed_mode_P,post_pause):
					if self.verbose: print('send_tables: Error')
					return self.FAILED

		#if self.verbose: print('send_tables: %s' % repr(move_tables))
		return self.SUCCESS


	def move(self, posid, direction, move_mode, motor, angle ):
		"""
		Sends single move and executes. This function is usually used from console.
		
		INPUTS
			direction: string, 'cw', 'ccw'
			move_mode: string, 'cruise', 'creep'
			motor: string,'theta', 'phi'
			angle: float, angle (in degrees) # question: what happens if direction and angle are opposite?
		"""
		xcode='0' # single command
		pause=0

		if self.verbose: print(posid,direction,move_mode,motor,angle)

		# make sure the passed arguments are valid 
		direction=direction.lower()
		if direction not in ['cw','ccw']:
			rstring = 'move: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring

		move_mode=move_mode.lower()    
		if move_mode not in ['creep','cruise','pause']:
			rstring = 'move: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		
		motor=motor.lower()
		if motor not in ['theta','phi']:
			rstring = 'move: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring

		mode=(direction,move_mode,motor)
		canbus = self.__get_canbus(posid)

		retcode=self.pmc.load_rows_angle(canbus, posid, xcode, mode, angle, pause)

		return self.SUCCESS

	def execute_sync(self, mode='hard'):
		"""
		Send the command to synchronously begin move sequences to all positioners
		on the petal simultaneously.
		mode='hard': Uses the hardware sync pin as the start signal.
		mode='soft': Using CAN command as the start signal.
		"""
		mode=mode.lower()
		canbus = self.__get_canbus(20000)
		

		if mode not in ['hard','soft']:
			rstring = 'execute_sync: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		if mode == 'hard':
			print ("This functionality is not yet implemented")
			pass
		if mode == 'soft':
			self.pmc.send_soft_sync(canbus , 20000)
			pass

		return self.SUCCESS   

	def set_led(self, posid, state):
		"""
		Send the command to set positioner LED ON or OFF
		""" 
		if not isinstance(posid,int):
			rstring = 'set_led: Invalid posid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		if state.lower() not in ['on','off']:
			rstring = 'execute_sync: Invalid LED state arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		# call canbus function
		canbus = self.__get_canbus(posid)
		retcode = self.pmc.set_reset_leds(canbus, posid, state.lower())
		# do anything with retcode?
		if retcode:
			return self.SUCCESS  
		else:
			return self.FAILED

	def set_currents(self, posid, P_currents, T_currents):
		canbus = self.__get_canbus(posid)

		retcode=self.pmc.set_currents(canbus, posid, P_currents, T_currents)		
		if retcode:
			return self.FAILED  
		else:
			return self.SUCCESS

	def set_periods(self, can_id, creep_period_m0, creep_period_m1, spin_period):
		canbus = self.__get_canbus(can_id)
		print(canbus)
		retcode=self.pmc.set_periods(canbus, can_id, creep_period_m0, creep_period_m1, spin_period)
		if retcode:
			return self.FAILED
		else:
			return self.SUCCESS

	def set_pos_constants(self, posids, settings):
		"""
		Sets positioners identified by ids in the list posids to corresponding
		settings in the (dictionary? list of dicts?) settings.
		"""
		print('set_pos_constants: ids = %s, settings = %s' % (repr(posids), repr(settings)))
		return self.SUCCESS

	def set_device(self, posid, attributes):
		"""
		Set a value on a device other than positioners or fiducials. This includes
		fans, power supplies, and sensor
		"""
		print('set_device: ', repr(posid), repr(attributes))
		return self.SUCCESS

	def get_device_status(self,posid):
		"""
		[To be done: Returns a (dictionary?) containing status of all positioners on the petal.]
		For now this function returns a status of 'BUSY' or 'DONE' for a single
		positioner with ID <posid>.
		"""
		#status=self.pmc.get_pos_status(posids)
		return status


	def get_fid_status(self):
		"""
		Returns a dictionary containing status of all fiducials on the petal.
		"""
		status ={'osu' : 34, 'michigan' : 3}
		return status

	def get_pos_status(self,posids):
		"""
		Returns a (dictionary?) containing status of all devices other than positioners
		and fiducials on the petal. This includes fans, power supplies, and sensors.
		"""
		print("<in get_pos_status>")
		canbus = self.__get_canbus(posids[0])
		retcode=self.pmc.get_pos_status(canbus,posids)
		
		return retcode

	def ready_for_tables(self,posids):
		status=False
		dev_status=self.get_pos_status(posids)
		for posid in dev_status:
			if dev_status[posid] == 'DONE':
				status=True
			else:
				status=False
				return status
		return status
	
	def main(self):
		while not self.shutdown_event.is_set():
			# Nothing to do
			time.sleep(1)

		print('Device exits')

######################################

class PositionerMoveControl(object):
	#can_frame_fmt = "=IB3x8s"
	#gear_ratio = {}
	#gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
	#gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
	#gear_ratio['faulhaber'] = 256.0          # faulhaber "256:1", output rotation/motor input

	"""
		INPUTS
			canlist: list of canbuses (strings). Example: canlist=['can0','can2']
	"""

	def __init__(self,role):
		self.verbose=True #False
		self.role=role
		self.__can_frame_fmt = "=IB3x8s"
		canlist=self.get_canconfig('canlist')
		self.pfcan={}
		print("**** canlist ***",canlist)
		for canbus in canlist:
			if self.verbose: print("canbus: "+canbus)
			self.pfcan[canbus]=posfidcan.PosFidCAN(canbus)
		self.Gear_Ratio=(46.0/14.0+1)**4 # gear_ratio for Namiki motors
		self.bitsum=0
		self.cmd={'led':5} # container for the command numbers 'led_cmd':5  etc.
		self.posid_all=20000

	def get_canconfig(self,para):
		"""
			Reads a list of can buses from the petalcontroller.config file. The file is expected to be
			in the same directory as petalcontroller.py
		"""

		if para not in ['canlist']:
			return 'FAILED'
		
		if para == 'canlist':
			try:
				cconfig=ConfigObj('petalcontroller.conf')
				canlist= cconfig['CAN'][self.role]['canlist']
				del cconfig
				return canlist
			except:
				print ("Error reading petalcontroller.conf file")
				return 'FAILED'


	def get_sids(self, canbus):
		"""
			Reads and returns silicon ID from microcontroller. 
		"""	
		posid=self.posid_all
		try:        
			sids=self.pfcan[canbus].send_command(posid,19, '')
			if self.verbose: print (">>>sids: ",sids)
			return True
		except:
			return False   

	def set_posid(self, canbus, sid, new_posid):
		"""
			Sets the positioner ID (CAN address). 
		"""	
		try:
			self.pfcan[canbus].send_command(posid,24, '')        
			self.pfcan[canbus].send_command(posid,19, '')
			return True
		except:
			return False  		


	def set_reset_leds(self, canbus, posid, state):
		
		"""
			Constructs the command to set the status of the test LED on the positioner board.
			Note: The LED will not be installed on production boards and this method will depreciate. 
		
			state:  'on': turns LED ON
					'off': turns LED OFF
			INPUTS
				canbus: string, can bus (example 'can2')        
		"""

		#onoff={'on':1,'off':0}
		select ={'on':1,'off':0}[state]

		print("set leds >>> canbus,posid,select",canbus,posid,select)
		try:        
			self.pfcan[canbus].send_command(posid,5, str(select).zfill(2))
			return True
		except:
			return False  

	def set_fiducials(self, canbus, posid, percent_duty):
		
		"""	Constructs the command to send fiducial control signals to the theta/phi motor pads.
			This also sets the device mode to fiducial (rather than positioner) in the firmware.

			INPUTS
				canbus: 		string, can bus (example 'can2')        
				posids:  		int, positioner id (example 1008)
				percent_dutys: 	list of floats, percent duty cycle of waveforms going to the 
								theta/phi pads (example .5)
				duty_periods:  	list of float or int, period of waveforms going to theta/phi 
								pads in ms (example 20 or 0.05)
		"""

		device_type = '01'  #fiducial = 01, positioner = 00
		duty = str(hex(int(65535.*percent_duty/100)).replace('0x','')).zfill(4)
		TIMDIV = '0FA0'
		#TIMDIVint = int(duty_period*72000.)
		#TIMDIV = str(hex(TIMDIVint).replace('0x', '')).zfill(8) 
		#if(TIMDIVint <= 1650):
		#	return False
		print(canbus, posid, 16, device_type + duty + TIMDIV)
		try:        
			
			self.pfcan[canbus].send_command(posid, 16, device_type + duty + TIMDIV)
			return True
		except:
			return False 

	def set_fiducial(self, canbus, posid, percent_duty):
		
		"""
			Constructs the command to send fiducial control signals to the theta/phi motor pads.
			This also sets the device mode to fiducial (rather than positioner) in the firmware.

			INPUTS
				canbus: 		string, can bus (example 'can2')        
				posid:  		int, positioner id (example 1008)

		"""

		device_type = '01'  #fiducial = 01, positioner = 00
		duty = str(hex(int(655.35*percent_duty)).replace('0x','')).zfill(4)
		#TIMDIVint = int(duty_period*72000.)
		#TIMDIV = str(hex(TIMDIVint).replace('0x', '')).zfill(8)
		TIMDIV ='0FA0' # hardcode this for the time being to 55 microsec. 
		#if(TIMDIVint <= 1650):
		#	print("Duty period too small") 
		#	return False 
		#print(">>>",canbus, posid, 16, device_type + duty + TIMDIV)
		try:        
			self.pfcan[canbus].send_command(posid, 16, device_type + duty + TIMDIV)
			return True
		except:
			return False 		


	def execute_sync(self, canbus, posid, mode):
		
		"""
			Constructs the command to set the status of the test LED on the positioner board.
			Note: The LED will not be installed on production boards and this method will depreciate. 
		
			mode:  'hard, soft'
					
			INPUTS
		"""
		mode='soft'
		try:        
			self.pfcan[canbus].send_command(posid,7, '')
			return True
		except:
			return False   


	def send_soft_sync(self, canbus, posid):
		
		"""
		Signals the positionrs to start execution of move tables.	      
		"""

		try:        
			self.pfcan[canbus].send_command(posid,7, '')
			return True
		except:
			return False  		


	def get_pos_status(self, canbus, posids):
		
		"""
		Signals the positionrs to start execution of move tables.	      
		"""
		status={}
		for posid in posids:
			posid=int(posid)
			status[posid]='UNKNOWN'
			try:        
				posid_return,stat=self.pfcan[canbus].send_command_recv(posid,13,'')
				print("posid_return,stat:",posid_return,stat)
				stat=ord(stat)
				if stat: status[posid]='BUSY'
				if not stat: status[posid]='DONE'
			except:
				return False
		return status		 


	def set_currents(self,canbus, posid, P_currents, T_currents):
		"""
			Sets the currents for motor 0 (phi) and motor 1 (theta).
			Currents are entered as percents (e.g. spin current = 70, cruise_current = 50, creep_current = 30)
		"""   

		spin_current_m0 ,cruise_current_m0 ,creep_current_m0 ,hold_current_m0 = P_currents
		spin_current_m1 ,cruise_current_m1 ,creep_current_m1 ,hold_current_m1 = T_currents

		spin_current_m0 = str(hex(spin_current_m0).replace('0x','')).zfill(2)
		print(spin_current_m0)
		cruise_current_m0 = str(hex(cruise_current_m0).replace('0x','')).zfill(2)
		creep_current_m0 = str(hex(creep_current_m0).replace('0x','')).zfill(2)
		hold_current_m0 = str(hex(hold_current_m0).replace('0x','')).zfill(2)   
		m0_currents = spin_current_m0 + cruise_current_m0 + creep_current_m0 + hold_current_m0
		print(m0_currents)
		spin_current_m1 = str(hex(spin_current_m1).replace('0x','')).zfill(2)
		cruise_current_m1 = str(hex(cruise_current_m1).replace('0x','')).zfill(2)
		creep_current_m1 = str(hex(creep_current_m1).replace('0x','')).zfill(2)
		hold_current_m1 = str(hex(hold_current_m1).replace('0x','')).zfill(2)           
		m1_currents = spin_current_m1 + cruise_current_m1 + creep_current_m1 + hold_current_m1
		print(m1_currents)
		try:
			self.pfcan[canbus].send_command(posid,2,m0_currents + m1_currents)
			return 0
		except:
			return 1   

	def set_periods(self, canbus, posid, creep_period_m0, creep_period_m1, spin_period):
		"""
			canbus - string that specifies the canbus, eg. 'can2'
			posid - int, positioner id, eg. 20000
			creep_period_m0 - e.g. period = 5: 18,000/3600/5 = 1 rev/sec = 60 rpm creep rate
			creep_period_m1 - e.g period=5: 18,000/3600/5 = 1 rev/sec = 60 rpm creep rate
			spin_period - Number of times to repeat each angular diplacement in spin-up table
		"""

		print(posid)
		posid = int(posid)
		print(canbus)      
		creep_period_m0=str(hex(creep_period_m0).replace('0x','')).zfill(2)
		creep_period_m1=str(hex(creep_period_m1).replace('0x','')).zfill(2)
		spin_steps=str(hex(spin_period).replace('0x','')).zfill(2)
		
		if self.verbose: print("Data sent: %s" % creep_period_m0+creep_period_m1+spin_steps)
		try:
			self.pfcan[canbus].send_command(posid,3,creep_period_m0 + creep_period_m1 + spin_steps)
			return 0

		except:
			print ("Sending command 3 failed")
			return 1  

	

	def load_table_rows(self, canbus, posid, xcode, motor, motor_steps, speed_mode, post_pause):
		"""
			Wrapper that will call load_rows

			INPUTS
				posid: integer, CAN address (also sometimes called CAN ID)
				motor: string, 'theta' or 'phi'
				motor_steps:  
				speed_mode:
				post_pause:
			
		"""            
 
		mode=['cw',None,None]
		if motor_steps == 0:
			mode[0] = 'pause_only'
		else:
			if motor_steps < 0 :
				mode[0] = 'ccw'
				motor_steps = abs(motor_steps)
		mode[1] = speed_mode
		mode[2] = motor
		mode=(mode[0],mode[1],mode[2])
   
		try:
			if self.load_rows(canbus, posid, xcode, mode, motor_steps , post_pause):
				return 1
			else:
				return  0
		except:
			print("Error loading table row!")
			return 1

	def load_rows_angle(self, canbus, posid, xcode, mode, angle, pause):
		""" 
			Provides a wrapper to call load_rows with an angle instead with motor steps.
			This is handy for console commands'
			INPUTS
				posid: CAN ID
				xcode: string, execution code('0': immediate, '1': store row as part of move table, '2': last row)
				mode: tupel of strings, ('cc' or 'ccw', 'cruise' or 'creep' or 'pause', 'theata' or 'phi')
				angle: float (degree)
				pause: integer (milliseconds)
		"""
		
		speed_mode=mode[1]

		if speed_mode == 'creep':  
			motor_steps = nint(angle*self.Gear_Ratio/.1)
		if speed_mode == 'cruise':
			motor_steps = nint(angle*self.Gear_Ratio/3.3)
      
		self.load_rows(canbus, posid, xcode, mode, motor_steps, pause)
			    


	def load_rows(self, canbus, posid, xcode, mode, motor_steps, pause):
		"""
			Sends rows (row = single CAN command) over CAN bus; calculates checksum and sends command including
			calculated checksum to firmware.

			INPUTS
				posid: integer, CAN address (also sometimes called CAN ID)
				excode: string, specifies how to process each row of move table (0,1,2)
								'0': command is executed immediately, i.e. not stored as part of move table on microcontrolelr
								'1': any command in movetable which is not the last one
								'2': last command, i.e end of move table
				mode: tuple, specifies mode of motion (ccw or cw, cruise or creep) and motor (theta = motor 1, phi = motor 0)               
						example select =(cw,creep,theta)
						cw_cruise_0 = 2, ccw_cruise_0 = 3, cw_cruise_1 = 6, 
						ccw_cruise_1 = 7, cw_creep_0 = 0, ccw_creep_0 = 1,
						cw_creep_1 = 4,  ccw_creep_1 = 5, pause_only = 8)
				motor_steps: positive integer
				pause: integer, time to pause after current command (i.e. before next command is executed) in milliseconds   
		"""
		
		if self.verbose: print ("load_rows: canbus,posid,xcode,mode,motor_steps,pause",canbus, posid, xcode, mode, motor_steps, pause)

		xcode=str(xcode)
		if xcode not in ['0','1','2']:
			print ("Invalid argument for xcode!")
			return 1

		# TBD: error check select tuple
		
		# TBD: error check motor_steps

		# TBD: error check pause, make sure it is positive integer

		s_pause = str(hex(pause).replace('0x','')).zfill(4)  # converts pause into hex string

		#select=dict(cw_cruise_0 = 2, ccw_cruise_0 = 3, cw_cruise_1 = 6, ccw_cruise_1 = 7, cw_creep_0 = 0, ccw_creep_0 = 1, cw_creep_1 = 4,  ccw_creep_1 = 5, pause_only = 8)
				
		s_motor_steps=str(hex(int(motor_steps)).replace('0x','').zfill(6)) # convert to hex string


		select=0
		if mode[1] == 'pause_only':
			select=8
		else:
			if mode[0] == 'ccw':
				select=set_bit(select,0)
			if mode[1] == 'cruise':
				select=set_bit(select,1)    
			if mode[2] == 'theta':
				select=set_bit(select,2)
		s_select=str(select)  

		# this is send for xcode 0,1,2 i.e. always
		try:
			hexdata=str(xcode + s_select + s_motor_steps + s_pause)            
			if self.verbose: print('Data sent is: %s (in hex)'%(hexdata))
			if self.verbose: print(canbus,posid) 
			self.pfcan[canbus].send_command(posid, 4, hexdata)  
		except:
			print ("Sending command 4 failed")
			return 1

		if xcode == '1': # increment bitsum if xcode=1 
			data=int(xcode + s_select,16) + int(s_motor_steps,16) + int(s_pause,16) + 4                             
			self.bitsum += data
			#print(str(hex(data).replace('0x','').zfill(8)))
			#print('Bitsum =', self.bitsum)
			return 0

		if xcode == '2': #else:
		#Send both last command and bitsum, reset bitsum for next move table    
			try:
				data=int(xcode + s_select,16) + int(s_motor_steps,16) + int(s_pause,16) + 4
				self.bitsum += data
				#print('Bitsum =', self.bitsum)                
				posid_return,stat=self.pfcan[canbus].send_command_recv(posid, 8, str(hex(self.bitsum).replace('0x','').zfill(8)))
				self.bitsum=0
				
				move_table_status = stat[4]
				if move_table_status != 1:
					print("Did not receive checksum match after sending a move table")
					return 1
				else:
					return 0	
			except:
				print ("Sending command 9 failed")
				return 1

		if xcode == '0':
			return 0

######################################

if (__name__ == '__main__'):
	p = PetalController(device_mode=True, service='PetalControl')
	p.run()
	sys.exit()

