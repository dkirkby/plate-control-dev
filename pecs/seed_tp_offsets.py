'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS

class TP_Offsets(PECS):

    def __init__(self,ptlids=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self,ptlids=ptlids, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.Eo_phi = 104.0
        self.clear_angle_margin = 3.0
        self.ptlid = list(self.ptls.keys())[0]

    def seed_vals(self, selection=None,enabled_only=False,auto_update=False):
        if not(selection):
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        for posid in posid_list:
            self.ptls[self.ptlid].set_posfid_val(posid,'OFFSET_T',0.0)
            self.ptls[self.ptlid].set_posfid_val(posid,'OFFSET_P',0.0)
        #updates = self.ptls[self.ptlid].initialize_self.ptls[self.ptlid].set_posfid_val(posid,'OFFSET_T',0.0)offsets_xy(ids=posid_list, auto_update=auto_update)
        return 'hi'

if __name__ == '__main__':
    off = TP_Offsets()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, or type all: ')
    selection = []
    if 'all' not in user_text.lower():
        user_text = user_text.split()
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    print('DONE!')
