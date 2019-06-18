'''
Runs an Arc Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc

class Arc(PECS):
    
    def __init__(petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(petal_id=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]

    def arc_calibration(selection=None,n_points_P=6, n_points_T=6,auto_update=True):
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
            measured_positions = self.fvc.measure(expected_positions)
            measured_positions = pandas.DataFrame(measured_positions)
            measured_positions.rename(columns={'q':'Q','s':'S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
            used_positions = measured_positions['DEVICE_ID'].isin(posid_list)
            request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'})
            used_positions.merge(request, how='outer',on='DEVICE_ID')
            T_data.append(used_positions)
        P_data = []
        for request in requests_list_P:
            self.ptls[self.ptlid].prepare_move(request)
            measured_positions = self.fvc.measure(expected_positions)
            measured_positions = pandas.DataFrame(measured_positions)
            measured_positions.rename(columns={'q':'Q','s':'S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
            used_positions = measured_positions['DEVICE_ID'].isin(posid_list)
            request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'})
            used_positions.merge(request, how='outer',on='DEVICE_ID')
            P_data.append(used_positions)
        data = self.ptls[self.ptlid].calibrate_from_arc_data(T_data,P_data,auto_update=auto_update)
        return data

if __name__ == '__main__':
    arc = Arc()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal' + self.petal_id +' : ')
    if user_text == '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    data = arc.arc_calibration(selection=selection)
    print(data)
    data.to_csv('arc_calibration_'+pc.filename_timestamp_str_now()+'.csv')
    
