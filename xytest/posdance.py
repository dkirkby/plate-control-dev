'''
Used to test the full range of motion for both arms of every positioner in a CAN bus.
'''
import sys, os
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
	basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
	sys.path.append(os.path.abspath(basepath+'/petal/'))
else:
	sys.path.append(os.path.abspath('../petal/'))

import petalcomm
import time

class _read_key:
	def __init__(self):
		import tty, sys

	def __call__(self):
		'''
		A function for single character input, copied directly from pf_utility.py
		'''
		import sys, tty, termios
		fd = sys.stdin.fileno()
		old_settings = termios.tcgetattr(fd)
		try:
			tty.setraw(sys.stdin.fileno())
			ch = sys.stdin.read(1)
		finally:
			termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
		return ch

def MoveAllandWait(direction, motor, angle):
	'''
	Moves the specified motor of every positioner a specified direction and specified angle, then waits 5 seconds so that
	without scheduling the low-level pcomm.move can be run repeatedly
	'''
	pcomm.move('can0', 20000, direction, 'cruise', motor, angle)
	time.sleep(4)

def RangeTest(StartPos):
	'''
	Moves every positioner on a single CAN bus through their approximately full range in both theta and phi,
	leaving each positioner in the neutral position.

	petalID    ... Petal controller ID
	StartPos   ... Either 'n' (neutral position) or 'r' (random position), a distinction made to minimize hard stop ramming.
	'''

	if StartPos == 'n':
		MoveAllandWait('CCW', 'theta', 200)
	if StartPos == 'r':
		MoveAllandWait('CCW', 'theta', 400)
		MoveAllandWait('CCW', 'phi', 200)

	MoveAllandWait('CW', 'theta', 400)
	MoveAllandWait('CCW', 'theta', 400)

	MoveAllandWait('CW', 'phi', 200)
	MoveAllandWait('CCW', 'phi', 200)

	MoveAllandWait('CW', 'theta', 195)

if __name__ == '__main__':

	_sel = _read_key()
	loop = True
	ptlID = input("Input Petal ID:")
	pcomm = petalcomm.PetalComm(ptlID)
	while loop:
		print("[n]eutral starting position - full range test")
		print("[r]andom starting position - full range test")
		print("[e]xit")
		print("Select: ")

		choice = _sel.__call__()
		choice = choice.lower()

		if choice == 'e':
			print ("Bye...")
			sys.exit()

		if choice == 'n':
			RangeTest(choice)

		if choice == 'r':
			RangeTest(choice)
