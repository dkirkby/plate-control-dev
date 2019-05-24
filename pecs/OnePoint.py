'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS

class OnePoint(PECS):

	def __init__(petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
		PECS.__init__(petal_id=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
		self.Eo_phi = 104.0
		self.clear_angle_margin = 3.0

	def one_point_calib(self, selection=[],mode='posTP',auto_update=True,tp_target=[0,self.Eo_phi+self.clear_angle_margin]):
		if not selection:
			posid_list = self.call_petal('get_positioner_list', enabled_only=enabled_only)
		elif posids[0][0] == 'c': #User passed busids
			posid_list = self.call_petal('get_positioner_list', enabled_only=enabled_only, busids=selection)
		else: #assume is a list of posids
			posid_list = selection
		if tp_target:
		requests = {} #May need different request structure in the future
			for posid in posid_list:
				requests[posid] = {'command':'ObsTP', 'target':tp_target, 'log_note':'One point calibration ' + mode}
			self.call_petal('prepare_move', requests)
			expected_positions = self.call_petal('execute_move')
		else:
			expected_positions = self.call_petal('get_positions')
		measured_positions = self.fvc.measure(expected_positions) #may need formatting of measured positons
		dtdp, updates = self.call_petal('test_and_update_TP', measured_positions, tp_updates_tol=0.0, tp_updates_fraction=1.0, tp_updates=mode, auto_update=auto_update)
		return dtdp, updates

if __name__ == '__main__':
	op = OnePoint()
	user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal' + self.petal_id +' : ')
	user_text = user_text.split()
	selection = []
	for item in user_text:
		selction.append(item)
	user_text = input('Please provide calibration mode (offsetTP or posTP), leave blank for posTP: ')
	if not user_text:
		mode = 'posTP'
	else:
		mode = user_text
	dtdp, updates = op.one_point_calib(selection=selection, mode=mode)
	print(updates)
	