'''
P.E.C.S. - Petal Engineer Control System
Kevin Fanning fanning.59@osu.edu

Simple wrapper of PETAL and FVC proxies to make mock daytools that call
commands in PetalApp in a similar manner to an OCS sequence.

FVC/Spotmatch/Platemaker handling are hidden behind the FVC proxy measure
function. See FVChandler.py for use.

Requires a running DOS Instance with one PetalApp
(multiple petals are not supported at the moment)
along with FVC, Spotmatch and Platemaker.

Adding multi-petal support (Duan 05/24)

'''

from DOSlib.proxies import FVC, PETAL


class PECS():

    '''input:
        petal_ids:  list of petal_ids, each petal_id is a string
    '''

    def __init__(self, ptlids=None, platemaker_instrument=None,
                 fvc_role=None, printfunc=print):
        if not(ptlids) and not(platemaker_instrument) and not(fvc_role):
            import configobj
            pecs_local = configobj.ConfigObj(
                    'pecs_local.conf', unrepr=True, encoding='utf-8')
            platemaker_instrument = pecs_local['pm_instrument']
            ptlids = [pecs_local['ptl_id']]
            fvc_role = pecs_local['fvc_role']
        self.platemaker_instrument = platemaker_instrument
        self.fvc_role = fvc_role
        self.ptlids = ptlids
        # create FVC to access functions in FVC proxy
        self.fvc = FVC(self.platemaker_instrument, fvc_role=self.fvc_role)
        self.printfunc(
            'proxy FVC created for instrument %s' % self.fvc.get('instrument'))
        self.ptls = {ptlid: PETAL(ptlid) for ptlid in ptlids}
        self.printfunc(f'proxy petals created for {ptlids}')

    def call_petal(self, ptlid, command, *args, **kwargs):
        '''
        Call petal, command is a command listed in PetalApp.commands.
        Required args/kwargs can be passed along.
        '''
        return self.ptls[ptlid]._send_command(command, *args, **kwargs)
