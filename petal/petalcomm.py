"""
PetalComm

some description
version history
etc

  Version History
  0.1.0    2/1/2016   JS     Initial version
  0.2.0    3/1/2016   KH     added communication code
"""
VERSION = '0.2.0'

import threading
import re
import time
import Pyro4
from DOSlib.advertise import Seeker

class PetalComm(object):
    """
    Handles communication between petal software running on floor control computers
    and petalbox software running on the petal.
    """

    def __init__(self, petal_id, controller = None):
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

        # Connect to the device (if we found anything
        if self.device == {}:
            print('Petal Controller %d not yet discovered. Continuing...' % self.petal_id)
        else:
            self.device['proxy'] = Pyro4.Proxy(self.device['pyro_uri'])
            print('Connected to Petal Controller %d' % self.petal_id)


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

    def get_device_status(self, can_ids):
        """Checks if all the positioners identified by can_id are ready to receive
        move tables.
        """
        # status = self.get_pos_status()
        # can_ids: list of can_ids (list of integers)
        # if everybody is stationary, then true
        try:
            return self._call_device('get_device_status',can_ids)
        except Exception as e:
            return 'FAILED: Can not execute get_device_status. Exception: %s' % str(e)

     def ready_for_tables(self, can_ids):
        """Checks if all the positioners identified by can_id are ready to receive
        move tables.
        Returns either True or False
        """
        # status = self.get_pos_status()
        # can_ids: list of can_ids (list of integers)
        # if everybody is stationary, then true
        try:
            return self._call_device('raedy_for_tables',can_ids)
        except Exception as e:
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

    def move(self, can_id, direction, mode, motor, angle):
        """
        Low level test command to move a single positioner
        """
        # add parameter checking
        try:
            # Michael's code expects motor as a string
            return self._call_device('move', can_id, direction, mode, str(motor), angle)
        except Exception as e:
            return 'FAILED: Can not execute send_move_excute command. Exception: %s' % str(e)
    def set_currents(self, can_id, P_currents, T_currents):
        """

        """
        try:
            return self._call_device('set_currents',can_id, P_currents, T_currents)
        except Exception as e:
            return 'FAILED: Can not set currents. Exception: %s' % str(e)

    def set_periods(self, can_id, creep_period_m0, creep_period_m1, spin_steps):
        """

        """
        try:
            return self._call_device('set_periods',can_id, creep_period_m0, creep_period_m1, spin_steps)
        except Exception as e:
            return 'FAILED: Can not set periods. Exception: %s' % str(e)


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
        if not isintance(can_ids, list) or not isinstance(settings,list):
            return 'FAILED: parameters must be passed as lists'
        try:
            return self._call_device('set_pos_constants',can_ids, settings)
        except Exception as e:
            return 'FAILED: Can not set fiducials. Exception: %s' % str(e)

    def set_fiducials(self, can_ids, percent_duty, duty_period):
        """
        Send settings over ethernet to the petal controller, where they are
        sent over CAN to the fiducials. Sets the fiducials identified by the list ids
        to the corresponding duty values.
        can_ids      ... list of fiducial ids
        percent_duty ... list of values, 0-100, 0 means off
        duty_period  ... list of values, ms, time between duty cycles

        Would probably be better as a dictionary of dictionaries like this:
        fiducials = { 1 : {'percent': percent_duty, 'period' : duty_period}, 4 : {'percent': ....  }
        """
        if not isintance(can_ids, list) or not isinstance(percent_duty,list) or not isinstance(duty_period, list):
            return 'FAILED: parameters must be passed as lists'
        try:
            return self._call_device('set_fiducials',can_ids, percent_duty, duty_period)
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
        if not isintance(attributes, dict):
            return 'FAILED: Attributes must be passed as dictionary'
        try:
            return self._call_device('set_device',id, attributes)
        except Exception as e:
            return 'FAILED: Can not set attributes. Exception: %s' % str(e)


    def set_led(self, can_id, state):
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
            return self._call_device('set_led',id, str(state).lower())
        except Exception as e:
            return 'FAILED: Can not set LED state. Exception: %s' % str(e)

    def get_pos_status(self):
        """
        Returns a (dictionary?) containing status of all positioners on the petal.
        """
        try:
            return self._call_device('get_pos_status')
        except Exception as e:
            return 'FAILED: Can not get positioner status. Exception: %s' % str(e)

    def get_fid_status(self):
        """
        Returns a (dictionary?) containing status of all fiducials on the petal.
        """
        try:
            return self._call_device('get_fid_status')
        except Exception as e:
            return 'FAILED: Can not get fiducial status. Exception: %s' % str(e)

    def get_sids(self,canbus):
        """
        Returns a list of silicon IDs on CANbus <canbus>.
        """
        try:
            return self._call_device('get_sids',canbus)
        except Exception as e:
            return 'FAILED: Can not get silicon IDs. Exception: %s' % str(e)

    def set_posid(self,canbus, sid, new_posid):
        """
        Sets the positioner ID (= CAN address) for positioner identified by sid to new_posid.
        """
        try:
            return self._call_device('set_posid',canbus, sid, new_posid)
        except Exception as e:
            return 'FAILED: Can not set posID. Exception: %s' % str(e)
