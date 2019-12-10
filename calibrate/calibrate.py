# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 21:23:25 2019

@author: Duan Yutong (dyt@physics.bu.edu)

positioner calibration calculations.
arc and grid target move requests have been generated assuming
the calibration values in DB at runtime. the calculations here shouldn't
require knowledge of the calibration values then, but they will be saved
in the test data products nevertheless. the seeded/initial calibration values
only serve to ensure spotmatch does not fail.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from posstate import PosState
from posmodel import PosModel
from postransforms import PosTransforms
idx = pd.IndexSlice


class PosCalibration:
    '''
    DOS app can pass the alignments of all petals as a dict keyed by pcid
    offline analysis can use DOSlib or psycopg2 to read alignments from DB

    similary DOS app can provide the petal
    '''

    def __init__(self, petal_alignemnts=None, use_doslib=False,
                 auto_update=False, printfunc=print):
        if petal_alignemnts is not None:
            self.petal_alignemnts = petal_alignemnts
        else:
            self.read_alignments(use_doslib=use_doslib)
        self.auto_update = auto_update
        self.printfunc = printfunc
        self.posmodels = {}

    def read_alignments(self, use_doslib):
        self.printfunc('Reading petal alignments from DB...')
        if use_doslib:
            from DOSlib.constants import ConstantsDB
            cdb = ConstantsDB()
            fpm = pd.DataFrame.from_dict(cdb.get_constants(
                group='focal_plane_metrology', tag='CURRENT', snapshot='DESI')
                ['focal_plane_metrology'], orient='index')
            alignments = {int(petal_loc): {'Tx': row['petal_offset_x'],
                                           'Ty': row['petal_offset_y'],
                                           'Tz': row['petal_offset_z'],
                                           'alpha': row['petal_rot_1'],
                                           'beta': row['petal_rot_2'],
                                           'gamma': row['petal_rot_3']}
                          for petal_loc, row in fpm.iterrows()}
        else:
            import psycopg2
            conn = psycopg2.connect(
                host="desi-db", port="5442", database="desi_dev",
                user="desi_reader", password="reader")
            # find the latest snapshot version of constants DB
            # may want and older one
            snap_ver = pd.read_sql_query('SELECT * from snapshots',
                                         conn)['version'].max()
            # read petal alignment for all petals
            q = pd.read_sql_query(f"""
            SELECT constants.elements.name, constants.elements.constants
            FROM constants.groups, constants.elements,
            constants.group_to_snapshot, constants.snapshots,
            constants.element_to_group
            WHERE constants.group_to_snapshot.snapshot_name = 'DESI'
            AND constants.group_to_snapshot.snapshot_version = '{snap_ver}'
            AND constants.groups.name = 'focal_plane_metrology'
            AND constants.groups.version
            = constants.group_to_snapshot.group_version
            AND constants.snapshots.version
            = constants.group_to_snapshot.snapshot_version
            AND constants.group_to_snapshot.group_name
            = constants.element_to_group.group_name
            AND constants.group_to_snapshot.group_version
            = constants.element_to_group.group_version
            AND constants.element_to_group.element_name
            = constants.elements.name
            AND constants.element_to_group.element_version
            = constants.elements.version
            ORDER BY constants.elements.name""", conn).set_index('name')
            alignments = {int(petal_loc): {'Tx': d['petal_offset_x'],
                                           'Ty': d['petal_offset_y'],
                                           'Tz': d['petal_offset_z'],
                                           'alpha': d['petal_rot_1'],
                                           'beta': d['petal_rot_2'],
                                           'gamma': d['petal_rot_3']}
                          for petal_loc, d in zip(q.index, q['constants'])}
        self.alignments = alignments

    def init_posmodels(self, data=None, posmodels=None):
        '''called upon receiving calibration data specified below'''
        self.printfunc('Initialising posmodels...')
        if posmodels is None:
            for posid in data.index.get_level_values('DEVICE_ID'):
                if posid not in self.posmodels.keys():
                    petal_loc = (data.reset_index().set_index('DEVICE_ID')
                                 .loc[posid, 'PETAL_LOC'].iloc[0])
                    self.posmodels[posid] = PosModel(state=PosState(
                        unit_id=posid, device_type='pos',
                        printfunc=self.printfunc),
                        petal_alignment=self.alignments[petal_loc])
        else:
            self.posmodels.update(posmodels)

    def calibrate_from_arc_data(self, data):
        """
        input data containing targets and FVC measurements for all petals
        is a pd dataframe with
            index:      (['T', 'P'], target_no, DEVICE_ID)
            columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                        tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

        for each positioner, calculate measured flatXY, fit with two circles
        to find centres and radii, calculate R1, F2, and then derive offsetsTP
        and convert measured QS -> flatXY -> poslocTP -> posintTP.
        From the fit we get radial deviations w.r.t. circle models and
        differences between target and measured/expected posintTP.

        return input dataframe with columns added:
            mea_posintT, mea_posintP, mea_flatX, mea_flatY,
            err_flatX, err_flatY, err_Q, err_S,
            err_posintT, err_posintP, err_radial  # measured - target or model

        and a calibration dataframe with
            index:      DEVICE_ID
            columns:    (['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
                          'LENGTH_R1', 'LENGTH_R2', ...# from collect_calib(),
                          'GEAR_RATIO_T', 'GEAR_RATIO_P',
                          'CENTRE_T', 'CENTRE_P', 'RADIUS_T', 'RADIUS_P'],
                         ['OLD', 'NEW'])
        """
        posids = data.index.droplevel([0, 1]).unique()
        self.init_posmodels(posids)  # double check that all posmodels exist
        for posid in posids:
            pass

    def calibrate_from_grid_data(self, data):
        """
        input data containing targets and FVC measurements  for all petals
        is a pd dataframe with
            index:      (target_no, DEVICE_ID)
            columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                        tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

        For each positioner, calculate measured flatXY, and fit it with float
        tgt_posintTP -> tgt_flatXY. From the fit we get 6 calibration params
        all at the same time, the residuals, and the fitted, expected posintTP

        return input dataframe with columns added:
            mea_posintT, mea_posintP, mea_flatX, mea_flatY,
            exp_posintT, exp_posintP, exp_flatX, exp_flatY, exp_Q, exp_S,
            err_flatX, err_flatY, err_Q, err_S  # measured - expected

        and a calibration dataframe with
            index:  DEVICE_ID
            column: (['OFFSET_T', 'OFFSET_P', 'OFFSET_X', 'OFFSET_Y',
                      'LENGTH_R1', 'LENGTH_R2', ...],  # from collect_calib()
                     ['OLD', 'NEW'])
        """
        self.printfunc(f'Calibrating with Grid data...')
        posids = sorted(data.index.get_level_values('DEVICE_ID').unique())
        self.init_posmodels(posids)  # double check that all posmodels exist
        param_keys = ['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
                      'LENGTH_R1', 'LENGTH_R2']
        cols = ['mea_flatX', 'mea_flatY',
                'tgt_flatX', 'tgt_flatY', 'tgt_Q', 'tgt_S']
        for col in cols:
            data[col] = np.nan
        # initial values for fitting
        p0 = [PosTransforms().alt[k] for k in param_keys]
        calibdf = pd.DataFrame(index=posids, columns=param_keys)
        for posid in posids:
            trans = self.posmodels[posid].trans
            trans.alt_override = True
            # measurement always in QS, but fit and derive params in flatXY
            QS = data.loc[idx[:, posid], ['mea_Q', 'mea_S']].values  # N x 2
            data.loc[idx[:, posid], ['mea_flatX', 'mea_flatY']] = (
                trans.QS_to_flatXY(QS.T).T)  # measured QS to flatXY
            # select pos data for fitting
            posdata = data.loc[idx[:, posid], :].droplevel(1, axis=0)
            posdata = posdata[~posdata.isnull().any(axis=1)]  # filter out nan
            if len(posdata) <= len(param_keys):
                self.printfunc(f'{posid} calibration failed, '
                               f'only {len(posdata)} valid grid points')
                continue  # skip this iteration for this posid in the loop
            mea_flatXY = posdata[['mea_flatX', 'mea_flatY']].values  # N x 2
            tgt_posintTP = posdata[['tgt_posintT', 'tgt_posintP']].values

            def target_xy(params):
                for key, param in zip(param_keys, params):
                    trans.alt[key] = param  # override transformation params
                flatXY = [trans.posintTP_to_flatXY(tp) for tp in tgt_posintTP]
                return np.array(flatXY)  # N x 2, target posintTP transformed

            def err_rms(params):  # function to be minimised
                err = target_xy(params) - mea_flatXY  # N x 2
                return np.linalg.norm(err) / np.sqrt(err.shape[0])

            # Ranges which values should be in
            bounds = ((0, 500), (0, 400),  # offsetsXY
                      (-180, 180), (-50, 50),  # offsetsTP
                      (2.5, 3.5), (2.5, 3.5))  # R1, R2
            res = minimize(fun=err_rms, x0=p0, bounds=bounds)
            self.printfunc(f'{posid} grid calibration, {mea_flatXY.shape[0]} '
                           f'points, err_rms = {res.fun:.3f}')
            # centralize offsetsTP (why needed if we can limit to +/-180?)
            for i, param_key in enumerate(param_keys):
                if param_key in ['OFFSET_T', 'OFFSET_P']:
                    res.x[i] = PosTransforms._centralized_angular_offset_value(
                        res.x[i])
            calibdf.loc[posid] = res.x  # save calibration results, 6 params
            data.loc[idx[:, posid],
                     ['tgt_flatX', 'tgt_flatY']] = tgtXY = target_xy(res.x)
            data.loc[idx[:, posid], ['tgt_Q', 'tgt_S']] = trans.flatXY_to_QS(
                tgtXY.values.T).T
            trans.alt_override = False  # finished fitting
            for c in ['flatX', 'flatY', 'Q', 'S']:  # calculate errors
                data[f'err_{c}'] = data[f'mea_{c}'] - data[f'tgt_{c}']
        return data, calibdf


if __name__ == '__main__':
    # sample calibration data
    df = pd.DataFrame(np.array([[9, -170, 150, 300, 30]]*3),
                      index=['M00001', 'M00002', 'M00003'],
                      columns=['PETAL_LOC', 'tgt_posintT', 'tgt_posintP',
                               'mea_Q', 'mea_S'])
    df['DEVICE_LOC'] = [78, 324, 517]
    data_grid = pd.concat([df]*10, keys=range(10),
                          names=['target_no', 'DEVICE_ID'])  # grid
    arc = pd.concat([df]*6, keys=range(10))  # one arc
    data_arc = pd.concat([arc, arc], keys=['T', 'P'],
                         names=['arc', 'target_no', 'DEVICE_ID'])
    posdata = data_grid.loc[idx[:, 'M00001'], :]
    posdata = data_arc.loc[idx['T', :, 'M00001'], :]
