import threading
import re
import time
import Pyro4
import sys
from sendcases import sendex
from DOSlib.advertise import Seeker
import posconstants as pc

class PetalComm(object):
    """
    Handles communication between petal software running on floor control computers
    and petalbox software running on the petal.
    """

    def __init__(self, petalbox_id, controller=None, user_interactions_enabled=False, printfunc=print):
        """
        Initialize the object and connect to the petal controller

        We support to methods to select the petal controller. If only the petal id is
        provided, the DOSlib advertiser module is used to find the corresponding controller.
        Or a dictionary with the ip and port information can be passed as controller. For example:

               my_class = PetalComm(5,controller = {'ip' : 192.1.15.78', 'port' : 7100})

        The no_dos flag should be managed one level up (just import a different PetalComm module) and
        not in this file
        """
        self.petalbox_id = int(petalbox_id)
        # Setup Seeker
        self.seeker_thread = None
        self.repeat = threading.Event()
        self.repeat.clear()
        self.found_controller = threading.Event()
        self.found_controller.clear()
        self.stype = '-dos-'
        self.service = 'PetalControl'
        self.device = {}
        self.printfunc = printfunc
        # Lock timeout, don't let overlapping _call_device commands reset the timeout
        self.lock_timeout = False

        # Make sure we have the correct information
        if isinstance(controller, dict):
            if 'ip' not in controller.keys() or 'port' not in controller.keys():
                raise RuntimeError('init: the IP address of the petal controller must be specified.')
            # Create the Pyro URI manually
            self.device['name'] = 'PC%02d' % self.petalbox_id
            self.device['node'] = str(controller['ip'])
            self.device['port'] = int(controller['port'])
            self.device['pyro_uri'] = 'PYRO:PC%02d@%s:%s' % (petalbox_id, str(controller['ip']),str(controller['port']))
        else:
            self.seeker = Seeker(self.stype, self.service, found_callback = self._found_dev)
            # Start Seeker thread
            self.repeat.set()
            self.delay = 0.5
            self.seeker_thread = threading.Thread(target=self._repeat_seeker)
            self.seeker_thread.setDaemon(True)
            self.seeker_thread.start()
            self.printfunc('Seeker thread is now running. Delay %s' % str(self.delay))
            # wait briefly for seeker to find all devices
            self.found_controller.wait(timeout = 2.0)
            self.delay = 4.0

        # Connect to the device (if we found anything)
        while self.device == {}:
            if user_interactions_enabled:
                err_question = 'Petal Controller ' + str(self.petalbox_id) + ' was not discovered. Do you want to:\n  1: try again now\n  2: quit now\n  3: continue anyway (not recommended)\nEnter 1, 2, or 3 >> '
                answer = input(err_question)
            else:
                answer = '1'
            if '1' in answer:
                time.sleep(1)
            elif '2' in answer:
                sys.exit(0)
            elif '3' in answer:
                self.printfunc('Ok, continuing along, even though petalcomm found nothing to talk to.')
                break
            else:
                self.printfunc('Input ' + str(answer) + ' not understood.')
        else:
            if self.device:
                self.device['proxy'] = Pyro4.Proxy(self.device['pyro_uri'])
                self.printfunc('Connected to Petal Controller %d' % self.petalbox_id)

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
                # Extract unit number and compare to self.petalbox_id
                m = re.search(r'\d+$', key)
                if m:
                    if self.petalbox_id == int(m.group()):
                        # Found the matching petal controller
                        if 'name' not in self.device or self.device['name'] != key:
                            self.printfunc('_found_dev: Found new device %s' % str(key))
                            self.device['name'] = key
                        # update proxy information?
                        if 'uid' in self.device and self.device['uid'] != dev[key]['uid']:
                            self.printfunc('_found_dev: Device %s rediscovered.' % key)
                            if 'proxy' in self.device:     # remove potentially stale info
                                del self.device['proxy']
                        self.device.update(dev[key])   # make a copy
                        self.found_controller.set()
                        
    def _call_device(self, cmd, *args, **kwargs):
        """
        Call remote function
        Input:  cmd   = function name
                args, kwargs are passed to the remote function
        Returns: return value received from remote function
        """
        timeout = kwargs.pop('pyrotimeout', 20.0)
        lockedtimeout = kwargs.pop('lockedtimeout', None)

        handle = None
        n_retries = 2
        for i in range(1, n_retries + 1):
            try:
                if lockedtimeout is not None:
                    self.lock_timeout = True
                    self.device['proxy']._pyroTimeout = lockedtimeout
                elif not self.lock_timeout:
                    self.device['proxy']._pyroTimeout = timeout
                handle = getattr(self.device['proxy'], cmd)
                if handle:
                    break
            except Exception as e1:
                self.printfunc(f'Exception while connecting to petalcontroller: {e1}')
                if i < n_retries and 'pyro_uri' in self.device:
                    uri = self.device['pyro_uri']
                    self.printfunc(f'Trying to re-establish connection to {uri}, attempt {i}')
                    self.device['proxy'] = Pyro4.Proxy(uri)
        if not handle:
            raise RuntimeError(f'Failed to connect to {uri} and get handle for command {cmd}')
        try:
            output = handle(*args, **kwargs)
            return output
        except Exception as e2:
            raise RuntimeError(f'Exception for command {cmd}. Message: {e2}')            

    def ready_for_tables(self, bus_ids=None, can_ids=None):
        """Checks if all the positioners identified by can_id are ready to receive
        move tables.

        INPUTS:
        (all inputs are dummy values, as of 2020-05-08 --- unused by petalcontroller.py!)
        bus_ids: list of CAN bus_ids (list of strings such as 'can10')
        can_ids: list of can_ids (list of integers)

        Returns either True or False (True if all listed can_ids are done executing
        their movements.
        """
        bus_ids = [] if bus_ids is None else bus_ids
        can_ids = [] if can_ids is None else can_ids
        try:
            retcode = self._call_device('ready_for_tables', bus_ids, can_ids)
            assert pc.is_boolean(retcode), f'non-boolean return value {retcode}'
            return pc.boolean(retcode)
        except Exception as e:
            print('FAILED: Can not execute ready_for_tables. Exception: %s' % str(e))
            print(bus_ids, can_ids)
            return 'FAILED: Can not execute ready_for_tables. Exception: %s' % str(e)           

    def send_and_execute_tables(self, move_tables, sync_mode):
        """
        Sends move tables for positioners over ethernet to the petal controller,
        where they are then sent over CAN to the positioners.
        
        In cases of SUCCESS or PARTIAL SUCCESS, petalcontroller shall immediately
        send the synchronized start signal upon completion of loading all tables.
 
        INPUTS:
            move_tables ... see method "_hardware_ready_move_tables()" in petal.py
        OUTPUT:
            tuple[0] ... string
            tuple[1] ... None or list or dict, depending on case defined by tuple[0]
        There are several valid output cases. Their identifying key strings and
        value formats are explicitly defined in posconstants.py. These cases ARE
        validated here, so higher level code does not need to double-check whether
        they conform to the interface given in posconstants.
        """
        try:
            assert sync_mode in ['hard', 'soft']
            output = self._call_device('send_and_execute_tables',
                                       move_tables,
                                       sync_mode,
                                       lockedtimeout=100,  # [2021-02-12] JHS + CAD, time for possible canbus and powersupply resets
                                      )
            self.lock_timeout = False
            sendex.validate(output)
            return output
        except Exception as e:

            msg = 'FAILED: Could not send_and_execute move tables, in an undefined way.'
            msg += ' I.e. petalcomm did not receive an error value from petalcontroller'
            msg += f' in a format it could understand. Exception: {e}'
            self.lock_timeout = False
            # Return None for error data, output must always be tuple
            return msg, None

    def move(self, bus_id, can_id, direction, mode, motor, angle):
        """
        Low level test command to move a single positioner
        """
        try:
            return self._call_device('move', bus_id, can_id, direction, mode, str(motor), angle)
        except Exception as e:
            return 'FAILED: Can not execute send_move_excute command. Exception: %s' % str(e)

    def all_fiducials_off(self):
        """
        Broadcast command to set all fiducials off
        """
        try:
            return self._call_device('all_fiducials_off')
        except Exception as e:
            return 'FAILED: Can not call all_fiducials_off. Exception: %s' % str(e)

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
 
    def send_gfa_serial(self, message):
        """
        Send out message to GFA serial port
        """
        try:
            return self._call_device('send_gfa_serial', message)
        except Exception as e:
            return 'FAILED: Can not send message to GFA port.  Exception: %s' % str(e)

    def recv_gfa_serial(self):
        """
        Receive message from GFA serial port
        """
        try:
            return self._call_device('recv_gfa_serial')
        except Exception as e:
            return 'FAILED: Can not read GFA port.  Exception: %s' % str(e)

    def setup_can(self):
        """
        Set up CAN channels
        """
        try:
            return self._call_device('setup_can')
        except Exception as e:
            return 'FAILED: Can not setup CAN channels: %s' % str(e)

    def configure(self, *args, **kwargs):
        """
        Configure petalcontroller settings
        """
        try:
            return self._call_device('configure', *args, **kwargs)
        except Exception as e:
            return 'FAILED: Can not configure petalcontroller: %s' % str(e)

    def ops_state(self, state = None):
        """
        Read/Set petalcontroller ops_state
        """
        try:
            return self._call_device('ops_state', state = state)
        except Exception as e:
            return 'FAILED: Exception calling petalcontroller ops_state: %s' % str(e)        

    def clear_errors(self):
        """
        Clear petalbox error states
        """
        try:
            return self._call_device('clear_errors')
        except Exception as e:
            return 'FAILED: Can not clear errors: %s' % str(e)

    def pbhelp(self):
        """
        Display petalcontroller commands and pbget/pbset keys
        """
        try:
            return self._call_device('pbhelp')
        except Exception as e:
            return 'FAILED: Can not display pbhelp info: %s' % str(e)

    def check_and_exit_stop_mode(self):
        """
        Check if stop mode is on and exit if it is
        """
        try:
            return self._call_device('check_and_exit_stop_mode')
        except Exception as e:
            return 'FAILED: Can not check if stop mode is on or exit stop mode: %s' % str(e)

    def power_up(self, en_supplies = 'both', en_can_boards = 'both', en_sync_buffers = 'both'):
        """
        Initializes positioner power, CAN and SYNC buffer lines so that everything is ready for CAN communications
        and movetables.
        
        INPUTS:
        en_supplies: string (1, 2, or 'both')  that specifies which supplies are enabled
        en_can_boards:  string (1, 2, or 'both') the specifies which CAN boards are enabled
        en_sync_buffers:  string (1, 2, or 'both') that specifies which SYNC buffers are enabled
        
        'both' is the default for all three arguments.
        """
        try:
            return self._call_device('power_up', en_supplies, en_can_boards, en_sync_buffers)
        except Exception as e:
            return 'FAILED: Could not execute the power_up method: %s' % str(e)

    def power_down(self):
        """
        Turn positioner power supplies, buffer enables, and CAN boards off.
        """
        try:
            return self._call_device('power_down')
        except Exception as e:
            return 'FAILED: Could not execute the power_down method: %s' % str(e)

    def get(self, what):
        """
        returns petal controller information
        """
        return self._call_device('get', what)

    def check_can_ready(self, can_bus_list):
        """
        Petalcontroller checks that canbus is up in the linux kernal.
        """
        try:
            return self._call_device('check_can_ready', can_bus_list)
        except Exception as e:
            return 'FAILED: could not check can ready: %s' % str(e)

    def powercycle_systec_boards(self):
        """
        Petalcontroller powercycles systec boards with sufficient timing to
        recover from problems. Recommended to not be in OBSERVING when calling
        this function.
        """
        try:
            return self._call_device('powercycle_systec_boards', pyrotimeout=40.0)
        except Exception as e:
            return 'FAILED: could not powercycle_systec_boards: %s' % str(e)
