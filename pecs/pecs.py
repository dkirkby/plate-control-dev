'''
P.E.C.S. - Petal Engineer Control System
Kevin Fanning fanning.59@osu.edu

Simple wrapper of PETAL and FVC proxies to make mock daytools that call commands
in PetalApp in a similar manner to an OCS sequence.

FVC/Spotmatch/Platemaker handling are hidden behind the FVC proxy measure function. 
See FVChandler.py for use.

Requires a running DOS Instance with one PetalApp (multiple petals are not supported at the
moment) along with FVC, Spotmatch and Platemaker.
'''
from DOSlib.proxies import FVC, PETAL


class PECS():

	def __init__(petal_id = None, platemaker_instrument = None, fvc_role = None, printfunc = print):
		if not(petal_id) and not(platemaker_instrument) and not(fvc_role):
			import configobj
			pecs_local = configobj.ConfigObj('pecs_local.conf',unrepr=True,encoding='utf-8')
			platemaker_instrument = pecs_local['pm_instrument']
			petal_id = pecs_local['ptl_id']
			fvc_role = pecs_local['fvc_role']
		self.platemaker_instrument = platemaker_instument
		self.fvc_role = fvc_role
		self.petal_name = petal_name
		self.petal_id = str(petal_id)
		self.fvc = FVC(self.platemaker_instrument, fvc_role =self.fvc_role) #Used to access functions in FVC proxy
		self.printfunc('proxy FVC created for instrument %s' % self.fvc.get('instrument'))
		self.ptl = PETAL(petal_id)
		self.printfunc('proxy petal created for petal %s' %self.petal_id)

	def call_petal(command, *args, **kwags):
		'''
		Call petal, command is a command listed in PetalApp.commands.
		Required args/kwargs can be passed along.
		'''
		return self.ptl._send_command(command, *args, **kwargs)