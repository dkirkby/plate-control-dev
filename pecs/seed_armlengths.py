'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS
import posconstants as pc

class Armlengths(PECS):

    def __init__(self,ptlids=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self,ptlids=ptlids, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.ptlid = list(self.ptls.keys())[0]

    def seed_vals(self, selection=None,enabled_only=False):
        ptl = self.ptls[self.ptlid]
        if not(selection):
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        for posid in posid_list:
            ptl.set_posfid_val(posid,'LENGTH_R1',pc.nominals['LENGTH_R1']['value'])
            ptl.set_posfid_val(posid,'LENGTH_R2',pc.nominals['LENGTH_R2']['value'])
        ptl.commit()
        ptl.commit_calib_DB()
        return

if __name__ == '__main__':
    arms = Armlengths()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, or type all: ')
    selection = []
    if 'all' not in user_text.lower():
        user_text = user_text.split()
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    updates = arms.seed_vals(selection=selection)
    print('Done!')
