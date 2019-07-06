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
from copy import copy
import logging
from glob import glob
from itertools import product
from functools import partial
from datetime import datetime, timezone
from multiprocessing import Process
from tqdm import tqdm
from io import StringIO
from shutil import copyfileobj
import tarfile
import pickle
import numpy as np
import pandas as pd
from PyPDF2 import PdfFileMerger
import posconstants as pc
import matplotlib
matplotlib.use('pdf')
plt = matplotlib.pyplot
plt.rcParams.update({'font.family': 'serif',
                     'mathtext.fontset': 'cm'})
Circle = matplotlib.patches.Circle
idx = pd.IndexSlice
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
        self.test_cfg = test_cfg  # petal id sections are string ids
        self.anticollision = test_cfg['anticollision']
        self.num_corr_max = self.test_cfg['num_corr_max']
        self.petal_cfgs = petal_cfgs
        self.ptlids = [  # validate string petal id sections and create list
            int(key) for key in test_cfg.keys() if len(key) == 2
            and key.isdigit() and (test_cfg[key]['mode'] is not None)]
        for ptlid in self.test_cfg.sections:  # convert petal id to int now
            self.test_cfg.rename(ptlid, int(ptlid))
        # create save dir for all files: logs, tables, pickels, gzips
        self.dir = os.path.join(
            pc.dirs['xytest_data'],
            f'{self.test_time.strftime(self.timefmtpath)}-{test_name}')
        self.dirs = {ptlid: os.path.join(self.dir, f'PTL{ptlid}')
                     for ptlid in self.ptlids}
        self.logs = {}  # set up log files and loggers for each petal
        self.log_paths = {}
        self.loggers = {}
        for ptlid in self.ptlids:
            self.log_paths[ptlid] = os.path.join(self.dirs[ptlid],
                                                 f'ptl_{ptlid}_realtime.log')
            # ensure save directory and log file exist if they don't already
            os.makedirs(self.dirs[ptlid], exist_ok=True)
            open(self.log_paths[ptlid], 'a').close()
            # create virtual file object for storing log entries
            # using stringio because it supports write() and flush()
            log = StringIO(newline='\n')
            # craete a new logger for each petal by unique logger name
            logger = logging.getLogger(f'PTL{ptlid}')
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
            logger.info(f'Log initialised for test: {test_name}, '
                        f'PTL{ptlid:02d}')
            # write configs to logs
            if petal_cfgs is not None:  # dump petal cfg to petal logger
                self._log_cfg(logger, petal_cfgs[ptlid])
            self._log_cfg(logger, test_cfg)
            self.logs[ptlid] = log  # assign logs and loggers to attributes
            self.loggers[ptlid] = logger
        self.logger = self.BroadcastLogger(self.ptlids, self.loggers)
        self.logger.info([f'petalconstants.py version: {pc.code_version}',
                          f'Saving to directory: {self.dir}',
                          f'Anticollision mode: {self.anticollision}'])

    @staticmethod
    def _log_cfg(logger, config):
        '''ConfigObj module has an outstanding bug that hasn't been fixed.
        It can only write to real files and not in-memory virtual viles
        that are newer io.StringIO objects.
        it also only writes bytes (binary b strings), not unicode strings.
        a log file needs a unicode stream that is io.StringIO.
        so we have to write by lines here to extract each line as text.
        also loggers only accept one line of string at a time.
        note ConfigObj.write() only spits out strings when filename is None
        '''
        logger.debug(f'=== Config file dump: {config.filename} ===')
        configcopy = copy(config)
        configcopy.filename = None
        for line in configcopy.write():
            logger.debug(line.decode('utf_8'))  # convert byte str to str
        logger.debug(f'=== End of config file dump: {config.filename} ===')

    class BroadcastLogger:
        # TODO: convert this to a class method?
        '''must call methods below for particular logger levels below
        input message can be a string of list of strings
        msg will be broadcasted to all petals
        '''
        def __init__(self, ptlids, loggers):
            self.ptlids = ptlids
            self.loggers = loggers

        def _log(self, msg, lvl):  # reserved for in-class use, don't call this
            if type(msg) is list:
                list(map(partial(self._log, lvl=lvl), msg))
            elif type(msg) is str:
                for ptlid in self.ptlids:
                    self.loggers[ptlid].log(lvl, msg)
            else:
                raise Exception('Wrong message data type sent to logger')

        def critical(self, msg):
            self._log(msg, 50)

        def error(self, msg):
            self._log(msg, 40)

        def warning(self, msg):
            self._log(msg, 30)

        def info(self, msg):
            self._log(msg, 20)

        def debug(self, msg):
            self._log(msg, 10)

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
                      'pos_t', 'pos_p', 'pos_bit', 'pos_flag']
        cols2 = []
        for field, i in product(cols2_base, range(self.num_corr_max+1)):
            cols2.append(f'{field}_{i}')
        cols = cols0 + cols1 + cols2
        dtypes = dtypes0 + [np.float32] * (len(cols1) + len(cols2))
        data = {col: pd.Series(dtype=dt) for col, dt in zip(cols, dtypes)}
        # build multi-level index
        iterables = [np.arange(self.ntargets), posids]
        names = ['target_no', 'DEVICE_ID']
        index = pd.MultiIndex.from_product(iterables, names=names)
        self.movedf = pd.DataFrame(data=data, index=index)
        # write ptlid column to movedf
        self.movedf = self.movedf.merge(self.posdf['PETAL_ID'].reset_index(),
                                        on='DEVICE_ID', right_index=True)
        self.logger.info(f'Move data table initialised '
                         f'for {len(self.posids)} positioners.')

    def make_summary_plots(self):  # make plots using MP
        self.logger.info('Making xyplots with multiprocessing...')
        for posid in tqdm(self.posids):
            p = Process(target=self.make_summary_plot, args=(posid,))
            p.start()
        self.logger.info('Waiting for the last MP chunk to complete...')
        p.join()
        self.make_summary_plot_binder()

    def make_summary_plot(self, posid):  # make one plot for a given posid
        row = self.posdf.loc[posid]  # row containing calibration values
        ptlid, offX, offY, r1, r2, posT = row[
            ['PETAL_ID', 'OFFSET_X', 'OFFSET_Y', 'LENGTH_R1', 'LENGTH_R2',
             'targetable_range_T']]
        rmin, rmax = r1 - r2, r1 + r2  # min and max patrol radii
        Tmin, Tmax = np.sort(posT) + row['OFFSET_T']  # targetable obsTheta
        path = os.path.join(self.dirs[ptlid],
                            '{}_xyplot_submove_{{}}.pdf'.format(posid))
        title = (f'XY Accuracy Test {self.test_time}\n'
                 f'Positioner {posid} ({self.ntargets} Targets)')
        moves = self.movedf.loc[idx[:, posid], :]  # all targets for a posid
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
                c = Circle((offX, offY), r, lw=0.5, color='b', fill=False)
                ax.add_patch(c)
            ax.plot(tgtX, tgtY, 'o', ms=4, color='C3', fillstyle='none',
                    label=r'target $(x, y)$')  # circles for all target points
            meaX, meaY = moves[f'meas_x_{n}'], moves[f'meas_y_{n}']
            ax.plot(meaX, meaY, '+', ms=6, mew=1, color='k',
                    label=r'measured $(x, y)$')  # measured xy for nth move
            errXY = moves[f'err_xy_{n}'] * 1000  # convert mm to microns
            for i in range(len(tgtX)):
                ax.annotate(f'{i+1}', xy=(tgtX[i]-0.2, tgtY[i]), color='C3',
                            size=6, horizontalalignment='right')
                ax.annotate(f'{i+1}', xy=(meaX[i]+0.2, meaY[i]), color='k',
                            size=6, horizontalalignment='left')
            u = r'$\mathrm{\mu m}$'
            text = (f'SUBMOVE: {n}\n'  # text box for submove errors
                    f'error max: {np.max(errXY):6.1f} {u}\n'
                    f'      rms: {np.rms(errXY):6.1f} {u}\n'
                    f'      avg: {np.mean(errXY):6.1f} {u}\n'
                    f'      min: {np.min(errXY):6.1f} {u}')
            ax.text(0.02, 0.98, text, transform=ax.transAxes,
                    horizontalalignment='left', verticalalignment='top',
                    family='monospace', fontsize=10,
                    bbox={'boxstyle': 'round', 'alpha': 0.8,
                          'facecolor': 'white', 'edgecolor': 'lightgrey'})
            ax.grid(linestyle='--')
            ax.set_aspect('equal')
            ax.set_title(title)
            ax.set_xlabel(r'$x/\mathrm{mm}$')
            ax.set_ylabel(r'$y/\mathrm{mm}$')
            ax.legend(loc='upper right', fontsize=10)
            fig.savefig(path.format(n), bbox_inches='tight')
            self.loggers[ptlid].debug(f'saved xyplot: {path.format(n)}')
            plt.close(fig)

    def make_summary_plot_binder(self):
        for ptlid in self.ptlids:
            self.loggers[ptlid].info(f'Creating xyplot binders...')
            for n in range(self.num_corr_max+1):
                template = os.path.join(self.dirs[ptlid],
                                        f'*_xyplot_submove_{n}.pdf')
                paths = glob(template)
                assert len(paths) == len(self.posids_ptl[ptlid]), (
                        f'Length mismatch: {len(paths)} ≠ '
                        f'{len(self.posids_ptl[ptlid])}')
                binder = PdfFileMerger()
                for path in paths:
                    binder.append(path)
                savepath = os.path.join(self.dirs[ptlid],
                                        f'{len(paths)}_xyplot_submove_{n}.pdf')
                binder.write(savepath)
                binder.close()
                self.loggers[ptlid].info(
                    f'Binder for submove {n} saved to: {savepath}')

    def export_move_data(self):
        '''must have writte self.posids_ptl, a dict keyed by ptlid'''
        self.movedf.to_pickle(os.path.join(self.dir, 'move_df.pkl'),
                              compression='gzip')
        self.logger.info(f'Focal plane move data written to: {self.dir}')
        self.movedf.to_csv(os.path.join(self.dir, 'move_df.csv'))
        for ptlid in self.ptlids:
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

    def make_archive(self):
        path = os.path.join(self.dir, f'{os.path.basename(self.dir)}.tgz')
        with tarfile.open(path, 'w:gz') as tar:
            tar.add(self.dir, arcname=f'{os.path.basename(self.dir)}.tar')
        self.logger.info(f'Test data archived: {path}')

    def dump_as_one_pickle(self):
        '''lod the dumped pickle file as follows, protocol is auto determined
        import pickle
        with open(path, 'rb') as handle:
            data = pickle.load(handle)
        '''
        del self.logger
        del self.loggers
        with open(os.path.join(self.dir, 'data_dump.pkl'), 'wb') as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def save_test_products(self):
        self.export_move_data()
        if self.test_cfg['make_plots']:
            self.make_summary_plots()  # plot for all positioners by default
        self.make_archive()
        self.dump_as_one_pickle()
