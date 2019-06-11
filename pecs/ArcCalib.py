'''
Runs an Arc Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
from pecs import PECS

class Arc(PECS)
	
	def __init__(petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
		PECS.__init__(petal_id=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
		self.Eo_phi = 104.0
		self.clear_angle_margin = 3.0
		self.ptlid = petal_id

	def arc_calibration(selection=[],n_points_P=6, n_points_T=6,auto_update=True):
		if not selection:
			posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:'DEVICE_ID'])
		elif posids[0][0] == 'c': #User passed busids
			posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
		else: #assume is a list of posids
			posid_list = selection
		requests_list_T, requests_list_P = self.ptls[self.ptlid].get_arc_requests(ids=posid_list)
		T_data = []
		for request in requests_list_T:
			self.ptls[self.ptlid].prepare_move(request)
			expected_positions = self.ptls[self.ptlid].execute_move()
			measured_positions = pandas.DataFrame.from_dict(measured_positions)
			measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
			request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'})
			measured_positions.merge(request, how='outer',on='DEVICE_ID')
			T_data.append(measured_positions)
		P_data = []
		for request in requests_list_P:
			self.ptls[self.ptlid].prepare_move(request)
			expected_positions = self.ptls[self.ptlid].execute_move()
			measured_positions = pandas.DataFrame.from_dict(measured_positions)
			measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
			request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'})
			measured_positions.merge(request, how='outer',on='DEVICE_ID')
			P_data.append(measured_positions)
		data = self.ptls[self.ptlid].calibrate_from_arc_data(T_data,P_data,auto_update=auto_update)
		return data

if __name__ == '__main__':
	arc = Arc()
	user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal' + self.petal_id +' : ')
	user_text = user_text.split()
	selection = []
	for item in user_text:
		selction.append(item)
	data = arc.arc_calibration(selection=selection)
	print(data)
	
