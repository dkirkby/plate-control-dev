'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS

class XY_Offsets(PECS):

    def __init__(petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(petal_id=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]
        self.index = PositionerIndex()

    def seed_vals(self, selection=[],auto_update=False):
        if not selection:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:'DEVICE_ID'])
        elif posids[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        updates = self.ptls[self.ptlid].initialize_offsets_xy(selection, auto_update=auto_update)
        return updates

if __name__ == '__main__':
    off = XY_Offsets()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal' + self.petal_id +' : ')
    user_text = user_text.split()
    selection = []
    for item in user_text:
        selction.append(item)
    user_text = input('Please provide whether to automatically update Offset XY (y/n): ')
    if 'y' in user_text.lower()
        mode = True
    else:
        mode = False
    updates = off.seed_vals(selection=selection, auto_update=mode)
    print(updates)