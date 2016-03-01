#!/usr/bin/env python
"""
   DOS device application to control the DESI positioner petal
	edit text below
   Commands:
   get     status, led, hardware
   set     led=on (off), current
   configure

   Sharev Variables
   publications:    <role>_LED  current LED setting
					<role>_STATUS
   Version History
   1/22/2016     KH     Initial version
   2/25/2016     PF     Addition of MightexLED software
"""

from DOSlib.application import Application
import DOSlib.discovery as discovery
import time, sys, os, re
import atexit
import platform
import threading
import posfidcan


class PetalController(Application):
	commands = [ 'send_tables',
				'execute_sync', 'set_device', 'get_fid_status', 'get_device_status', 'set_fiducials',  'set_led']
	defaults = {'some_canbus_stuff' : 10.0,
				'hardware' : 'simulator',
				}

	def init(self):
		"""Initialize PetalController application. Set up variables, discovery"""
		self.info('INITIALIZING Device %s' % self.role)
		self.loglevel('INFO')
		self.statusSV = self.shared_variable('STATUS')
		self.statusSV.publish()
		# customize for petal controller needs
		self.ledSV = self.shared_variable("LED")
		self.ledSV.publish()
		
		# Get configuration information (add more configuration variables as needed)
		try:
			self.same_canbus_stuff = float(self.config['some_canbus_stuff']) 
		except:
			self.same_canbus_stuff = self.default['some_canbus_stuff']
		self.hardware = self.config['hardware']
		
		# Setup data structure for LED information 
#		self.led_info = {'port': self.config['serial_port'],'channel' : 1, 'max_current': self.max_current, 'current' : 0.0, 'state' : 'OFF'}
		self.controller = None

		# Setup application to be discovered by others
		if self.connected:
			self._setup_discovery(discovery.discover, discovery.discoverable)
		# Update status and initialization is done ...
		self.statusSV.write('INITIALIZED')
		# ... unless we want to configure us ourselves
		retcode = self.configure('constants = DEFAULT')
		self.info('Initialized')
		self.pmc=PositionerMoveControl()

	# callback functions for discovery
	def _setup_discovery(self, discover, discoverable):
		# Setup application for discovery and discover other DOS applications
		discoverable(role = self.role, tag = 'PETALCONTROLLER', interface = self.role)
		self.info('_setup_discovery: Done')

	# PML functions (functions that can be accessed remotely)


	def set_fiducials(self, *args, **kwargs):
		"""
		Set the ficucial power levels and period
		Inputs include list with percentages, periods and ids
		Returns SUCCESS or error message.

		ids          ... list of fiducial ids
		percent_duty ... list of values, 0-100, 0 means off
		duty_period  ... list of values, ms, time between duty cycles
		"""
		try:
			a, kw = dos_parser(*args, **kwargs)
		except:
			a= []
			kw = {}
		#need to decide calling format
		# lets assume it's 3 lists in ids, percent, period order

		if len(a) != 3:
			rstring = 'set_fiducials: Invalid arguments'
			self.error(rstring)
			return 'FAILED: ' + rstring

		for id in range(len(ids)):
			# assemble arguments for canbus/firmware function
			print('ID: %s, Percent %s, Period %s' % (a[0][id],a[1][id],a[2][id]))

		return self.SUCCESS


	def send_tables(self, move_tables):
#    """Sends move tables for positioners over ethernet to the petal controller,
#        where they are then sent over CAN to the positioners. See method
#        "hardware_ready_move_tables" in class PosArrayMaster for definition of the
#        move_tables format.
#   """
		pass


	def execute_sync(self,mode='hard'):
		"""Send the command to synchronously begin move sequences to all positioners
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


	def set_led(self,pos_id,state):
		"""Send the command to set positioner LED ON or OFF

		""" 
		if not isinstance(pos_id,int):
			rstring = 'set_led: Invalid pos_id arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
		if state.lower() not in ['on','off']:
			rstring = 'execute_sync: Invalid LED state arguments.'
			self.error(rstring)
			return 'FAILED: ' + rstring
			self.pmc.set_led(pos_id,state.lower())

		return self.SUCCESS  


	def set_pos_constants(self, posids, settings):
		"""Sets positioners identified by ids in the list posids to corresponding
		settings in the (dictionary? list of dicts?) settings.
		"""
		pass

	def set_fiducials(self, ids, percent_duty, duty_period):
		"""Sets the fiducials identified by the list ids to the corresponding duty cycles.
			ids          ... list of fiducial ids
			percent_duty ... list of values, 0-100, 0 means off
			duty_period  ... list of values, ms, time between duty cycles
		"""
		pass


	def set_device(self, id, key, value):
		"""Set a value on a device other than positioners or fiducials. This includes
		fans, power supplies, and sensors.
		"""
		pass

	def get_pos_status(self):
		"""Returns a (dictionary?) containing status of all positioners on the petal.
		"""
		pass


	def get_fid_status(self):
		"""Returns a (dictionary?) containing status of all fiducials on the petal.
		"""
	# (to-do)
		return status

	def get_device_status(self):
		"""Returns a (dictionary?) containing status of all devices other than positioners
		and fiducials on the petal. This includes fans, power supplies, and sensors.
		""" 
		execute_moves_soft_sync(self)
		"""Send the command to synchronously begin move sequences to all positioners,
		using CAN command as the start signal.
		"""
		pass


 




	
	def main(self):
		while not self.shutdown_event.is_set():
			# Periodically poll controller and update shared variable
			if not self.controller:
				time.sleep(1)
			else:
				update = self.controller.status()
				if type(update) is dict:
					self.led_info.update(update)
					self.ledSV.write(self.led_info)
				time.sleep(1)
		print('Device exits')

# Instance Connection Callbacks
	def about_to_connect_to_instance(self, *args, **kwargs):
		pass

	def did_connect_to_instance(self, *args, **kwargs):
		self.info('connected, setting up discovery stuff')
		discovery.reset()
		discovery.reset_discovered()
		self._setup_discovery(discovery.discover, discovery.discoverable)

	def about_to_disconnect_from_instance(self, *args, **kwargs):
		pass

	def did_disconnect_from_instance(self, *args, **kwargs):
		self.info('disconnected, clearing discovery stuff')
		discovery.reset()
		discovery.reset_discovered()

######################################

######################################


class PositionerMoveControl(object):
	def __init__(self):
						
		self.pfcan=posfidcan.PosFidCAN('can2')


	def set_reset_leds(self, pos_id, select):
		
		self.pfcan.send_command(pos_id,6, str(select).zfill(2))


if (__name__ == '__main__'):
	i = PetalController(device_mode=True, service='PetalControl')
	i.run()
	sys.exit()

