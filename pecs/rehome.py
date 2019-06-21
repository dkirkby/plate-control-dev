'''
Runs a one_point_calibration through petal and fvc proxies. Needs running DOS instance. See pecs.py
'''
from pecs import PECS
import pandas
from DOSlib.positioner_index import PositionerIndex
import posconstants as pc

class Rehome(PECS):

    def __init__(self, petal_id=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self, ptlids=petal_id, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.ptlid = list(self.ptls.keys())[0]

    def rehome(self, selection=None,enabled_only=True,axis='both'):
        if not selection:
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(self.ptls[self.ptlid].get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        self.ptls[self.ptlid].rehome_pos(posid_list, axis=axis)

if __name__ == '__main__':
    rh = rehome_pos()
    warning = input('WARNING: this script will drive positioners to their hardstops. Be sure you know what you are doing! (enter to continue)')
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, leave it blank to use all on petal: ')
    if user_text != '':
        user_text = user_text.split()
        selection = []
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    user_text = input('Please provide axis (both, theta_only, phi_only): ')
    if not(user_text in ['both','theta_only','phi_only']):
        print('Invalid input!')
    else:
        rh.rehome(selection=selection, axis=user_text)
    print('Done!')
