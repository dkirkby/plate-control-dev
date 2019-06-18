# -*- coding: utf-8 -*-
"""
Created on Thu May 23 22:18:28 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Store xy test, anti-collision data in a class for debugging.
Most fields are dictionaries indexed by petal id:

FPTestData.petal_cfgs[petal_id]:    hw setup file for each petal
FPTestData.logs[petal_id]:          StringIO object equivalent to log file
FPTestData.loggers[petal_id]:       logger which writes new lines to log file

"""
import os
import logging
from itertools import product
from datetime import datetime, timezone
from io import StringIO
from shutil import copyfileobj
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
# from posschedstats import PosSchedStats
import posconstants as pc

idx = pd.IndexSlice
plt.rcParams.update({'font.family': 'serif',
                     'mathtext.fontset': 'cm'})
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))


class FPTestData:
    ''' data will be saved in:
            /xytest_data/{time}-{test_name}/PTL{ptlid}/*.*
    '''

    timefmt = '%Y-%m-%dT%H:%M:%S%z'
    timefmtpath = '%Y_%m_%d-%H_%M_%S%z'
    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
        datefmt=timefmt)

    @property  # calling self.now returns properly formatted current timestamp
    def now(self): return datetime.now(timezone.utc).astimezone()

    def __init__(self, test_name, test_cfg, petal_cfgs=None):

        self.test_name = test_name
        self.test_time = self.now
        self.test_cfg = test_cfg
        self.simulate = test_cfg['simulate']
        self.anticollision = test_cfg['anticollision']
        self.num_corr_max = self.data.test_cfg['num_corr_max']
        self.petal_cfgs = petal_cfgs
        self.ptlids = [
            key for key in test_cfg.keys() if len(key) == 2
            and key.isdigit() and (test_cfg[key]['mode'] is not None)]
        # create save dir for all files: logs, tables, pickels, gzips
        self.dir = os.path.join(
            pc.dirs['xytest_data'],
            f"{self.test_time.strftime(self.timefmtpath)}-{test_name}")
        self.dirs = {ptlid: os.path.join(self.dir, f'PTL{ptlid}')
                     for ptlid in self.ptlids}
        self.logs = {}  # set up log files and loggers for each petal
        self.log_paths = {}
        self.loggers = {}
        for ptlid in self.ptlids:
            self.log_paths[ptlid] = os.path.join(self.dirs[ptlid],
                                                 f'ptl_{ptlid}_realtime.log')
            # create virtual file object for storing log entries
            # using stringio because it supports write() and flush()
            log = StringIO(newline='\n')
            # craete a new logger for each petal by unique logger name
            logger = logging.getLogger(f'PTL_{ptlid}')
            logger.handlers = []  # clear handlers that might exisit already
            logger.setLevel(logging.DEBUG)  # log everything, DEBUG level up
            fh = logging.FileHandler(self.log_paths[ptlid],
                                     mode='a', encoding='utf-8')
            sh = logging.StreamHandler(stream=log)  # pseudo-file handler
            ch = logging.StreamHandler()  # console handler, higher log level
            ch.setLevel(logging.INFO)  # only stdout INFO or more severe logs
            fh.setFormatter(self.log_formatter)
            sh.setFormatter(self.log_formatter)
            ch.setFormatter(self.log_formatter)
            logger.addHandler(fh)
            logger.addHandler(sh)
            logger.addHandler(ch)
            logger.info(f'Log initialised for test {test_name}, PTL_{ptlid}')
            # write configs to logs
            if petal_cfgs is not None:
                self._log_cfg(logger, petal_cfgs[ptlid])
            self._log_cfg(logger, test_cfg)
            self.logs[ptlid] = log  # assign logs and loggers to attributes
            self.loggers[ptlid] = logger
        self.logger.info([f'petalconstants.py version: {pc.code_version}',
                          f'Saving to directory: {self.dir}',
                          f'Simulation mode enabled: {self.simulate}'])
        self.movedata = {}  # keyed by posid, one table for each positioner

    @staticmethod
    def _log_cfg(logger, config):
        '''ConfigObj module has an outstanding bug that hasn't been fixed.
        It can only write to real files and not in-memory virtual viles,
        such as StringIO objects, although its documentation claims support.
        We have to write to memory by lines here.
        '''
        logger.debug(f'=== Config file dump: {config.filename} ===')
        for line in config.write(outfile=None):
            logger.debug(line)
        logger.debug(f'=== Config file dump complete: {config.filename} ===')

    def logger(self):
        '''must call methods for particular logger levels below
        input message can be a string of list of strings
        msg will be broadcasted to all petals
        '''
        def _log(self, lvl, msg):
            if type(msg) is list:
                map(_log, msg)
            elif type(msg) is str:
                for ptlid in self.ptlids:
                    self.loggers[ptlid].log(lvl, msg)
            else:
                raise Exception('Wrong logger message type')

        def critical(self, msg):
            _log(50, msg)

        def error(self, msg):
            _log(40, msg)

        def warning(self, msg):
            _log(30, msg)

        def info(self, msg):
            _log(20, msg)

        def debug(self, msg):
            _log(10, msg)

    def initialise_movedata(self, posids, n_targets):
        '''initialise column names for move data table for each positioner
        existing attributes required (see xytest.py):
            self.ptlids
        '''
        # build column names and data types
        cols0 = ['timestamp', 'cycle', 'move_log']
        dtypes0 = ['datetime64[ns]', np.uint32, str]
        cols1 = ['target_x', 'target_y']
        cols2_base = ['meas_x', 'meas_y', 'err_x', 'err_y', 'err_xy',
                      'pos_t', 'pos_p']
        cols2 = []
        for field, i in product(cols2_base, range(self.num_corr_max+1)):
            cols2.append(f'{field}_{i}')
        cols = cols0 + cols1 + cols2
        dtypes = dtypes0 + [np.float32] * (len(cols1) + len(cols2))
        data = {col: pd.Series(dtype=dt) for col, dt in zip(cols, dtypes)}
        # build multi-level index
        iterables = [np.arange(self.ntargets), posids]
        names = ['target_no', 'posid']
        index = pd.MultiIndex.from_product(iterables, names=names)
        self.movedf = pd.DataFrame(data=data, index=index)

    def make_summary_plot(self, posid):
        row = self.posdf.loc[posid]  # row containing calibration values
        ptlid, offX, offY, r1, r2 = \
            row[['ptlid', 'OFFSET_X', 'OFFSET_Y', 'LENGTH_R1', 'LENGTH_R2']]
        rmin, rmax = r1 - r1, r1 + r2  # min and max patrol radii
        posT = np.sort(row[['targetable_range_T_0', 'targetable_range_T_1']])
        Tmin, Tmax = posT + row['OFFSET_T']  # min and max targetable obsTheta
        path = os.path.join(self.dirs[ptlid],
                            '{}_xyplot_submove_{{}}.pdf'.format(posid))
        title = (f'XY Accuracy Test {self.now}\n'  # shared by submove plots
                 f'Positioner {posid} ({self.ntargets} targets)')
        moves = self.movedf.loc[idx[:, posid]]  # all targets for a posid
        tgtX, tgtY = moves['target_x'], moves['target_y']  # target obsXY
        Tmin_line_x = [offX, offX + rmax * np.cos(np.radians(Tmin))]
        Tmin_line_y = [offY, offY + rmax * np.sin(np.radians(Tmin))]
        Tmax_line_x = [offX, offX + rmax * np.cos(np.radians(Tmax))]
        Tmax_line_y = [offY, offY + rmax * np.sin(np.radians(Tmax))]
        # make one plot for each submove
        for n in range(self.num_corr_max+1):  # one plot for each submove
            fig, ax = plt.subplots(figsize=(10, 8))
            ax.plot(Tmin_line_x, Tmin_line_y, '-', lw=0.5, color='C2',
                    label=r'$\theta_\mathrm{min}$')  # theta min line
            ax.plot(Tmax_line_x, Tmax_line_y, '--', lw=0.8, color='C2',
                    label=r'$\theta_\mathrm{max}$')  # theta max line
            for r in [rmin, rmax]:  # inner and outer patrol circles
                c = Circle((offX, offY), r, lw=0.5, color='C0', fill=False)
                ax.add_patch(c)
            ax.plot(tgtX, tgtY, 'o', ms=4, color='C3', fillstyle='none',
                    label=r'target $(x, y)$')  # circles for all target points
            meaX, meaY = moves[f'meas_x_{n}'], moves[f'meas_y_{n}']
            ax.plot(meaX, meaY, '+', ms=6, mew=1, color='k',
                    label=r'measured $(x, y)$')  # measured xy for nth move
            errXY = moves[f'err_xy_{n}'] * 1000  # convert mm to microns
            u = r'$\mathrm{\mu m}$'
            text = (f'SUBMOVE: {n} {u}\n',  # text box for submove errors
                    f'error max: {np.max(errXY): 6.1f} {u}\n'
                    f'      rms: {np.max(errXY): 6.1f} {u}\n'
                    f'      avg: {np.rms(errXY): 6.1f} {u}\n'
                    f'      min: {np.min(errXY): 6.1f} {u}')
            ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=10,
                    horizontalalignment='left', verticalalignment='top',
                    bbox={'boxstyle': 'square', 'alpha': 0.8})
            ax.grid(True)
            ax.set_aspect('equal')
            ax.set_title(title)
            ax.set_xlabel(r'$x/\mathrm{mm}$')
            ax.set_ylabel(r'$y/\mathrm{mm}$')
            ax.legend(loc='upper right', fontsize=8)
            fig.savefig(path.format(n), bbox_inches='tight')
            self.loggers[ptlid].info(f'saved xyplot: {path.format(n)}')

    def export_move_data(self):
        '''must have writte self.posids_ptl, a dict keyed by ptlid'''
        self.movedf.to_pickle(os.path.join(self.dir, 'move_df.pkl'),
                              compression='gzip')
        self.logger.info(f'Focal plane move data written to: {self.dir}.')
        self.movedf.to_csv(os.path.join(self.dir, 'move_df.csv'))
        for ptlid in self.ptlids:
            os.makedirs(self.dirs[ptlid], exist_ok=True)
            def makepath(name): return os.path.join(self.dirs[ptlid], name)
            for posid in self.posids_ptl[ptlid]:  # write move data csv
                df_pos = self.movedf.loc[idx[:, posid], :].droplevel(1)
                df_pos.to_pickle(makepath(f'{posid}_df.pkl'),
                                 compression='gzip')
                df_pos.to_csv(makepath(f'{posid}_df.csv'))
            with open(makepath(f'ptl_{ptlid}_export.log'), 'w') as handle:
                self.logs[ptlid].seek(0)
                copyfileobj(self.logs[ptlid], handle)  # write final logs
            self.loggers[ptlid].info('Petal move data written to: '
                                     f'{self.dirs[ptlid]}')

    def dump_as_one_pickle(self):
        with open(os.path.join(self.dir, 'data_dump.pkl'), 'wb') as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)
