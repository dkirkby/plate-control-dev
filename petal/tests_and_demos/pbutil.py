''' This is a test utility for exercising the full functionality of the petal box'''
import os
import sys
sys.path.append(os.path.abspath('/home/msdos/focalplane/plate_control/trunk/petal'))
import petalcomm
import time

can_frame_fmt = "=IB3x8s"
can_bus_list = ['can10', 'can12', 'can11', 'can13', 'can14', 'can15', 'can16','can17', 'can22', 'can23']

class _read_key:
	def __init__(self):
		import tty, sys

	def __call__(self):
		import sys, tty, termios
		fd = sys.stdin.fileno()
		old_settings = termios.tcgetattr(fd)
		try:
			tty.setraw(sys.stdin.fileno())
			ch = sys.stdin.read(1)
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
		return ch

def set_duty_fan(fan='GFA_FAN1', duty=0):
	'''Switch duty cycle of GFA inlet and outlet fans
		fan = fan name, either 'GFA_FAN1' or 'GFA_FAN2' (string)
		state = 0 if on, 1 if on (integer)'''
	pc.fan_pwm_ptl(fan, duty)

def switch_outputs(output = 'GFA_FAN1', state = 0):
	'''Switch state of any output
		output = output name, either 'GFA_FAN1' or 'GFA_FAN2' (string)
		state = 0 if on, 1 if on (integer)'''
	pc.switch_en_ptl(output, state)


if __name__ == '__main__':

	nargs=len(sys.argv)
	if nargs>1:
		pcnum = sys.argv[1]
	else:
		pcnum = input('Enter the petalcontroller number (eg. 11): ')
	pc = petalcomm.PetalComm(pcnum)

	_sel=_read_key()
	loop=True

	print("")
	print(" |||| Welcome to the petalbox test utility |||| ")
	print("")

	while loop:
		print("\n")
		print("[t]emperature sensor readout")
		print("[f]an test")
		print("[o]utput test")
		print("[i]nput test")
		print("[c]an channel test (must have radial board with fipos on each channel)")
		print("[a]dc test")
		print("[s]erial port test")
		print("\n[e]xit\n")
		print("Select: \n")
		
		sel=_sel.__call__()		

		sel=sel.lower()
		if sel=='e':
			print ("Bye...")
			sys.exit()

		if sel=='t':	#list all found 1-Wire temperature sensors (by serial number) and their readings
			print("\n\n**Reading Temperature Sensor(s)**\n")
			temperatures = pc.read_temp_ptl()
			print('TEMPERATURE READINGS BY SENSOR SERIAL NUMBER: {}'.format(temperatures))

		if sel=='f':   #run fan through a sequence of duty cycles and print out tachometer readings
			print("\n\n**Running Fan Sequence**\n")
			print("**The inlet and outlet parts of the fan will now cycle through 3 different speed settings and turn off.")
			switch_outputs('GFA_FAN1', 1)
			switch_outputs('GFA_FAN2', 1)
			for duty in [0, 10, 20]:
				set_duty_fan('GFA_FAN1', duty)
				time.sleep(1)
				set_duty_fan('GFA_FAN2', duty)
				time.sleep(2)
				fan_readings = pc.read_fan_tach()
				print('\nTACHOMETER READINGS FOR {} % DUTY ARE: {}'.format(duty, fan_readings)) 
			switch_outputs('GFA_FAN1', 0)
			switch_outputs('GFA_FAN2', 0)

		if sel=='o':	#switch all outputs off, allow user to measure or observe, then switch them all on
			print("\n\n**Beginning Test on Petalbox Outputs**\n")
			print("**Switching all outputs to OFF state")
			outputs = ['SYNC', 'GFAPWR_EN', 'BUFF_EN1', 'BUFF_EN2', 'TEC_CTRL']
			for output in outputs:
				switch_outputs(output, 0)
			switch_outputs('PS1_EN', 1)
			switch_outputs('PS2_EN', 1)
			input("Press Enter when ready to switch all outputs ON...")
			print("**Switching all outputs to ON state")
			for output in outputs:
				switch_outputs(output, 1)
			switch_outputs('PS1_EN', 0)
			switch_outputs('PS2_EN', 0)

		if sel=='i':    #allow the user to switch the inputs and read back their states
			print("\n\n**Beginning Test on Petalbox Inputs**\n")
			input("Switch all inputs off and press Enter...")
			pospwr_state = pc.read_HRPG600() 
			gfa_ovrtmp_state = pc.read_gfa_ovrtmp()
			print('Positioner Power State: {}   GFA Over Temp State: {}'.format(pospwr_state, gfa_ovrtmp_state))
			input("\n\nSwitch all inputs on and press Enter...")
			pospwr_state = pc.read_HRPG600() 
			gfa_ovrtmp_state = pc.read_gfa_ovrtmp()
			print('Positioner Power State: {}   GFA Over Temp State: {}'.format(pospwr_state, gfa_ovrtmp_state))

		if sel=='c':    #request id info from all radial board CAN channels, assumes radial board is hooked up with a fipos device on each channel
			print("\n\n**Beginning CAN Channel Readout**\n")
			for can_bus in can_bus_list:
				print('CHANNEL: {}\nCAN IDs: '.format(can_bus))
				try:
					print(str([key for key in pc.get_posfid_info(can_bus)]).strip("'[]'")) 
					print('____________________________________________________________')
				except:	
					print("\nNo devices found or CAN channel is not up\n")

		if sel=='a':    #allow the user to switch the inputs and read back their states
			print("\n\n**Reading ADC**\n")
			adc_readings = [pc.read_adc(i) for i in range(5)]
			print('ADC0, ADC1, ADC2, ADC3, ADC4: ', adc_readings)
			
		if sel=='s':    #sends message to serial port and reads it back 100x
			for count in range(100):
				pc.send_gfa_serial('Test Message')
				print(pc.recv_gfa_serial() == 'Test Message\n'.encode('utf-8'))
							
