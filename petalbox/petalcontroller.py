#!/usr/bin/env python3
"""
   PROTODESI VERSION
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
   7/07/2016    IG          added telemetry functions: switch_en_ptl, read_temp_ptl, fan_pwm_ptl
   2/09/2016    IG          Implemented multiple canbus functionality (canbus received from unit_configuration files), removed set_fiducial command
  
"""

from DOSlib.application import Application
import time
import threading
import subprocess
import netifaces
import configobj

try:
    import ptltel
    telemetry_available = True
except:
    telemetry_available = False
import sys
import os

nonresponsive_canids = []
pc_defaults = '/home/msdos/dos_home/dos_products/petalbox/pc_safe_settings.conf'

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
    commands = ['set_led',              # implemented - usefull for testing (of rev 2 positioner boards)
                'set_device',            
                'get_fid_status',
                'get_device_status', 
                'get_pos_status', 
                'set_fiducials',  
                'configure',
                'move',                 # implemented - usefull for testing 
                'execute_sync',         # implemented
                'send_tables',          # implemented
                'set_posid',
                'get_sids',
                'set_periods',
                'set_currents',
                'ready_for_tables',
                'read_temp_ptl',
                'fan_pwm_ptl',
                'read_fan_pwm',
                'switch_en_ptl',
                'read_switch_ptl',
                'get_GPIO_names',
                'read_HRPG600',
                'read_fan_tach',
                'get_nonresponsive_canids',
                'reset_nonresponsive_canids',
                'pbset',
                'pbget',
                'get_posfid_info'
                ]

    # Default configuration (can be overwritten by command line or config file)
    defaults = {'default_petal_id' : 1,
                'controller_type' : 'HARDWARE',
                'autoconf' : True,
                }

    def init(self):
        """
        Initialize PetalController application. Set up variables, call configure
        """
        self.info('INITIALIZING Device %s' % self.role)
        self.loglevel('INFO')
        self.verbose=False
        # Get configuration information (add more configuration variables as needed)
        try:
            self.default_petal_id = int(self.config['default_petal_id'])
        except:
            self.default_petal_id = self.default['default_petal_id']
        self.autoconf = True if 'T' in str(self.config['autoconf']).upper() else False
        self.controller_type = self.config['controller_type']
        self.pc_defaults = configobj.ConfigObj(pc_defaults, unrepr=True, encoding='utf-8')
        self.simulator=False
        self.simulated_switch = {}
        self.simulated_pwm = {}
        self.fidstatus = {}
        self.pb_statuses = {}

        if self.controller_type =='SIMULATOR':
            self.simulator=True
        self.info('init: using controller type: %s' % self.controller_type)

        # Find list of canbus interfaces with SYSTEC module
        self.canlist = []
        for i in netifaces.interfaces():
            if i.startswith('can'):    # got a canbus interface
                try:
                    if 'broadcast' in netifaces.ifaddresses(i)[netifaces.AF_LINK][0]:
                        self.info('init: Found SYSTEC interface %s' % i)
                        self.canlist.append(i)
                except:
                    pass

        # If autoconf is set True, set the bitrate on the can interface(s) and bring them up using ip system calls
        if self.autoconf == True:
            try:
                for can in self.canlist:
                    retcode = subprocess.call(('sudo ip link set %s down' % can).split()) 
                    retcode += subprocess.call(('sudo ip link set %s type can bitrate 500000' % can).split()) 
                    retcode += subprocess.call(('sudo ip link set %s up' % can).split())                
                    self.info('init: Configured canbus interface %r. Return code: %r' % (can, retcode))

            except Exception as e:
               if self.verbose: print('Error initializing detected CAN channel(s).  Exception: ' + str(e))

        #communicate only with list of canbuses that have been both detected and configured
        self.canlist = self.canlist and self.pc_defaults[str(self.role)]['can_bus_list']

        # Bring in the Positioner Move object
        self.pmc=PositionerMoveControl(self.role, self.controller_type, self.canlist) # controller_type is HARDWARE or SIMULATOR
        if not self.simulator and telemetry_available:
            self.pt = ptltel.PtlTelemetry()

        self.status = 'INITIALIZED'
        self.info('Initialized')
        # call configure to setup the posid map
        retcode = self.configure('constants = DEFAULT')


    def configure(self, constants = 'DEFAULT'):
        """
        configure petal controller,
        load safe fan/power supply values
        """
        self.info('configuring...')
        self.pc_defaults.reload()
        #read power supply settings from config file and set accordingly
        self.switch_en_ptl("PS1_EN", 1 if self.pc_defaults[str(self.role)]['supply_power'][0] == 'on' else 0)
        self.switch_en_ptl("PS2_EN", 1 if self.pc_defaults[str(self.role)]['supply_power'][1] == 'on' else 0)
        self.switch_en_ptl("GFAPWR_EN", 1 if self.pc_defaults[str(self.role)]['supply_power'][2] == 'on' else 0)

        #read back default fan settings from config file and set accordingly
        self.switch_en_ptl("GFA_FAN1", 1 if self.pc_defaults[str(self.role)]['fan_power'][0] == 'on' else 0)
        self.switch_en_ptl("GFA_FAN2", 1 if self.pc_defaults[str(self.role)]['fan_power'][1] == 'on' else 0)
        self.fan_pwm_ptl("GFA_FAN1", self.pc_defaults[str(self.role)]['fan_duty'][0])
        self.fan_pwm_ptl("GFA_FAN2", self.pc_defaults[str(self.role)]['fan_duty'][1])

        #read back default sync/buffer enable settings from config file and set accordingly
        self.switch_en_ptl("BUFF_EN1", 0 if self.pc_defaults[str(self.role)]['buffer_enables'][0] == 'on' else 1)
        self.switch_en_ptl("BUFF_EN2", 0 if self.pc_defaults[str(self.role)]['buffer_enables'][1] == 'on' else 1)
        self.switch_en_ptl("SYNC", 1 if self.pc_defaults[str(self.role)]['sync'] == 'on' else 0)

        #read back default CAN board enable settings from config file and set accordingly
        self.switch_en_ptl("CANBRD1_EN", 1 if self.pc_defaults[str(self.role)]['can_power'][0] == 'on' else 0)
        self.switch_en_ptl("CANBRD2_EN", 1 if self.pc_defaults[str(self.role)]['can_power'][1] == 'on' else 0)

        #read back stop mode value and set
        if(self.pc_defaults[str(self.role)]['stop_mode'] == 'on'):
            self.pmc.enter_stop_mode(self.canlist)
        
        #read back fiducial initial settings and set
        self.fids = self.pc_defaults[str(self.role)]['fid_settings']
        self.can_map = self.pc_defaults[str(self.role)]['can_map']
        
        for key,value in self.fids.items():
            canbus = self.can_map[key]
            self.set_fiducials([canbus], [key], [value])

        self.status = 'READY'

        #initialize self.pb_statuses dictionary
        self.pb_statuses['all'] = 'return dictionary of all petalbox settings available'
        self.pb_statuses['power'] = [[self.pc_defaults[str(self.role)]['supply_power'][0] , self.pc_defaults[str(self.role)]['supply_power'][1], self.pc_defaults[str(self.role)]['supply_power'][2]], self.read_HRPG600()]
        self.pb_statuses['gfa_fan'] = {'inlet': [self.pc_defaults[str(self.role)]['fan_power'][0], self.pc_defaults[str(self.role)]['fan_duty'][0]], 'outlet': [self.pc_defaults[str(self.role)]['fan_power'][1], self.pc_defaults[str(self.role)]['fan_duty'][1]]}
        self.pb_statuses['sync'] = self.pc_defaults[str(self.role)]['sync']
        self.pb_statuses['buffers'] = [self.pc_defaults[str(self.role)]['buffer_enables'][0], self.pc_defaults[str(self.role)]['buffer_enables'][1]]
        self.pb_statuses['can_en'] = [self.pc_defaults[str(self.role)]['can_power'][0], self.pc_defaults[str(self.role)]['can_power'][1]]
        self.pb_statuses['temp'] = self.read_temp_ptl()
        self.pb_statuses['stop_mode'] = self.pc_defaults[str(self.role)]['stop_mode']
        self.pb_statuses['can_map'] = self.pc_defaults[str(self.role)]['can_map']
        self.pb_statuses['fids'] = self.pc_defaults[str(self.role)]['fid_settings']
        return self.SUCCESS
    
# PML functions (functions that can be accessed remotely)
    def pbset(self, key, value):
        """
        Setter for various petalbox telemetry and positioner variables.
        """
        if key not in ['power', 'gfa_fan', 'can_en', 'sync', 'buffers', 'stop_mode', 'can_map', 'fids']:  #setable keys
            return 'INVALID KEY' 
        if key == 'power': #[pos1pwr = 'on'/'off', pos2pwr = 'on'/'off', gfapwr = 'on'/'off'], or 'on', 'off' (turns all power supplies 'on'/'off')
            if not isinstance(value, list):
                if value not in ['on', 'off']:
                    return 'INVALID VALUE'
                else:
                    for pwrsupply in ["PS1_EN", "PS2_EN", "GFAPWR_EN"]:
                        pwr = 1 if value == 'on' else 0
                        self.switch_en_ptl(pwrsupply, pwr)
                    self.pb_statuses[key][0] = [value, value, value]
            else:
                for idx, pwrsupply in enumerate(["PS1_EN", "PS2_EN", "GFAPWR_EN"]):
                    pwr = 1 if value[idx] == 'on' else 0
                    self.switch_en_ptl(pwrsupply, pwr)
                self.pb_statuses[key][0] = value

        elif key == 'gfa_fan': #set enables and speed in format {'inlet': ['on'/'off', 50], 'outlet': ['on'/'off', 75]}
            if not isinstance(value, dict):
                return 'INVALID VALUE'
            self.switch_en_ptl("GFA_FAN1", 1 if value['inlet'][0] == 'on' else 0)
            self.switch_en_ptl("GFA_FAN2", 1 if value['outlet'][0] == 'on' else 0)
            self.fan_pwm_ptl("GFA_FAN1", int(value['inlet'][1]))
            self.fan_pwm_ptl("GFA_FAN2", int(value['outlet'][1]))
            self.pb_statuses[key] = value

        elif key == 'sync':
            if value not in ['on', 'off']:
                return 'INVALID VALUE'
            self.switch_en_ptl("SYNC", 1 if value == 'on' else 0)
            self.pb_statuses[key] = value

        elif key == 'buffers':
            if not isinstance(value, list):
                if value not in ['on', 'off']:
                    return 'INVALID VALUE'
                else:
                    for buffer in ["BUFF_EN1", "BUFF_EN2"]:
                        buff = 0 if value == 'on' else 1
                        self.switch_en_ptl(buffer, buff)
                    self.pb_statuses[key] = [value, value]
            else:
                for idx, buffer in enumerate(["BUFF_EN1", "BUFF_EN2"]):
                    buff = 0 if value[idx] == 'on' else 1
                    self.switch_en_ptl(buffer, buff)
                self.pb_statuses[key] = value

        elif key == 'can_en':
            if not isinstance(value, list):
                if value not in ['on', 'off']:
                    return 'INVALID VALUE'
                else:
                    for canbrd in ["CANBRD1_EN", "CANBRD2_EN"]:
                        en = 1 if value == 'on' else 0
                        self.switch_en_ptl(canbrd, en)
                    self.pb_statuses[key] = [value, value]
            else:
                for idx, canbrd in enumerate(["CANBRD1_EN", "CANBRD2_EN"]):
                    en = 1 if value[idx] == 'on' else 0
                    self.switch_en_ptl(canbrd, en)
                self.pb_statuses[key] = value
        
        elif key == 'fids':
            if not isinstance(value, list):
                return 'INVALID VALUE'
            else:
                self.set_fiducials(value[0], value[1], value[2])

        elif key == 'pbdefaults':
            #update config file from petal              
            pass

        elif key == 'stop_mode':
            if value not in ['on', 'off']:
                return 'INVALID VALUE'
            if value == 'on':
                self.enter_stop_mode(self.canlist)
            else:
                self.exit_stop_mode()
            self.pb_statuses[key] = value

        return self.SUCCESS

    def pbget(self, key):
        """
        Returns petal box statuses in format listed below.  Returns 'INVALID KEY' string if queried for non-existant status key.
        """
        if key == 'all':
            return self.pb_statuses
        if key == 'pos_temp':
            #self.pmc.get_pos_temp()
            pass
        if key == 'temp':
            self.pb_statuses[key] = self.read_temp_ptl()
        if key == 'fan_tach':
            pb_statuses[key] = self.read_fan_tach()
        if key == 'posfid_info':  #returns dict  {can_id: [s_id, can_bus, fw_vr, bl_vr]}
            info_list = [] 
            for canbus in self.canlist:
                info_list.append(self.get_posfid_info(canbus))
            return info_list
        if key == 'fids':
            self.pb_statuses[key] = self.get_fid_status()
        if key == 'power':
            self.pb_statuses[key] = [self.pb_statuses[key], self.read_HRPG600()]
            pass
        if key == 'can_en':
            pass

        return self.pb_statuses.get(key, 'INVALID KEY')

    def enter_stop_mode(self, canbuses):
        for canbus in canbuses:
            self.pmc.enter_stop_mode(canbus)

    def exit_stop_mode(self):
        self.switch_en_ptl("SYNC", 1)
        self.pb_statuses['sync'] = 'on'

    def get_posfid_info(self, canbus):
        pos_info = {}
        fw_vr = self.pmc.get_from_all(canbus, 20000, 11)
        fw_vr = self.pmc.format_versions(fw_vr)

        bl_vr = self.pmc.get_from_all(canbus, 20000, 15)
        bl_vr = self.pmc.format_versions(bl_vr)

        sid64 = self.pmc.get_from_all(canbus, 19)
        sid64 = self.pmc.format_sids(sid64)

        sidupper = self.pmc.get_from_all(canbus, 20000, 18)
        sidupper = self.pmc.format_sids(sidupper)

        sidlower = self.pmc.get_from_all(canbus, 20000, 17)
        sidlower = self.pmc.format_sids(sidlower)

        sidfull = {}
        for key,value in sidupper.items():
            sidfull[key] = sidupper[key] + ':' + sidlower[key]

        for key, value in sid64.items():
            try:
                bl = bl_vr[key]
            except:
                bl = 'too old'
            pos_info[key] = [fw_vr[key], bl, sidfull[key], sid64[key]]

    def get_sids(self, canbus):
        """
        Send the command to get silicon IDs
        """ 

        if self.pmc.get_sids(canbus):
            return self.SUCCESS  
        else:
            return self.FAILED

    def get_nonresponsive_canids(self):
        return nonresponsive_canids 

    def reset_nonresponsive_canids(self):
        nonresponsive_canids[:] = []
        return nonresponsive_canids 

    def set_posid(self, canbus, sid, new_posid):
        """
        Send the command to set positioner ID based on silicon IDs
        """ 
        if self.pmc.set_posid(canbus,sid,posid):
            return self.SUCCESS  
        else:
            return self.FAILED

    def get_GPIO_names(self):
        """
        Returns dictionary of GPIO pin names and descriptions
        """
        if telemetry_available:
            try:
                names_desc = self.pt.get_GPIO_names()
            except:
                return self.FAILED
        else:
            if self.simulator:
                names_desc = {'PS1_OK': 'Input for reading back feedback signal from positioner power supply 1', 'PS2_EN': 'Output pin that enables positioner power supply 1 when set high', 'GFA_FAN1': 'Output for enabling power to GFA fan 1', 'GFAPWR_OK': 'Input for reading back feedback signal from GFA power supply', 'PS2_OK': 'Input for reading back feedback signal from positioner power supply 2', 'CANBRD2_EN': 'Output for switching power to SYSTEC CAN board 2', 'CANBRD1_EN': 'Output for switching power to SYSTEC CAN board 1', 'GFAPWR_EN': 'Output for enabling GFA power supply', 'GFA_PWM2': 'Output (PWM) for controlling GFA_FAN2 speed', 'GFA_TACH2': 'Input (pulsed) connected to GFA_FAN2 tachometer sensor', 'W1': 'Input (1-wire) pin to which all temperature sensors are connected', 'BUFF_EN1': 'Active low enable for SYNC', 'BUFF_EN2': 'Active low enable for SYNC','GFA_TACH1': 'Input (pulsed) connected to GFA_FAN1 tachometer sensor', 'SYNC': 'Output pin for sending synchronization signal to positioners', 'GFA_FAN2': 'Output for enabling power to GFA fan 2', 'GFA_PWM1': 'Output (PWM) for controlling GFA_FAN1 speed', 'PS1_EN': 'Output pin that enables positioner power supply 1 when set high'}
            else:
                return 'FAILED: No GPIO name information available'
        return names_desc

    def read_HRPG600(self):
        """
        Read "DC-OK" signals from HRPG-600 series power supplies.  Returns dictionary, eg: {"PS1_OK" : True, "PS2_OK" : True, "GFAPWR_OK" : True}
        True = ON, False = OFF
        """
        if telemetry_available:
            try:
                psok = self.pt.read_HRPG600()
            except:
                return self.FAILED
        else:
            if self.simulator:
                psok = {"PS1_OK" : True, "PS2_OK" : True, "GFAPWR_OK" : True}
            else:
                return 'FAILED: No HRPG600 feedback information available'
        return psok

    def read_fan_tach(self):
        """
        Read GFA fan tachometer readings (in rpm), returns dict eg:  {'GFA_FAN1' : 5000, 'GFA_FAN2' : 5000}
        """
        if telemetry_available:
            try:
                tach = self.pt.read_fan_tach()
            except:
                return self.FAILED

        else:
            if self.simulator:
                tach = {'GFA_FAN1' : 5000, 'GFA_FAN2' : 5000}
            else:
                return 'FAILED: No GFA fan tachometer information available'
        return tach 

    def read_GPIOstate(self, pin_name):
        """
        Returns direction and value for GPIO pins setup as regular inputs and outputs (not PWM, 1-wire, or pulsed)
        """
        if telemetry_available:
            try:
                gpio_state = self.pt.read_GPIOstate(pin_name)
            except:
                return self.FAILED
        else:
            if self.simulator:
                gpio_state = ('out', 1)
            else:
                return 'FAILED: No GPIO state information available'
        return gpio_state

    def read_PWMstate(self):
        """
        Returns pwm duty cycle settings for GFA_FAN1 and GFA_FAN2 as dict.  eg: {'GFA_FAN1': 50, 'GFA_FAN2' : 10}
        """
        if telemetry_available:
            try:
                pwms = self.pt.read_PWMstate()
            except:
                return self.FAILED

        else:
            if self.simulator:
                pwms = {'GFA_FAN1' : 50, 'GFA_FAN2' : 10}
            else:
                return 'FAILED: No PWM duty setting information available'
        return pwms
        

    def read_temp_ptl(self):
        """
        Returns dictionary of temperatures in degrees C, by temp. sensor id.  eg. {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}, number of entries depends on the number of 1-wire devices detected on P8_07       
        """
        if telemetry_available:
            try:    
                temps = self.pt.read_temp_sensors()
            except IOError:
                return 'FAILED: no temperature sensors detected'
        else:
            if self.simulator:
                temps =  {'28-000003f9c7c0': 22.812, '28-0000075c977a': 22.562}
            else:
                return 'FAILED: No temperature information available'
        return temps

    def fan_pwm_ptl(self, pwm_out, percent_duty):
        """
        Set PWM duty cycle for fans.
    
        INPUTS
            pwm_out     string: 'GFA_FAN1' or 'GFA_FAN2')
            percent_duty    float 0. to 100., 0. = off

        RETURNS
            SUCCESS OR FAILED   
        
        """

        if pwm_out not in ['GFA_FAN1', 'GFA_FAN2']:
            return 'FAILED: invalid device for fan_pwm_ptl command'

        try:
            percent_duty = float(percent_duty)
            if percent_duty < 0.: percent_duty = 0.
            if percent_duty > 100.: percent_duty = 100.
        except:
            if self.verbose: 
                self.info('fan_pwm_ptl: pwm value error')
            return 'FAILED: fan_pwm_ptl: pwm value error'

        if telemetry_available:
            try:
                self.pt.control_pwm(str(pwm_out), percent_duty)
                return self.SUCCESS
            except Exception as e:
                rstring = 'fan_pwm_ptl: Exception calling control_pwm: %s' % str(e)
                self.error(rstring)
                return 'FAILED: ' + rstring
        else:
            if self.simulator:
                self.simulated_pwm[pwm_out] = percent_duty
                return self.SUCCESS
        return 'FAILED: Petalbox telemetry not available'

   
    def read_fan_pwm(self, pwm_out = None):
        """
        Read PWM duty cycle for fan or aux pwm.
    
        INPUTS
            pwm_out     None or string: 'GFA_FAN1', 'GFA_FAN2', 'PWM_AUX1', or 'PWM_AUX2')

        RETURNS
            dictionary with duty cycles        
        """
        allowed = ['GFA_FAN1', 'GFA_FAN2']
        if pwm_out is not None and pwm_out not in allowed:
            return 'FAILED: invalid device for fan_pwm_ptl command'
        results = {}
        if telemetry_available:
            if pwm_out == None:
                devices = allowed
            else:
                devices = [pwm_out]
            try:
                for d in devices:
                    results[d] = self.pt.read_pwm(d)
                return results
            except Exception as e:
                rstring = 'read_fan_pwm: Exception calling read_pwm: %s' % str(e)
                self.error(rstring)
                return 'FAILED: ' + rstring
        else:
            if self.simulator:
                if pwm_out == None:
                    return self.simulated_pwm
                elif pwm_out in self.simulated_pwm:
                    return {pwm_out : self.simulated_pwm[pwm_out]}
                else:
                    return 'FAILED: Invalid device for read_fan_pwm command'
        return 'FAILED: Petalbox telemetry not available'
    

    def switch_en_ptl(self, pin_name = "SYNC", state = 0):
        """
        Switch state of Beaglebone GPIO outputs (power supply enables, fan enables, etc.)

        INPUTS
            pin_name    string, eg. "GFA_FAN1"
            state       int 0, or 1 (0 = off, 1 = on)

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
			"CANBRD1_EN" = "P8_9"
			"CANBRD2_EN" = "P8_11"
			"BUFF_EN1" = "8_10"
			"BUFF_EN2" = "8_8"
        """
       
        if telemetry_available:
            try:
                self.pt.switch(pin_name, state)
                return self.SUCCESS
            except Exception as e:
                rstring = 'switch_en_ptl: Exception calling switch function: %s' % str(e)
                self.error(rstring)
                return 'FAILED: ' + rstring
        else:
            if self.simulator:
                self.simulated_switch[pin_name] = state
                return self.SUCCESS
            return 'FAILED: Petalbox telemetry is not available'

    
    def read_switch_ptl(self, pin_name = None):
        """
        Read state of Beaglebone GPIO outputs (power supply enables, fan enables, etc.)

        INPUTS
            pin_name    string, eg. "GFA_FAN1"

        RETURNS
            dictionary with pin states


        PIN NAMES

                        #Outputs
                        "SYNC" = "P9_12"
                        "PS1_EN" = "P9_11"
                        "PS2_EN" = "P9_13"
                        "GFA_FAN1" = "P8_12"
                        "GFA_FAN2" = "P8_14"
                        "GFAPWR_EN" = "P8_15"
        """
        if telemetry_available:
            try:
                retcode = self.pt.read_switch()
                if pin_name == None:
                    return retcode
                elif pin_name in retcode:   # add check that retcode is a dictionary
                    return retcode[pin_name]
                else:
                    return 'FAILED: Invalid pin name'
            except Exception as e:
                rstring = 'read_switch_ptl: Exception calling read_switch function: %s' % str(e)
                self.error(rstring)
                return 'FAILED: ' + rstring
        else:
            if self.simulator:
                if pin_name == None:
                    return self.simulated_switch
                elif pin_name in self.simulated_switch:
                    return {pin_name : self.simulated_switch[pin_name]}
                else:
                    return 'FAILED: Invalid pin name'
        return 'FAILED: Petalbox telemetry is not available'
    
    def set_fiducials(self, canbuses, ids, percent_duty):
        """
        Set the ficucial power levels (by setting the duty percentage)
        Inputs include list with canbuses, percentages, periods and ids
        Returns SUCCESS or error message.
        canbuses     ... list of strings that specify the can bus number, eg. ['can2', 'can3']
        ids          ... list of fiducial can ids
        percent_duty ... list of values, 0-100, 0 means off
        
        """
        #set single fiducial without having to use list notation on the console
        if not isinstance(ids, list) and not isinstance(percent_duty,list) and not isinstance(canbuses, list):
            canbuses = [canbuses]
            ids = [ids]
            percent_duty = [percent_duty]

        #set list of fiducials on single canbus to the same duty cycle, this operation is assumed if canbus and duty != list, but ids is a list
        if isinstance(ids, list) and not isinstance(percent_duty, list) and not isinstance(canbuses, list):
            canbuses = [canbuses] * len(ids)
            percent_duty = [percent_duty] * len(ids)
    
        for id in range(len(ids)):
            # assemble arguments for canbus/firmware function
        
            posid=int(ids[id])

            duty = int(percent_duty[id])
            canbus = str(canbuses[id])
            self.fidstatus[str(ids[id])] = int(percent_duty[id])

            if not self.simulator:
                if not self.pmc.set_fiducials(canbus, posid, duty):
                    if self.verbose: print('set_fiducials: Error')
                    return self.FAILED
            else:
                pass        

            if self.verbose: print('ID: %s, Percent %s' % (ids[id],percent_duty[id]))
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
                {'canid': 0,'busid': 'can0', 'nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}

            The fields have the following types and meanings:

                canid         ... unsigned integer          ... identifies the positioner by 'CAN_ID'
                busid	      ... string                    ... identifies the positioner's canbus as string such as 'can0'
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
        if self.verbose:
            self.info("*** tables***")
            self.info(move_tables)

        #reset SYNC line
        self.switch_en_ptl('SYNC', 0)
        self.pb_statuses['sync'] = 'off'

        if not self.simulator:
            for table in move_tables:  # each table is a dictionary
                posid=int(table['canid'])
                canbus = str(table['busid'])
                nrows=table['nrows']
                xcode = '1'
                if self.verbose:
                    print("** nrows **"+str(nrows))   #for each table, xcode starts as 1
                for row in range(nrows):
                    motor_steps_T=table['motor_steps_T'][row]
                    motor_steps_P=table['motor_steps_P'][row]
                    speed_mode_T=table['speed_mode_T'][row]
                    speed_mode_P=table['speed_mode_P'][row]
                    post_pause=nint(table['postpause'][row])

                    if (motor_steps_T & motor_steps_P): #simultaneous movement of theta and phi
                        post_pause_T = 0        #first axis command gets sent with 0 post_pause to make firmware perform simultaneous theta/phi move
                    else:
                        post_pause_T = post_pause       
     
                    if self.verbose: print("send_tables:",  canbus, posid,xcode,'theta',motor_steps_T,speed_mode_T,post_pause)
                    if not self.pmc.load_table_rows(canbus, posid,xcode,'theta',motor_steps_T,speed_mode_T,post_pause_T):
                        if self.verbose: print('send_tables: Error')
                        #return self.FAILED
                    if row == (nrows - 1):  #last row in move table, xcode = 2
                        xcode='2'
                    if not self.pmc.load_table_rows(canbus, posid,xcode,'phi',motor_steps_P,speed_mode_P,post_pause):
                        if self.verbose: print('send_tables: Error')
                        #return self.FAILED
        else:
            pass                

        #if self.verbose: print('send_tables: %s' % repr(move_tables))
        return self.SUCCESS


    def move(self, canbus, posid, direction, move_mode, motor, angle ):
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
    
        if mode not in ['hard','soft']:
            rstring = 'execute_sync: Invalid arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring
        if mode == 'hard':
            self.switch_en_ptl('SYNC', 1)
            self.pb_statuses['sync'] = 'on'
        if mode == 'soft':	#send soft sync command to all CAN buses that have been both detected and configured
            for canbus in self.canlist:     
                self.pmc.send_soft_sync(canbus , 20000)

        return self.SUCCESS

    def set_led(self, canbus, posid, state):
        """
        Send the command to set positioner LED ON or OFF
        """ 
        if not isinstance(posid,int):
            rstring = 'set_led: Invalid posid arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring
        if state.lower() not in ['on','off']:
            rstring = 'set_led: Invalid LED state arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring

        if self.pmc.set_reset_leds(canbus, posid, state.lower()):
            return self.SUCCESS
        else:
            return self.FAILED

    def set_currents(self, canbus, posid, P_currents, T_currents):
        if self.pmc.set_currents(canbus, posid, P_currents, T_currents):
            return self.SUCCESS
        else:
            return self.FAILED

    def set_periods(self, canbus, can_id, creep_period_m0, creep_period_m1, spin_period):

        if self.pmc.set_periods(canbus, can_id, creep_period_m0, creep_period_m1, spin_period):
            return self.SUCCESS
        else:
            return self.FAILED

   
    def set_pos_constants(self, posids, settings):
        """
        Sets positioners identified by ids in the list posids to corresponding
        settings in the (dictionary? list of dicts?) settings.
        """
        if self.verbose:
            print('set_pos_constants: ids = %s, settings = %s' % (repr(posids), repr(settings)))
        return self.SUCCESS

    def set_device(self, posid, attributes):
        """
        Set a value on a device other than positioners or fiducials. This includes
        fans, power supplies, and sensor
        """
        if self.verbose:
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
        status = self.fidstatus
        return status

    def get_pos_status(self, busids, posids):
        """
        Returns positioner movement status.
        Output is a dictionary with keys = can ids and values = status
        """
        
        retcode=self.pmc.get_pos_status(busids, posids)
        
        return retcode

    def ready_for_tables(self, busids, posids):
        status=False
        if self.verbose:
            print('ready_for_tables - BUSIDS POSIDS: ', busids, posids)
        dev_status=self.get_pos_status(busids, posids)
        
        try:
            for posid in dev_status:
                if dev_status[posid] != 'BUSY':
                    status=True
                else:
                    status=False
                    return status
            return status
        except:
            return True
    
    def main(self):
        while not self.shutdown_event.is_set():
            # Nothing to do
            time.sleep(1)

        if self.verbose: print('Device exits')

######################################

class PositionerMoveControl(object):
    #can_frame_fmt = "=IB3x8s"
    #gear_ratio = {}
    #gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
    #gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
    #gear_ratio['faulhaber'] = 256.0          # faulhaber "256:1", output rotation/motor input

    """
        INPUTS
            role: device (role) name for this petal controller (string)
            controller_type:  either HARDWARE or SIMULATOR  (string)
            can_list: list of canbuses (strings). Example: canlist=['can0','can2']
    """

    def __init__(self,role,controller_type, can_list):
        if controller_type == 'HARDWARE':
            import posfidcan
        else:
            import posfidcansim as posfidcan

        self.verbose=False
        self.role=role
        self.__can_frame_fmt = "=IB3x8s"
        if isinstance(can_list, (list, tuple)) and len(can_list) != 0:
            can_list = can_list
        elif isinstance(can_list,str):
            can_list = [can_list]
      
        self.pfcan={}
        if self.verbose:
            print("**** canlist ***",can_list)
        for canbus in can_list:
            try:
                self.pfcan[canbus]=posfidcan.PosFidCAN(canbus)
            except Exception as e:
                if self.verbose: print('ERROR in pmc init: ', str(e))
        self.Gear_Ratio=(46.0/14.0+1)**4 # gear_ratio for Namiki motors
        self.bitsum=0
        self.cmd={'led':5} # container for the command numbers 'led_cmd':5  etc.
        self.posid_all=20000

    def enter_stop_mode(self, canbus):
        self.pfcan[canbus].send_command(20000, 40, '')
   
    def format_sids(self, sid_dict):
        for key,value in sid_dict.items():
            sid_dict[key] = ":".join("{:02x}".format(c) for c in value)
        return sid_dict

    def format_versions(self, vr_dict):
        for key,value in vr_dict.items():
            if len(value) == 1:
                vr_dict[key] = fw=str(int(ord(value))/10)
            else:
                vr_dict[key] = str(int(str(value[1]),16))+"."+str(int(str(value[0]),16))
        return vr_dict

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
        if self.verbose:
            print("set leds >>> canbus,posid,select",canbus,posid,select)
        try:        
            self.pfcan[canbus].send_command(posid,5, str(select).zfill(2))
            return True
        except:
            return False  

    def set_fiducials(self, canbus, posid, percent_duty):
        
        """ Constructs the command to send fiducial control signals to the theta/phi motor pads.
            This also sets the device mode to fiducial (rather than positioner) in the firmware.

            INPUTS
                canbus:         list of strings, can bus (example 'can2')        
                posids:         list of ints, positioner id (example 1008)
                percent_dutys:  list of floats, percent duty cycle of waveforms going to the 
                                theta/phi pads (example .5)
        """

        device_type = '01'  #fiducial = 01, positioner = 00
        duty = str(hex(int(65535.*percent_duty/100)).replace('0x','')).zfill(4)
        if self.verbose:
            print(canbus, posid, 16, duty)
        try:        
            self.pfcan[canbus].send_command(posid, 25, device_type)
            self.pfcan[canbus].send_command(posid, 16, duty)
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

    def get_from_all(self, canbus, command):
        data = self.pfcan[canbus].send_command_recv_multi(20000, command, '')
        return data


    def get_pos_status(self, busids, posids):
        
        """
        Signals the positionrs to start execution of move tables.         
        """
        status={}
        if self.verbose:
            print('BUSIDS get_pos_status: ',busids) 
        for id in range(len(posids)):
            posid=posids[id]
            status[posid]='UNKNOWN'
                 
            canbus = busids[id]
            try:
                posid_return,stat=self.pfcan[canbus].send_command_recv(posid,13,'')
                if self.verbose: print("posid_return,stat: ",posid_return,stat)
                stat=ord(stat)
            except:
                return_str = 'ERROR: Unresponsive positioner. CAN_ID = %s  BUS_ID = %s'%(str(posid), canbus)
                if posid not in nonresponsive_canids:
                    nonresponsive_canids.append(posid)
                return return_str
            if stat: status[posid]='BUSY'
            if not stat: status[posid]='DONE'
        return status        


    def set_currents(self,canbus, posid, P_currents, T_currents):
        """
            Sets the currents for motor 0 (phi) and motor 1 (theta).
            Currents are entered as percents (e.g. spin current = 70, cruise_current = 50, creep_current = 30)
        """   

        spin_current_m0 ,cruise_current_m0 ,creep_current_m0 ,hold_current_m0 = P_currents
        spin_current_m1 ,cruise_current_m1 ,creep_current_m1 ,hold_current_m1 = T_currents

        spin_current_m0 = str(hex(spin_current_m0).replace('0x','')).zfill(2)
        #print(spin_current_m0)
        cruise_current_m0 = str(hex(cruise_current_m0).replace('0x','')).zfill(2)
        creep_current_m0 = str(hex(creep_current_m0).replace('0x','')).zfill(2)
        hold_current_m0 = str(hex(hold_current_m0).replace('0x','')).zfill(2)   
        m0_currents = spin_current_m0 + cruise_current_m0 + creep_current_m0 + hold_current_m0
        #print(m0_currents)
        spin_current_m1 = str(hex(spin_current_m1).replace('0x','')).zfill(2)
        cruise_current_m1 = str(hex(cruise_current_m1).replace('0x','')).zfill(2)
        creep_current_m1 = str(hex(creep_current_m1).replace('0x','')).zfill(2)
        hold_current_m1 = str(hex(hold_current_m1).replace('0x','')).zfill(2)           
        m1_currents = spin_current_m1 + cruise_current_m1 + creep_current_m1 + hold_current_m1
        #print(m1_currents)
        try:
            self.pfcan[canbus].send_command(posid,2,m0_currents + m1_currents)
            return True
        except:
            return False

    def set_periods(self, canbus, posid, creep_period_m0, creep_period_m1, spin_period):
        """
            canbus - string that specifies the canbus, eg. 'can2'
            posid - int, positioner id, eg. 20000
            creep_period_m0 - e.g. period = 5: 18,000/3600/5 = 1 rev/sec = 60 rpm creep rate
            creep_period_m1 - e.g period=5: 18,000/3600/5 = 1 rev/sec = 60 rpm creep rate
            spin_period - Number of times to repeat each angular diplacement in spin-up table
        """

        if self.verbose:  print(posid)
        posid = int(posid)
        if self.verbose:  print('SET_PERIODS CANBUS: ' + canbus)      
        creep_period_m0=str(hex(creep_period_m0).replace('0x','')).zfill(2)
        creep_period_m1=str(hex(creep_period_m1).replace('0x','')).zfill(2)
        spin_steps=str(hex(spin_period).replace('0x','')).zfill(2)
        
        if self.verbose: print("Data sent: %s" % creep_period_m0+creep_period_m1+spin_steps)
        try:
            self.pfcan[canbus].send_command(posid,3,creep_period_m0 + creep_period_m1 + spin_steps)
            return True
        except:
            if self.verbose: print ("Sending command 3 failed")
            return False
    

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
                return 0
        except:
            if self.verbose: print("Error loading table row!")
            return 0

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
            if self.verbose: print ("Invalid argument for xcode!")
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
            if self.verbose: print ("Sending command 4 failed")
            return 0

        if xcode == '1': # increment bitsum if xcode=1 
            data=int(xcode + s_select,16) + int(s_motor_steps,16) + int(s_pause,16) + 4                             
            self.bitsum += data
            #print(str(hex(data).replace('0x','').zfill(8)))
            #print('Bitsum =', self.bitsum)
            return 1

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
                    if self.verbose: print("Did not receive checksum match after sending a move table")
                    return 0
                else:
                    return 1
            except:
                self.bitsum=0
                if posid not in nonresponsive_canids:
                    nonresponsive_canids.append(posid)
                if self.verbose: print ("Sending command 8 failed")
                return 0
        if xcode == '0':
            return 1
        return 0    

######################################

if (__name__ == '__main__'):
    """
    command line arguments are forwarded to the application framework
    Arguments for the PetalController include controller_type  (set to SIMULATOR
    to run without canbus/BBB hardware) and role. The convention is to give the
    PetalControllers the role name PCx where x is the petal number (from 0 - 9)
    """
    p = PetalController(device_mode=True, service='PetalControl')
    p.run()
    sys.exit()

