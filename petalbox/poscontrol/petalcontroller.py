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

from serial_device2 import SerialDevice, SerialDevices, find_serial_device_ports, WriteFrequencyError

class PetalController(Application):
    commands = ['configure', 'get', 'set', 'send_tables',
                'execute_moves_hard_sync', 'set_device', 'get_fid_status', 'get_device_status', 'set_fiducials', ]
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
        self.led_info = {'port': self.config['serial_port'],'channel' : 1, 'max_current': self.max_current, 'current' : 0.0, 'state' : 'OFF'}
        self.controller = None

        # Setup application to be discovered by others
        if self.connected:
            self._setup_discovery(discovery.discover, discovery.discoverable)
        # Update status and initialization is done ...
        self.statusSV.write('INITIALIZED')
        # ... unless we want to configure us ourselves
        retcode = self.configure('constants = DEFAULT')
        self.info('Initialized')

    # callback functions for discovery
    def _setup_discovery(self, discover, discoverable):
        # Setup application for discovery and discover other DOS applications
        discoverable(role = self.role, tag = 'PETALCONTROLLER', interface = self.role)
        self.info('_setup_discovery: Done')

    # PML functions (functions that can be accessed remotely)
    def configure(self, constants = None):
        """Configure Simple Device application"""
        self.info('Configuring using constants %s' % repr(constants))
        
        # Do something like connect to your hardware, call a driver init function etc
        try:
            self.controller = MightexLED(port = '/dev/tty.usbserial-AH00N5LG')
            #self.controller = LedSimulator(port='usb0')
        except Exception as e:
            self.error('configure: Exception connecting to LED controller: %s' % str(e))
            return self.FAILED
        
        self.led_info = self.controller.status()
        # and write this information to the shared variable
        self.ledSV.write(self.led_info)
        # update status and we are configured
        self.statusSV.write('READY')
        self.debug('configure: connected: %s, core connected: %s, sve connected: %s' % (self.connected, self.core_connected
, self.sve_connected))
        return self.SUCCESS

    def get(self, params):
        """ Retrieve parameters dynamically.
            Options include:
            status, led, hardware
        """
        if params.lower() == 'status':
            return self.statusSV._value
        elif params.lower() == 'led':
            if not self.controller:
                return 'FAILED: No LED controller connected'
            self.led_info.update(self.controller.status())
            return self.led_info
        elif params.lower() == 'hardware':
            return self.hardware
        else:
            return 'Invalid parameter for get command: %s' % params
        
    def set(self, *args, **params):
        """ Set parameters dynamically.
            Options include:
            led, current
        """ 
        if not self.controller:
            return 'FAILED: LED controller is not connected'
        if 'led' in params:
            if params['led'] in ['ON', 'on', True]:
                return self.controller.turn_on()
            elif params['led'] in ['OFF', 'off', False]:
                return self.controller.turn_off()
            else:
                return 'FAILED: invalid parameter'
        elif 'current' in params:
            try:
                i = float(params['current'])
            except:
                return 'Invalid value for current'
            return self.controller.set(current=i)
        else:
            return 'Failed: incorrect parameter for set command.'

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
    """Sends move tables for positioners over ethernet to the petal controller,
    where they are then sent over CAN to the positioners. See method
    "hardware_ready_move_tables" in class PosArrayMaster for definition of the
    move_tables format.
    """
        pass

#def execute_moves_hard_sync(self):
#    """Send the command to synchronously begin move sequences to all positioners
#    on the petal simultaneously. Uses the hardware sync pin as the start signal.
#    """
#    pass
#
#def execute_moves_soft_sync(self):
#    """Send the command to synchronously begin move sequences to all positioners,
#    using CAN command as the start signal.
#    """
#    pass



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
    """ execute_moves_soft_sync(self):
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
#
# This includes the MightexLED and MightexDevice classes
# MightexLED class will interface with the Illuminator App
# Writte by P. Fagrelius
######################################

class MightexLED(object):
    """
    This class interfaces with the LED DOS application.
    It contains a limited number of functions that correspond to PML functions.
    -Initializes the LED
    -status: creates the led_info, which is held in the variable self.controller
    -turn_on, turn_off
    -set: set current, max_current, and channel
    """
    
    def __init__(self,PORT):
        # port == '/dev/tty.usbserial-AH00N5LG'
        self.port = PORT
        self.controller = None
        self.channel = 1
        try:
            self.led = MightexDevice(port=self.port)
            print('LED has successfully connected')
        except:
            print('cannot find LED on that port')
        
        
        self.max_current = self.led.get_normal_parameters(self.channel)['current_max']
        self.current_set = self.led.get_normal_parameters(self.channel)['current']
        self.controller = {'port' : self.port, 'max_current': self.max_current, 'current' : 0.0, 'state' : 'OFF','channel': self.channel}

        mode = self.led.get_mode(self.channel)
        if mode == 'DISABLE':
            self.controller['state'] = 'OFF'
            self.controller['current'] = 0.0
        elif mode == 'NORMAL':
            self.controller['state'] = 'ON'
            self.controller['current'] = self.led.get_normal_parameters(self.channel)['current']
        
    
    def status(self):
        """
        Created led_info for the shared variables.
        Includes channel, current, state
        """
        try:
            return self.controller
        except:
            raise ValueError('status cannot be read')
        

    def turn_on(self):
        """
        Turn on the LED by setting the mode to NORMAL
        """
        try:
            self.led.set_mode_normal(self.channel)
            self.controller['state']='ON'
            self.controller['current']=self.current_set
            return 'LED was successfully turned on'
        except:
            return 'FAILED: LED was not turned on'
        
    def turn_off(self):
        """
        Disable the LED channel
        """
        try:
            self.led.set_mode_disable(self.channel)
            self.controller['state'] = 'OFF'
            self.controller['current'] = 0.0
            return 'LED was successfully turned off'
        except:
            return 'Setting disable mode returned an error'

    def set(self, **kwargs):
        """
        Set the current, max_current, channel
        """
        if 'current' in kwargs:
            if float(kwargs['current']) == self.controller['current']:
                return 'The LED current was already set to that value'
            else:
                self.led.set_normal_parameters(self.channel,self.controller['max_current'],float(kwargs['current']))
                self.controller['current'] = float(kwargs['current'])
                return 'SUCCESS'
        elif 'max_current' in kwargs:
            if float(kwargs['max_current']) == self.controller['max_current']:
                return 'The LED max_current was already set to that value'
            else:
                self.led.set_normal_parameters(self.channel,float(kwargs['max_current']),self.controller['current'])
                self.controller['max_current'] = float(kwargs['max_current'])
                return 'SUCCESS'
        if 'channel' in kwargs:
            if int(kwargs['channel']) == self.channel:
                return 'The channel was already set to that'
            else:
                self.channel = int(kwargs['channel'])
                self.led.set_normal_parameters(int(kwargs['channel']),self.controller['max_current'],self.controller['current'])
                self.controller['channel'] = int(kwargs['channel'])
                return 'SUCCESS'
                
        else:
            return 'FAILED: Invalid parameter'

def find_mightex_device_port(baudrate=None,
                             try_ports=None,
                             serial_number=None,
                             debug=None):
    mightex_device_ports = find_mightex_device_ports(baudrate=baudrate,
                                                     try_ports=try_ports,
                                                     serial_number=serial_number,
                                                     debug=debug)
    if len(mightex_device_ports) == 1:
        return mightex_device_ports.keys()[0]
    elif len(mightex_device_ports) == 0:
        serial_device_ports = find_serial_device_ports(try_ports)
        err_string = 'Could not find any Mightex devices. Check connections and permissions.\n'
        err_string += 'Tried ports: ' + str(serial_device_ports)
        raise RuntimeError(err_string)
    else:
        err_string = 'Found more than one Mightex device. Specify port or serial_number.\n'
        err_string += 'Matching ports: ' + str(mightex_device_ports)
        raise RuntimeError(err_string)

class MightexError(Exception):
    def __init__(self,value):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
DEBUG = False
BAUDRATE = 9600

class MightexDevice(object):
    """This includes most of the functions from MightexDevice, but does not include any of the functionality for strobe and trigger capabilities, which won't be used for ProtoDESI"""
    _TIMEOUT = 0.05
    _WRITE_WRITE_DELAY = 0.05
    _RESET_DELAY = 2.0


    def __init__(self,*args,**kwargs):
        if 'debug' in kwargs:
            self.debug = kwargs['debug']
        else:
            kwargs.update({'debug': DEBUG})
            self.debug = DEBUG
        if 'try_ports' in kwargs:
            try_ports = kwargs.pop('try_ports')
        else:
            try_ports = None
        if 'baudrate' not in kwargs:
            kwargs.update({'baudrate': BAUDRATE})
        elif (kwargs['baudrate'] is None) or (str(kwargs['baudrate']).lower() == 'default'):
            kwargs.update({'baudrate': BAUDRATE})
        if 'timeout' not in kwargs:
            kwargs.update({'timeout': self._TIMEOUT})
        if 'write_write_delay' not in kwargs:
            kwargs.update({'write_write_delay': self._WRITE_WRITE_DELAY})
        if ('port' not in kwargs) or (kwargs['port'] is None):
            port =  find_mightex_device_port(baudrate=kwargs['baudrate'],
                                             try_ports=try_ports,
                                             debug=kwargs['debug'])
            kwargs.update({'port': port})

        t_start = time.time()
        self._serial_device = SerialDevice(*args,**kwargs)
        atexit.register(self._exit_mightex_device)
        self._lock = threading.Lock()
        time.sleep(self._RESET_DELAY)
        t_end = time.time()
        self._debug_print('Initialization time =', (t_end - t_start))

    def _debug_print(self, *args):
        if self.debug:
            print(*args)

    def _exit_mightex_device(self):
        pass

    def _args_to_request(self,*args):
        request = ' '.join(map(str,args))
        request = request + '\n\r';
        return request

    def _send_request(self,*args):
        '''
        Sends request to device over serial port and
        returns number of bytes written.
        '''
        self._lock.acquire()
        request = self._args_to_request(*args)
        self._debug_print('request', request)
        bytes_written = self._serial_device.write_check_freq(request,delay_write=True)
        self._lock.release()
        return bytes_written

    def _send_request_get_response(self,*args):
        '''
        Sends request to device over serial port and
        returns response.
        '''
        self._lock.acquire()
        request = self._args_to_request(*args)
        self._debug_print('request', request)
        response = self._serial_device.write_read(request,use_readline=True,check_write_freq=True)
        self._lock.release()
        response = response.strip()
        if '#!' in response:
            raise MightexError('The command is valid and executed, but an error occurred during execution.')
        elif '#?' in response:
            raise MightexError('The latest command is a valid command but the argument is NOT in valid range.')
        response = response.replace('#','')
        #print('response #1',response)
        return response

    def close(self):
        '''
        Close the device serial port.
        '''
        self._serial_device.close()

    def get_port(self):
        return self._serial_device.port

    def get_device_info(self):
        '''
        Get device_info.
        '''
        request = self._args_to_request('DEVICEINFO')
        self._debug_print('request', request)
        response = self._send_request_get_response(request)
        if 'Mightex' not in response:
            # try again just in case
            response = self._send_request_get_response(request)
            if 'Mightex' not in response:
                raise MightexError('"Mightex" not in device_info.')
        return response

    def get_serial_number(self):
        '''
        Get serial_number.
        '''
        device_info = self.get_device_info()
        serial_number_str = 'Serial No.:'
        p = re.compile(serial_number_str+'\d+-?\d+-?\d+')
        found_list = p.findall(device_info)
        if len(found_list) != 1:
            raise MightexError('serial_number not found in device_info.')
        else:
            serial_number = found_list[0]
            serial_number = serial_number.replace(serial_number_str,'')
            return serial_number

    def get_mode(self,channel):
        '''
        Get channel mode. Modes = ['DISABLE','NORMAL','STROBE','TRIGGER']
        '''
        channel = int(channel)
        request = self._args_to_request('?MODE',channel)
        
        self._debug_print('request', request)
        response = self._send_request_get_response(request)
        #print('response',response)
        if response == '0':
            return 'DISABLE'
        elif response == '1':
            return 'NORMAL'
        elif response == '2':
            return 'STROBE'
        elif response == '3':
            return 'TRIGGER'
        else:
            raise MightexError('Unknown response: {0}'.format(response))

    def get_channel_count(self):
        '''
        Get channel count.
        '''
        channel_count = 0
        while True:
            try:
                channel_count += 1
                mode = self.get_mode(channel_count)
            except MightexError:
                break
        channel_count -= 1
        return channel_count

    def set_mode_disable(self,channel):
        '''
        Set DISABLE mode.
        '''
        channel = int(channel)
        request = self._args_to_request('MODE',channel,0)
        self._debug_print('request', request)
        self._send_request(request)

    def set_mode_normal(self,channel):
        '''
        Set NORMAL mode.
        '''
        channel = int(channel)
        request = self._args_to_request('MODE',channel,1)
        self._debug_print('request', request)
        self._send_request(request)

    def set_normal_parameters(self,channel,current_max,current):
        '''
        Set NORMAL mode parameters. current_max is the maximum current
        allowed for NORMAL mode, in mA. current is the working current
        for NORMAL mode, in mA.
        '''
        channel = int(channel)
        current_max = int(current_max)
        current = int(current)
        request = self._args_to_request('NORMAL',channel,current_max,current)
        self._debug_print('request', request)
        self._send_request(request)

    def set_normal_current(self,channel,current):
        '''
        Set the working current for NORMAL mode, in mA.
        '''
        channel = int(channel)
        current = int(current)
        request = self._args_to_request('CURRENT',channel,current)
        self._debug_print('request', request)
        self._send_request(request)

    def get_normal_parameters(self,channel):
        '''
        Get NORMAL mode parameters. current_max is the maximum current
        allowed for NORMAL mode, in mA. current is the working current
        for NORMAL mode, in mA.
        '''
        channel = int(channel)
        request = self._args_to_request('?CURRENT',channel)
        self._debug_print('request', request)
        response = self._send_request_get_response(request)
        response_list = response.split(' ')
        parameters = {}
        parameters['current_max'] = int(response_list[-2])
        parameters['current'] = int(response_list[-1])
        return parameters


    def get_load_voltage(self,channel):
        '''
        For XV Module (e.g. AV04 or SV04), use this method to get the
        voltage on the load of the specified channel. It will return
        the voltage in mV.  Note: As the controller polls the load
        voltage in a 20ms interval, this feature is proper for NORMAL
        mode or slow STROBE mode only.
        '''
        channel = int(channel)
        request = self._args_to_request('LoadVoltage',channel)
        self._debug_print('request', request)
        response = self._send_request_get_response(request)
        channel_str = "{0}:".format(channel)
        response = response.replace(channel_str,'')
        response = int(response)
        return response

    def reset(self):
        '''
        Soft reset device.
        '''
        request = self._args_to_request('Reset')
        self._debug_print('request', request)
        self._send_request(request)

    def restore_factory_defaults(self):
        '''
        This method will reset the device mode and all related parameters
        to the factory defaults. Note that these parameters become the
        current device settings in volatile memory, use the
        "store_parameters" method to save the current settings to
        non-volatile memory.
        '''
        request = self._args_to_request('RESTOREDEF')
        self._debug_print('request', request)
        self._send_request(request)

    def store_parameters(self):
        '''
        This method will store the current settings in volatile memory to
        non-volatile memory.
        '''
        request = self._args_to_request('STORE')
        self._debug_print('request', request)
        self._send_request(request)

    def store_parameters(self):
        '''
        This method will store the current settings in volatile memory to
        non-volatile memory.
        '''
        request = self._args_to_request('STORE')
        self._debug_print('request', request)
        self._send_request(request)


######################################
#
# This is the simulator class for the illuminator hardware
# A similar class has to be written for the real thing
#
######################################

class LedSimulator():
    def __init__(self, port):
        #
        # Create a fake SerialDevice. Through an error (as an example) if port == tty8
        self.controller = None
        if port == 'tty8':
            raise Exception('Cannot find LED Controller hardware on port %s' % port)
        self.controller = {'port' : port, 'voltage' : 0.0, 'current' : 0.0, 'state' : 'OFF'}
    
    def status(self):
        if self.controller == None:
            raise Exception('No LED controller connected')
        return  dict(self.controller)

    def turn_on(self):
        self.controller['state'] = 'ON'
        self.controller['current'] = self.controller['voltage'] * 10.0
        return 'SUCCESS'

    def turn_off(self):
        self.controller['state'] = 'OFF'
        self.controller['current'] = 0.0
        return 'SUCCESS'

    def set(self, **kwargs):
        if self.controller['state'] == 'OFF':
            return 'FAILED: Controller is off'
        if 'current' in kwargs:
            self.controller['current'] = float(kwargs['current'])
            self.controller['voltage'] = self.controller['current']/10.0
            return 'SUCCESS'
        elif 'voltage' in kwargs:
            self.controller['voltage'] = float(kwargs['voltage'])
            self.controller['current'] = self.controller['voltage']*10.0
            return 'SUCCESS'
        else:
            return 'FAILED: Invalid parameter'


if (__name__ == '__main__'):
    i = Illuminator(device_mode=True, service='DOStest')
    i.run()
    sys.exit()

