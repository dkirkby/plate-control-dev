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
    All available petal role names:     self.ptlm.Petals.keys()
    All selected petals:                self.ptlm.participating_petals
    Selected PCIDs:                     self.pcids from pecs_local.cfg
    '''

    def __init__(self, fvc=None, ptlm=None, printfunc=print, interactive=None):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        pecs_local = ConfigObj(  # set basic self attributes
            os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'pecs_local.cfg'),
            unrepr=True, encoding='utf-8')
        for attr in pecs_local.keys():
            setattr(self, attr, pecs_local[attr])
        self.printfunc = printfunc
        if fvc is None:  # instantiate FVC proxy, sim or real
            if 'SIM' in self.fvc_role.upper():
                self.fvc = FVC_proxy_sim(max_err=0.0001)
            else:
                os.environ[]
                self.fvc = FVC(self.pm_instrument, fvc_role=self.fvc_role,
                               constants_version=self.constants_version)
            self.print(f"FVC proxy created for instrument: "
                       f"{self.fvc.get('instrument')}")
        else:
            self.fvc = fvc
            self.print(f"Reusing existing FVC proxy: "
                       f"{self.fvc.get('instrument')}")
        if ptlm is None:
            self.ptlm = PetalMan()
            pcids = [self._role2pcid(role)
                     for role in self.ptlm.participating_petals]
            self.print(f'PetalMan proxy initialised with active petal '
                       f'role numbers (PCIDs): {pcids}')
        else:
            self.ptlm = ptlm
            self.print(f'Reusing existing PetalMan proxy with active petals: '
                       f'{self.ptlm.participating_petals}')
        if self.illuminated_petals == 'all':
            self.illuminated_petals = self.ptlm.Petals.keys()
        else:
            assert set(self.illuminated_petals).issubset(
                set(self.ptlm.Petals.keys())), (
                'Illuminated petals must be in availible petals!')
        # fvc stuff
        self.fvc_collector = SimpleProxy('FVCCOLLECTOR')
        try:
            self.fvc_collector._send_command('configure')
        except Exception:
            self.print('FVC collector unavailable')
        if interactive is None:
            pass
        elif (self.pcids is None) or interactive:  # boolean
            self.interactive_ptl_setup()  # choose which petal to operate
        else:
            self.ptl_setup(self.pcids)  # use PCIDs specified in cfg

    def exp_setup(self):
        assert hasattr(self, 'data'), (
            'FPTestData must be initialised before calling exposure setup.')
        self.exp = Exposure(readonly=False)
        self.exp.sequence = self.data.test_name
        self.data.set_dirs(self.exp.id)  # directory setup
        self.fvc.save_centers = True
        self.fvc.save_centers_path = self.data.dir

    def print(self, msg):
        if hasattr(self, logger):
            self.logger.debug(msg)  # use broadcast logger to log to all pcids
        self.printfunc(msg)

    def _parse_yn(self, yn_str):
        #  Trying to accept varieties like y/n, yes/no
        if 'y' in yn_str.lower():
            return True
        elif 'n' in yn_str.lower():
            return False
        else:
            self.print(f'Invalid input: {yn_str}, must be y/n')

    @staticmethod
    def _pcid2role(pcid):
        return f'PETAL{pcid}'

    @staticmethod
    def _role2pcid(role):
        return int(role.replace('PETAL', ''))

    def ptl_setup(self, pcids, posids=None):
        '''input pcids must be a list of integers'''
        self.print(f'Setting up petals and positioners for {len(pcids)} '
                   f'selected petals, PCIDs: {pcids}')
        for pcid in pcids:  # illumination check
            assert f'PETAL{pcid}' in self.illuminated_petals, (
                f'PC{pcid:02} must be illuminated.')
        self.ptlm.participating_petals = [self._pcid2role(pcid)
                                          for pcid in self.pcids]
        if posids is None:
            ret = self.ptlm.get_positioners(enabled_only=True)
            posinfo = pd.concat(list(ret.values())).set_index('DEVICE_ID')
            posids = sorted(posinfo.index)
            self.print(f'Defaulting to all {len(posids)} enabled positioners')
        else:
            ret = self.ptlm.get_positioners(posids=posids, enabled_only=True)
            posinfo = pd.concat(list(ret.values())).set_index('DEVICE_ID')
            posids0 = list(set(posids) & set(posinfo.index))
            self.print(f'Validated {len(posids0)} of {len(posids)} '
                       f'positioners specified')
        self.posids = posids0
        self.posinfo = posinfo
        self.ptl_roles = self.ptlm.participating_petals

    def interactive_ptl_setup(self):
        self.print(f'Running interactive setup for PECS')
        pcids = self._interactively_get_pcid()  # set selected ptlid
        posids = self._interactively_get_posids()  # set selected posids
        self.ptl_setup(pcids, posids=posids)

    def pcid_lookup(self, posid):
        if posid in self.posinfo.index:
            return self.posinfo.loc[posid, 'PETAL_LOC']
        else:
            raise ValueError(f'Invalid posid {posid} not found in PCIDs: '
                             f'{self.pcids}')

    def ptl_role_lookup(self, posid):
        return self.pcid2role(self.pcid_lookup(posid))

    def _interactively_get_pcid(self):
        pcids = input(f'Please enter integer PCIDs seperated by '
                      f'spaces. Leave blank to select all available petals: ')
        if pcids == '':
            pcids = self.pcids
        for pcid in pcids:  # validate pcids against petalman available roles
            assert f'PETAL{pcid}' in self.ptlm.Petals.keys(), (
                f'PC{pcid:02} unavailable, all available ICS petal roles: '
                f'{self.ptlm.Petals.keys()}')
        self.print(f'Selected {len(self.pcids)} petals, PCIDs: {self.pcids}')
        self.ptlm.participating_petals = [self._pcid2role(p) for p in pcids]
        return pcids

    def _interactively_get_posids(self):
        user_text = input('Please list canids (can??) or posids, seperated by '
                          'spaces. Leave blank to select all positioners: ')
        kwarg = {}
        if user_text != '':
            selection = user_text.split()
            kw = 'busids' if 'can' in selection[0] else 'posids'
            kwarg.update({kw, selection})
        ret = self.ptlm.get_positioners(enabled_only=True, **kwarg)
        posinfo = pd.concat(list(ret.values()))
        posids = sorted(posinfo['DEVICE_ID'])
        self.print(f'Selected {len(posids)} positioners')
        return posids

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
            self.print('Expected positions of positioners by PetalApp '
                       'are contaminated by fiducials.')
        self.print(
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
            self.print('Measured positions of positioners by FVC '
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
            self.print(f'All {len(exppos.index)} back-illuminated '
                       f'positioners measured by FVC')
        else:
            self.print(f'Missing {len(unmatched)} of expected backlit fibres:'
                       f'\n{sorted(unmatched)}')
        return exppos, meapos, matched, unmatched

    def fvc_collect(self, destination='/data/msdos/focalplane/'):
        self.print('Collecting FVC images associated with exposure ID '
                   f'{self.exp.id} to: {destination}')
        os.makedirs(destination, exist_ok=True)
        try:
            self.fvc_collector._send_command(
                'collect', expid=self.exp.id, output_dir=destination,
                logbook=False)
        except Exception as e:
            self.print(f'FVC collector failed: {e}')

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
            self.print('pause_interval = 0, continuing without pause...')
        elif self.pause_interval > 0:
            self.print(f'Pausing for {self.pause_interval} s...')
            self.countdown_sec(self.pause_interval)
