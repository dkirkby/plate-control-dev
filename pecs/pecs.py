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
import posconstants as pc
from DOSlib.proxies import FVC, PetalMan, SimpleProxy  # , Illuminator
from DOSlib.exposure import Exposure
from fvc_sim import FVC_proxy_sim

# Required environment variable
PECS_CONFIG_FILE = os.environ.get('PECS_CONFIG_FILE') # corresponds to e.g. 'pecs_default.cfg' or 'pecs_lbnl.cfg'
assert PECS_CONFIG_FILE

class PECS:
    '''if there is already a PECS instance from which you want to re-use
       the proxies, simply pass in pecs.fvc and pecs.ptls
       
        All available petal role names:     self.ptlm.Petals.keys()
        All selected petals:                self.ptlm.participating_petals
        Selected PCIDs:                     self.pcids from pecs_*.cfg
        
        For different hardware setups, you need to intialize including the
        correct config file for that local setup. This will be stored in
        fp_settings/hwsetups/ with a name like pecs_default.cfg or pecs_lbnl.cfg.
    '''
    def __init__(self, fvc=None, ptlm=None, printfunc=print, interactive=None,
                 test_name='PECS'):
        # Allow local config so scripts do not always have to collect roles
        # and names from the user. No check for illuminator at the moment
        # since it is not used in tests.
        self._pcid2role = lambda pcid: f'PETAL{pcid}'
        self._role2pcid = lambda role: int(role.replace('PETAL', ''))
        self.use_desimeter = False
        self.match_to_positioner_centers = False
        self.match_radius = 50
        self.exptime = 1.
        self.start_time = pc.now()
        self.test_name = test_name

        pecs_local = ConfigObj(PECS_CONFIG_FILE, unrepr=True, encoding='utf-8')
        for attr in pecs_local.keys():
            setattr(self, attr, pecs_local[attr])
        self.printfunc = printfunc
        if fvc is None:  # instantiate FVC proxy, sim or real
            if 'SIM' in self.fvc_role.upper():
                self.fvc = FVC_proxy_sim(max_err=0.0001)
            else:
                self.fvc = FVC(self.pm_instrument, fvc_role=self.fvc_role,
                               constants_version=self.constants_version,
                               use_desimeter=self.use_desimeter,
                               match_to_positioner_centers=self.match_to_positioner_centers)
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
            # Only use petals that are availible in Petalman
            self.pcids = list(set(self.pcids) & set(pcids))
            self.print(f'PetalMan proxy initialised with active petal '
                       f'role numbers (PCIDs): {pcids}')
        else:
            self.ptlm = ptlm
            self.print(f'Reusing existing PetalMan proxy with active petals: '
                       f'{self.ptlm.participating_petals}')
        if self.illuminated_pcids == 'all':
            self.illuminated_ptl_roles = list(self.ptlm.Petals.keys())
        else:
            self.illuminated_ptl_roles = [self._pcid2role(pcid)
                                          for pcid in self.illuminated_pcids
                                          if self._pcid2role(pcid)
                                          in list(self.ptlm.Petals.keys())]
        assert set(self.illuminated_ptl_roles) <= set(
            self.ptlm.Petals.keys()), (
            'Illuminated petals must be in availible petals!')
        if interactive or (self.pcids is None):
            self.interactive_ptl_setup()  # choose which petal to operate
        elif interactive is False:
            self.ptl_setup(self.pcids)  # use PCIDs specified in cfg
        #Setup exposure ID last incase aborted doing the above
        self._get_expid()

    def exp_setup(self):
        '''
        Temp function to setup fptestdata while PECS still has some integration with it
        '''
        assert hasattr(self, 'data'), (
            'FPTestData must be initialised before calling exposure setup.')
        self.test_name = self.data.test_name
        self.exp.program = self.test_name
        self.data.set_dirs(self.exp.id)
        self.start_time = self.data.t_i
        self.fvc.save_centers = True
        # fvc centre jsons are written by non-msdos account, note access
        self.fvc.save_centers_path = self.data.dir

    def _get_expid(self):
        '''
        Setup entry in exposureDB to get and exposure ID. 
        '''
        self.exp = Exposure(readonly=False)
        self.exp.sequence = 'Focalplane'
        self.exp.program = self.test_name
        self.exp.exptime = self.exptime
        self.iteration = 0
        self.print(f'DESI exposure ID set up as: {self.exp.id}')

    def print(self, msg):
        if hasattr(self, 'logger'):
            self.logger.info(msg)  # use broadcast logger to log to all pcids
        else:
            self.printfunc(msg)

    def _parse_yn(self, yn_str):
        #  Trying to accept varieties like y/n, yes/no
        if 'y' in yn_str.lower():
            return True
        elif 'n' in yn_str.lower():
            return False
        else:
            return self._parse_yn(
                input(f'Invalid input: {yn_str}, must be y/n:'))

    def ptl_setup(self, pcids, posids=None, illumination_check=False):
        '''input pcids must be a list of integers'''
        self.print(f'Setting up petals and positioners for {len(pcids)} '
                   f'selected petals, PCIDs: {pcids}')
        if illumination_check:
            for pcid in pcids:  # illumination check
                assert self._pcid2role(pcid) in self.illuminated_ptl_roles, (
                    f'PC{pcid:02} must be illuminated.')
        self.ptlm.participating_petals = [self._pcid2role(pcid)
                                          for pcid in self.pcids]
        if posids is None:
            posids0, posinfo = self.get_enabled_posids(posids='all', include_posinfo=True)
            self.print(f'Defaulting to all {len(posids0)} enabled positioners')
        else:
            ret = self.ptlm.get_positioners(posids=posids, enabled_only=False)
            posinfo = pd.concat(list(ret.values())).set_index('DEVICE_ID')
            posids0 = sorted(set(posids) & set(posinfo.index))  # double check
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
        return self._pcid2role(self.pcid_lookup(posid))

    def _interactively_get_pcid(self):
        pcids = input(f'Please enter integer PCIDs seperated by spaces. '
                      f'Leave blank to select petal specified in cfg: ')
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
        enabled_only, kwarg = True, {}
        if user_text == '':
            self.print(f'Defaulting to all enabled positioners...')
            posids = None
        else:
            selection = user_text.split()
            kw = 'busids' if 'can' in selection[0] else 'posids'
            kwarg.update({kw: selection})
            enabled_only = False
            self.print(f'{len(selection)} items specified, '
                       'allowing disabled positioners to be selected...')
            ret = self.ptlm.get_positioners(enabled_only=enabled_only, **kwarg)
            posinfo = pd.concat(list(ret.values()))
            posids = sorted(posinfo['DEVICE_ID'])
            self.print(f'Selected {len(posids)} positioners')
        return posids

    def fvc_measure(self, exppos=None, match_radius=None, matched_only=True,
                    check_unmatched=False, test_tp=False):
        '''use the expected positions given, or by default use internallly
        tracked current expected positions for fvc measurement
        returns expected_positions (df), measured_positions (df)
        (bot have DEVICE_ID as index and sorted) and
        matched_posids (set), unmatched_posids (set)'''

        if match_radius is None :
            match_radius = self.match_radius
        if exppos is None:
            # participating_petals=None gets responses from all
            # not just selected petals
            exppos = (self.ptlm.get_positions(
                          return_coord='QS',
                          participating_petals=self.illuminated_ptl_roles)
                      .sort_values(by='DEVICE_ID').reset_index(drop=True))
        if np.any(['P' in device_id for device_id in exppos['DEVICE_ID']]):
            self.print('Expected positions of positioners by PetalApp '
                       'are contaminated by fiducials.')
        self.print(f'Calling FVC.measure with exptime = {self.exptime} s, '
                   f'expecting {len(exppos)} backlit positioners...')
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
                  .set_index('DEVICE_ID').sort_index())
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
        fvc_data = pd.concat([meapos,
                    exppos[exppos.index.isin(meapos.index)][['PETAL_LOC','DEVICE_LOC']]],
                    axis=1)
        #Call handle fvc feedback
        self.ptlm.handle_fvc_feedback(fvc_data, check_unmatched=check_unmatched,
                                      test_tp=test_tp, auto_update=True,
                                      err_thresh=self.max_err, up_tol=self.tp_tol,
                                      up_frac=self.tp_frac)
        self.iteration += 1
        return exppos, meapos, matched, unmatched

    def move_measure(self, request, match_radius=None, check_unmatched=False,
                     test_tp=False, anticollision=None):
        '''
        Wrapper for often repeated moving and measuring sequence.
        Returns data merged with request
        '''
        self.print(f'Moving positioners... Exposure {self.exp.id}, iteration {self.iteration}')
        self.ptlm.set_exposure_info(self.exp.id, self.iteration)
        self.ptlm.prepare_move(request, anticollision=anticollision)
        self.ptlm.execute_move(reset_flags=False, control={'timeout': 120})
        _, meapos, matched, _ = self.fvc_measure(
            exppos=None, matched_only=True, match_radius=match_radius, 
            check_unmatched=check_unmatched, test_tp=test_tp)
        result = self._merge_match_and_rename_fvc_data(request, meapos, matched)
        self.ptlm.clear_exposure_info()
        return result
    
    def rehome_and_measure(self, posids, axis='both', debounce=True, log_note='',
                           match_radius=None, check_unmatched=False, test_tp=False,
                           anticollision=None):
        '''Wrapper for sending rehome command and then measuring result.
        Returns whatever fvc_measure returns.
        '''
        assert axis in {'both', 'phi', 'phi_only', 'theta', 'theta_only'}
        assert debounce in {True, False}
        self.print(f'Rehoming positioners, axis={axis}, anticollision={anticollision}' +
                   f', debounce={debounce}, exposure={self.exp.id}, iteration={self.iteration}')
        self.ptlm.set_exposure_info(self.exp.id, self.iteration)
        enabled = self.get_enabled_posids(posids)
        posids_by_petal = {}
        for posid in enabled:
            pcid = self.pcid_lookup(posid)
            if pcid not in posids_by_petal:
                posids_by_petal[pcid] = set()
            posids_by_petal[pcid].add(posid)
        for pcid, these_posids in posids_by_petal.items():
            # 2020-07-12 [JHS] this happens sequentially petal by petal, only because
            # I haven't studied the PetalMan / PECS interfaces sufficiently well to
            # understand how to call the rehome_pos commands simultanously across
            # multiple petals. That said, this is probably such a rarely called function
            # that it's not critical to achieve that parallelism right now.
            role = self._pcid2role(pcid)
            self.ptlm.rehome_pos(ids=these_posids, axis=axis, anticollision=anticollision,
                                 debounce=debounce, log_note=log_note, participating_petals=role)
        # 2020-07-21 [JHS] dissimilar results than move_measure func, since no "request" data structure here 
        result = self.fvc_measure(exppos=None, matched_only=True, match_radius=match_radius, 
                                  check_unmatched=check_unmatched, test_tp=test_tp)
        self.ptlm.clear_exposure_info()
        return result

    def home_adc(self):
        try:
            adc = SimpleProxy('ADC')
            if self._parse_yn(input('Home ADC? (y/n): ')):
                self.print('Homing ADC...')
                retcode = adc._send_command('home', controllers=[1, 2])
                self.print(f'ADC.home returned code: {retcode}')
        except Exception as e:
            print(f'Exception homing ADC, {e}')

    def fvc_collect(self):
        destination = os.path.join(
            '/exposures/desi', pc.dir_date_str(t=self.start_time),
            f'{self.exp.id:08}')
        # os.makedirs(destination, exist_ok=True)  # no permission anyway
        try:
            fvccoll = SimpleProxy('FVCCOLLECTOR')
            retcode = fvccoll._send_command('configure')
            self.print(f'FVCCollector.configure returned code: {retcode}')
            retcode = fvccoll._send_command(
                'collect', expid=self.exp.id, output_dir=destination,
                logbook=False)
            self.print(f'FVCCollector.collect returned code: {retcode}')
            if retcode == 'SUCCESS':
                self.print('FVC data associated with exposure ID '
                           f'{self.exp.id} collected to: {destination}')
            expserv = SimpleProxy('EXPOSURESERVER')
            retcode = expserv._send_command('distribute', source=destination)
            self.print(f'ExposureServer.distribute returned code: {retcode}')
            if retcode == 'SUCCESS':
                self.print(f'symlink created for: {destination}')
        except Exception as e:
            self.print(f'FVC collection failed with exception: {e}')

    @staticmethod
    def countdown_sec(t):  # in seconds
        t = int(t)
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

    def decorate_note(self, log_note=''):
        '''Adds additional information to a positioner log note. The intended
        usage is to include important facts known only to PECS, when constructing
        the LOG_NOTE field that gets saved to the posmovedb.'''
        log_note = pc.join_notes(log_note, f'expid={self.exp.id}')
        log_note = pc.join_notes(log_note, f'use_desimeter={self.use_desimeter}')
        return log_note
                
    def get_enabled_posids(self, posids='sub', include_posinfo=False):
        '''Returns list of the enabled posids.
        
        INPUTS:
            posids ... 'sub' --> return enabled subset of PECS' self.posids property
                   ... 'all' --> return all currently enabled posids
                   ... some iterable --> return just the enabled subset of iterable
        
            include_posinfo ... boolean, whether to return a second item with
                                additional "posinfo" data
        '''
        if posids == 'sub':
            selected_posids = self.posids
        elif posids == 'all':
            selected_posids = None
        else:
            try:
                iterator = iter(posids)
                selected_posids = [p for p in iterator]
            except:
                assert False, f'error, could not iterate arg posids={posids}'
        ret = self.ptlm.get_positioners(enabled_only=True, posids=selected_posids)
        posinfo = pd.concat(list(ret.values())).set_index('DEVICE_ID')
        posids = sorted(posinfo.index)
        if include_posinfo:
            return posids, posinfo
        return posids
    
    def _merge_match_and_rename_fvc_data(self, request, meapos, matched):
        '''Returns results of fvc measurement after checking for target matches
        and doing ome pandas juggling, very specifc to the other data interchange
        formats in pecs etc.
        
        request ... pandas dataframe with index column DEVICE_ID and request data
        meapos ... pandas dataframe with index column DEVICE_ID and fvc data
        matched ... set of posids
        '''
        # meapos may contain not only matched but all posids in expected pos
        matched_df = meapos.loc[sorted(matched & set(self.posids))]
        merged = matched_df.merge(request, on='DEVICE_ID').set_index('DEVICE_ID')
        
        # columns get renamed
        merged.rename(columns={'X1': 'tgt_posintT', 'X2': 'tgt_posintP',
                               'Q': 'mea_Q', 'S': 'mea_S', 'FLAGS': 'FLAG'},
                      inplace=True)
        mask = merged['FLAG'].notnull()
        merged.loc[mask, 'STATUS'] = pc.decipher_posflags(merged.loc[mask, 'FLAG'])
        
        # get expected (tracked) posintTP angles
        exppos = (self.ptlm.get_positions(return_coord='posintTP',
                                          participating_petals=self.ptl_roles)
                  .set_index('DEVICE_ID')[['X1', 'X2']])
        exppos.rename(columns={'X1': 'posintT', 'X2': 'posintP'}, inplace=True)
        result = merged.join(exppos, on='DEVICE_ID')
        return result