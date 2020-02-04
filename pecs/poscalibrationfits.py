# -*- coding: utf-8 -*-
"""
Created on Mon Dec 9 21:23:25 2019

@author: Duan Yutong (dyt@physics.bu.edu)

positioner calibration calculations.
arc and grid target move requests have been generated assuming
the calibration values in DB at runtime. the calculations here shouldn't
require knowledge of the calibration values then, but they will be saved
in the test data products nevertheless. the seeded/initial calibration values
only serve to ensure spotmatch does not fail.

'mea_' is measured, 'exp_' is internally-tracked/expected, 'tgt_' is target
"""
import os
from glob import glob
import numpy as np
from scipy import optimize
import pandas as pd
from tqdm import tqdm
import posconstants as pc
from postransforms import PosTransforms
from posstate import PosState
from posmodel import PosModel
from DOSlib.positioner_index import PositionerIndex
from fptestdata import BroadcastLogger
idx = pd.IndexSlice
keys_fit = ['OFFSET_X', 'OFFSET_Y', 'OFFSET_T', 'OFFSET_P',
            'LENGTH_R1', 'LENGTH_R2']  # initial values for fitting


class PosCalibrationFits:
    '''
    DOS app can pass the alignments of all petals as a dict keyed by pcid
    offline analysis can use DOSlib or psycopg2 to read alignments from DB

    similary DOS app DOS calls init_posmodels after initialisation to
    supply posmodels of all petals, a dict keyed by posids
    '''

    def __init__(self, petal_alignments=None, use_doslib=False,
                 posmodels=None, loggers=None, printfunc=print):
        self.logger = BroadcastLogger(loggers=loggers, printfunc=printfunc)
        if petal_alignments is not None:
            self.petal_alignments = petal_alignments
        else:
            self.read_alignments(use_doslib=use_doslib)
        if posmodels is not None:
            self.init_posmodels(posmodels=posmodels)
        self.pi = PositionerIndex()

    def read_alignments(self, use_doslib):
        self.logger.debug('Reading petal alignments from DB...')
        if use_doslib:
            from DOSlib.constants import ConstantsDB
            group, tag, snapshot = 'focal_plane_metrology', 'CURRENT', 'DESI'
            df = pd.DataFrame.from_dict(ConstantsDB().get_constants(
                group=group, tag=tag, snapshot=snapshot)
                [group], orient='index')
            alignments = {int(petal_loc): {'Tx': row['petal_offset_x'],
                                           'Ty': row['petal_offset_y'],
                                           'Tz': row['petal_offset_z'],
                                           'alpha': row['petal_rot_1'],
                                           'beta': row['petal_rot_2'],
                                           'gamma': row['petal_rot_3']}
                          for petal_loc, row in df.iterrows()}
        else:
            import psycopg2
            conn = psycopg2.connect(
                host="desi-db", port="5442", database="desi_dev",
                user="desi_reader", password="reader")
            # find the latest snapshot version, may want and older one
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
        self.logger.info(f'Petal alignments loaded: {alignments}')
        self.petal_alignments = alignments

    def init_posmodels(self, posids):
        '''called upon receiving calibration data specified below
        supply either posmodels (online) or data (offline)'''
        self.logger.debug('Initialising posmodels...')
        self.posmodels, self.petal_locs, self.petal_ids = {}, {}, {}
        for posid in tqdm(posids):
            posinfo = self.pi.find_by_device_id(posid)
            self.petal_locs[posid] = petal_loc = posinfo['PETAL_LOC']
            self.petal_ids[posid] = petal_id = posinfo['PETAL_ID']
            if posid not in self.posmodels:
                self.posmodels[posid] = PosModel(state=PosState(
                    unit_id=posid, petal_id=petal_id, device_type='pos',
                    printfunc=self.logger.debug),
                    petal_alignment=self.petal_alignments[petal_loc])
        self.posids = posids

    @staticmethod  # this is the old implementation without bounds, often fails
    def fit_circle_lsq(x):  # input x is a N x 2 array for (x, y) points in 2D
        '''example data: x = np.array([[1, 0], [2, 1], [3, 0]]) '''
        def calc_radius(xc):  # 1 x 2 array
            '''calculate distance of each 2D point from the center (xc, yc)'''
            return np.sqrt(np.sum(np.square(x - xc), axis=1))  # 1 x N array

        def radial_variations(xc):
            '''calculate distance bewteen all points and the circle model'''
            Ri = calc_radius(xc)  # 1 x N array
            return Ri - Ri.mean()  # 1 x N array

        ctr0 = np.mean(x, axis=0)  # 1 x 2 np array, initial estimate of centre
        ctr, _ = optimize.leastsq(radial_variations, ctr0)
        return ctr, calc_radius(ctr), radial_variations(ctr)

    @staticmethod
    def fit_circle(x, ctr0=None, exp=1): 
        # input x is a N x 2 array for (x, y) points in 2D
        # example data: x = np.array([[1, 0], [2, 1], [3, 0]])

        def radial_dist(x0, y0):
            return np.linalg.norm(x - (x0, y0), axis=1)

        def residuals(rs, r):
            return rs - r

        def circle_min(params):
            x0, y0, r = params
            rs = radial_dist(x0, y0)
            dr = residuals(rs, r)
            # reduced penalty for phi outliners with exp=1
            return np.sum(np.power(np.abs(dr), exp))

        if ctr0 is None:
            ctr0 = np.mean(x, axis=0)
        p0 = (ctr0[0], ctr0[1], 3)  # initial values: centre_x, centre_y, radius
        bounds = ((ctr0[0]-3, ctr0[0]+3), (ctr0[1]-3, ctr0[1]+3), (1, 5))
        sol = optimize.minimize(fun=circle_min, x0=p0, bounds=bounds)
        dr = residuals(radial_dist(*sol.x[:2]), sol.x[2])
        return sol.x[:2], sol.x[2], dr  # centre, radius, residuals sum

    def calibrate_from_arc_data(self, data):
        """
        input data is a pd dataframe containing targets and FVC measurements
        for all petals with
            index:      (['T', 'P'], target_no, DEVICE_ID)
            columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                        tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

        for each positioner, calculate measured flatXY, fit with two circles
        to find centres and radii, calculate R1, F2, and then derive offsetsTP
        and convert measured QS -> flatXY -> poslocTP -> posintTP.
        From the fit we get radial deviations w.r.t. circle models and
        differences between target and measured/expected posintTP.

        return input dataframe with columns added:
            tgt_flatXY, tgt_QS (directly from tgt_posintTP)
            mea_flatXY (measurements directly from mea_QS)
            exp_flatXY, exp_QS, exp_posintTP(fitted expectation)
            err_flatXY, err_QS (fitted expectation - measured)
            err_posintTP (fitted expectation - target)

        and a calibration dataframe with
            index:      DEVICE_ID
            columns:    OFFSET_X, OFFSET_Y, OFFSET_T, OFFSET_P,
                        LENGTH_R1, LENGTH_R2, centre_T, centre_P
                        radius_T, radius_P, residuals_T, residuals_P,
                        GEAR_RATIO_T, GEAR_RATIO_P
        """
        posids = data.index.get_level_values('DEVICE_ID').unique()
        self.logger.debug(f'Analysing arc calibration measurement data...')
        self.init_posmodels(posids=posids)  # double check all posmodels exist
        cols = ['tgt_flatX', 'tgt_flatY', 'tgt_Q', 'tgt_S',
                'mea_flatX', 'mea_flatY', 'exp_posintT', 'exp_posintP',
                'exp_flatX', 'exp_flatY', 'exp_Q', 'exp_S']
        for col in cols:  # add new empty columns to grid data dataframe
            data[col] = np.nan
        poscals = []  # each entry is a row of calibration values for one posid
        self.logger.debug(f'Fitting loop for {len(posids)} positioners...')
        for posid in tqdm(posids):
            poscal, posmea, posmodel = {}, {}, self.posmodels[posid]
            trans, state = posmodel.trans, posmodel.state 
            tgt_posintTP = data.loc[idx[:, :, posid],
                                    ['tgt_posintT', 'tgt_posintP']].values
            tgt_XY = np.array(
                [trans.posintTP_to_flatXY(tp) for tp in tgt_posintTP])
            data.loc[idx[:, :, posid], ['tgt_flatX', 'tgt_flatY']] = tgt_XY
            data.loc[idx[:, :, posid], ['tgt_Q', 'tgt_S']] = \
                trans.flatXY_to_QS(tgt_XY.T).T
            # measurement always in QS, but fit and derive params in flatXY
            # keep using existing calibration to do conversions
            # measured QS may have NaN values if missing, filter out
            QS = data.loc[idx[:, :, posid], ['mea_Q', 'mea_S']]  # Nx2
            mask = QS.notnull().all(axis=1)
            data.loc[QS[mask].index, ['mea_flatX', 'mea_flatY']] = (
                trans.QS_to_flatXY(QS[mask].T).T)  # doesn't depend on calib

            def fit_arc(arc):  # arc is 'T' or 'P', define a func to exit loop
                posmeaarc = (data.xs((arc, posid), level=('axis', 'DEVICE_ID'))
                             [['mea_flatX', 'mea_flatY']])
                # select valid (non-null) measurement data points only for fit
                # reduced to tables of length L and M
                posmea[arc] = posmeaarc[posmeaarc.notnull().all(axis=1)]
                if len(posmea[arc]) < 3:  # require at least 3 points remaining
                    return None
                ctr0 = ((state._val['OFFSET_X'], state._val['OFFSET_Y']) 
                        if arc == 'T' else None)  # initial guess for centre
                exp = 2 if arc == 'T' else 1
                return self.fit_circle(posmea[arc].values, ctr0=ctr0, exp=exp)

            fits = [fit_arc(arc) for arc in ['T', 'P']]
            if None in fits:
                self.logger.error(f'{posid} arc calibration failed, '
                                  f'at least 3 points required, skipping...',
                                  pcid=self.petal_locs[posid])
                poscals.append({})
                continue
            for i, arc in enumerate(['T', 'P']):  # loop over two arcs
                poscal[f'centre_{arc}'] = fits[i][0]
                poscal[f'radius_{arc}'] = fits[i][1]
                poscal[f'residuals_{arc}'] = fits[i][2]
                # data.loc[idx[arc, posmea[arc].index, posid],
                #          'err_radial'] = fits[i][2]
            poscal.update({'OFFSET_X': poscal['centre_T'][0],
                           'OFFSET_Y': poscal['centre_T'][1],
                           'LENGTH_R1': np.linalg.norm(poscal['centre_T']
                                                       - poscal['centre_P']),
                           'LENGTH_R2': poscal['radius_P'].mean()})
            if poscal['LENGTH_R1'] == 0 or poscal['LENGTH_R2'] == 0:
                poscals.append(poscal)  # the rest will only trigger warnings
                self.logger.error(
                    f'{posid}: trivial fitted armlength(s): '
                    f'R1 = {poscal["LENGTH_R1"]}, R2 = {poscal["LENGTH_R2"]}',
                    pcid=self.petal_locs[posid])
                continue
            # caluclate offset T using phi arc centre and target posintT
            xy = poscal['centre_P'] - poscal['centre_T']  # 1 x 2 array
            p_mea_poslocT = np.degrees(np.arctan2(xy[1], xy[0]))  # float
            t_tgt_posintT = data.loc[idx['T', posmea['T'].index, posid],
                                     'tgt_posintT']  # length L
            p_tgt_posintP = data.loc[idx['P', posmea['P'].index, posid],
                                     'tgt_posintP']  # length M
            # subtract constant target posintT of phi arc
            poscal['OFFSET_T'] = PosTransforms._centralize_angular_offset(
                p_mea_poslocT - p_tgt_posintP.values[0])
            # calculate offset P still using phi arc
            xy = posmea['P'].values - poscal['centre_P']  # phi arc wrt phi ctr
            angles = np.degrees(np.arctan2(xy[:, 1], xy[:, 0]))  # 1 x M array
            # subtract poslocT of phi arc to convert phi angles to poslocP
            # poslocP = 0 is parallel to T arm
            p_mea_poslocP = angles - p_mea_poslocT  # 1 x M array
            # choose angles in [0, 360) rather than [-180, 180)
            p_mea_poslocP[p_mea_poslocP < 0] += 360  # 1 x M array
            p_tgt_direction = np.sign(np.diff(p_tgt_posintP).mean())
            p_mea_poslocP_wrapped = PosTransforms._wrap_consecutive_angles(
                    p_mea_poslocP, p_tgt_direction)  # 1 x M array
            # take median difference between wrapped poslocP and
            # expected posintP, ideally these diffences are similar
            poscal['OFFSET_P'] = PosTransforms._centralize_angular_offset(
                np.median(p_mea_poslocP_wrapped - p_tgt_posintP))
            p_exp_posintP_wrapped = p_mea_poslocP_wrapped - poscal['OFFSET_P']
            data.loc[idx['P', posmea['P'].index, posid],
                     'exp_posintT'] = p_mea_poslocT - poscal['OFFSET_T']
            data.loc[idx['P', posmea['P'].index, posid],
                     'exp_posintP'] = p_exp_posintP_wrapped
            # done with phi arc, transform measured theta arc to posintTP
            trans.alt_override = True  # enable override in pos transforms
            trans.alt.update({key: poscal[key] for key in keys_fit})
            t_exp_posintTP = np.array([
                trans.flatXY_to_posintTP(flatXY, range_limits='full')[0]
                for flatXY in posmea['T'].values])  # L x 1 array
            t_tgt_direction = np.sign(np.diff(t_tgt_posintT).mean())
            t_exp_posintT_wrapped = PosTransforms._wrap_consecutive_angles(
                    t_exp_posintTP[:, 0], t_tgt_direction)  # length L
            data.loc[idx['T', posmea['T'].index, posid],
                     'exp_posintT'] = t_exp_posintT_wrapped
            data.loc[idx['T', posmea['T'].index, posid],
                     'exp_posintP'] = t_exp_posintTP[:, 1].mean()
            # convert target coordinates using existing calibration
            # these are meant to be equivalent to posintTP issued at the time
            tgt_posintTP = data.loc[idx[:, :, posid],
                                    ['tgt_posintT', 'tgt_posintP']].values
            exp_XY = np.array(
                [trans.posintTP_to_flatXY(tp) for tp in tgt_posintTP])
            data.loc[idx[:, :, posid], ['exp_flatX', 'exp_flatY']] = exp_XY
            data.loc[idx[:, :, posid], ['exp_Q', 'exp_S']] = \
                trans.flatXY_to_QS(exp_XY.T).T
            trans.alt_override = False  # disable override in pos transforms
            # gear ratios, good feedback on how successful the calib was
            poscal['GEAR_CALIB_T'] = ratio_T = np.median(
                np.diff(t_exp_posintT_wrapped) / np.diff(t_tgt_posintT))
            poscal['GEAR_CALIB_P'] = ratio_P = np.median(
                np.diff(p_exp_posintP_wrapped) / np.diff(p_tgt_posintP))
            for c in ['flatX', 'flatY', 'Q', 'S']:  # calculate errors
                data[f'err_{c}'] = data[f'exp_{c}'] - data[f'mea_{c}']
            for c in ['posintT', 'posintP']:  # calculate errors
                data[f'err_{c}'] = data[f'exp_{c}'] - data[f'tgt_{c}']
            poscals.append(poscal)
            for ratio, arc in zip([ratio_T, ratio_P], ['T', 'P']):
                if abs(ratio - 1) > 0.3:  # print a warning
                    self.logger.warning(
                        f'{posid}: GEAR_CALIB_{arc} = {ratio:.6f}',
                        pcid=self.petal_locs[posid])
        return data, pd.DataFrame(poscals, index=posids)

    def calibrate_from_grid_data(self, data):
        """
        input data is a pd dataframe containing targets and FVC measurements
        for all petals with
            index:      (target_no, DEVICE_ID)
            columns:    PETAL_LOC, DEVICE_LOC, BUS_ID,
                        tgt_posintT, tgt_posintP, mea_Q, mea_S, FLAG, STATUS

        For each positioner, calculate measured flatXY, and fit it with float
        tgt_posintTP -> tgt_flatXY. From the fit we get 6 calibration params
        all at the same time, the residuals, and the fitted, expected posintTP

        return input dataframe with columns added:
            tgt_flatXY, tgt_QS (directly from tgt_posintTP)
            mea_flatXY (measurements directly from mea_QS)
            exp_flatXY, exp_QS, exp_posintTP (fitted expectation)
            err_flatXY, err_QS  (fitted expectation - measured)
            err_posintTP (fitted expectation - target)

        and a calibration dataframe with
            index:  DEVICE_ID
            column: 'OFFSET_T', 'OFFSET_P', 'OFFSET_X', 'OFFSET_Y',
                    'LENGTH_R1', 'LENGTH_R2'
        """
        posids = data.index.get_level_values('DEVICE_ID').unique()
        self.logger.debug(f'Analysing grid calibration measurement data...')
        self.init_posmodels(posids=posids)  # double check all posmodels exist
        cols = ['tgt_flatX', 'tgt_flatY', 'tgt_Q', 'tgt_S',
                'mea_flatX', 'mea_flatY', 'exp_posintT', 'exp_posintP',
                'exp_flatX', 'exp_flatY', 'exp_Q', 'exp_S']
        for col in cols:  # add new empty columns to grid data dataframe
            data[col] = np.nan
        p0 = [PosTransforms.alt[key] for key in keys_fit]
        poscals = []  # each entry is a row of calibration for one posid
        self.logger.debug(f'Fitting loop for {len(posids)} positioners...')
        for posid in tqdm(posids):
            trans = self.posmodels[posid].trans
            tgt_posintTP = data.loc[idx[:, :, posid],
                                    ['tgt_posintT', 'tgt_posintP']].values
            tgt_XY = np.array(
                [trans.posintTP_to_flatXY(tp) for tp in tgt_posintTP])
            data.loc[idx[:, :, posid], ['tgt_flatX', 'tgt_flatY']] = tgt_XY
            data.loc[idx[:, :, posid], ['tgt_Q', 'tgt_S']] = \
                trans.flatXY_to_QS(tgt_XY.T).T
            # measurement always in QS, but fit and derive params in flatXY
            QS = data.loc[idx[:, posid], ['mea_Q', 'mea_S']]  # Nx2
            mask = QS.notnull().all(axis=1)
            data.loc[QS[mask].index, ['mea_flatX', 'mea_flatY']] = (
                trans.QS_to_flatXY(QS[mask].T).T)  # doesn't depend on calib
            # select only valid measurement data points for fit
            posdata = data.xs(posid, level='DEVICE_ID')[[
                'mea_flatX', 'mea_flatY', 'tgt_posintT', 'tgt_posintP']]
            mask = posdata.index[~posdata.isnull().any(axis=1)]
            posdata = posdata.loc[mask]  # filter nan
            if len(posdata) <= len(keys_fit):
                self.logger.error(f'{posid} calibration failed: '
                                  f'only {len(posdata)} valid grid points',
                                  pcid=self.petal_locs[posid])
                poscals.append({})
                continue  # skip this iteration for this posid in the loop
            mea_flatXY = posdata[['mea_flatX', 'mea_flatY']].values  # N x 2
            tgt_posintTP = posdata[['tgt_posintT', 'tgt_posintP']].values

            def exp_xy(params):
                for key, param in zip(keys_fit, params):
                    trans.alt[key] = param  # override transformation params
                flatXY = [trans.posintTP_to_flatXY(tp) for tp in tgt_posintTP]
                return np.array(flatXY)  # N x 2, target posintTP transformed

            def err_rms(params):  # function to be minimised
                err = exp_xy(params) - mea_flatXY  # N x 2
                return np.linalg.norm(err) / np.sqrt(err.shape[0])

            trans.alt_override = True  # enable override in pos transforms
            # Ranges which values should be in
            bounds = ((0, 500), (0, 400),  # offsetsXY
                      (-180, 180), (-50, 50),  # offsetsTP
                      (2.5, 3.5), (2.5, 3.5))  # R1, R2
            result = optimize.minimize(fun=err_rms, x0=p0, bounds=bounds)
            # centralize offsetsTP (why needed if we can limit to +/-180?)
            # for i, param_key in enumerate(keys_fit):
            #     if param_key in ['OFFSET_T', 'OFFSET_P']:
            #         result.x[i] = (
            #             PosTransforms._centralized_angular_offset_value(
            #                 res.x[i]))
            poscal = {key: result.x[i] for i, key in enumerate(keys_fit)}
            exp_XY = exp_xy(result.x)  # expected XY using fitteds results
            data.loc[idx[mask, posid], ['exp_flatX', 'exp_flatY']] = exp_XY
            data.loc[idx[mask, posid], ['exp_Q', 'exp_S']] = \
                trans.flatXY_to_QS(exp_XY.T).T
            data.loc[idx[mask, posid], ['exp_posintT', 'exp_posintT']] = \
                np.array([trans.flatXY_to_posintTP(xy)[1] for xy in exp_XY])
            trans.alt_override = False  # turn it back off when finished
            for c in ['flatX', 'flatY', 'Q', 'S']:  # calculate errors
                data[f'err_{c}'] = data[f'exp_{c}'] - data[f'mea_{c}']
            for c in ['posintT', 'posintP']:  # calculate errors
                data[f'err_{c}'] = data[f'exp_{c}'] - data[f'tgt_{c}']
            poscals.append(poscal)
            if result.fun > 0.4:  # print a warning
                self.logger.warning(f'{posid} grid calibration, {len(posdata)}'
                                    f' points, err_rms = {result.fun:.3f}',
                                    pcid=self.petal_locs[posid])
        return data, pd.DataFrame(poscals,
                                  index=pd.Series(posids, name='DEVICE_ID'))


if __name__ == '__main__':
    # sample calibration data
    # df = pd.DataFrame(np.array([[9, -170, 150, 300, 30]]*3),
    #                   index=['M00001', 'M00002', 'M00003'],
    #                   columns=['PETAL_LOC', 'tgt_posintT', 'tgt_posintP',
    #                            'mea_Q', 'mea_S'])
    # df['DEVICE_LOC'] = [78, 324, 517]
    # data_grid = pd.concat([df]*10, keys=range(10),
    #                       names=['target_no', 'DEVICE_ID'])  # grid
    # arc = pd.concat([df]*6, keys=range(10))  # one arc
    # data_arc = pd.concat([arc, arc], keys=['T', 'P'],
    #                      names=['axis', 'target_no', 'DEVICE_ID'])
    # posdata = data_grid.loc[idx[:, 'M00001'], :]
    # posdata = data_arc.loc[idx['T', :, 'M00001'], :]

    # redo calibration by fitting measured data only
    path = "/data/focalplane/logs/kpno/20200203/00046362-arc_calibration-754_previously_disabled/data_arc.pkl.gz"
    measured = pd.read_pickle(path)
    calib = PosCalibrationFits(use_doslib=True)
    movedf, calibdf = calib.calibrate_from_arc_data(measured)
    movedf.to_pickle(os.path.join(os.path.dirname(path), "movedf.pkl.gz"))
    calibdf.to_pickle(os.path.join(os.path.dirname(path), "calibdf_new.pkl.gz"))

    # redo calibration by loading CalibrationData and generate new products
    # expids = [46362]  # redo fit
    # for expid in expids:
    #     paths = glob(pc.dirs['kpno']+f'/*/{expid:08}*/*data.pkl')
    #     assert len(paths) == 1, paths
    #     path = paths[0]
    #     print(f'Re-processing FP test data:\n{path}')
    #     # with open(os.path.join(paths[0]), 'rb') as h:
    #     #     data = pickle.load(h)
    #     # path = glob(pc.dirs['kpno']+f'/*/{expid:08}*/*data_*.pkl.gz')[0]
    #     # measured = pd.read_pickle(path)
    #     calib_type = data.mode.replace('_calibration', '')
    #     measured = data.data_arc if calib_type == 'arc' else data.data_grid
    #     fit = PosCalibrationFits(use_doslib=True)
    #     data.movedf, data.calib_fit = getattr(
    #         fit, f'calibrate_from_{calib_type}_data')(measured)
    #     data.write_calibdf(data.calib_old, data.calib_fit)
    #     data.generate_data_products()
