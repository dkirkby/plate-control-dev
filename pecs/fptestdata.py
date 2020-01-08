# -*- coding: utf-8 -*-
"""
Created on Thu May 23 22:18:28 2019

@author: Duan Yutong (dyt@physics.bu.edu)

Store xy test, anti-collision, calibration data in an offline class.
DOSlib dependence is kept out of this
Most fields are dictionaries indexed by petal id:

FPTestData.logs[pcid]:          StringIO object equivalent to log file
FPTestData.loggers[pcid]:       logger which writes new lines to log file

"""

import os
import io
from itertools import product, chain
from functools import partial, reduce
import shutil
import subprocess
import pickle
import logging
from copy import copy
from datetime import timezone
import multiprocessing
from multiprocessing import Process  # Pool
import tarfile
from glob import glob
import numpy as np
import pandas as pd
from tqdm import tqdm
from PyPDF2 import PdfFileMerger
from configobj import ConfigObj
import posconstants as pc
import psycopg2
import matplotlib
# matplotlib.use('pdf')  # manually specify backend if savefig doesn't work
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
# plt.ioff()  # turn off interactive mode, doesn't work in matplotlib 2
plt.rcParams.update({'font.family': 'serif',
                     'mathtext.fontset': 'cm'})
Circle = matplotlib.patches.Circle
idx = pd.IndexSlice
np.rms = lambda x: np.sqrt(np.mean(np.square(x)))
np.nanrms = lambda x: np.sqrt(np.nanmean(np.square(x)))
# sys.path.append(os.path.abspath('.'))


class BroadcastLogger:
    '''must call methods below for particular logger levels below
    support input message as a string of list of strings
    msg will be broadcasted to all petals
    info level or above will be printed to stdout in terminal
    '''

    def __init__(self, loggers=None, printfunc=print):
        if loggers is None:
            self.loggers_available = False
        else:
            self.pcids = list(loggers.keys())
            self.loggers = loggers
            self.loggers_available = True
        self.printfunc = printfunc

    def _log(self, msg, lvl):  # reserved for in-class use, don't call this
        if type(msg) is list:
            list(map(partial(self._log, lvl=lvl), msg))
        elif type(msg) is str:
            if self.loggers_available:
                for pcid in self.pcids:
                    self.loggers[pcid].log(lvl, msg)
            self.printfunc(msg)
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


class FPTestData:
    ''' on-mountain xy accuracy test and calibration data will be saved in:
            /data/focalplane/kpno/{date}/{expid}/pc{pcid}/
    '''
    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)-8s]: %(message)s',
        datefmt=pc.timestamp_format)

    def __init__(self, test_name, test_cfg=None):

        self.test_name = test_name
        if test_cfg is None:
            self.test_cfg = ConfigObj()
        else:  # for xy accuracy test
            self.test_cfg = test_cfg
            for key, val in test_cfg.items():
                setattr(self, key, val)  # copy test settings to self attr
        if 'pcids' in test_cfg:
            self.pcids = test_cfg['pcids']  # calibration cfg contains pcids
        else:  # get pcids from xy test cfg
            self.pcids = [  # validate string pcid sections and create list
                int(key) for key in test_cfg.keys() if len(key) == 2
                and key.isdigit() and (test_cfg[key]['mode'] is not None)]
            for pcid in self.test_cfg.sections:  # convert pcid to int now
                self.test_cfg.rename(pcid, int(pcid))
        self._init_loggers()
        self.logger.debug([f'posconstants.py version: {pc.code_version}',
                           f'anticollision mode: {self.anticollision}'])
        self.schedstats = {}

    def set_dirs(self, expid):
        self.filename = (
            f'{pc.filename_timestamp_str(t=self.t_i)}-{self.test_name}')
        self.dir = os.path.join(
            pc.dirs['kpno'], pc.dir_date_str(t=self.t_i), f'{expid:08}')
        self.dirs = {pcid: os.path.join(self.dir, f'pc{pcid:02}')
                     for pcid in self.pcids}
        self.test_cfg.filename = os.path.join(self.dir, f'{self.filename}.cfg')
        for d in [self.dir] + list(self.dirs.values()):
            os.makedirs(d, exist_ok=True)

    def _init_loggers(self):
        '''need to know the product directories before initialising loggers'''
        self.logs = {}  # set up log files and loggers for each petal
        self.log_paths = {}
        self.loggers = {}
        for pcid in self.pcids:
            # use the same directory for all real-time logs
            self.log_dir = pc.dirs['kpno']
            # ensure save directory and log file exist if they don't already
            os.makedirs(self.log_dir, exist_ok=True)
            self.log_paths[pcid] = os.path.join(
                self.log_dir,
                f'{self.test_name}-pc{pcid:02}_realtime.log')
            open(self.log_paths[pcid], 'a').close()  # create empty log files
            # create virtual file object for storing log entries
            # using stringio because it supports write() and flush()
            log = io.StringIO(newline='\n')
            # craete a new logger for each petal by unique logger name
            logger = logging.getLogger(f'PC{pcid:02}')
            logger.handlers = []  # clear handlers that might exisit already
            logger.setLevel(logging.DEBUG)  # log everything, DEBUG level up
            fh = logging.FileHandler(self.log_paths[pcid],  # real-time log
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
            logger.info(f'Logger initialised for PC{pcid:02}, writing '
                        f'real-time log to: {self.log_paths[pcid]}')
            # write configs to logs
            self._log_cfg(logger.debug, self.test_cfg)
            self.logs[pcid] = log  # assign logs and loggers to attributes
            self.loggers[pcid] = logger
        self.logger = BroadcastLogger(loggers=self.loggers)

    def print(self, string, pcid=None):
        '''use in the absence of logger(s)'''
        assert type(string) is str
        if pcid is None:
            if hasattr(self, 'logger'):
                self.logger.debug(string)
        else:
            if hasattr(self, 'loggers'):
                self.loggers[pcid].debug(string)
            print(string)

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
            printfunc(line)  # now line is utf8 str which needs no decode
            #  printfunc(line.decode('utf_8'))  # convert byte str to str
        printfunc(f'=== End of config file dump: {config.filename} ===')

    def read_telemetry(self):
        try:
            conn = psycopg2.connect(host="desi-db", port="5442",
                                    database="desi_dev",
                                    user="desi_reader", password="reader")
            self.telemetry = pd.read_sql_query(  # get temperature data
                f"""SELECT * FROM pc_telemetry_can_all
                    WHERE time >= '{self.t_i.astimezone(timezone.utc)}'
                    AND time < '{self.t_f.astimezone(timezone.utc)}'""",
                conn).sort_values('time')  # posfid_temps, time, pcid
            self.print(f'{len(self.telemetry)} entries from telemetry DB '
                       f'between {self.t_i} and {self.t_f} loaded')
            self.db_telemetry_available = True
        except Exception:
            self.db_telemetry_available = False

    def abnormal_pos_df(self, pcid=None):
        abnormaldf = self.abnormaldf
        if pcid is not None:  # then filter out the selected PCID
            abnormaldf = self.abnormaldf[self.abnormaldf['PCID'] == pcid]
        posids_abnormal = abnormaldf.index.droplevel(0).unique()
        rows = []
        for posid in posids_abnormal:
            counts_list = []  # counts by submove
            for i in range(self.num_corr_max+1):
                counts_list.append(abnormaldf.loc[idx[:, posid], :]
                                   [f'pos_status_{i}'].value_counts())
            row = reduce(lambda x, y: x.add(y, fill_value=0), counts_list)
            rows.append(row)
        df_status = (pd.DataFrame(rows, index=posids_abnormal, dtype=np.int64)
                     .drop('Normal positioner', axis=1, errors='ignore'))
        return df_status.fillna(value=0)

    def plot_posfid_temp(self, pcid=None):

        def temp_telemetry_present(pcid):
            return not self.telemetry[self.telemetry['pcid'] == pcid].empty

        def plot_petal(pcid, ax, max_on=True, mean_on=False, median_on=True):
            query = self.telemetry[self.telemetry['pcid'] == pcid]
            if max_on:
                ax.plot(query['time'], query['posfid_temps_max'], '-o',
                        label=f'PC{pcid:02} posfid max')
            if mean_on:
                ax.plot(query['time'], query['posfid_temps_mean'], '-o',
                        label=f'PC{pcid:02} posfid mean')
            if median_on:
                ax.plot(query['time'], query['posfid_temps_median'], '-o',
                        label=f'PC{pcid:02} posfid median')

        if not self.db_telemetry_available:
            print('DB telemetry query unavailable on this platform.')
            return
        # perform telemetry data sanity check needed since there's been
        # so many issues with the petalcontroller code and bad telemetry data
        for stat in ['max', 'mean', 'median']:
            field = f'posfid_temps_{stat}'
            if self.telemetry[field].isnull().any():
                print(f'Telemetry data from DB failed sanity check for '
                      f'temperature plot. Field "{field}" contains '
                      f'null values.')
                return
        # make sure at least one pcid present has valid temp temeletry data
        for i in self.pcids:
            if not temp_telemetry_present(i):
                print(f'PC{i:02} telemetry missing from DB.')
                if i == pcid:  # plotting only one petal, and it's missing
                    return
        if not np.any([temp_telemetry_present(i) for i in self.pcids]):
            print(f'No telemetry available in DB during this session for '
                  f'any PCID tested.')
            return  # plotting all petals, but not any is present
        pd.plotting.register_matplotlib_converters()
        fig, ax = plt.subplots(figsize=(6.5, 3.5))  # now ok to plot something
        if pcid is None:  # loop through all petals, plot max only
            for pcid in self.pcids:  # at least one is present, not sure which
                if temp_telemetry_present(pcid):
                    plot_petal(pcid, ax,
                               max_on=True, mean_on=False, median_on=False)
        else:  # pcid is an integer, plot the one given pcid only
            plot_petal(pcid, ax)
        ax.legend()
        ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
        ax.xaxis.set_tick_params(rotation=45)
        ax.set_xlabel('Time (UTC)')
        ax.set_ylabel('Temperature (°C)')
        suffix = '' if pcid is None else f'_pc{pcid:02}'
        fig.savefig(os.path.join(self.dir, 'figures',
                                 f'posfid_temp{suffix}.pdf'),
                    bbox_inches='tight')

    @staticmethod
    def add_hist_annotation(ax):
        for rect in ax.patches:  # add annotations
            height = rect.get_height()
            ax.annotate(f'{int(height)}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 5),  # vertical offset
                        textcoords='offset points', size='small',
                        ha='center', va='bottom')
        ax.set_ylim([0.1, ax.get_ylim()[1]*3])

    def export_data_logs(self):
        '''must have writte self.posids_pc, a dict keyed by pcid'''
        self.test_cfg.write()  # write test config
        for attr in ['movedf', 'gradedf', 'calibdf', 'abnormaldf', 
                     'exppos', 'meapos', 'calib_fit']:
            if not hasattr(self, attr):
                continue  # skip a df if it doesn't exist
            getattr(self, attr).to_pickle(
                os.path.join(self.dir, f'{attr}.pkl.gz'), compression='gzip')
            # getattr(self, attr).to_csv(os.path.join(self.dir, f'{attr}.csv'))
            self.print(f'Positioner {attr} written to: {self.dir}')
        for pcid in self.pcids:
            self.log_paths[pcid] = os.path.join(self.dirs[pcid],
                                                f'pc{pcid:02}_export.log')
            # for posid in self.posids_pc[pcid]:  # write movedf for each posid
            #     df_pos = self.movedf.loc[idx[:, posid], :].droplevel(1)
            #     df_pos.to_pickle(makepath(f'{posid}_df.pkl.gz'),
            #                      compression='gzip')
            #     df_pos.to_csv(makepath(f'{posid}_df.csv'))
            with open(self.log_paths[pcid], 'w') as handle:
                self.logs[pcid].seek(0)
                shutil.copyfileobj(self.logs[pcid], handle)  # save logs
            self.print(f'PC{pcid:02} data written to: '
                       f'{self.log_paths[pcid]}', pcid=pcid)
            if pcid in self.schedstats:
                self.schedstats[pcid].to_csv(os.path.join(
                    self.dirs[pcid], 'schedstats.csv'))

    def dump_as_one_pickle(self):
        try:
            del self.logger
            del self.loggers
        except AttributeError:
            pass
        name = self.__class__.__name__.lower()
        with open(os.path.join(self.dir, f'{name}.pkl'), 'wb') as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def make_archive(self):
        # exclude fits fz file which is typically 1 GB and the existing tgz
        excl_patterns = ['fvc-*.fits.fz', '*.tar.gz']
        self.print(f'Making tgz archive with exclusion patterns: '
                       f'{excl_patterns}')
        all_paths = glob(os.path.join(self.dir, '*'))
        excl_paths = list(chain.from_iterable(
            [glob(os.path.join(self.dir, pattern))
             for pattern in excl_patterns]))
        paths = [path for path in all_paths if path not in excl_paths]
        dirbase = os.path.basename(self.dir)
        output_path = os.path.join(self.dir, f'{dirbase}.tar.gz')
        with tarfile.open(output_path, 'w:gz') as arc:
            for p in paths:
                arc.add(p, arcname=os.path.join(dirbase, os.path.basename(p)))
        self.print(f'Test data archived: {output_path}')


class XYTestData(FPTestData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def isolate_abnormal_flags(self):
        masks = []  # get postiioners with abnormal flags
        for i in range(self.num_corr_max+1):
            masks.append(self.movedf[f'pos_flag_{i}'] != 4)
        mask = reduce(lambda x, y: x | y, masks)
        self.abnormaldf = self.movedf[mask]

    def initialise_movedata(self, posids, n_targets):
        '''initialise column names for move data table for each positioner
        existing attributes required (see xytest.py):
            self.pcids
        '''
        # build column names and data types, all in petal-local flatXY CS
        cols0 = ['timestamp', 'cycle', 'move_log']
        dtypes0 = ['datetime64[ns]', np.uint64, str]
        cols1 = ['tgt_x', 'tgt_y']
        dtypes1 = [np.float64] * len(cols1)
        cols2_base = ['mea_q', 'mea_s', 'mea_x', 'mea_y',
                      'err_x', 'err_y', 'err_xy',
                      'posintT', 'posintP', 'flag', 'status']
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
        self.logger.debug(f'Move data table initialised '
                          f'for {len(self.posids)} positioners.')

    @staticmethod
    def grade_pos(err_0_max, err_corr_max, err_corr_rms,
                  err_corr_95p_max, err_corr_95p_rms):
        '''these criteria were set by UMich lab tests, all in microns
        '''
        if np.any(np.isnan([err_0_max, err_corr_max, err_corr_rms,
                            err_corr_95p_max])):
            return pc.grades[-1]
        if (err_0_max <= 100) & (err_corr_max <= 15) & (err_corr_rms <= 5):
            grade = pc.grades[0]
        elif ((err_0_max <= 250) & (err_corr_max <= 25) & (err_corr_rms <= 10)
              & (err_corr_95p_max <= 15) & (err_corr_95p_rms <= 5)):
            grade = pc.grades[1]
        elif ((err_0_max <= 250) & (err_corr_max <= 50) & (err_corr_rms <= 20)
              & (err_corr_95p_max <= 25) & (err_corr_95p_rms <= 10)):
            grade = pc.grades[2]
        elif ((err_0_max <= 500) & (err_corr_max <= 50) & (err_corr_rms <= 20)
              & (err_corr_95p_max <= 25) & (err_corr_95p_rms <= 10)):
            grade = pc.grades[3]
        else:
            grade = pc.grades[4]
        return grade

    def calculate_grades(self):
        rows = []  # determine performance grade of each positioner one by one
        for posid in self.posids:
            pos_data = (self.movedf.loc[idx[:, posid], :]
                        .reset_index(drop=True).copy())
            # exclude entries where posflag is not equal to 4, set to nan
            for i in range(self.num_corr_max+1):
                mask = pos_data[f'pos_flag_{i}'] != 4
                pos_data.loc[mask, f'err_xy_{i}'] = np.nan
            err_0_max = np.max(pos_data['err_xy_0']) * 1000  # max blind err μm
            err_corr = pos_data[  # select corrective moves only
                [f'err_xy_{i}' for i in range(1, self.num_corr_max+1)]].values
            err_corr = err_corr[~np.isnan(err_corr)]  # filter out nan
            if len(err_corr) == 0:
                err_corr_max = err_corr_rms = np.nan
                err_corr_95p_max = err_corr_95p_rms = np.nan
                grade = 'N/A'
            else:
                err_corr_max = np.max(err_corr) * 1000  # μm
                err_corr_rms = np.rms(err_corr) * 1000  # μm
                # take reduced sample at 95 percentile, excluding 5% worst pts
                err_corr_95p = err_corr[
                    err_corr <= np.percentile(err_corr, 95)]
                err_corr_95p_max = np.max(err_corr_95p) * 1000  # μm
                err_corr_95p_rms = np.rms(err_corr_95p) * 1000  # μm
                grade = self.grade_pos(
                    err_0_max, err_corr_max, err_corr_rms,
                    err_corr_95p_max, err_corr_95p_rms)
            rows.append({'DEVICE_ID': posid,
                         'err_0_max': err_0_max,  # max blind move xy error
                         'err_corr_max': err_corr_max,  # max corr move err
                         'err_corr_rms': err_corr_rms,  # max corr move rms
                         'err_corr_95p_max': err_corr_95p_max,  # best 95%
                         'err_corr_95p_rms': err_corr_95p_rms,  # best 95%
                         'grade': grade})
        self.gradedf = (pd.DataFrame(rows)
                        .set_index('DEVICE_ID').join(self.posdf))

    def make_summary_plots(self, n_threads_max=32, make_binder=True, mp=True):
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
            n_threads = min(n_threads_max, 2*multiprocessing.cpu_count())
            self.print(f'Making summary xyplots with {n_threads} threads '
                       f'on {multiprocessing.cpu_count()} cores for '
                       f'submoves {list(range(self.num_corr_max+1))}...')
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
            self.print(
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
                self.print('Last MP chunk completed, creating xyplot binders...')
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
        title = (f'XY Accuracy Test {self.t_i}\n'
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
            meaX, meaY = moves[f'mea_x_{n}'], moves[f'mea_y_{n}']
            ax.plot(meaX, meaY, '+', ms=6, mew=1, color='k',
                    label=r'measured $(x, y)$')  # measured xy for nth move
            errXY = moves[f'err_xy_{n}'] * 1000  # convert mm to microns
            for i in range(len(tgtX)):
                ax.annotate(f'{i+1}', xy=(tgtX[i]-0.2, tgtY[i]), color='C3',
                            size=6, ha='right')
                ax.annotate(f'{i+1}', xy=(meaX[i]+0.2, meaY[i]), color='k',
                            size=6, ha='left')
            u = r'$\mathrm{\mu m}$'
            text = (f'SUBMOVE: {n}\n'  # text box for submove errors
                    f'error max: {np.max(errXY):6.1f} {u}\n'
                    f'      rms: {np.rms(errXY):6.1f} {u}\n'
                    f'      avg: {np.mean(errXY):6.1f} {u}\n'
                    f'      min: {np.min(errXY):6.1f} {u}')
            ax.text(0.02, 0.98, text, transform=ax.transAxes,
                    family='monospace', fontsize=10, ha='left', va='top',
                    bbox={'boxstyle': 'round', 'alpha': 0.8,
                          'facecolor': 'white', 'edgecolor': 'lightgrey'})
            ax.grid(linestyle='--')
            ax.set_aspect('equal')
            ax.set_title(title)
            ax.set_xlabel(r'$x/\mathrm{mm}$')
            ax.set_ylabel(r'$y/\mathrm{mm}$')
            ax.legend(loc='upper right', fontsize=10)
            fig.savefig(path.format(n), bbox_inches='tight')
            if hasattr(self, 'logger'):
                self.loggers[pcid].debug(f'xyplot saved: {path.format(n)}')
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
        self.print(f'Writing xyplot binder for submove {n}...')
        binder.write(savepath)
        binder.close()
        self.print(f'Binder for submove {n} saved to: {savepath}')

    def plot_grade_dist(self, pcid=None):
        if pcid is None:  # show all positioners tested
            grade_counts = self.gradedf['grade'].value_counts()
            ptlstr = 'petals' if len(self.pcids) > 1 else 'petal'
            title = (
                f'Overall grade distribution '
                f'({len(self.posids)} positioners, {len(self.pcids)} '
                + ptlstr + ')')
        else:
            mask = self.gradedf['PCID'] == pcid
            grade_counts = self.gradedf[mask]['grade'].value_counts()
            title = (f'PC{pcid:02} grade distribution '
                     f'({len(self.posids_pc[pcid])} positioners)')
        for grade in pc.grades:
            if grade not in grade_counts.index:  # no count, set to zero
                grade_counts[grade] = 0
        fig, ax = plt.subplots(figsize=(6.5, 3.5))
        ax.bar(pc.grades, grade_counts.reindex(pc.grades),
               log=True, alpha=0.7)
        ax.set_title(title)
        self.add_hist_annotation(ax)
        ax.set_xlabel('Postiioner performance grade')
        ax.set_ylabel('Count')
        suffix = '' if pcid is None else f'_pc{pcid:02}'
        fig.savefig(os.path.join(self.dir, 'figures',
                                 f'grade_distribution{suffix}.pdf'),
                    bbox_inches='tight')
        return grade_counts

    def plot_error_dist(self, pcid=None, grade=None,
                        outliers=None, exclude_outliers=False):
        '''two subplots, left blind moves, right corrective moves'''

        def plot_error_hist(ax, column_name, cuts, title, vlines=None):
            colours = {grade: f'C{i}' for i, grade in enumerate(pc.grades)}
            grades_present = sorted(err['grade'].unique())
            if 'N/A' in grades_present:
                grades_present.remove('N/A')
            ax.hist([err[err['grade'] == grade][column_name]
                     for grade in grades_present],
                    log=True, histtype='bar', stacked=False, alpha=0.7,
                    color=[colours[grade] for grade in grades_present],
                    label=[f'Grade {grade}' for grade in grades_present])
            self.add_hist_annotation(ax)
            ax.set_ylim(top=2e3)
            ax.set_title(title)
            ax.set_xlabel('Error (μm)')
            ax.set_ylabel('Count')
            if vlines is not None:
                for vline in vlines:
                    ax.axvline(vline)
            ax.legend()
            # add text for counts
            rows = []
            cuts = (list(cuts) + [err[column_name].max()]
                    if sorted(cuts)[-1] < err[column_name].max()
                    else list(cuts))
            for cut in cuts:
                rows.append({'Error within (μm)': int(cut),
                             'Count': int(np.sum(err[column_name] <= cut))})
            text = pd.DataFrame(rows).to_string(index=False)
            ax.text(0.7, 0.97, text, ha='right', va='top',
                    family='monospace', size='small', transform=ax.transAxes,
                    bbox={'boxstyle': 'round', 'alpha': 0.1,
                          'facecolor': 'white', 'edgecolor': 'grey'})

        err = self.gradedf  # show all positioners tested by default
        err = err[err['grade'] != 'N/A']  # filter out N/A grades
        n_outliers = 0  # initial value
        if pcid is None:  # no outlier exclusion for entire FP plot
            ptlstr = 'petals' if len(self.pcids) > 1 else 'petal'
            posstr = 'positioners' if len(err) > 1 else 'positioner'
            title = (
                f'Overall {{}} distribution '
                f'\n({len(err)} {posstr}, {len(self.pcids)} '
                + ptlstr + ')')
        else:  # showing only one petal given pcid
            err = err[err['PCID'] == pcid]
            if grade is not None:
                err = err[err['grade'] == grade]
            if outliers is not None and exclude_outliers:
                n_outliers = len(set(err.index) & set(outliers))
                err = err[~err.index.isin(outliers)]
            posstr = 'positioners' if len(err) > 1 else 'positioner'
            olstr = 'outliers' if n_outliers > 1 else 'outlier'
            suffix = (f', {n_outliers} {olstr} excluded' if n_outliers > 1
                      else '')
            title = (f'PC{pcid:02} {{}} distribution '
                     f'\n({len(err)} {posstr}{suffix})')
        if len(err) == 0:
            return  # empty plot
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        plot_error_hist(
            axes[0], 'err_0_max', [0, 100, 200, 300, 400, 500, 1000],
            title.format('max blind move error'))
        plot_error_hist(
            axes[1], 'err_corr_rms', [0, 5, 10, 20, 30, 50, 100, 200],
            title.format('rms corrective move error'))
        plt.tight_layout()
        suffix1 = '' if pcid is None else f'_pc{pcid:02}'
        suffix2 = '' if grade is None else f'_grade_{grade}'.lower()
        fig.savefig(os.path.join(self.dir, 'figures',
                                 f'error_distribution{suffix1}{suffix2}.pdf'),
                    bbox_inches='tight')

    def plot_error_heatmaps(self, pcid, outliers=None):
        # load nominal theta centres for plotting in local ptlXYZ
        path = os.path.join(
            os.getenv('PLATE_CONTROL_DIR',
                      '/software/products/plate_control-trunk'),
            'petal', 'positioner_locations_0530v14.csv')
        ptlXYZ_df = pd.read_csv(path,
                                usecols=['device_location_id', 'X', 'Y', 'Z'],
                                index_col='device_location_id')
        ptlXYZ_df.index.rename('device_loc', inplace=True)
        gradedf = self.gradedf[self.gradedf['PCID'] == pcid]
        n_outliers = 0
        if outliers is not None:
            gradedf = gradedf[~gradedf.index.isin(outliers)]
            n_outliers = len(outliers)

        def plot_error_heatmap(ax, column_name, vmin, vmax, title):
            # plot all empty circles
            ax.scatter(ptlXYZ_df['X'], ptlXYZ_df['Y'],
                       marker='o', facecolors='none', edgecolors='grey',
                       s=45, lw=0.8)
            hm = ax.scatter(gradedf['OFFSET_X'], gradedf['OFFSET_Y'],
                            c=gradedf[column_name], cmap='plasma',
                            marker='o', s=36, vmin=vmin, vmax=vmax)
            ax.set_aspect('equal')
            ax.set_xlabel('x (mm)')
            ax.set_title(title)
            return hm

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        col_names = ['err_0_max', 'err_corr_rms']
        move_names = ['max blind move', 'rms corrective move']
        vmin = gradedf[col_names].min().min()
        vmax = gradedf[col_names].max().max()
        for col_name, move_name, ax in zip(col_names, move_names, axes):
            olstr = 'outliers' if n_outliers > 1 else 'outlier'
            title = (
                f'PC{pcid:02} {move_name} error map\n({len(gradedf)} '
                f'positioners, {n_outliers} {olstr} excluded)')
            hm = plot_error_heatmap(ax, col_name, vmin, vmax, title)
            fig.colorbar(hm, ax=ax, fraction=0.028, pad=0.025)
        axes[0].set_ylabel('y (mm)')
        plt.tight_layout()
        # fig.subplots_adjust(wspace=0)
        # cbar_ax = fig.add_axes([0.91, 0.225, 0.01, 0.555])
        # fig.colorbar(hm, cax=cbar_ax)
        fig.savefig(os.path.join(self.dir, 'figures',
                                 f'{pcid}_error_heatmaps.pdf'),
                    bbox_inches='tight')

    def generate_report(self):
        # define input and output paths for pweave
        self.print(f'Generating xy accuracy test report for {self.filename}')
        path_output = os.path.join(self.dir,
                                   f'{self.filename}-report.html')
        with open(os.path.join(pc.dirs['xytest_data'], 'pweave_test_src.txt'),
                  'w') as h:
            h.write(os.path.join(self.dir, 'xytestdata.pkl'))
        # add sections for each pcid to markdown document
        shutil.copyfile('xytest_report_master.pmd', 'xytest_report.pmd')
        with open('xytest_report_master_petal.pmd', 'r') as h:
            petal_section = h.read()
        ptlstr = 'petals' if len(self.pcids) > 1 else 'petal'
        if hasattr(self, 'posids_disabled'):
            posid_section = '''
#### Appendix: complete list of positioners tested for <%=len(data.pcids)%> {0}
``<%=sorted(set(data.posids) | data.posids_disabled)%>``
        '''.format(ptlstr)
        else:
            posid_section = '''
#### Appendix: complete list of positioners tested for <%=len(data.pcids)%> {0}
``<%=data.posids%>``
        '''.format(ptlstr)
        with open('xytest_report.pmd', 'a+') as h:
            for pcid in self.pcids:
                h.write(petal_section.format(pcid))
                h.write(posid_section)
        subprocess.call(['pweave', 'xytest_report.pmd',
                         '-f', 'pandoc2html', '-o', path_output])

    def generate_data_products(self):
        self.read_telemetry()
        self.isolate_abnormal_flags()
        self.calculate_grades()
        self.export_data_logs()
        self.make_summary_plots()  # plot for all positioners by default
        self.dump_as_one_pickle()  # loggers lost as they cannot be serialised
        if shutil.which('pandoc') is None:
            self.print('You must have a complete installation of pandoc '
                       'and/or TexLive. Skipping test report...')
        else:
            self.generate_report()  # requires pickle
        self.make_archive()


class CalibrationData(FPTestData):

    def __init__(self, test_cfg_dict):
        test_cfg = ConfigObj()
        test_cfg.update(test_cfg_dict)
        super().__init__(test_cfg['mode']+'_calibration', test_cfg=test_cfg)
        # stores calibration values, old and new
        # iterables = [['OLD', 'NEW'], param_keys]
        # columns = pd.MultiIndex.from_product(
        #     iterables, names=['label', 'param_key'])

    def write_calibdf(self, calibdf_old, calibdf_fit, calibdf_new):
        self.calibdf = pd.concat(
            [calibdf_old, calibdf_fit, calibdf_new], axis=1,
            keys=['OLD', 'FIT', 'NEW'],
            names=['label', 'field'], sort=False)

    def generate_report(self):
        path = os.path.join(
            pc.dirs['calib_logs'],
            f'{pc.filename_timestamp_str()}-arc_calibration')

    def make_summary_plots(self, n_threads_max=32, make_binder=True, mp=True):
        pass

    def make_arc_plot(self, posid):
        posmov = self.movedf.xs(posid, level='DEVICE_ID')
        poscal = self.calibdf.loc[posid, 'FIT']
        pcid = posmov['PETAL_LOC'].values[0]
        fig = plt.figure(figsize=(14, 8))
        for plot_row, axis in enumerate(['T', 'P']):
            other_axis = 'P' if axis == 'T' else 'T'
            axis_name = r'\theta' if axis == 'T' else r'\varphi'
            other_axis_name = r'\varphi' if axis == 'T' else r'\theta'
            tgt = posmov.xs(axis, level='axis')[f'tgt_posint{axis}']
            mea = posmov.xs(axis, level='axis')[f'mea_posint{axis}']
            other_tgt = posmov.xs(
                axis, level='axis')[f'tgt_posint{other_axis}'].median()
            rad = poscal[f'radius_{axis}'].mean()
            ctr = poscal[f'centre_{axis}']
            mea_xy = (posmov.xs(axis, level='axis')
                      [['mea_flatX', 'mea_flatY']].values)
            # column 1: cicle/arc plot in xy space
            ax = plt.subplot(2, 3, plot_row * 3 + 1)
            ang_i = np.degrees(np.arctan2(  # initial measured angle in deg
                mea_xy[0, 1] - ctr[1], mea_xy[0, 0] - ctr[0]))
            ang_f = ang_i + mea.diff().sum()  # final measured angle in deg
            if ang_i > ang_f:
                ang_f += 360
            ref_arc_ang = np.radians(np.append(  # 5 deg step
                np.arange(ang_i, ang_f, 5), ang_f))  # last point at final
            ref_arc_x = rad * np.cos(ref_arc_ang) + ctr[0]
            ref_arc_y = rad * np.sin(ref_arc_ang) + ctr[1]
            # where global observer would nominally see the axis's
            # local zero point in this plot
            ang_0 = ang_i - tgt[0]  # just use 1st point to get T/P offset
            line_0_x = [ctr[0], ctr[0]+rad*np.cos(np.radians(ang_0))]
            line_0_y = [ctr[1], ctr[1]+rad*np.sin(np.radians(ang_0))]
            plt.plot(ctr[0], ctr[1], 'k+')  # axis centre black +
            plt.plot(line_0_x, line_0_y, 'k--')  # zero line of posintTP
            plt.plot(ref_arc_x, ref_arc_y, 'b-')  # ref arc at 5 deg spacing
            plt.plot(mea_xy[:, 0], mea_xy[:, 1], 'ko')  # measured pts in black
            plt.plot(mea_xy[0, 0], mea_xy[0, 1], 'ro')  # 1st measured pt red
            txt_ang_0 = np.mod(ang_0+360, 360)
            txt_ang_0 = (txt_ang_0-180 if 90 < txt_ang_0 < 270
                         else txt_ang_0)
            txt_0 = (f'${axis_name}=0$\n'
                     f'$({other_axis_name}={other_tgt:.1f}\\degree)$')
            line_0 = np.append(np.concatenate([np.diff(line_0_x),
                                               np.diff(line_0_y)]), 0)  # 3D
            line_0_ctr = np.array([line_0_x, line_0_y]).mean(axis=1)  # 2D
            shift = np.cross(line_0, [0, 0, 0.21])[:2]
            txt_0_xy = line_0_ctr + np.sign(np.abs(txt_ang_0-270)-90) * shift
            plt.text(txt_0_xy[0], txt_0_xy[1], txt_0, fontsize=12,
                     rotation=txt_ang_0, ha='center', va='center')
            for i, xy in enumerate(mea_xy):
                ang_xy = np.arctan2(xy[1]-ctr[1], xy[0]-ctr[0])  # in rad
                txt_x = ctr[0] + rad*0.85*np.cos(ang_xy)
                txt_y = ctr[1] + rad*0.85*np.sin(ang_xy)
                plt.text(txt_x, txt_y, f'{i}', ha='center', va='center')
            if axis == 'T':
                calib_vals_txt = ''
                calib_keys = [
                    'LENGTH_R1', 'LENGTH_R2', 'OFFSET_T', 'OFFSET_P',
                    'GEAR_CALIB_T', 'GEAR_CALIB_P', 'OFFSET_X', 'OFFSET_Y']
                for key in calib_keys:
                    calib_vals_txt += f'{key:12s} = {poscal[key]:6.3f}\n'
                plt.text(
                    0.03, 0.97, calib_vals_txt, transform=ax.transAxes,
                    fontsize=8, color='gray', family='monospace',
                    ha='left', va='top',
                    bbox={'boxstyle': 'round', 'alpha': 0.8,
                          'facecolor': 'white', 'edgecolor': 'lightgrey'})
            plt.xlabel('flat$X$/mm')
            plt.ylabel('flat$Y$/mm')
            plt.title(f'measured ${axis_name}$ arc points')
            plt.grid(True)
            plt.axis('equal')
            # column 2: angle deviation as a function of target angle
            plt.subplot(2, 3, plot_row * 3 + 2)
            err_ang = mea - tgt
            plt.plot(tgt, err_ang, 'ko-')  # measured points
            plt.plot(tgt[0], err_ang[0], 'ro')  # 1st measured pt in red
            for i in tgt.index:
                plt.annotate(f'{i}', xy=(tgt[i], err_ang[i]), xytext=(0, 15),
                             textcoords='offset points',
                             ha='center', va='center')
            plt.xlabel(f'target ${axis_name} / \\degree$')
            plt.ylabel(f'$\\delta{axis_name} / \\degree$'.format(axis_name))
            plt.title(f'${axis_name}$ angle deviations')
            plt.grid(True)
            yr = max(err_ang) - min(err_ang)
            plt.ylim(top=plt.ylim()[1]+0.1*yr)
            # column 3: radius variations as a function of target angle
            plt.subplot(2, 3, plot_row * 3 + 3)
            err_rad = (poscal[f'radius_{axis}'] - rad) * 1000  # μm
            plt.plot(tgt, err_rad, 'ko-')
            plt.plot(tgt[0], err_rad[0], 'ro')
            for i in tgt.index:
                plt.annotate(f'{i}', xy=(tgt[i], err_rad[i]),xytext=(0, 15),
                             textcoords='offset points',
                             ha='center', va='center')
            plt.xlabel(f'target ${axis_name} / \\degree$')
            plt.ylabel(f'$\\delta R / \\mu$m'.format(axis_name))
            plt.title(r'radius variations')
            plt.grid(True)
            yr = max(err_rad) - min(err_rad)
            plt.ylim(top=plt.ylim()[1]+0.1*yr)
        fig.suptitle(f'Arc calibration {pc.timestamp_str(self.t_i)} '
                     f'Positioner {posid}')
        fig.tight_layout(pad=0.5, rect=[0, 0, 1, 0.95])
        path = os.path.join(
            self.dirs[pcid],
            '{posid}-{pc.filename_timestamp_str(self.t_i)}-arc_calib.pdf')
        # plt.savefig(path)
        # plt.close(fig)
        fig.savefig(r'D:\fig.pdf', bbox_inches='tight')

    def generate_data_products(self):
        self.read_telemetry()
        self.export_data_logs()
        # self.make_arc_plots()
        self.dump_as_one_pickle()  # loggers lost as they cannot be serialised
        if shutil.which('pandoc') is None:
            self.print('You must have a complete installation of pandoc '
                       'and/or TexLive. Skipping test report...')
        else:
            self.generate_report()  # requires pickle
        self.make_archive()


if __name__ == '__main__':
    '''load the dumped pickle file as follows, protocol is auto determined'''
    # arc calib expids
    expids = [38563]
    # grid calib expids
    # expids = ['00034382']
    from poscalibrationfits import PosCalibrationFits
    for expid in expids:
        paths = glob(pc.dirs['kpno']+f'/*/{expid:08}/*data.pkl')
        assert len(paths) == 1, paths
        print(f'Re-processing FP test data:\n{paths[0]}')
        # try:
        with open(os.path.join(paths[0]), 'rb') as h:
            data = pickle.load(h)
        path = os.path.join(os.path.dirname(paths[0]), 'data_arc.pkl.gz')
        data_arc = pd.read_pickle(path)
        fit = PosCalibrationFits()
        data.movedf, data.calib_fit = fit.calibrate_from_arc_data(data_arc)
        # try:
        #     calib_old = data.calibdf['OLD']
        #     calib_new = data.calibdf['NEW']
        # except:
        #     calib_old = data.calibdf.xs('OLD', level='label')
        #     calib_new = data.calibdf.xs('NEW', level='label')
        # data.write_calibdf(calib_old, calib_fit, calib_new)
        # data.movedf.index.set_names('axis', level='arc', inplace=True)
        # # # data.generate_data_products()
        data.export_data_logs()
        data.dump_as_one_pickle()
        # # if shutil.which('pandoc') is not None:
        # #     data.generate_report()
        data.make_archive()
        # except Exception as e:
        #     print(e)
        #     pass
