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
'''

import os
import sys
import time
import numpy as np
import pandas as pd
from configobj import ConfigObj
from DOSlib.proxies import FVC, Petal, SimpleProxy  # , Illuminator
from DOSlib.exposure import Exposure
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
        if type(printfunc) is dict:  # a dict for all petals
            # if input printfunc is already a dict, check consistency
            assert set(self.pcids) == set(printfunc.keys()), (
                'Input pcids mismatch')
            self.printfuncs = printfunc
        else:  # if a single printfunc is supplied
            self.printfuncs = {pcid: printfunc for pcid in self.pcids}
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
            for pcid in self.pcids:
                self.ptls[pcid] = Petal(pcid)  # no sim state ctrl
                self.printfuncs[pcid](
                    f'Petal proxy initialised for {pcid}, '
                    f'simulator mode: {self.ptls[pcid].simulator_on}')
        else:
            self.ptls = ptls
            self.printfunc(
                f'Reusing existing petal proxies for petals {self.pcids}')
        # self.illuminator = Illuminator()  # this crashes KF 06/18/19
        # fvc stuff
        self.fvc_collector = SimpleProxy('FVCCOLLECTOR')
        try:
            self.fvc_collector._send_command('configure')
        except Exception:
            self.printfunc('FVC collector unavailable')

    def exp_setup(self):
        assert hasattr(self, 'data'), (
            'FPTestData must be initialised before calling exposure setup')
        self.exp = Exposure(readonly=False)
        self.exp.sequence = self.data.test_name
        self.data.set_dirs(self.exp.id)  # directory setup
        self.fvc.save_centers = True
        self.fvc.save_centers_path = self.data.dir

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
            self.printfunc(f'Invalid input: {yn_str}, must be y/n')

    def ptl_setup(self, pcid=None, posids=None):

        if pcid is None:
            pcid = self.pcids[0]
            self.printfunc(f'Defaulting to pcid = {pcid}')
        self.pcid = pcid
        self.ptl = self.ptls[self.pcid]
        if posids is None:
            posids = sorted(self.ptl.get_positioners(
                enabled_only=True)['DEVICE_ID'])
            self.printfunc(
                f'Defaulting to all {len(posids)} enabled positioners')
        self.posids = posids

    def interactive_ptl_setup(self):
        self.printfunc(f'Running interactive setup for PECS')
        pcid = self._interactively_get_ptl()  # set selected pcid
        posids = self._interactively_get_posids(pcid)  # set selected posids
        self.ptl_setup(pcid=pcid, posids=posids)

    def _interactively_get_ptl(self):
        pcid = input(f'Availible PCIDs: {list(self.ptls.keys())}\n'
                     f'Please enter a PCID (integer only): ')
        if pcid.isdigit():
            self.printfunc(f'Selected PCID = {pcid}')
            return int(pcid)
        else:
            self.printfunc('Invalid input, must be an integer, retry')
            return self._interactively_get_ptl()

    def _interactively_get_posids(self, pcid):
        user_text = input('Please list CAN bus IDs or posids, seperated by '
                          'SPACES. \nLeave blank to use all positioners: ')
        if user_text == '':
            selection = None
        else:
            selection = user_text.split()
        user_text = input('Use enabled positioners only? (y/n): ')
        enabled_only = self._parse_yn(user_text)
        if selection is None:
            posids = sorted(self.ptls[pcid].get_positioners(
                enabled_only=enabled_only)['DEVICE_ID'])
        elif 'can' in selection[0]:  # User passed a list of canids
            posids = sorted(self.ptls[pcid].get_positioners(
                enabled_only=enabled_only, busids=selection)['DEVICE_ID'])
        else:  # assume is a list of posids
            posids = sorted(self.ptls[pcid].get_positioners(
                enabled_only=enabled_only, posids=selection)['DEVICE_ID'])
        self.printfunc(f'Selected {len(posids)} positioners')
        return posids

    def fvc_measure(self, exppos=None, match_radius=50, matched_only=True):
        '''use the expected positions given, or by default use internallly
        tracked current expected positions for fvc measurement
        returns expected_positions (df), measured_positions (df)
        (bot have DEVICE_ID as index and sorted) and
        matched_posids (set), unmatched_posids (set)'''
        if exppos is None:
            # get all backlit fibres, enabled and disabled
            exppos_list = [(self.ptls[pcid].get_positions(return_coord='QS')
                            .sort_values(by='DEVICE_ID'))
                           for pcid in self.pcids]  # includes all posids
            exppos = pd.concat(exppos_list)
        if np.any(['P' in device_id for device_id in exppos['DEVICE_ID']]):
            self.printfunc('Expected positions of positioners by PetalApp '
                           'are contaminated by fiducials.')
        self.printfunc(
            f'Calling FVC.measure expecting {len(exppos)} positioners...')
        seqid = None
        if hasattr(self, 'exp'):
            seqid = self.exp.id
        # measured_QS, note that expected_pos was changed in place
        meapos = (pd.DataFrame(self.fvc.measure(
                      expected_positions=exppos, seqid=seqid,
                      exptime=self.exptime, match_radius=match_radius,
                      matched_only=matched_only,
                      all_fiducials=self.all_fiducials))
                  .rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())  # indexed by DEVICE_ID
        if np.any(['P' in device_id for device_id in meapos.index]):
            self.printfunc('Measured positions of positioners by FVC '
                           'are contaminated by fiducials.')
        meapos.columns = meapos.columns.str.upper()  # clean up header to save
        exppos = (exppos.rename(columns={'id': 'DEVICE_ID'})
                  .set_index('DEVICE_ID').sort_index())
        exppos.columns = exppos.columns.str.upper()
        # find the posids that are unmatched, missing from FVC return
        matched = set(exppos.index) & set(meapos.index)
        unmatched = set(exppos.index) - matched
        if len(unmatched) == 0:
            self.printfunc(f'All {len(exppos.index)} back-illuminated '
                           f'positioners measured by FVC')
        else:
            self.printfunc(
                f'Missing {len(unmatched)} of expected backlit fibres:'
                f'\n{sorted(unmatched)}')
        return exppos, meapos, matched, unmatched

    def fvc_collect(self, destination='/data/msdos/focalplane/'):
        self.printfunc('Collecting FVC images associated with exposure ID '
                       f'{self.exp.id} to: {destination}')
        os.makedirs(destination, exist_ok=True)
        try:
            self.fvc_collector._send_command(
                'collect', expid=self.exp.id, output_dir=destination,
                logbook=False)
        except Exception as e:
            self.printfunc(f'FVC collector failed: {e}')

    @staticmethod
    def countdown_sec(t):  # in seconds
        for i in reversed(range(t)):
            sys.stderr.write(f'\rSleeping... ({i} s / {t} s)')
            time.sleep(1)
            sys.stdout.flush()
        print(f'\nSleep finished ({t} s)')

    def pause(self, press_enter=False):
        '''pause operation between positioner moves for heat monitoring'''
        if self.pause_interval is None or press_enter:
            input('Paused for heat load monitoring for unspecified interval. '
                  'Press enter to continue: ')
        elif self.pause_interval == 0:  # no puase needed, just continue
            self.printfunc('pause_interval = 0, continuing without pause...')
        elif self.pause_interval > 0:
            self.printfunc(f'Pausing for {self.pause_interval} s...')
            self.countdown_sec(self.pause_interval)
