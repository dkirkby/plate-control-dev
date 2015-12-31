# PERHAPS MORE PRODUCTIVE TO WRITE A VISUALIZER / SIMULATOR THAT TAKES INPUT FROM POSARRAYMASTER?

import numpy
import time
import serial
import serial.tools.list_ports
import warnings
import string
import posmodel

class LegacyPositionerComm(object):
    """Placeholder for PetalComm which interacts with legacy (circa mid-2015)
    fiber positioner driver (Lawicell CAN-USB via ascii command) and firmware
    (OpenLoopTest.c).

    The functionality here will be completely (and much more cleanly) replaced
    by a new PetalComm module. In the interim, this module will allow testing
    other aspects of the positioner control software on real positioner hardware.
    """

    def __init__(self, com_port):
        """com_port argument is a string, such as 'COM5'
        """
        self.steps_arg_n_bytes = 2  # number of bytes used to argue a quantity of steps to driver
        self.max_arguable_steps = self.steps_arg_n_bytes ** 16 - 1  # how large of an 'n steps' argument can be sent to driver
        self.CAN_comm = LawicellCANUSB(com_port)  # object that communicates over CAN with hardware
        self.settings_hold_time = 0.05 # seconds to wait for commands to get sent to firmware
        self.tables = []                                                          # very specific to this hacked-together legacy implementation
        self.master = []                                                          # very specific to this hacked-together legacy implementation
        typical_posmodel = posmodel.PosModel()                                    # very specific to this hacked-together legacy implementation
        self.stepsize_cruise = typical_posmodel._stepsize_cruise                  # very specific to this hacked-together legacy implementation
        self.speed_cruise = typical_posmodel._motor_speed_cruise                  # very specific to this hacked-together legacy implementation
        self.spinup_distance = typical_posmodel.state.read('SPINUPDOWN_DISTANCE') # very specific to this hacked-together legacy implementation
        self.stepsize_creep = typical_posmodel._stepsize_creep                    # very specific to this hacked-together legacy implementation
        self.speed_creep = typical_posmodel._motor_speed_creep                    # very specific to this hacked-together legacy implementation
        self.est_time_buffer = 0.1                                                # very specific to this hacked-together legacy implementation

# The send_tables and execute_moves command are what interface to the non-legacy other aspects of the code.
    def send_tables(self,tables):
        self.tables = tables # in non-legacy future code, this is where tables get uploaded to positioners

    def execute_moves(self):
        for tbl in self.tables:
            self.set_motor_params(self.master.get(tbl['posid'],'BUS_ID'),
                                  self.master.get(tbl['posid'],'CREEP_PERIOD'),
                                  self.master.get(tbl['posid'],'CURR_SPIN_UP_DOWN'),
                                  self.master.get(tbl['posid'],'CURR_CRUISE'),
                                  self.master.get(tbl['posid'],'CURR_CREEP'),
                                  self.master.get(tbl['posid'],'CURR_HOLD'))
            n = tbl['nrows']
            T = self.master.get(tbl['posid'],'MOTOR_ID_T')
            P = self.master.get(tbl['posid'],'MOTOR_ID_P')
            cruise_steps = LegacyPositionerComm.zeros2d(n,2)
            creep_steps  = LegacyPositionerComm.zeros2d(n,2)
            for i in range(n):
                if tbl['speed_mode_T'][i] == 'cruise':
                    cruise_steps[i][T] = tbl['motor_steps_T'][i]
                elif tbl['speed_mode_T'][i] == 'creep':
                    creep_steps[i][T] = tbl['motor_steps_T'][i]
                else:
                    print('bad speed_mode_T')
                if tbl['speed_mode_P'][i] == 'cruise':
                    cruise_steps[i][P] = tbl['motor_steps_P'][i]
                elif tbl['speed_mode_P'][i] == 'creep':
                    creep_steps[i][P] = tbl['motor_steps_P'][i]
                else:
                    print('bad speed_mode_P')
                self.move_motors(self.master.get(tbl['posid'],'BUS_ID'),cruise_steps[i],creep_steps[i])
                #print('Moving ' + str(self.master.get(tbl['posid'],'BUS_ID')) + ' by...  Tcruise:' + str(cruise_steps[i][T]) + '  Tcreep:' + str(creep_steps[i][T]) + '  Pcruise:' + str(cruise_steps[i][P]) + '  Pcreep:' + str(creep_steps[i][P]))
                #time.sleep(tbl['move_time'][i])
                #time.sleep(tbl['postpause'][i])

# The items below are all specific to legacy firmware, and not for general future usage or copying.
    def set_motor_params(self, busid, creep_period, curr_spin_up_down, curr_cruise, curr_creep, curr_hold):
        self.set_creep_parameters(busid, curr_hold, should_bump_creep_current = 0)
        self.set_creep_periods(busid, creep_period)
        self.set_currents(busid, curr_spin_up_down, curr_cruise, curr_creep)

    def move_motors(self, bus_id, steps_cruise, steps_creep):
        """Inputs: bus_id       ... canbus integer id of the positioner to command
                   steps_cruise ... [1x2] cruise steps on motor0, motor1 axes, sign indicates direction
                   steps_creep  ... [1x2] creep steps on motor0, motor1 axes, sign indicates direction

        be sure to call set_motor_params appropriately at least once for the given positioner before any move_motors
        """

        # break up creep steps by sign
        steps_creep_ccw = [0,0]
        steps_creep_cw = [0,0]
        for i in range(len(steps_creep)):
            if steps_creep[i] > 0:
                steps_creep_ccw[i] = steps_creep[i]
            else:
                steps_creep_cw[i] = -steps_creep[i]

        # if desired number of steps is greater than driver argument allows, must request multiple consecutive moves
        types = [['cruise','cruise'],['creep_ccw','creep_ccw'],['creep_cw','creep_cw']]
        steps = [steps_cruise, steps_creep_ccw, steps_creep_cw]
        i = 0
        while i < len(steps):
            while abs(steps[i][0]) > self.max_arguable_steps or abs(steps[i][1]) > self.max_arguable_steps:
                steps.insert(i,[0,0])
                types.insert(i,types[i])
                for j in range(len(steps[i])):
                    if abs(steps[i+1][j]) > self.max_arguable_steps:
                        sign = numpy.sign(steps[i+1][j])
                        steps[i][j] = sign * self.max_arguable_steps
                        steps[i+1][j] -= sign * self.max_arguable_steps
                i += 1
            i += 1

        # clean up any all-zero rows
        i = 0
        while i < len(steps):
            if all(x == 0 for x in steps[i]):
                steps.pop(i)
                types.pop(i)
            else:
                i += 1

        # loop thru the (possibly) multiple moves, executing them
        est_time = [0]*len(steps)
        distance_moved = [[0,0]]*len(steps)
        for i in range(len(steps)):
            # form bytes flagging which types of moves to execute
            bits = LegacyPositionerComm.zeros2d(2,8)
            exec_bytes = ''
            strbits=''
            for j in range(len(steps[i])):
                for n in range(0, 3):  # enable cw spin-up, cruise, spin-down
                    if steps[i][j] > 0 and types[i][j] == 'cruise':
                        bits[j][n] = 1
                    else:
                        bits[j][n] = 0
                for n in range(3, 6):  # enable ccw spin-up, cruise, spin-down
                    if steps[i][j] < 0 and types[i][j] == 'cruise':
                        bits[j][n] = 1
                    else:
                        bits[j][n] = 0
                if steps[i][j] != 0 and types[i][j] == 'creep_ccw':
                    bits[j][6] = 1
                else:
                    bits[j][6] = 0
                if steps[i][j] != 0 and types[i][j] == 'creep_cw':
                    bits[j][7] = 1
                else:
                    bits[j][7] = 0
                for k in bits[j]:
                    strbits+=str(k)
                exec_bytes += '{0:{width}{base}}'.format(int(strbits, base=2), base='X', width=2)  # base = X for uppercase Hexadecimal numbers
                strbits=''
            exec_bytes = exec_bytes.replace(' ','0')

            # send number of steps for the next move
            cruise_amts = [0]*4
            creep_amts  = [0]*4
            this_time = [0,0]
            this_distance_moved = [0,0]

            for j in range(len(steps[i])):
                if types[i][j] == 'cruise':
                    J = j*2 # to put into correct places in the cruise_amts array
                    cruise_amts[J] = abs(steps[i][j])
                    cruise_time = abs(steps[i][j]) * self.stepsize_cruise / self.speed_cruise
                    this_time[j] = cruise_time + (cruise_time != 0) * self.spinup_distance / self.speed_cruise
                    this_distance_moved[j] = steps[i][j] * self.stepsize_cruise + numpy.sign(steps[i][j]) * 2 * self.spinup_distance
                elif types[i][j] == 'creep_cw':
                    J = j*2 # to put into correct places in the creep_amts array
                    creep_amts[J] = abs(steps[i][j])
                    this_time[j] = abs(steps[i][j]) * self.stepsize_creep / self.speed_creep
                    this_distance_moved[j] = -steps[i][j] * self.stepsize_creep
                elif types[i][j] == 'creep_ccw':
                    J = j*2 + 1  # to put into correct places in the creep_amts array
                    creep_amts[J] = abs(steps[i][j])
                    this_time[j] = abs(steps[i][j]) * self.stepsize_creep / self.speed_creep
                    this_distance_moved[j] = steps[i][j] * self.stepsize_creep
                distance_moved[i][j] += this_distance_moved[j]
                est_time[i] += max(this_time)
            self.send_cmd(bus_id,'Set_Cruise_and_CW_Creep_Amounts', cruise_amts)
            self.send_cmd(bus_id,'Set_CCW_Creep_and_CW_Creep_Amounts', creep_amts)
            deg = '\u00b0'
            print('time: {:.3f}   motor1: {:9s} {:8.1f}{}   motor0: {:9s} {:8.1f}{}'.format(est_time[i],types[i][1],distance_moved[i][1],deg,types[i][0],distance_moved[i][0],deg))
            self.send_cmd(bus_id, 'Execute_Move', exec_bytes) # send command to driver, and start timer for (assumed) completion
            #time.sleep(est_time[i] + self.est_time_buffer) # WAIT FOR MOVE TO COMPLETE (or may handle pausing at a higher level)

        # return the total distance moved
        total_distance = [0,0]
        total_distance[0] = sum([distance_moved[k][0] for k in range(len(distance_moved))])
        total_distance[1] = sum([distance_moved[k][1] for k in range(len(distance_moved))])
        return distance_moved

    def send_cmd(self, bus_id, cmd_name, args):
        """
        Constructs command line string and executes it. Typically don't
        use this function directly, but not privatized yet for debugging
        purposes.

        If args is ...
        1xN char array ... assumed that every 2 chrs is a hex byte of even length
        Nx2 char array ... assumed that each row is a hex byte
        1D number array ... assumed that each entry is a decimal number
        """
        pause_after_send = self.settings_hold_time
        if cmd_name == 'Set_Currents':
            cmd_num = 2
            bytes_per_arg = 1
        elif cmd_name == 'Set_Creep_Periods':
            cmd_num = 3
            bytes_per_arg = 2
        elif cmd_name == 'Set_Creep_Parameters':
            cmd_num = 4
            bytes_per_arg = 1
        elif cmd_name == 'Set_Cruise_and_CW_Creep_Amounts':
            cmd_num = 5
            bytes_per_arg = self.steps_arg_n_bytes
        elif cmd_name == 'Set_CCW_Creep_and_CW_Creep_Amounts':
            cmd_num = 6
            bytes_per_arg = self.steps_arg_n_bytes
        elif cmd_name == 'Execute_Move':
            cmd_num = 7
            bytes_per_arg = 1
            pause_after_send = 0
        else:
            warnings.warn('Bad command "{}"'.format(cmd_name))
            cmd_num = 0

        # get identifier
        if not(type(args) is str):
            args = numpy.matrix(args)
            args = numpy.array(args)  # use to have an array of 1*5 shape. If you just want a list 1*5 use a tolist
        hexid = LegacyPositionerComm._get_CAN_identifier(bus_id, cmd_num)

        # argument byte construction
        hexbytes = []
        unspaced_bytes_str = ''
        if LegacyPositionerComm.isnumeric(args) and (1 in args.shape):

            for i in range(0, args.size):
                n_hex_digits = 2 * bytes_per_arg
                next_byte = '{0:{width}{base}}'.format(int(args[0][i]), base='X', width=n_hex_digits)
                if len(next_byte) > n_hex_digits:
                    max_val = 16 ** n_hex_digits - 1
                    warnings.warn(
                        'arg({}) value {} is greater than range. {} will be sent instead'.format(i, args[i], max_val))
                unspaced_bytes_str += next_byte
            unspaced_bytes_str.replace(' ', '0')  # replace whitespace by 0
        elif type(args) is str:
            unspaced_bytes_str = args
        elif LegacyPositionerComm.ischar(args) and args.shape[1] == 2:
            hexbytes = args
        elif args:
            warnings.warn('Bad arguments to send_cmd')
        if unspaced_bytes_str:
            i = 1
            while i <= len(unspaced_bytes_str) / 2:
                I = 2 * (i - 1)
                hexbytes.append(unspaced_bytes_str[I] + unspaced_bytes_str[I + 1])
                hexbytes[i-1] = hexbytes[i-1].replace(' ','0')
                i += 1

        # send ths CAN message
        self.CAN_comm.send_CAN_frame(hexid, hexbytes)
        time.sleep(pause_after_send)

    def set_currents(self, bus_id, curr_spin_up_down, curr_cruise, curr_creep):
        args = [[], [], [], [], [], [], [], []]
        a = 0
        args[a] = curr_spin_up_down  # motor 0
        a += 1
        args[a] = curr_cruise  # motor 0
        a += 1
        args[a] = curr_creep # motor 0 cw
        a += 1
        args[a] = curr_creep  # motor 0 ccw
        a += 1
        args[a] = curr_spin_up_down  # motor 1
        a += 1
        args[a] = curr_cruise  # motor 1
        a += 1
        args[a] = curr_creep  # motor 1 cw
        a += 1
        args[a] = curr_creep  # motor 1 ccw

        self.send_cmd(bus_id, 'Set_Currents', args)

    def set_creep_periods(self, bus_id, period_creep):
        args = [[], [], [], []]
        a = 0
        args[a] = period_creep  # motor 0 cw
        a += 1
        args[a] = period_creep  # motor 0 ccw
        a += 1
        args[a] = period_creep  # motor 1 cw
        a += 1
        args[a] = period_creep  # motor 1 ccw

        self.send_cmd(bus_id, 'Set_Creep_Periods', args)

    def set_creep_parameters(self, bus_id, curr_hold_after_creep, should_bump_creep_current):
        args = [[], [], [], [], []]
        a = 0
        args[a] = curr_hold_after_creep  # motor 0 cw
        a += 1
        args[a] = curr_hold_after_creep  # motor 0 ccw
        a += 1
        args[a] = curr_hold_after_creep  # motor 1 cw
        a += 1
        args[a] = curr_hold_after_creep  # motor 1 ccw

        # activation/desactivation of bumping to high final current during last phrase of creep
        bits = 0
        bits += should_bump_creep_current**2  # motor 0 cw
        bits += should_bump_creep_current**3  # motor 0 ccw
        bits += should_bump_creep_current**6  # motor 1 cw
        bits += should_bump_creep_current**7  # motor 1 ccw
        a += 1
        args[a] = bits

        self.send_cmd(bus_id, 'Set_Creep_Parameters', args)


    @staticmethod
    def _get_CAN_identifier(bus_id, cmd_num):
        # bits 16-4 are the positioner id number
        # bits 3-0 are the command number
        n_bits = 29
        n_cmd_bits = 4
        n_id_bits = n_bits - n_cmd_bits
        identifier = '{0:{width}{base}}'.format(bus_id, base='b', width=n_id_bits)
        identifier=identifier.replace(' ','0')  # replace whitespace by 0
        identifier = identifier + '{0:{width}{base}}'.format(cmd_num, base='b', width=n_cmd_bits)
        identifier=identifier.replace(' ','0')  # replace whitespace by 0
        hexid = '{0:{width}{base}}'.format(int(identifier, base=2), base='X', width=8)  # base = X for uppercase Hexadecimal numbers
        hexid = hexid.replace(' ', '0')  # replace whitespace by 0
        return hexid

    @staticmethod
    def isnumeric(t):
        """
        look if there is number inside t
        :param :str
        :return: bool
        """
        a = 0
        i = 0
        if type(t) is str:
            return False
        while a == 0 and i < len(t):
            if not str.isalnum(str(t[0][i]).replace('.','0')) or str.isalpha(str(t[0][i])):
                a = 1
            i += 1
        if a == 0:
            return True
        else:
            return False

    @staticmethod
    def ischar(t):
        """
        look if there is only char inside t
        :param t: str
        :return:bool
        """
        a = 0
        i = 0
        while a == 0 and i < len(t):
            if not str.isalpha(str(t[i])):
                a = 1
            i += 1
        if a == 0:
            return True
        else:
            return False

    @staticmethod
    def zeros2d(m,n):
        """Returns an [m][n] dimensioned list of zeros."""
        return [[0 for x in range(n)] for y in range(m)]

class LawicellCANUSB(object):
    """ Class : LawicellCANUSB
    # -----------------------
    # Takes care of the sending CAN commands over USB
    #
    # The CANUSB cable is treated as essentially an RS232 port. Simple to
    # implement, though purportedly not as fast as DLL interface the vendor
    # alternatively provides.
    #
    # This class is based on a brief interface manual ( describing ASCII
    # format of CAN commands ) posted by the cale vendor. See www.canusb.com
    """
    read_timeout = 0.15  # sec
    read_poll_period = 0.001  # sec
    CAN_speed = 'S6'  # currently motor driver board requires 'S6'; Lawicell allows 'S0' thru 'S8' = [ 10,20,50,100,125,250,500,800,1000] Kbit

    # methods
    def __init__(self, com_port):
        """com_port argument is a string, such as 'COM5'
        """
        self.print_all_can_msgs = False
        self.com_port = com_port
        print('Initializing serial port at', self.com_port, '\n')
        self.port = serial.Serial(self.com_port)
        self.port.baudrate = 112500
        self.port.bytesize = serial.EIGHTBITS
        self.port.parity = serial.PARITY_NONE
        self.port.stopbits = serial.STOPBITS_ONE
        if self.version_ok:
            self.initCANUSB()
            self.read()  # clear out any bytes in the serial port buffer
        else:
            warnings.warn('Bad response when doing version check.')


    def send_CAN_frame(self, hexid, hexbytes):
        """
        # function 'send_CAN_frame' is the principle one o interact with
        :param hexid: 8 hex digit identifier ( 00000000-1FFFFFFF)
        :param hexbytes:  N*2 column vector of hex bytes to send
        :return: response from the can usb
        """
        hexid_length = None
        msg = 'T'  # use 29 bit frame
        if msg == 't':
            hexid_length = 3
        if msg == 'T':
            hexid_length = 8
        if hexid.isalnum() and len(hexid) == hexid_length:
            msg = msg + hexid                                      # msg = T00000000-1FFFFFFFF
        else:
            warnings.warn('Bad hexid {}'.format(hexid))
        datalength = len(hexbytes)
        max_bytes = 8
        if datalength > max_bytes:
            warnings.warn('Too many bytes {} truncating message to {}'.format(datalength, max_bytes))
            hexbytes = hexbytes[0:max_bytes]
            datalength = max_bytes
        msg += str(datalength)
        if not hexbytes:
                pass     # do nothing
        elif len(hexbytes[0]) == 2:
            for i in range(0, datalength):
                msg = msg + hexbytes[i]
        else:
            warnings.warn('Badly sized hexbytes array ')
        self.initCANUSB()
        if self.print_all_can_msgs:
            print('Sending CAN frame :', msg)
        response = self.writeread(msg)
        self.closeCANUSB()
        return response

    def read_status_flags(self):
        # 1. CAN receive FIFO queue full
        # 2. CAN transmit FIFO queue full
        # 3. Error warning (EI)
        # 4. Data overrun (DOI)
        # 5. not used
        # 6. Error passive (EPI)
        # 7. Arbitration lost (ALI)
        # 8. Bus error (BEI)
        self.initCANUSB()
        response = self.writeread('F')
        self.closeCANUSB()
        bool1 = []

        if str(response[0]) == 'F':
            d = [int(response[0], 16), int(response[1], 16)]
            b = ['{0:b}'.format(d[0]), '{0:b}'.format(d[1])]
            for i in range(1, len(b)):
                if b[i] == 1:
                    bool1[i] = 1
        return bool

    def writeread(self, str1):
        self.write(str1)
        ticstart = time.clock()
        while (time.clock() - ticstart) <= self.read_timeout: # TODO : try to figure out how to know that the positionner has already done the mvt
            time.sleep(self.read_poll_period)
        response = self.read()
        return response

    def write(self, str1):
        if not self.port.isOpen():
            self.port = serial.Serial(self.com_port)
        self.port.write(bytes(str1,'utf-8'))

    def read(self):
        if not (self.port.isOpen()):
            self.port = serial.Serial(self.com_port)
        nbytes = self.port.inWaiting()
        response = ''
        if nbytes > 0:
            response = self.port.read(nbytes)
            if len(response) > 1:
                response = response[0]
        if response:
            if ord(response) == 13:  # ascii carriage return
                response = ' '
            if ord(response) == 7:  # ascii bell
                response = ' '
                print('CANUSB returned error 7 \n')
        return response

    def version_ok(self):
        response = self.writeread('V')
        bool1 = False
        if len(response) == 5 and response[0] == 'V':
            bool1 = True
            print('CANUSB : HW version = ', response[1], response[2], ', SW version = ', response[3], response[4])
        else:
            warnings.warn('CANUSB response \n ')
        return bool1

    def initCANUSB(self):
        self.closeCANUSB()              # close CAN port (if it was open already
        self.writeread('2-3')           # clear buffer in CANUSB
        self.writeread(self.CAN_speed)  # set CAN speed
        self.writeread('O')             # open the can port

    def closeCANUSB(self):
        self.writeread('C')  # close CAN port

    def delete(self):
        self.closeCANUSB()
        if self.port.isOpen():
            self.port.close()
        del self.port
