'''
Runs a Grid Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc
import pandas

class Grid(PECS)
	
	def __init__(self,petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
		PECS.__init__(self,ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
		self.ptlid = list(self.ptls.keys())[0]
		return

	def grid_calibration(selection=[],n_points_P=9, n_points_T=4,auto_update=True):
		if not selection:
			posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:'DEVICE_ID'])
		elif posids[0][0] == 'c': #User passed busids
			posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
		else: #assume is a list of posids
			posid_list = selection
		requests_list = self.ptls[self.ptlid].get_grid_requests(ids=posid_list)
		meas_data = []
		i = 1
		for request in requests_list:
			print('Measuring grid point '+str(i)+' of '+str(len(requests_list_T)))
            i += 1 
			self.ptls[self.ptlid].prepare_move(request)
			expected_positions = self.ptls[self.ptlid].execute_move()
			measured_positions = pandas.DataFrame.from_dict(measured_positions)
			measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
			request.rename(columns={'TARGET_X1':'TARGET_T','TARGET_X2':'TARGET_P'}, inplace=True)
			merged_data = measured_positions.merge(request, how='outer',on='DEVICE_ID')
			meas_data.append(merged_data)
		updates = self.ptls[self.ptlid].calibrate_from_grid_data(meas_data,auto_update=auto_update)
		return updates

if __name__ == '__main__':
	grid = Grid()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    if user_text == '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
	updates = grid.grid_calibration(selection=selection)
	print(updates)
	updates.to_csv('grid_calibration_'+pc.filename_timestamp_str_now()+'.csv')
	
