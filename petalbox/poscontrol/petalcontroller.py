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
import sys

def set_bit(value, bit):
    return value | (1<<bit)

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
                'send_move_execute'
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


    def send_move_execute(self, pos_id, direction, mode, motor, angle ):
        """
        Sends single move and executes.
        arguments:
            direction: cw, ccw
            mode: cruise, creep
            motor: theta, phi   (1,0)
            angle: angle (in degrees)
        """
        ex_code=0 # single command
        pause=0
        select=0
        if direction.lower() in ['cw','ccw']:
            if direction.lower()=='cw':
                select=set_bit(select,0)     
        else:
            rstring = 'send_move_execute: Invalid arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring

        if mode.lower() in ['creep','cruise']:
            if mode.lower()=='cruise':
                select=set_bit(select,1)     
        else:
            rstring = 'send_move_execute: Invalid arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring

        if motor in ['0','1']:
            if motor=='1':
                select=set_bit(select,2)     
        else:
            rstring = 'send_move_execute: Invalid arguments.'
            self.error(rstring)
            return 'FAILED: ' + rstring

        select_flags=select  #2  # CW cruise
        
        retcode=self.pmc.load_rows(12, ex_code, select_flags, angle, pause, readback=True)

#        print('send_tables: %s' % repr(move_tables))
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

        retcode = self.pmc.set_reset_leds(pos_id,state.lower())
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
    can_frame_fmt = "=IB3x8s"
    def __init__(self):
                        
        self.pfcan=posfidcan.PosFidCAN('can2')
        self.Gear_Ratio=337 # needs to be fixed - correct value is in Joe's Matlab code
        self.bitsum=0
        self.cmd={} # container for the command numbers 'led_cmd':5  etc.



    def set_reset_leds(self, pos_id, state):
        onoff={'on':1,'off':0}
        select =onoff[state]
        try:        
            self.pfcan.send_command(pos_id,5, str(select).zfill(2))
            return False
        except:
            return True   


    def set_currents(self,pos_id, spin_current_m0, cruise_current_m0, creep_current_m0, hold_current_m0, spin_current_m1, cruise_current_m1, creep_current_m1, hold_current_m1):
       
        spin_current_m0 = str(hex(spin_current_m0).replace('0x','')).zfill(2)
        cruise_current_m0 = str(hex(cruise_current_m0).replace('0x','')).zfill(2)
        creep_current_m0 = str(hex(creep_current_m0).replace('0x','')).zfill(2)
        hold_current_m0 = str(hex(hold_current_m0).replace('0x','')).zfill(2)   

        spin_current_m1 = str(hex(spin_current_m1).replace('0x','')).zfill(2)
        cruise_current_m1 = str(hex(cruise_current_m1).replace('0x','')).zfill(2)
        creep_current_m1 = str(hex(creep_current_m1).replace('0x','')).zfill(2)
        hold_current_m1 = str(hex(hold_current_m1).replace('0x','')).zfill(2)           
    
        try:
            self.pfcan.send_command(pos_id,2,spin_current_m0 + cruise_current_m0 + creep_current_m0 + hold_current_m0 + spin_current_m1 + cruise_current_m1 + creep_current_m1 + hold_current_m1)
            return 0
        except:
            return 1   


    def set_periods(self,pos_id, creep_period_m0, creep_period_m1, spin_steps):
           
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


    def load_rows(self,pos_id, ex_code,select,amount,pause,readback=True):
        
        ex_code=str(ex_code)    # 0,1,2 -   0: happens immediately
                                #           1: command in movetable
                                #           2: last command, i.e end of move table
        #select_flags=str(select_flags)      # 
        pause = str(hex(pause).replace('0x','')).zfill(4)

        #select=dict(cw_cruise_0 = 2, ccw_cruise_0 = 3, cw_cruise_1 = 6, ccw_cruise_1 = 7, cw_creep_0 = 0, ccw_creep_0 = 1, cw_creep_1 = 4,  ccw_creep_1 = 5, pause_only = 8)
        
        if select in [0,4,1,5]:   #== 0 or select[select_flags] == 4 or select[select_flags] == 1 or select[select_flags] == 5):
            amount=amount*self.Gear_Ratio/.1
        else:
            amount=amount*self.Gear_Ratio/3.3
            
        
        amount=str(hex(int(amount)).replace('0x','').zfill(6))
        #elect_flags=str(select[select_flags])
        select=str(select)
        if ex_code in ['1','2']:       

            try:
            
                print('Data sent is: %s (in hex)'%(str(ex_code + select + amount + pause)))
                self.pfcan.send_command(pos_id,4, str(ex_code + select  + amount + pause))
                

                if(ex_code=='1'):   
                    
                    print(str(hex(int(ex_code + select,16) + int(amount,16) + int(pause,16) + 4).replace('0x','').zfill(8)))                                      
                    self.bitsum += int(ex_code + select,16) + int(amount,16) + int(pause,16) + 4
                    print('Bitsum =', self.bitsum)

                return 0
    
            except:

                print ("Sending command 4 failed")
                return 1
        else:
            #Send both last command and bitsum, reset bitsum for next move table    
        
            try:
                print('we got here!')
                print('excode',ex_code)
                print('selectflags',select)
                print('amaunt',amount)
                print('pause',pause)	            
                print('Data sent is: %s (in hex)'%(str(ex_code + select + amount + pause)))

                self.pfcan.send_command(pos_id,4, str(ex_code + select + amount + pause))
                self.bitsum += int(ex_code + select,16) + int(amount,16) + int(pause,16) + 4
                print('Bitsum =', self.bitsum)
                
                self.pfcan.send_command(pos_id,9, str(hex(self.bitsum).replace('0x','').zfill(8)))
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

