'''
Runs an Arc Calibration using fvc and petal proxies. Requires running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc
import pandas

class Arc(PECS):
    
    def __init__(self,petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self,ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]

    def arc_calibration(self,selection=None,enabled_only=True,n_points_P=6, n_points_T=6,auto_update=True, match_radius=80):
        if not selection:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif posids[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        requests_list_T, requests_list_P = self.ptls[self.ptlid].get_arc_requests(ids=posid_list)
        T_data = []
        old_radius = self.fvc.get('match_radius')
        self.fvc.set(match_radius=match_radius)
        i = 1
        for request in requests_list_T:
            print('Measuring theta arc point '+str(i)+' of '+str(len(requests_list_T)))
            i += 1 
            self.ptls[self.ptlid].prepare_move(request)
            expected_positions = self.ptls[self.ptlid].execute_move()
            measured_positions = self.fvc.measure(expected_positions)
            measured_positions = pandas.DataFrame(measured_positions)
            measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
            used_positions = measured_positions[measured_positions['DEVICE_ID'].isin(posid_list)]
            request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'},inplace=True)
            merged = used_positions.merge(request, how='outer',on='DEVICE_ID')
            T_data.append(merged)
        P_data = []
        i = 1
        for request in requests_list_P:
            print('Measuring phi arc point '+str(i)+' of '+str(len(requests_list_P)))
            i += 1
            self.ptls[self.ptlid].prepare_move(request)
            expected_positions = self.ptls[self.ptlid].execute_move()
            measured_positions = self.fvc.measure(expected_positions)
            measured_positions = pandas.DataFrame(measured_positions)
            measured_positions.rename(columns={'q':'MEASURED_Q','s':'MEASURED_S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
            used_positions = measured_positions[measured_positions['DEVICE_ID'].isin(posid_list)]
            request.rename(columns={'X1':'TARGET_T','X2':'TARGET_P'},inplace=True)
            merged = used_positions.merge(request, how='outer',on='DEVICE_ID')
            P_data.append(merged)
        self.fvc.set(match_radius=old_radius)
        data = self.ptls[self.ptlid].calibrate_from_arc_data(T_data,P_data,auto_update=auto_update)
        data['auto_update'] = auto_update
        data['enabled_only'] = enabled_only
        return data

if __name__ == '__main__':
    arc = Arc()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    if user_text == '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    data = arc.arc_calibration(selection=selection)
    print(data)
    data.to_csv(pc.dirs['all_logs']+'/calib_logs/arc_calibration_'+pc.filename_timestamp_str_now()+'.csv')
    
