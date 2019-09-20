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
        ptlids:                list of petal ids, each petal id is an integer
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
                 illuminator_role=None, constants_version=None):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        if None in [platemaker_instrument, fvc_role, ptlids,
                    constants_version]:
            from configobj import ConfigObj
            pecs_local = ConfigObj(
                os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             'pecs_local.cfg'),
                unrepr=True, encoding='utf-8')
            platemaker_instrument = pecs_local['pm_instrument']
            fvc_role = pecs_local['fvc_role']
            ptlids = pecs_local['ptlids']
            constants_version = pecs_local['constants_version']
            all_fiducials = (True if 'T' in
                             str(pecs_local['all_fiducials']).upper()
                             else False)
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
        self.constants_version = constants_version
        # call fvc proxy
        if 'SIM' in self.fvc_role.upper():
            self.fvc = FVC_proxy_sim()
        else:
            self.fvc = FVC(self.platemaker_instrument, fvc_role=self.fvc_role,
                           constants_version=self.constants_version,
                           all_fiducials=all_fiducials)
        self.printfunc(
            "FVC proxy created for instrument: {self.fvc.get('instrument')}")
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

    def _parse_yn(self, yn_str):
        if 'y' in yn_str.lower():
            return True
        elif 'n':
            return False
        else:
            self.printfunc(f'Invalid input: {yn_str}. Must be y/n.')

    def ptl_setup(self, petal_id=None, posids=None):

        if petal_id is None:
            ptlid = self.ptlids[0]
            self.printfunc(f'Defaulting to ptlid = {ptlid}')
        self.ptlid = ptlid
        self.ptl = self.ptls[self.ptlid]
        if posids is None:
            posids = sorted(list(self.ptl.get_positioners(
                enabled_only=True)['DEVICE_ID']))
            self.printfunc(
                f'Defaulting to all {len(posids)} enabled positioners')
        self.posids = posids

    def interactive_ptl_setup(self):
        self.printfunc(f'Running interactive setup for PECS')
        ptlid = self._interactively_get_ptl()  # set selected ptlid
        posids = self._interactively_get_posids(ptlid)  # set selected posids
        self.ptl_setup(petal_id=ptlid, posids=posids)

    def _interactively_get_ptl(self):
        ptlid = input(f'Availible petal IDs: {list(self.ptls.keys())}\n'
                      f'Please enter a petal ID (integer only): ')
        if ptlid.isdigit():
            self.printfunc(f'Selecting ptlid = {ptlid}')
            return int(ptlid)
        else:
            self.printfunc('Invalid input, must be an integer, retry')
            self._get_ptlid()

    def _interactively_get_posids(self, ptlid):
        user_text = input('Please list CAN bus IDs or posids, seperated by '
                          'SPACES. \nLeave blank to use all positioners: ')
        if user_text == '':
            selection = None
        else:
            selection = user_text.split()
        user_text = input('Use enabled positioners only? (y/n): ')
        enabled_only = self._parse_yn(user_text)
        if selection is None:
            posids = sorted(list(self.ptls[ptlid].get_positioners(
                enabled_only=enabled_only)['DEVICE_ID']))
        elif 'can' in selection[0]:  # User passed a list of canids
            posids = sorted(list(self.ptls[ptlid].get_positioners(
                enabled_only=enabled_only, busids=selection)['DEVICE_ID']))
        else:  # assume is a list of posids
            posids = sorted(selection)
        self.printfunc(f'Selecting {len(posids)} positioners')
        return posids
