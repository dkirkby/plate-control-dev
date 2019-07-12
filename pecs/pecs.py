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

Added basic FVC simulator (Kevin 2019/05/30)

Added illuminator proxy for xy test control over LED (Duan 2019/06/07)

'''

from DOSlib.proxies import FVC, Petal  # , Illuminator
from fvc_sim import FVC_proxy_sim
import os


class PECS:

    '''input:
        ptlids:                list of petal ids, each petal id is a string
        printfuncs:            dict of print functions, or a single print func
                               (each petal may have its own print function or
                                logger instance for log level filtering and
                                log file separation purposes)
        platemaker_instrument: name of the platemaker instrument file
                               (for single usually something like petal5)
        fvc_role:              The DOS role name of the the FVC application
                               usually FVC or FVC1 or FVC2
    '''

    def __init__(self, ptlids=None, printfunc=print,
                 platemaker_instrument=None, fvc_role=None,
                 illuminator_role=None):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        if not(platemaker_instrument) or not(fvc_role) or not(ptlids):
            from configobj import ConfigObj
            pecs_local = ConfigObj(
                os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             'pecs_local.conf'),
                unrepr=True, encoding='utf-8')
            platemaker_instrument = pecs_local['pm_instrument']
            fvc_role = pecs_local['fvc_role']
            ptlids = pecs_local['ptlids']
        self.ptlids = ptlids
        if type(printfunc) is not dict:  # if a single printfunc is supplied
            printfuncs = {ptlid: printfunc for ptlid in ptlids}
        else:
            printfuncs = printfunc
        # if input printfunc is already a dict, need to check consistency still
        assert set(ptlids) == set(printfuncs.keys()), 'Input ptlids mismatch'
        self.ptlids = ptlids
        self.printfuncs = printfuncs
        self.platemaker_instrument = platemaker_instrument
        self.fvc_role = fvc_role
        self.illuminator_role = illuminator_role
        # call fvc proxy
        if 'SIM' in self.fvc_role.upper():
            self.fvc = FVC_proxy_sim()
        else:
            self.fvc = FVC(self.platemaker_instrument, fvc_role=self.fvc_role)
        self.printfunc('FVC proxy created for instrument: '
                       f"{self.fvc.get('instrument')}")
        self.ptls = {}  # call petal proxy
        for ptlid in ptlids:
            self.ptls[ptlid] = Petal(petal_id=ptlid)  # no sim state control
            self.printfuncs[ptlid](
                f'Petal proxy initialised for {ptlid}, '
                f'simulator mode: {self.ptls[ptlid].simulator_on}')
        # this crashes don't uncomment this KF 06/18/19
        # self.illuminator = Illuminator()

    def printfunc(self, msg):
        '''self.printfuncs is a dict indexed by ptlids as specified for input,
        this function prints to all of them for messages shared across petals
        '''
        for pf in self.printfuncs.values():
            pf(msg)

    # We don't need this since any PetalApp methods can be directly called
    # Was a more PML like call to petal, but yes, not needed.
    # def call_petal(self, ptlid, command, *args, **kwargs):
    #     '''
    #     Call petal app, command is a command listed in PetalApp.commands.
    #     Required args/kwargs can be passed along.
    #     '''
    #     return self.ptls[ptlid](command, *args, **kwargs)
