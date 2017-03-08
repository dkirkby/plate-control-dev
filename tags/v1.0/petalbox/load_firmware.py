#load_firmware
#
import bootloadcontrol as blc
HEX_FILE = 'fw31.hex'
CANBUS='can0'
posids=[86,69,44,43,224]
for posid in posids:
	bc=BootLoadControl()
	print('Programming ' + str(pos_id)+' with '+ hex_file_name + '.....')
	bc.program(posid, HEX_FILE)

print('Done!')