#!/usr/bin/env python

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
   2/29/2016     MS, KH     Initial version
   1/30/2016     MS, KH     set_led (test) function added
"""

from DOSlib.application import Application
import time
import threading
import posfidcan
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
	comands = ['set_led',
				'set_device', 
				'get_fid_status', 
				'get_device_status', 
				'set_fiducials',  
				'configure',
				'get_positioner_map',
				'send_move_execute',
				'send_table'
				]

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
		self.pmc=PositionerMoveControl()

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

	def set_fiducials(self, ids, percent_duty, duty_period):
		"""
		Set the ficucial power levels and period
		Inputs include list with percentages, periods and ids
		Returns SUCCESS or error message.
		
		ids          ... list of fiducial ids
		percent_duty ... list of values, 0-100, 0 means off
		duty_period  ... list of values, ms, time between duty cycles
		"""
		if not isinstance(ids, list) or not isinstance(percent_duty,list) or not isinstance(duty_period,list):
			rstring = 'set_fiducials: Invalid arguments'
			self.error(rstring)
			return 'FAILED: ' + rstring
	
		for id in range(len(ids)):
			# assemble arguments for canbus/firmware function
			print('ID: %s, Percent %s, Period %s' % (ids[id],percent_duty[id],duty_period[id]))
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

		for table in move_tables:  # each table is a dictionary
			nrows=table['nrows']
			for row in range(nrows):
				motor_steps_T=table['motor_steps_T'][row]
				motor_steps_P=table['motor_steps_P'][row]
				speed_mode_T=table['speed_mode_T'][row]
				speed_mode_P=table['speed_mode_P'][row]
				post_pause=table['postpause'][row]    
				if not load_table_rows(posid,'theta',motor_steps_T,speed_mode_T,post_pause):
					if self.verbose: print('send_tables: Error')
					return self.FAILED
				if not load_table_rows(posid,'phi',motor_steps_P,speed_mode_P,post_pause):
					if self.verbose: print('send_tables: Error')
					return self.FAILED

		if self.verbose: print('send_tables: %s' % repr(move_tables))
		return self.SUCCESS


	def send_move_execute(self, posid, direction, move_mode, motor, angle ):
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


		# make sure the passed arguments are valid 
		direction=direction.lower()
		if direction not in ['cw','ccw']:
			rstring = 'send_move_execute: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring

		move_mode=move_mode.lower()    
		if move_mode not in ['creep','cruise','pause']:
			rstring = 'send_move_execute: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		
		motor=motor.lower() 
		if motor not in ['theta','phi']:
			rstring = 'send_move_execute: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring

		mode=(direction,move_mode,motor)
   
		retcode=self.pmc.load_rows_angle(posid, xcode, mode, angle, pause)

		return self.SUCCESS



	def execute_sync(self, mode='hard'):
		"""
		Send the command to synchronously begin move sequences to all positioners
		on the petal simultaneously.
		mode='hard': Uses the hardware sync pin as the start signal.
		mode='soft': Using CAN command as the start signal.
		"""
		mode=mode.lower()
		if mode not in ['hard','soft']:
			rstring = 'execute_sync: Invalid arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		if mode == 'hard':
			pass
		if mode == 'soft':
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

		retcode = self.pmc.set_reset_leds(posid,state.lower())
		# do anything with retcode?
		if retcode:
			return self.SUCCESS  
		else:
			return self.FAILED

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

	def get_pos_status(self):
		"""
		Returns a (dictionary?) containing status of all positioners on the petal.
		"""
		status ={'osu' : 42, 'michigan' : 6}
		return status

	def get_fid_status(self):
		"""
		Returns a dictionary containing status of all fiducials on the petal.
		"""
		status ={'osu' : 34, 'michigan' : 3}
		return status

	def get_device_status(self):
		"""
		Returns a (dictionary?) containing status of all devices other than positioners
		and fiducials on the petal. This includes fans, power supplies, and sensors.
		"""
		return self.status
	
	def main(self):
		while not self.shutdown_event.is_set():
			# Nothing to do
			time.sleep(1)

		print('Device exits')

######################################

class PositionerMoveControl(object):
	can_frame_fmt = "=IB3x8s"
	gear_ratio = {}
	gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
	gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
	gear_ratio['faulhaber'] = 256.0          # faulhaber "256:1", output rotation/motor input

	def __init__(self):
						
		self.pfcan=posfidcan.PosFidCAN('can2')
		self.Gear_Ratio=(46.0/14.0+1)**4 #gear_ratio['namiki']
		self.bitsum=0
		self.cmd={'led':5} # container for the command numbers 'led_cmd':5  etc.


	def set_reset_leds(self, posid, state):
		
		"""
			Constructs the command to set the status of the test LED on the positioner board.
			Note: The LED will not be installed on production boards and this method will depreciate. 
		
			state:  'on': turns LED ON
					'off': turns LED OFF

		"""

		#onoff={'on':1,'off':0}
		select ={'on':1,'off':0}[state]
		try:        
			self.pfcan.send_command(posid,5, str(select).zfill(2))
			return True
		except:
			return False   


	def set_currents(self,posid, spin_current_m0, cruise_current_m0, creep_current_m0, hold_current_m0, spin_current_m1, cruise_current_m1, creep_current_m1, hold_current_m1):
		"""
			Sets the currents for motor 0 and motor 1.
		"""   
		spin_current_m0 = str(hex(spin_current_m0).replace('0x','')).zfill(2)
		cruise_current_m0 = str(hex(cruise_current_m0).replace('0x','')).zfill(2)
		creep_current_m0 = str(hex(creep_current_m0).replace('0x','')).zfill(2)
		hold_current_m0 = str(hex(hold_current_m0).replace('0x','')).zfill(2)   

		spin_current_m1 = str(hex(spin_current_m1).replace('0x','')).zfill(2)
		cruise_current_m1 = str(hex(cruise_current_m1).replace('0x','')).zfill(2)
		creep_current_m1 = str(hex(creep_current_m1).replace('0x','')).zfill(2)
		hold_current_m1 = str(hex(hold_current_m1).replace('0x','')).zfill(2)           
	
		try:
			self.pfcan.send_command(posid,2,spin_current_m0 + cruise_current_m0 + creep_current_m0 + hold_current_m0 + spin_current_m1 + cruise_current_m1 + creep_current_m1 + hold_current_m1)
			return 0
		except:
			return 1   


	def set_periods(self,posid, creep_period_m0, creep_period_m1, spin_steps):
		"""
			Needs definitions of arguments.
		"""      
		creep_period_m0=str(creep_period_m0).zfill(2)
		creep_period_m1=str(creep_period_m1).zfill(2)
		spin_steps=str(hex(spin_steps).replace('0x','')).zfill(4)
		
		print("Data sent: %s" % creep_period_m0+creep_period_m1+spin_steps)
		try:
			self.scan.send_command(pid,3,creep_period_m0 + creep_period_m1 + spin_steps)
			return 0

		except:
			print ("Sending command 3 failed")
			return 1  

	def load_table_rows(posid,motor,motor_steps,speed_mode,post_pause):
		"""
			Wrapper that will call load_rows

			INPUTS
				posid: integer, CAN address (also sometimes called CAN ID)
				motor: string, 'theta' or 'phi'
				motor_steps:  
				speed_mode:
				post_pause:

				
		"""            

	def load_rows_angle(self, posid, xcode, mode, angle, pause):
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

		if speed_mode == 'creep':   #== 0 or select[select_flags] == 4 or select[select_flags] == 1 or select[select_flags] == 5):
			motor_steps = nint(angle*self.Gear_Ratio/.1)
		if speed_mode == 'cruise':
			motor_steps = nint(angle*self.Gear_Ratio/3.3)      
		self.load_rows(posid, xcode, mode, motor_steps, pause)    


	def load_rows(self, posid, xcode, mode, motor_steps, pause):
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

		#elect_flags=str(select[select_flags])
		#select=str(select)

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

		if xcode in ['1','2']:
			try:
				hexdata=str(xcode + s_select + s_motor_steps + s_pause)            
				print('Data sent is: %s (in hex)'%(hexdata))
				
				self.pfcan.send_command(posid, 4, hexdata)                
 
				if xcode == '1':   
					data=int(xcode + s_select,16) + int(s_motor_steps,16) + int(s_pause,16) + 4
					print(str(hex(data).replace('0x','').zfill(8)))                                      
					self.bitsum += data
					print('Bitsum =', self.bitsum)

				return 0
	
			except:

				print ("Sending command 4 failed")
				return 1
		else:
		#Send both last command and bitsum, reset bitsum for next move table    
			try:
				hexdata=str(xcode + s_select + s_motor_steps + s_pause)
				print('Data sent is: %s (in hex)'%(hexdata))
				self.pfcan.send_command(posid, 4, hexdata)
				data=int(xcode + s_select,16) + int(s_motor_steps,16) + int(s_pause,16) + 4
				self.bitsum += data
				print('Bitsum =', self.bitsum)                
				self.pfcan.send_command(posid,9, str(hex(self.bitsum).replace('0x','').zfill(8)))
				self.bitsum=0
				
				return 0
	
			except:
				print ("Sending command 4 or 9 failed")
				return 1                    
######################################

if (__name__ == '__main__'):
	p = PetalController(device_mode=True, service='PetalControl')
	p.run()
	sys.exit()

