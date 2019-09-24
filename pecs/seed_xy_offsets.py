'''
Seeds offsetsXY using nominal hole locations and the petal location. Needs running DOS instance. See pecs.py
'''
import os
import posconstants as pc
from pecs import PECS

class XY_Offsets(PECS):

    def __init__(self,ptlids=None, platemaker_instrument=None, fvc_role=None, printfunc = print):
        PECS.__init__(self,ptlids=ptlids, platemaker_instrument=platemaker_instrument, fvc_role=fvc_role, printfunc=printfunc)
        self.ptlid = list(self.ptls.keys())[0]

    def seed_vals(self, selection=None,enabled_only=False,auto_update=False):
        ptl = self.ptls[self.ptlid]
        if not(selection):
            posid_list = list(ptl.get_positioners(enabled_only=enabled_only).loc[:,'DEVICE_ID'])
        elif selection[0][0] == 'c': #User passed busids
            posid_list = list(ptl.get_positioners(enabled_only=enabled_only, busids=selection).loc[:,'DEVICE_ID'])
        else: #assume is a list of posids
            posid_list = selection
        updates = ptl.initialize_offsets_xy(ids=posid_list, auto_update=auto_update)
        return updates

if __name__ == '__main__':
    off = XY_Offsets()
    user_text = input('Please list BUSIDs or POSIDs (not both) seperated by spaces, or type all: ')
    selection = []
    if 'all' not in user_text.lower():
        user_text = user_text.split()
        for item in user_text:
            selection.append(item)
    else:
        selection = None
    print(f'Selection is: {selection}')
    updates = off.seed_vals(selection=selection, auto_update=True)
    path = os.path.join(
        pc.dirs['calib_logs'],
        f'{pc.filename_timestamp_str_now()}-seed_xy_offsets.csv')
    updates.to_csv(path)
    print(updates[['DEVICE_ID', 'DEVICE_LOC', 'OFFSET_X', 'OFFSET_Y',
                   'POS_INT_T', 'POS_INT_P', 'LENGTH_R1', 'LENGTH_R2']])
    print(f'Seed XY offsets data saved to: {path}')
