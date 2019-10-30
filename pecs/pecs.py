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
import os
import pandas as pd
from configobj import ConfigObj
from fvc_sim import FVC_proxy_sim


class PECS:
    '''if there is already a PECS instance from which you want to re-use
       the proxies, simply pass in pecs.fvc and pecs.ptls
    '''
    def __init__(self, fvc=None, ptls=None, printfunc=print):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        pecs_local = ConfigObj(  # set basic self attributes
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'pecs_local.cfg'),
            unrepr=True, encoding='utf-8')
        for attr in pecs_local.keys():
            setattr(self, attr, pecs_local[attr])
        # self.ptlids = pecs_local['ptlids']
        # self.all_fiducials = pecs_local['all_fiducials']
        # self.constants_version = pecs_local['constants_version']
        # self.pm_instrument = pecs_local['pm_instrument']
        # self.fvc_role = pecs_local['fvc_role']
        # self.illuminator_role = pecs_local['illuminator_role']
        if type(printfunc) is dict:  # a dict for all petals
            # if input printfunc is already a dict, check consistency
            assert set(self.ptlids) == set(printfunc.keys()), (
                'Input ptlids mismatch')
            self.printfuncs = printfunc
        else:  # if a single printfunc is supplied
            self.printfuncs = {ptlid: printfunc for ptlid in self.ptlids}
        if fvc is None:  # instantiate FVC proxy, sim or real
            if 'SIM' in self.fvc_role.upper():
                self.fvc = FVC_proxy_sim(max_err=0.0001)
            else:
                self.fvc = FVC(self.pm_instrument, fvc_role=self.fvc_role,
                               constants_version=self.constants_version)
            self.printfunc(f"FVC proxy created for instrument: "
                           f"{self.fvc.get('instrument')}")
        else:
            self.fvc = fvc
            self.printfunc(f"Reusing existing FVC proxy: "
                           f"{self.fvc.get('instrument')}")
        if ptls is None:
            self.ptls = {}  # call petal proxy
            for ptlid in self.ptlids:
                self.ptls[ptlid] = Petal(petal_id=ptlid)  # no sim state ctrl
                self.printfuncs[ptlid](
                    f'Petal proxy initialised for {ptlid}, '
                    f'simulator mode: {self.ptls[ptlid].simulator_on}')
        else:
            self.ptls = ptls
            self.printfunc(
                f'Reusing existing petal proxies for petals {self.ptlids}')
        # self.illuminator = Illuminator()  # this crashes KF 06/18/19

    def printfunc(self, msg):
        '''self.printfuncs is a dict indexed by ptlids as specified for input,
        this function prints to all of them for messages shared across petals
        '''
        for pf in self.printfuncs.values():
            pf(msg)

    def _parse_yn(self, yn_str):
        #  Trying to accept varieties like y/n, yes/no
        if 'y' in yn_str.lower():
            return True
        elif 'n' in yn_str.lower():
            return False
        else:
            self.printfunc(f'Invalid input: {yn_str}. Must be y/n.')

    def ptl_setup(self, petal_id=None, posids=None):

        if petal_id is None:
            petal_id = self.ptlids[0]
            self.printfunc(f'Defaulting to ptlid = {petal_id}')
        self.ptlid = petal_id
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
            self.printfunc(f'Selected ptlid = {ptlid}')
            return int(ptlid)
        else:
            self.printfunc('Invalid input, must be an integer, retry')
            return self._interactively_get_ptl()

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
            posids = sorted(list(self.ptls[ptlid].get_positioners(
                enabled_only=enabled_only, posids=selection)['DEVICE_ID']))
        self.printfunc(f'Selected {len(posids)} positioners')
        return posids

    def fvc_measure(self, exppos=None, match_radius=30, matched_only=True):
        '''use the expected positions given, or by default use internallly
        tracked current expected positions for fvc measurement
        returns expected_positions (df), measured_positions (df)
        (bot have DEVICE_ID as index and sorted) and
        matched_posids (set), unmatched_posids (set)'''
        if exppos is None:
            exppos_list = [(self.ptls[ptlid].get_positions(return_coord='QS')
                            .sort_values(by='DEVICE_ID'))
                           for ptlid in self.ptlids]  # includes all posids
            exppos = pd.concat(exppos_list)
        mr_old = self.fvc.get('match_radius')  # hold old match radius
        self.fvc.set(match_radius=match_radius)  # set larger radius for calib
        # measured_QS, note that expected_pos was changed in place
        meapos = (pd.DataFrame(self.fvc.measure(
                      exppos, matched_only=matched_only,
                      all_fiducials=self.all_fiducials))
                  .rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())  # indexed by DEVICE_ID
        self.fvc.set(match_radius=mr_old)  # restore old radius after measure
        meapos.columns = meapos.columns.str.upper()  # clean up header to save
        exppos = (exppos.rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())
        exppos.columns = exppos.columns.str.upper()
        # find the posids that are unmatched, missing from FVC return
        matched = set(exppos.index).intersection(set(meapos.index))
        unmatched = set(exppos.index) - matched
        if len(unmatched) == 0:
            self.printfunc(f'All {len(exppos.index)} positioners matched.')
        else:
            self.printfunc(
                f'Missing {len(unmatched)} of expected backlit fibres'
                f'\n{sorted(unmatched)}')
        return exppos, meapos, matched, unmatched
