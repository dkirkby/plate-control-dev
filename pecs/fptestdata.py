# -*- coding: utf-8 -*-
"""
Created on Thu May 23 22:18:28 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Store xy test, anti-collision data in a class for debugging.
Most fields are dictionaries indexed by petal id:

FPTestData.petal_cfgs[pcid]:    hw setup file for each petal
FPTestData.logs[pcid]:          StringIO object equivalent to log file
FPTestData.loggers[pcid]:       logger which writes new lines to log file

"""

import os
# import sys
from copy import copy
import logging
from glob import glob
from itertools import product
from functools import partial
import multiprocessing
from multiprocessing import Process  # Pool
from tqdm import tqdm
import io
import shutil
import subprocess
import tarfile
import pickle
from datetime import timezone
import numpy as np
import pandas as pd
import posconstants as pc
from PyPDF2 import PdfFileMerger
import psycopg2
import matplotlib
# matplotlib.use('pdf')
import matplotlib.pyplot as plt
# plt.ioff()  # turn off interactive mode, doesn't work in matplotlib2
plt.rcParams.update({'font.family': 'serif',
                     'mathtext.fontset': 'cm'})
Circle = matplotlib.patches.Circle
idx = pd.IndexSlice
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))
# sys.path.append(os.path.abspath('.'))


class FPTestData:
    ''' data will be saved in:
            /xytest_data/{time}-{test_name}/PC{pcid}/*.*
    '''

    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
        datefmt=pc.timestamp_format)

    def __init__(self, test_name, test_cfg, petal_cfgs=None):

        self.test_name = test_name
        self.start_time = pc.now()
        self.test_cfg = test_cfg  # pcid sections are string ids
        self.anticollision = test_cfg['anticollision']
        self.num_corr_max = test_cfg['num_corr_max']
        self.petal_cfgs = petal_cfgs
        self.pcids = [  # validate string pcid sections and create list
            int(key) for key in test_cfg.keys() if len(key) == 2
            and key.isdigit() and (test_cfg[key]['mode'] is not None)]
        for pcid in self.test_cfg.sections:  # convert pcid to int now
            self.test_cfg.rename(pcid, int(pcid))
        # create save dir for all files: logs, tables, pickels, gzips
        self.dir_name = f'{pc.filename_timestamp_str_now()}-{test_name}'
        self.dir = os.path.join(pc.dirs['xytest_data'], self.dir_name)
        self.dirs = {pcid: os.path.join(self.dir, f'pc{pcid:02}')
                     for pcid in self.pcids}
        self._init_loggers()
        self.logger.info([f'petalconstants.py version: {pc.code_version}',
                          f'Saving to directory: {self.dir}',
                          f'Anticollision mode: {self.anticollision}'])

    def _init_loggers(self):
        self.logs = {}  # set up log files and loggers for each petal
        self.log_paths = {}
        self.loggers = {}
        for pcid in self.pcids:
            self.log_paths[pcid] = os.path.join(self.dirs[pcid],
                                                f'pc{pcid:02}_realtime.log')
            # ensure save directory and log file exist if they don't already
            os.makedirs(self.dirs[pcid], exist_ok=True)
            open(self.log_paths[pcid], 'a').close()
            # create virtual file object for storing log entries
            # using stringio because it supports write() and flush()
            log = io.StringIO(newline='\n')
            # craete a new logger for each petal by unique logger name
            logger = logging.getLogger(f'PC{pcid:02}')
            logger.handlers = []  # clear handlers that might exisit already
            logger.setLevel(logging.DEBUG)  # log everything, DEBUG level up
            fh = logging.FileHandler(self.log_paths[pcid],
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
            logger.info(f'Logger initialised for test: {self.test_name}, '
                        f'petal: PC{pcid:02d}')
            # write configs to logs
            if self.petal_cfgs is not None:  # dump petal cfg to petal logger
                self._log_cfg(logger.debug, self.petal_cfgs[pcid])
            self._log_cfg(logger.debug, self.test_cfg)
            self.logs[pcid] = log  # assign logs and loggers to attributes
            self.loggers[pcid] = logger
        self.logger = self.BroadcastLogger(self.pcids, self.loggers)

    @staticmethod
    def _log_cfg(printfunc, config):
        '''ConfigObj module has an outstanding bug that hasn't been fixed.
        It can only write to real files and not in-memory virtual viles
        that are newer io.StringIO objects.
        it also only writes bytes (binary b strings), not unicode strings.
        a log file needs a unicode stream that is io.StringIO.
        so we have to write by lines here to extract each line as text.
        also loggers only accept one line of string at a time.
        note ConfigObj.write() only spits out strings when filename is None
        '''
        configcopy = copy(config)
        configcopy.filename = None
        printfunc(f'=== Config file dump: {config.filename} ===')
        for line in configcopy.write():
            printfunc(line.decode('utf_8'))  # convert byte str to str
        printfunc(f'=== End of config file dump: {config.filename} ===')

    class BroadcastLogger:
        '''must call methods below for particular logger levels below
        input message can be a string of list of strings
        msg will be broadcasted to all petals
        '''
        def __init__(self, pcids, loggers):
            self.pcids = pcids
            self.loggers = loggers

        def _log(self, msg, lvl):  # reserved for in-class use, don't call this
            if type(msg) is list:
                list(map(partial(self._log, lvl=lvl), msg))
            elif type(msg) is str:
                for pcid in self.pcids:
                    self.loggers[pcid].log(lvl, msg)
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
            self.pcids
        '''
        # build column names and data types, all in petal-local flatXY CS
        cols0 = ['timestamp', 'cycle', 'move_log']
        dtypes0 = ['datetime64[ns]', np.uint64, str]
        cols1 = ['target_x', 'target_y']
        dtypes1 = [np.float64] * len(cols1)
        cols2_base = ['meas_q', 'meas_s', 'meas_x', 'meas_y',
                      'err_x', 'err_y', 'err_xy',
                      'pos_int_t', 'pos_int_p', 'pos_flag', 'pos_status']
        cols2 = []  # add suffix for base column names corrective moves
        for field, i in product(cols2_base, range(self.num_corr_max+1)):
            cols2.append(f'{field}_{i}')
        cols = cols0 + cols1 + cols2  # list of all columns
        dtypes2 = [np.float64] * (len(cols2) - 2) + [np.int64, str]
        dtypes = dtypes0 + dtypes1 + dtypes2
        data = {col: pd.Series(dtype=dt) for col, dt in zip(cols, dtypes)}
        # build multi-level index
        iterables = [np.arange(self.ntargets), posids]
        names = ['target_no', 'DEVICE_ID']
        index = pd.MultiIndex.from_product(iterables, names=names)
        self.movedf = pd.DataFrame(data=data, index=index)
        # write pcid column to movedf
        self.movedf = self.movedf.merge(self.posdf['PCID'].reset_index(),
                                        on='DEVICE_ID', right_index=True)
        self.logger.info(f'Move data table initialised '
                         f'for {len(self.posids)} positioners.')

    def complete_data(self):
        self.end_time = pc.now()  # define end time
        self.read_telemetry()

    def read_telemetry(self):
        try:
            conn = psycopg2.connect(host="desi-db", port="5442",
                                    database="desi_dev",
                                    user="desi_reader", password="reader")
            self.telemetry = pd.read_sql_query(  # get temperature data
                f"""SELECT * FROM pc_telemetry_can_all
                    WHERE time >= '{self.start_time.astimezone(timezone.utc)}'
                    AND time < '{self.end_time.astimezone(timezone.utc)}'""",
                conn).sort_values('time')  # posfid_temps, time, pcid
            print(f'{len(self.telemetry)} entries from telemetry DB '
                  f'between {self.start_time} and {self.end_time} were loaded')
            self.db_telemetry_available = True
        except Exception:
            self.db_telemetry_available = False

    def make_summary_plots(self, n_threads_max=32, make_binder=True, mp=True):

        n_threads = min(n_threads_max, 2*multiprocessing.cpu_count())
        pstr = (f'Making summary xyplots with {n_threads} threads on '
                f'{multiprocessing.cpu_count()} cores for '
                f'submoves {list(range(self.num_corr_max+1))}...')
        if hasattr(self, 'logger'):
            self.logger.info(pstr)
        else:
            print(pstr)
        if mp:
            # the following implementation fails when loggers are present
            # pbar = tqdm(total=len(self.posids))

            # def update_pbar(*a):
            #     pbar.update()

            # with Pool(processes=n_threads) as p:
            #     for posid in self.posids:
            #         p.apply_async(self.make_summary_plot, args=(posid,),
            #                       callback=update_pbar)
            #     p.close()
            #     p.join()
            pool = []
            n_started = 0
            for posid in tqdm(self.posids):
                np = Process(target=self.make_summary_plot, args=(posid,))
                if n_started % n_threads_max == 0:  # all cores occupied, wait
                    [p.join()
                     for p in pool[n_started-n_threads_max:n_started-1]]
                np.start()
                n_started += 1
                pool.append(np)
            self.logger.info(
                f'Waiting for the last MP chunk of {n_threads} to complete...')
            [p.join() for p in pool[n_started-n_threads_max:-1]]
        else:
            for posid in tqdm(self.posids):
                self.make_summary_plot(posid)
        if make_binder:
            if mp:
                # the following implementation fails when loggers are present
                # with Pool(processes=n_threads) as p:
                #     for pcid, n in product(self.pcids,
                #                            range(self.num_corr_max+1)):
                #         p.apply_async(self.make_summary_plot_binder,
                #                       args=(pcid, n))
                #     p.close()
                #     p.join()
                self.logger.info('Last MP chunk completed. '
                                 'Creating xyplot binders...')
                for pcid, n in tqdm(product(self.pcids,
                                    range(self.num_corr_max+1))):
                    np = Process(target=self.make_summary_plot_binder,
                                 args=(pcid, n))
                    np.start()
                    pool.append(np)
                [p.join() for p in pool]
            else:
                for pcid, n in tqdm(product(self.pcids,
                                            range(self.num_corr_max+1))):
                    self.make_summary_plot_binder(pcid, n)
        return True

    def make_summary_plot(self, posid):  # make one plot for a given posid
        row = self.posdf.loc[posid]  # row containing calibration values
        offX, offY = 0, 0
        pcid, r1, r2, posintT = row[
            ['PCID', 'LENGTH_R1', 'LENGTH_R2', 'targetable_range_T']]
        rmin, rmax = r1 - r2, r1 + r2  # min and max patrol radii
        Tmin, Tmax = np.sort(posintT) + row['OFFSET_T']  # targetable poslocT
        path = os.path.join(self.dirs[pcid],
                            '{}_xyplot_submove_{{}}.pdf'.format(posid))
        title = (f'XY Accuracy Test {self.start_time}\n'
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
            pstr = f'saved xyplot: {path.format(n)}'
            if hasattr(self, 'loggers'):
                self.loggers[pcid].debug(pstr)
            else:
                pass  # print(pstr)
            plt.close(fig)

    def make_summary_plot_binder(self, pcid, n):
        template = os.path.join(self.dirs[pcid],
                                f'*_xyplot_submove_{n}.pdf')
        paths = sorted(glob(template))
        assert len(paths) == len(self.posids_pc[pcid]), (
                f'Length mismatch: {len(paths)} ≠ '
                f'{len(self.posids_pc[pcid])}')
        binder = PdfFileMerger()
        for path in paths:
            binder.append(path)
        savepath = os.path.join(
            self.dirs[pcid],
            f'{len(paths)}_positioners-xyplot_submove_{n}.pdf')
        pstr = f'Writing xyplot binder for submove {n}...'
        if hasattr(self, 'loggers'):
            self.loggers[pcid].info(pstr)
        else:
            print(pstr)
        binder.write(savepath)
        binder.close()
        pstr = f'Binder for submove {n} saved to: {savepath}'
        if hasattr(self, 'loggers'):
            self.loggers[pcid].info(pstr)
        else:
            print(pstr)

    def export_data_logs(self):
        '''must have writte self.posids_pc, a dict keyed by pcid'''
        self.movedf.to_pickle(os.path.join(self.dir, 'movedf.pkl.gz'),
                              compression='gzip')
        self.movedf.to_csv(os.path.join(self.dir, 'movedf.csv'))
        self.logger.info(f'Focal plane move data written to: {self.dir}')
        for pcid in self.pcids:
            def makepath(name): return os.path.join(self.dirs[pcid], name)
            for posid in self.posids_pc[pcid]:  # write move data csv
                df_pos = self.movedf.loc[idx[:, posid], :].droplevel(1)
                df_pos.to_pickle(makepath(f'{posid}_df.pkl.gz'),
                                 compression='gzip')
                df_pos.to_csv(makepath(f'{posid}_df.csv'))
            with open(makepath(f'pc{pcid:02}_export.log'), 'w') as handle:
                self.logs[pcid].seek(0)
                shutil.copyfileobj(self.logs[pcid], handle)  # save logs
            self.loggers[pcid].info('Petal move data written to: '
                                    f'{self.dirs[pcid]}')

    def dump_as_one_pickle(self):
        del self.logger
        del self.loggers
        with open(os.path.join(self.dir, 'data_dump.pkl'), 'wb') as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def generate_report(self):
        # define input and output paths for pweave
        print('Generating xy accuracy test report...')
        path_output = os.path.join(self.dir,
                                   f'{self.dir_name}-xytest_report.html')
        with open(os.path.join(pc.dirs['xytest_data'], 'pweave_test_src.txt'),
                  'w') as h:
            h.write(os.path.join(self.dir, 'data_dump.pkl'))
        # add sections for each pcid to markdown document
        shutil.copyfile('xytest_report_master.md', 'xytest_report.md')
        with open('xytest_report_master_petal.md', 'r') as h:
            petal_section = h.read()
        ptlstr = 'petals' if len(self.pcids) > 1 else 'petal'
        posid_section = '''
#### Appendix: complete list of positioners tested for <%=len(data.pcids)%> {0}
``<%=data.posids%>``
        '''.format(ptlstr)
        with open('xytest_report.md', 'a+') as h:
            for pcid in self.pcids:
                h.write(petal_section.format(pcid))
                h.write(posid_section)
        subprocess.call(['pweave', 'xytest_report.md',
                         '-f', 'pandoc2html', '-o', path_output])

    def make_archive(self):
        path = os.path.join(self.dir, f'{os.path.basename(self.dir)}.tar.gz')
        with tarfile.open(path, 'w:gz') as arc:  # ^tgz doesn't work properly
            arc.add(self.dir, arcname=os.path.basename(self.dir))
        print(f'Test data archived: {path}')
        return path

    def finish_xyaccuracy_test_products(self):
        self.complete_data()
        self.export_data_logs()
        self.make_summary_plots()  # plot for all positioners by default
        self.dump_as_one_pickle()  # loggers lost as they cannot be serialised
        if shutil.which('pandoc') is None:
            print('To generate an xy test report, you must have a complete '
                  'installation of pandoc and/or TexLive. '
                  'Skipping test report generation from markdown template...')
        else:
            self.generate_report()  # requires pickle
        self.make_archive()


if __name__ == '__main__':

    '''load the dumped pickle file as follows, protocol is auto determined'''
    folders = ['20191021T154939-0700-petal3_can10',
                 '20191024T150231-0700-petal9',
                 '20191031T150117-0700-petal0_can1011',
                 '20191106T100257-0700-petal0_can1011',
                 '20191107T114725-0700-petal0_short',
                 '20191112T191119-0700-petal0_full']
                 # '20191113T143453-0700-cmx_psf-3',
                 # '20191113T145131-0700-cmx_psf-4',
                 # '20191113T151057-0700-cmx_psf-1',
                 # '20191113T153032-0700-cmx_psf-2',
                 # '20191113T191026-0700-cmx_dither',
                 # '20191113T191844-0700-cmx_dither',
                 # '20191113T192440-0700-cmx_dither',
                 # '20191113T203313-0700-petal2_full',
                 # '20191113T204603-0700-petal2_full',
                 # '20191115T155812-0700-petal9_full',
                 # '20191116T184321-0700-cmx_dither_petal0_63064',
                 # '20191116T185036-0700-cmx_dither_petal0_63064']
    for dir_name in folders:
        try:
            # dir_name = '20191115T155812-0700-petal9_full'
            with open(os.path.join(pc.dirs['xytest_data'],
                                   dir_name, 'data_dump.pkl'),
                      'rb') as handle:
                data = pickle.load(handle)
            # data.make_summary_plots()
            if shutil.which('pandoc') is not None:
                data.generate_report()
            # data.make_archive()
        except Exception as e:
            print(e)
