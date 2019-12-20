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
import os
import sys
import time
import numpy as np
import pandas as pd
from configobj import ConfigObj
from DOSlib.proxies import FVC, PetalMan, SimpleProxy  # , Illuminator
from DOSlib.exposure import Exposure
from fvc_sim import FVC_proxy_sim


class PECS:
    '''if there is already a PECS instance from which you want to re-use
       the proxies, simply pass in pecs.fvc and pecs.ptls
    '''
    def __init__(self, fvc=None, ptlm=None, printfunc=print):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        pecs_local = ConfigObj(  # set basic self attributes
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'pecs_local.cfg'),
            unrepr=True, encoding='utf-8')
        for attr in pecs_local.keys():
            setattr(self, attr, pecs_local[attr])
        if isinstance(printfunc, dict):  # a dict for all petals
            # if input printfunc is already a dict, skip consistency check
            # assert set(self.pcids) == set(printfunc.keys()), (
            #     'Input pcids mismatch')
            self.printfuncs = printfunc
        else:  # if a single printfunc is supplied, use it for all pcids
            self.printfuncs = {pcid: printfunc for pcid in range(10)}
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
            self.printfunc(f'PetalMan proxy initialised with active petals: '
                           f'{self.ptlm.participating_petals}')
        else:
            self.ptlm = ptlm
            self.printfunc(
                f'Reusing existing PetalMan proxy with active petals: '
                f'{self.ptlm.participating_petals}')
        if self.illuminated_petals is not None:
            assert set(self.illuminated_petals).issubset(
                set(self.ptlm.Petals.keys())), (
                'Illuminated petals must be in availible petals!')
        # fvc stuff
        self.fvc_collector = SimpleProxy('FVCCOLLECTOR')

    def exp_setup(self):
        assert hasattr(self, 'data'), (
            'FPTestData must be initialised before calling exposure setup.')
        self.exp = Exposure(readonly=False)
        self.exp.sequence = self.data.test_name
        # directory setup
        self.data.set_dirs(self.exp.id)

    def printfunc(self, msg):
        '''self.printfuncs is a dict indexed by pcids as specified for input,
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

    def ptl_setup(self, petal_roles=None, posids=None, ids=None):

        if petal_roles is None:
            self.printfunc(
                f'Defaulting to petal roles: {self.ptlm.participating_petals}')
        else:
            for ptl in petal_roles:
                assert 'PETAL' in ptl, (f'Petal role names are always '
                                        f'PETAL###, invalid role name {ptl}')
                if self.illuminated_petals is not None:
                    assert ptl in self.illuminated_petals, (
                        f'{ptl} must be illuminated!')
            self.ptlm.participating_petals = petal_roles
        if posids is None and ids is None:
            retcode = self.ptlm.get_positioners(enabled_only=True)
            ids = pd.concat(list(retcode.values()))
            posids = sorted(ids['DEVICE_ID'])
            self.printfunc(
                f'Defaulting to all {len(posids)} enabled positioners')
        elif posids is None:
            posids = sorted(ids['DEVICE_ID'])
        elif ids is None:
            retcode = self.ptlm.get_positioners(enabled_only=False,
                                                posids=posids)
            ids = pd.concat(list(retcode.values()))
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
        assert isinstance(posid, str), 'Must be single positioner!'
        retcode = self.ptlm.get_positioners(enabled_only=False, posids=[posid])
        for ptl in retcode.keys():
            if not retcode[ptl].empty:
                return ptl
        return

    def _interactively_get_ptl(self):
        ptls = input(f'Availible petal roles: {list(self.ptlm.Petals.keys())}'
                     f'\nPlease enter list petal roles seperated by SPACES. '
                     f'Leave blank for all petals: ')
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
        if selection is None:
            retcode = self.ptlm.get_positioners(enabled_only=True)
            ids = pd.concat(list(retcode.values()))
            posids = sorted(ids['DEVICE_ID'])
        elif 'can' in selection[0]:  # User passed a list of canids
            retcode = self.ptlm.get_positioners(enabled_only=True,
                                                busids=selection)
            ids = pd.concat(list(retcode.values()))
            posids = sorted(ids['DEVICE_ID'])
        else:  # assume selection is a list of posids
            retcode = self.ptlm.get_positioners(enabled_only=True,
                                                posids=selection)
            ids = pd.concat(list(retcode.values()))
            posids = sorted(ids['DEVICE_ID'])
        return posids, ids

    def fvc_measure(self, exppos=None, match_radius=50, matched_only=True):
        '''use the expected positions given, or by default use internallly
        tracked current expected positions for fvc measurement
        returns expected_positions (df), measured_positions (df)
        (bot have DEVICE_ID as index and sorted) and
        matched_posids (set), unmatched_posids (set)'''
        if exppos is None:
            # participating_petals=None gets responses from all
            # not just selected petals
            exppos = (self.ptlm.get_positions(
                          return_coord='QS',
                          participating_petals=self.illuminated_petals)
                      .sort_values(by='DEVICE_ID').reset_index())
        if np.any(['P' in device_id for device_id in exppos['DEVICE_ID']]):
            self.printfunc('Expected positions of positioners by PetalApp '
                           'are contaminated by fiducials.')
            # raise Exception('Expected positions of positioners by PetalApp '
            #                 'are contaminated by fiducials.')
        self.printfunc(f'Calling FVC measure expecting '
                       f'{len(exppos)} positioners...')
        # measured_QS, note that expected_pos was changed in place
        meapos = (pd.DataFrame(self.fvc.measure(
                      expected_positions=exppos, seqid=self.exp.id,
                      exptime=self.exptime, match_radius=match_radius,
                      matched_only=matched_only,
                      all_fiducials=self.all_fiducials))
                  .rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())  # indexed by DEVICE_ID
        if np.any(['P' in device_id for device_id in meapos.index]):
            print('Measured positions of positioners by FVC '
                  'are contaminated by fiducials.')
        meapos.columns = meapos.columns.str.upper()  # clean up header to save
        exppos = (exppos.rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())
        exppos.columns = exppos.columns.str.upper()
        # recover flags
        meapos['FLAGS'] |= exppos.loc[list(meapos.index)]['FLAGS']
        # find the posids that are unmatched, missing from FVC return
        matched = set(exppos.index) & set(meapos.index)
        unmatched = set(exppos.index) - matched
        if len(unmatched) == 0:
            self.printfunc(f'All {len(exppos.index)} positioners matched.')
        else:
            self.printfunc(
                f'Missing {len(unmatched)} of expected backlit fibres:'
                f'\n{sorted(unmatched)}')
        return exppos, meapos, matched, unmatched

    def fvc_collect(self):
        self.printfunc('Collecting FVC images associated with exposure ID '
                       f'{self.exp.id} to: {self.data.dir}')
        self.fvc_collector._send_command('collect', expid=self.exp.id,
                                         output_dir=self.data.dir)

    @staticmethod
    def countdown_sec(t, dt=1):  # in seconds
        for i in reversed(range(3)):
            sys.stderr.write(f'\rSleeping... ({i*dt+dt} s / {t} s)')
            time.sleep(dt)  # sleep until a whole second boundary
            sys.stdout.flush()
        print(f'\nSleep finished ({t} s).')

    def pause(self):
        '''pause operation between positioner moves for heat monitoring'''
        if self.pause_interval is None:
            input('Paused for heat load monitoring for unspecified interval. '
                  'Press enter to continue: ')
        elif self.pause_interval == 0:
            # no puase needed, just continue
            self.printfunc('Pause interval = 0, continuing without pause...')
        elif self.pause_interval > 0:
            self.printfunc(f'Pausing for {self.pause_interval} s...')
            self.countdown_sec(self.pause_interval)
