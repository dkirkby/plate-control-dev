#!/usr/bin/env python

"""
   DOS device application to control the DESI positioner petal
   Features:
     scan canbus and build pos_id map  (tpd)
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

class PetalController(Application):
    """
    PetalController inherits the DOS (device/application) framework
    init() is called by the framework during initialization
    main() is the runtime loop
    when main returns, the entire calibration exits
    """
   
    # List of remotely accessible commands
    commands = ['send_tables',
                'execute_sync', 
                'set_device', 
                'get_fid_status', 
                'get_device_status', 
                'set_fiducials',  
                'set_led',
                'configure',
                'get_positioner_map',
                ]

    # Default configuration (can be overwritten by command line or config file)
    defaults = {'default_petal_id' : 1,
                'hardware' : 'beaglebone',
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
        self.hardware = self.config['hardware']
		
        # Bring in the Positioner Move object
        self.pmc=PositionerMoveControl()

        self.status = 'INITIALIZED'
        self.info('Initialized')
        # call configure to setup the pos_id map
        retcode = self.configure('constants = DEFAULT')
    def configure(self, constants = 'DEFAULT'):
        """
        configure petal controller,
        scan canbus to setup pos_id map
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
        Sends move tables for positioners over ethernet to the petal controller,
        where they are then sent over CAN to the positioners. See method
        "hardware_ready_move_tables" in class PosArrayMaster for definition of the
        move_tables format.
        """
        print('send_tables: %s' % repr(move_tables))
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

    def set_led(self, pos_id, state):
        """
        Send the command to set positioner LED ON or OFF
        """ 
        if not isinstance(pos_id,int):
            rstring = 'set_led: Invalid pos_id arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring
        if state.lower() not in ['on','off']:
            rstring = 'execute_sync: Invalid LED state arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring
        # call canbus function
        retcode = self.pmc.set_led(pos_id,state.lower())
        # do anything with retcode?
        
        return self.SUCCESS  

    def set_pos_constants(self, posids, settings):
        """
        Sets positioners identified by ids in the list posids to corresponding
        settings in the (dictionary? list of dicts?) settings.
		"""
        print('set_pos_constants: ids = %s, settings = %s' % (repr(posids), repr(settings)))
        return self.SUCCESS

    def set_device(self, pos_id, attributes):
        """
        Set a value on a device other than positioners or fiducials. This includes
		fans, power supplies, and sensor
        """
        print('set_device: ', repr(pos_id), repr(attributes))
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
	def __init__(self):
						
		self.pfcan=posfidcan.PosFidCAN('can2')


	def set_reset_leds(self, pos_id, select):
		
		self.pfcan.send_command(pos_id,6, str(select).zfill(2))

######################################

if (__name__ == '__main__'):
	p = PetalController(device_mode=True, service='PetalControl')
	p.run()
	sys.exit()

