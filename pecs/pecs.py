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

Adding multi-petal support; it doesn't cost any more work now,
but will simply our life so much (Duan 2019/05/24)

'''

from DOSlib.proxies import FVC, Petal


class PECS:

    '''input:
        ptlids:         list of petal ids, each petal id is a string
        printfuncs:     dict of print functions, or a single print function
                        (each petal may have its own print function or
                         logger instance for log level filtering and
                         log file separation purposes)
    '''

    def __init__(self, ptlids=None, platemaker_instrument=None, fvc_role=None,
                 printfunc=print, simulate=False):
        if not(ptlids) and not(platemaker_instrument) and not(fvc_role):
            import configobj
            pecs_local = configobj.ConfigObj(
                    'pecs_local.conf', unrepr=True, encoding='utf-8')
            platemaker_instrument = pecs_local['pm_instrument']
            ptlids = [pecs_local['ptl_id']]
            fvc_role = pecs_local['fvc_role']
        self.platemaker_instrument = platemaker_instrument
        self.ptlids = ptlids
        if type(printfunc) is not dict:  # if a single printfunc is supplied
            printfuncs = {ptlid: printfunc for ptlid in ptlids}
        assert len(ptlids) == len(printfuncs.keys()), 'Input lengths mismatch'
        self.printfuncs = printfuncs
        # create FVC to access functions in FVC proxy
        self.fvc = FVC(self.platemaker_instrument, fvc_role=fvc_role)
        self._print(
            'FVC proxy created for instrument %s' % self.fvc.get('instrument'))
        self.ptls = {}
        for ptlid in ptlids:
            self.ptls[ptlid] = Petal(petal_id=ptlid)
            self.printfuncs[ptlid](f'Petal proxy created for {ptlid}')

    def _print(self, msg):
        '''self.printfuncs is a dict indexed by ptlids as specified for input,
        this function prints to all of them for messages shared across petals
        '''
        for pf in self.printfuncs.values():
            pf(msg)

    def call_petal(self, ptlid, command, *args, **kwargs):
        '''
        Call petal, command is a command listed in PetalApp.commands.
        Required args/kwargs can be passed along.
        '''
        return self.ptls[ptlid](command, *args, **kwargs)
