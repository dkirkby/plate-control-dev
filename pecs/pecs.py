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

from DOSlib.proxies import FVC, PetalMan  # , Illuminator
import os
import pandas as pd
from configobj import ConfigObj
from fvc_sim import FVC_proxy_sim


class PECS:
    '''if there is already a PECS instance from which you want to re-use
       the proxies, simply pass in pecs.fvc and pecs.ptls
    '''
    def __init__(self, fvc=None, ptlm=None, printfunc=print):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        self.printfunc = printfunc
        pecs_local = ConfigObj(  # set basic self attributes
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'pecs_local.cfg'),
            unrepr=True, encoding='utf-8')
        for attr in pecs_local.keys():
            setattr(self, attr, pecs_local[attr])
        # self.all_fiducials = pecs_local['all_fiducials']
        # self.constants_version = pecs_local['constants_version']
        # self.pm_instrument = pecs_local['pm_instrument']
        # self.fvc_role = pecs_local['fvc_role']
        # self.illuminator_role = pecs_local['illuminator_role']
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
        if ptlm is None:
            self.ptlm = PetalMan()
            self.printfunc()
        else:
            self.ptlm = ptlm
            self.printfunc(
                f'Reusing existing PetalMan proxy with active petals '
                f'{self.ptlm.participating_petals}')
        # self.illuminator = Illuminator()  # this crashes KF 06/18/19

    def _parse_yn(self, yn_str):
        #  Trying to accept varieties like y/n, yes/no
        if 'y' in yn_str.lower():
            return True
        elif 'n' in yn_str.lower():
            return False
        else:
            self.printfunc(f'Invalid input: {yn_str}. Must be y/n.')

    def ptl_setup(self, petal_roles=None, posids=None, ids=None):

        if petal_roles is None:
            self.printfunc(f'Defaulting to petal roles = {self.ptlm.participating_petals}')
        else:
            for ptl in petal_roles:
                assert ('PETAL' in ptl), 'Petal role names are always PETAL###, invalid role name {ptl}'
            self.ptlm.participating_petals = petal_roles
        if (posids is None) and (ids is None):
            retcode = self.ptlm.get_positioners(enabled_only=True)
            dflist = []
            for p in retcode.values():
                dflist.append(p)
            ids = pd.concat(dflist)
            posids = sorted(list(ids['DEVICE_ID']))
            self.printfunc(
                f'Defaulting to all {len(posids)} enabled positioners')
        elif posids is None:
            posids = sorted(list(ids['DEVICE_ID']))
        elif ids is None:
            retcode = self.ptlm.get_positioners(enabled_only=False, posids=posids)
            dflist = []
            for p in retcode.values():
                dflist.append(p)
            ids = pd.concat(dflist)
        self.posids = posids
        self.ids = ids

    def interactive_ptl_setup(self):
        self.printfunc(f'Running interactive setup for PECS')
        ptls = self._interactively_get_ptl()  # set selected ptlid
        posids, ids = self._interactively_get_posids()  # set selected posids
        self.ptl_setup(petal_roles=ptls, posids=posids, ids=ids)

    def get_owning_ptl(self, posid):
        """
        Finds the petal that owns this positioner
        """
        assert(isinstance(posid,str)), 'Must be single positioner!'
        retcode = self.ptlm.get_positioners(enabled_only=False, posids=[posid])
        for ptl in retcode.keys():
            if not retcode[ptl].empty:
                return ptl
        return

    def _interactively_get_ptl(self):
        ptls = input(f'Availible petal roles: {list(self.ptlm.Petals.keys())}\n'
                      f'Please enter list petal roles seperated by SPACES. \n'
                      f' Leave blank for all petals: ')
        if ptls == '':
            return list(self.ptlm.Petals.keys())
        petal_roles = ptls.split()
        # Validate roles
        for role in petal_roles:
            accepted = False
            for availible in self.ptlm.Petals.keys():
                if role == availible:
                    accepted = True
            if not accepted:
                self.printfunc(f'Invalid role {role}, try again.')
                return self._interactively_get_ptl()
        self.ptlm.participating_petals = petal_roles
        return petal_roles


    def _interactively_get_posids(self):
        user_text = input('Please list CAN bus IDs or posids, seperated by '
                          'SPACES. \nLeave blank to use all positioners: ')
        if user_text == '':
            selection = None
        else:
            selection = user_text.split()
        user_text = input('Use enabled positioners only? (y/n): ')
        enabled_only = self._parse_yn(user_text)
        if selection is None:
            retcode = self.ptlm.get_positioners(enabled_only=True)
            dflist = []
            for p in retcode.values():
                dflist.append(p)
            ids = pd.concat(dflist)
            posids = sorted(list(ids['DEVICE_ID']))
        elif 'can' in selection[0]:  # User passed a list of canids
            retcode = self.ptlm.get_positioners(enabled_only=True, busids=selection)
            dflist = []
            for p in retcode.values():
                dflist.append(p)
            ids = pd.concat(dflist)
            posids = sorted(list(ids['DEVICE_ID']))
        else:  # assume is a list of posids
            retcode = self.ptlm.get_positioners(enabled_only=True, posids=selection)
            dflist = []
            for p in retcode.values():
                dflist.append(p)
            ids = pd.concat(dflist)
            posids = sorted(list(ids['DEVICE_ID']))
        return posids, ids

    def fvc_measure(self, exppos=None, match_radius=30):
        '''use the expected positions given, or by default use internallly
        tracked current expected positions for fvc measurement
        returns expected_positions (df), measured_positions (df),
        matched_posids (set), unmatched_posids (set)'''
        if exppos is None:
            # participating_petals=None gets responses from all - not just selected petals
            exppos = (self.ptlm.get_positions(return_coord='QS', participating_petals=None)
                      .sort_values(by='DEVICE_ID'))  # includes all posids
        mr_old = self.fvc.get('match_radius')  # hold old match radius
        if mr_old != match_radius: # Ignore call if the same.
            self.fvc.set(match_radius=match_radius)  # set larger radius for calib
        # measured_QS, note that expected_pos was changed in place
        meapos = (pd.DataFrame(self.fvc.measure(exppos, all_fiducials=self.all_fiducials))
                  .rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())  # indexed by DEVICE_ID
        if mr_old != match_radius:
            self.fvc.set(match_radius=mr_old)  # restore old radius after measure
        meapos.columns = meapos.columns.str.upper()  # clean up header to save
        # find the posids that are unmatched, missing from FVC return
        matched = set(self.posids).intersection(set(meapos.index))
        unmatched = set(self.posids) - matched
        if len(unmatched) == 0:
            self.printfunc(f'All {len(self.posids)} positioners matched.')
        else:
            self.printfunc(f'Missing {len(unmatched)} of selected positioners'
                           f'\n{sorted(list(unmatched))}')
        return exppos, meapos, sorted(matched), sorted(unmatched)
