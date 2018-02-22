import threading
import re
import time
import Pyro4
import sys
from DOSlib.advertise import Seeker

class PetalComm(object):
    """
    Handles communication between petal software running on floor control computers
    and petalbox software running on the petal.
    """

    def __init__(self, petal_id, controller = None, user_interactions_enabled = False):
        """
        Initialize the object and connect to the petal controller

        We support to methods to select the petal controller. If only the petal id is
        provided, the DOSlib advertiser module is used to find the corresponding controller.
        Or a dictionary with the ip and port information can be passed as controller. For example:

               my_class = PetalComm(5,controller = {'ip' : 192.1.15.78', 'port' : 7100})

        The no_dos flag should be managed one level up (just import a different PetalComm module) and
        not in this file
        """
        self.petal_id = int(petal_id)
        # Setup Seeker
        self.seeker_thread = None
        self.repeat = threading.Event()
        self.repeat.clear()
        self.found_controller = threading.Event()
        self.found_controller.clear()
        self.stype = '-dos-'
        self.service = 'PetalControl'
        self.device = {}

        # Make sure we have the correct information
        if isinstance(controller, dict):
            if 'ip' not in controller.keys() or 'port' not in controller.keys():
                raise RuntimeError('init: the IP address of the petal controller must be specified.')
            # Create the Pyro URI manually
            self.device['name'] = 'PC%d' % self.petal_id
            self.device['node'] = str(controller['ip'])
            self.device['port'] = int(controller['port'])
            self.device['pyro_uri'] = 'PYRO:PC%d@%s:%s' % (petal_id, str(controller['ip']),str(controller['port']))
        else:
            self.seeker = Seeker(self.stype, self.service, found_callback = self._found_dev)
            # Start Seeker thread
            self.repeat.set()
            self.delay = 0.5
            self.seeker_thread = threading.Thread(target=self._repeat_seeker)
            self.seeker_thread.setDaemon(True)
            self.seeker_thread.start()
            print('Seeker thread is now running. Delay %s' % str(self.delay))
            # wait briefly for seeker to find all devices
            self.found_controller.wait(timeout = 1.0)
            self.delay = 4.0

        # Connect to the device (if we found anything)
        while self.device == {}:
            if user_interactions_enabled:
                err_question = 'Petal Controller ' + str(self.petal_id) + ' was not discovered. Do you want to:\n  1: try again now\n  2: quit now\n  3: continue anyway (not recommended)\nEnter 1, 2, or 3 >> '
                answer = input(err_question)
            else:
                answer = '1'
            if '1' in answer:
                time.sleep(1)
            elif '2' in answer:
                sys.exit(0)
            elif '3' in answer:
                print('Ok, continuing along, even though petalcomm found nothing to talk to.')
                break
            else:
                print('Input ' + str(answer) + ' not understood.')
        else:
            if self.device:
                self.device['proxy'] = Pyro4.Proxy(self.device['pyro_uri'])
                print('Connected to Petal Controller %d' % self.petal_id)

    def is_connected(self):
        """
        Returns the status of the found_controller flag.
        """
        return self.found_controller.is_set()
    
    # Internal callback and utility functions
    def _repeat_seeker(self):
        while self.repeat.is_set():
            self.seeker.seek()
            time.sleep(self.delay)

    def _found_dev(self, dev):
        for key in dev:
            if dev[key]['service'] == self.service:   # Found a petal controller
                # Extract unit number and compare to self.petal_id
                m = re.search(r'\d+$', key)
                if m:
                    if self.petal_id == int(m.group()):
                        # Found the matching petal controller
                        if 'name' not in self.device or self.device['name'] != key:
                            print('_found_dev: Found new device %s' % str(key))
                            self.device['name'] = key
                        # update proxy information?
                        if 'uid' in self.device and self.device['uid'] != dev[key]['uid']:
                            print('_found_dev: Device %s rediscovered.' % key)
                            if 'proxy' in self.device:     # remove potentially stale info
                                del self.device['proxy']
                        self.device.update(dev[key])   # make a copy
                        self.found_controller.set()
                        
    def _call_device(self, cmd, *args, **kwargs):
        """
        Call remote function
        Input:  cmd   = function name
                args, kwargs are passed to the remove function
        Returns: return value received from remote function
        """
        try:
            return getattr(self.device['proxy'],cmd)(*args, **kwargs)
        except:
            if 'pyro_uri' in self.device:
                try:
                    self.device['proxy'] = Pyro4.Proxy(self.device['pyro_uri'])
                    return getattr(self.device['proxy'],cmd)(*args, **kwargs)
                except Exception as e:
                    raise RuntimeError('_call_device: Exception for command %s. Message: %s' % (str(cmd),str(e)))
            # Failed to get status from device
            raise RuntimeError('_call_device: remote device not reachable %s' % '' if 'name' not in self.device else self.device)

    def get_pos_status(self, bus_ids, can_ids):
        """Checks if all the positioners identified by can_id are ready to receive
        move tables.
        """
        # status = self.get_pos_status()
        # can_ids: list of can_ids (list of integers)
        # if everybody is stationary, then true
        try:
            return self._call_device('get_pos_status', bus_ids, can_ids)
        except Exception as e:
            return 'FAILED: Can not execute get_pos_status. Exception: %s' % str(e)

    def ready_for_tables(self, bus_ids, can_ids):
        """Checks if all the positioners identified by can_id are ready to receive
        move tables.
        Returns either True or False
        """
        # status = self.get_pos_status()
        # bus_ids: list of bus_ids (list of strings such as 'can0')
        # can_ids: list of can_ids (list of integers)
        # if everybody is stationary, then true
        
        try:
            retcode = self._call_device('ready_for_tables', bus_ids, can_ids)
            if type(retcode) != bool:
                print(retcode)
            return retcode
        except Exception as e:
            print('FAILED: Can not execute ready_for_tables. Exception: %s' % str(e))
            print(bus_ids, can_ids)
            return 'FAILED: Can not execute ready_for_tables. Exception: %s' % str(e)           

    def send_tables(self, move_tables):
        """
        Sends move tables for positioners over ethernet to the petal controller,
        where they are then sent over CAN to the positioners. See method
        "hardware_ready_move_tables" in class PosArrayMaster for definition of the
        move_tables format.

        No information on the format of move_tables so we just pass it along
        """
        try:
            return self._call_device('send_tables',move_tables)
        except Exception as e:
            return 'FAILED: Can not send move tables. Exception: %s' % str(e)

    def execute_sync(self, mode):
        """
        Send the command to synchronously begin move sequences to all positioners
        on the petal simultaneously.
        mode can be either hard or soft
        """
        if str(mode).lower() not in ['hard','soft']:
            return 'FAILED: Invalid value for mode argument'
        try:
            return self._call_device('execute_sync', str(mode).lower())
        except Exception as e:
            return 'FAILED: Can not execute sync command. Exception: %s' % str(e)

    def move(self, bus_id, can_id, direction, mode, motor, angle):
        """
        Low level test command to move a single positioner
        """
        # add parameter checking
        try:
            # Michael's code expects motor as a string
            return self._call_device('move', bus_id, can_id, direction, mode, str(motor), angle)
        except Exception as e:
            return 'FAILED: Can not execute send_move_excute command. Exception: %s' % str(e)
        
    def set_currents(self, bus_id, can_id, P_currents, T_currents):
        """

        """
        try:
            return self._call_device('set_currents', bus_id, can_id, P_currents, T_currents)
        except Exception as e:
            return 'FAILED: Can not set currents. Exception: %s' % str(e)

    def set_periods(self, bus_id, can_id, creep_period_m0, creep_period_m1, spin_steps):
        """

        """
        try:
            return self._call_device('set_periods', bus_id, can_id, creep_period_m0, creep_period_m1, spin_steps)
        except Exception as e:
            return 'FAILED: Can not set periods. Exception: %s' % str(e)
    
    def set_bump_flags(self, bus_id, can_id, curr_hold, bump_cw_flg, bump_ccw_flg):
        """
        Set motor CW/CCW bump flags and hold current.
        bus_id       ... bus id string (eg. 'can0')
        can_id       ... positioner can id
        curr_hold    ... hold current, int between 0 and 100
        bump_cw_flg  ... flag for switching CW bump, bool, on if True
        bump_ccw_flg ... flag for switching CCW bump, bool, on if True     
        """
        try:
            return self._call_device('set_bump_flags', bus_id, can_id, curr_hold, bump_cw_flg, bump_ccw_flg)
        except Exception as e:
            return 'FAILED: Can not set bump flags. Exception: %s' % str(e)

    def set_pos_constants(self, can_ids, settings):
        """
        Send settings over ethernet to the petal controller, where they are
        sent over CAN to the positioners identified the list 'canids', with the setting
        values in the corresponding (dictionary? list of dicts?) 'settings'.

        canids       ... list of psoitioner can ids
        settings     ... list settings dictionaries

        Would probably be better as a dictionary of dictionaries like this:
        constants = { 1 : {'some setting': value, 'another setting' : another_value}, 4 : {'some setting': ....  }
        """
        if not isinstance(can_ids, list) or not isinstance(settings,list):
            return 'FAILED: parameters must be passed as lists'
        try:
            return self._call_device('set_pos_constants',can_ids, settings)
        except Exception as e:
            return 'FAILED: Can not set positioner constants. Exception: %s' % str(e)

    def set_fiducials(self, bus_ids, can_ids, percent_duty):
        """
        Send settings over ethernet to the petal controller, where they are
        sent over CAN to the fiducials. Sets the fiducials identified by the list ids
        to the corresponding duty values.
        bus_ids      ... list of bus ids where you find each fiducial
        can_ids      ... list of can id addresses for each fiducial on its bus
        percent_duty ... list of values, 0-100, 0 means off
        """
        if not isinstance(bus_ids, list) or not isinstance(can_ids, list) or not isinstance(percent_duty,list):
            return 'FAILED: parameters must be passed as lists'
        try:
            return self._call_device('set_fiducials', bus_ids, can_ids, percent_duty)
        except Exception as e:
            return 'FAILED: Can not set fiducials. Exception: %s' % str(e)

    def set_device(self, can_id, attributes):
        """
        Set a value on a device other than positioners or fiducials. This includes
        fans, power supplies, and sensors.

        For now pos_id is a single positioner id (int)
        this should really be passed as a dictionary so key, value lists were change to the attributes dictionary
        Could also be a dictionary of dictionaries if multiple ids and attributes are passed at once
        lot's of possibilities...

        As implemented, this routine does no error checking or reformatting but passes the parameters on the the petal controller
        """
        try:
            id = int(can_id)
        except:
            return 'FAILED: Invalid positioner id'
        if not isinstance(attributes, dict):
            return 'FAILED: Attributes must be passed as dictionary'
        try:
            return self._call_device('set_device',id, attributes)
        except Exception as e:
            return 'FAILED: Can not set attributes. Exception: %s' % str(e)

    def set_led(self, bus_id, can_id, state):
        """
        Set the led on positioner id on or off
        Input:
             can_id  (int)  positioner id on can bus
             state   (str)  on, offf
        """
        try:
            id = int(can_id)
        except:
            return 'FAILED: Invalid positioner id'
        if str(state).lower() not in ['on', 'off']:
            return 'FAILED: Invalid LED state'

        try:
            return self._call_device('set_led',bus_id, id, str(state).lower())
        except Exception as e:
            return 'FAILED: Can not set LED state. Exception: %s' % str(e)
    
    def get_nonresponsive_canids(self):
        """
        Returns a list of integer canids that correspond to unresponsive positioners, as determined by the petalcontroller.
        """
        try:
            return self._call_device('get_nonresponsive_canids')
        except Exception as e:
            return 'FAILED: Can not get list of nonresponsive canids. Exceptions: %s' % str(e)

    def reset_nonresponsive_canids(self):
        """
        Resets list of non-responsive canids to being empty.
        """
        try:
            return self._call_device('reset_nonresponsive_canids')
        except Exception as e:
            return 'FAILED: Can not reset list of nonresponsive canids. Exceptions: %s' % str(e)

    def get_device_status(self):
        """
        Returns a (dictionary?) containing status of all positioners on the petal.
        """
        try:
            return self._call_device('get_device_status')
        except Exception as e:
            return 'FAILED: Can not get device status. Exception: %s' % str(e)

    def get_fid_status(self):
        """
        Returns a (dictionary?) containing status of all fiducials on the petal.
        """
        try:
            return self._call_device('get_fid_status')
        except Exception as e:
            return 'FAILED: Can not get fiducial status. Exception: %s' % str(e)

    def get_posfid_info(self,canbus):
        """
        Retrieves CAN ids found on the canbus with corresponding sids and software versions.
        """
        try:
            return self._call_device('get_posfid_info',canbus)
        except Exception as e:
            return 'FAILED: Can not read devices. Exception: %s' % str(e)


    def set_canid(self,canbus, sid, new_posid):
        """
        Sets the positioner ID (= CAN address) for positioner identified by sid to new_posid.
        """
        try:
            return self._call_device('set_canid',canbus, sid, new_posid)
        except Exception as e:
            return 'FAILED: Can not set CAN id. Exception: %s' % str(e)

    def read_temp_ptl(self):
        """
        Returns a dictionary of temperature sensor readings on BeagleBone 1-wire bus.
        Keys are temperature sensor serial numbers and values are temperatures in degrees C.
        """
        try:

            return self._call_device('read_temp_ptl')
        except Exception as e:
            return 'FAILED: Can not read temperature sensors.  Exception: %s' % str(e)

    def fan_pwm_ptl(self, pwm_out, percent_duty):
        """
        Sets PWM duty cycles for pwm output (pwm_out= 'GFA_FAN1' or 'GFA_FAN2')
        """
        try:
            return self._call_device('fan_pwm_ptl', pwm_out, percent_duty)
        except Exception as e:
            return 'FAILED:  Can not set PWM.  Exception: %s' % str(e)

    def read_fan_pwm(self, pwm_out = None):
        """
        Read back PWM duty cycles for pwm output (pwm_out= 'GFA_FAN1' or 'GFA_FAN2')
        """
        try:
            return self._call_device('read_fan_pwm', pwm_out)
        except Exception as e:
            return 'FAILED:  Can not read PWM.  Exception: %s' % str(e)

    def switch_en_ptl(self, pin_name, state):
        """
        Switches power supply enable lines/ device enable lines to either high or low (state = 1 or 0)
        PIN NAMES:  "SYNC", "PS1_EN", "PS2_EN", "GFAPWR_EN", "GFA_FAN1", "GFA_FAN2"
        """
        try:
            return self._call_device('switch_en_ptl', pin_name, state)
        except Exception as e:
            return 'FAILED: Can not switch GPIO.  Exception: %s' % str(e)

    def read_switch_ptl(self, pin_name = None):
        """
        Read back switch
        Switches power supply enable lines/ device enable lines to either high or low (state = 1 or 0)
        PIN NAMES:  "SYNC", "PS1_EN", "PS2_EN", "GFAPWR_EN", "GFA_FAN1", "GFA_FAN2"
        """
        try:
            return self._call_device('read_switch_ptl', pin_name)
        except Exception as e:
            return 'FAILED: Can not read switch GPIO.  Exception: %s' % str(e)

    def read_HRPG600(self):
        """
        Read back power supply status signals, returns dict:  {"PS1_OK" : True, "PS2_OK" : True, "GFAPWR_OK" : True}
        True = ON, False = OFF
        """
        try:
            return self._call_device('read_HRPG600')
        except Exception as e:
            return 'FAILED: Can not read HRPG600 power supply status signals.  Exception: %s' % str(e)

    def get_GPIO_names(self):
        """
        Returns dictionary of all pin names (inputs, outputs, pwm, 1-wire).  Names are keys, values are descriptions of the pin functionality
        """
        try:
            return self._call_device('get_GPIO_names')
        except Exception as e:
            return 'FAILED: Can not read GPIO names.  Exception: %s' % str(e)

    def read_fan_tach(self):
        """
        Reads GFA fan tachometer signals, returns dictionary:  {'GFA_FAN1' : 5000, 'GFA_FAN2' : 5000}
        """
        try:
            return self._call_device('read_fan_tach')
        except Exception as e:
            return 'FAILED: Can not read GPIO names.  Exception: %s' % str(e)

    def select_mode(self, pid, mode = 'normal'):
        """
        Starts up in normal mode rather than bootloader mode
        """
        try:
            return self._call_device('select_mode', pid, mode)
        except Exception as e:
            return 'FAILED: Can not select mode.  Exception: %s' % str(e)

    def pbget(self, key):
        """
        Request telemetry, positioner and fiducial settings from the petal controller.
        """
        try:
            return self._call_device('pbget', key)
        except Exception as e:
            return 'FAILED: Can not retrieve petalbox setting with pbget.  Exception: %s' % str(e)

    def pbset(self, key, value):
        """
        Set telemetry, positioner and fiducial settings from the petal controller.
        """
        try:
            return self._call_device('pbset', key, value)
        except Exception as e:
            return 'FAILED: Can not set petalbox setting with pbset.  Exception: %s' % str(e)









