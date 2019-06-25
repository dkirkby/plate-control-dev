'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS
import pandas
from DOSlib.positioner_index import PositionerIndex
import posconstants as pc

class OnePoint(PECS):

    def __init__(self, petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self, ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]
        self.index = PositionerIndex()

    def one_point_calib(self, selection=None,enabled_only=True,mode='posTP',auto_update=True,tp_target='default', match_radius=80):
        if tp_target == 'default':
            tp_target = [0,self.Eo_phi+self.clear_angle_margin]
        if not selection:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        if tp_target:
            requests = {'DEVICE_ID':[],'TARGET_X1':[],'TARGET_X2':[],'LOG_NOTE':[],'COMMAND':[]}
            for posid in posid_list:
                requests['DEVICE_ID'].append(posid)
                requests['X1'].append(tp_target[0])
                requests['X2'].append(tp_target[1])
                requests['LOG_NOTE'].append('One point calibration ' + mode)
                requests['COMMAND'].append('posTP')
            self.ptls[self.ptlid].prepare_move(pandas.DataFrame.from_dict(requests))
            expected_positions = self.ptls[self.ptlid].execute_move()
        else:
            expected_positions = self.ptls[self.ptlid].get_positions()
        expected_positions.to_csv('test.csv')
        old_radius = self.fvc.get('match_radius')
        self.fvc.set(match_radius=match_radius)
        measured_positions = self.fvc.measure(expected_positions) #may need formatting of measured positons
        self.fvc.set(match_radius=old_radius)
        measured_positions = pandas.DataFrame(measured_positions)
        measured_positions.rename(columns={'q':'Q','s':'S','flags':'FLAGS', 'id':'DEVICE_ID'},inplace=True)
        used_positions = measured_positions[measured_positions['DEVICE_ID'].isin(posid_list)]
        updates = self.ptls[self.ptlid].test_and_update_TP(used_positions, tp_updates_tol=0.0, tp_updates_fraction=1.0, tp_updates=mode, auto_update=auto_update)
        updates['auto_update'] = auto_update
        updates['tp_target'] = [tp_target for i in range(len(updates))]
        updates['enabled_only'] = enabled_only
        return updates

if __name__ == '__main__':
    op = OnePoint()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    if user_text != '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    user_text = input('Please provide calibration mode (offsetTP or posTP), leave blank for posTP: ')
    if not user_text:
        mode = 'posTP'
    else:
        mode = user_text
    updates = op.one_point_calib(selection=selection, mode=mode, tp_target=[0,170])
    print(updates)
    updates.to_csv(pc.dirs['ALL_LOGS']+'/calib_logs/one_point_'+pc.filename_timestamp_str_now()+'.csv')
    
