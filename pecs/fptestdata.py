# -*- coding: utf-8 -*-
"""
Created on Thu May 23 22:18:28 2019

@author: Duan Yutong

Store xy test, anti-collision data in a class for debugging.
Most fields are dictionaries indexed by petal id:

FPTestData.petal_cfgs[petal_id]:    hw setup file for each petal
FPTestData.logs[petal_id]:          StringIO object equivalent to log file
FPTestData.loggers[petal_id]:       logger which writes new lines to log file

"""
import os
from datetime import datetime, timezone
from itertools import product
from io import StringIO
from shutil import copyfileobj
import pickle
import numpy as np
import pandas as pd
import logging
from posschedstats import PosSchedStats
import posconstants as pc

idx = pd.IndexSlice


class FPTestData:
    ''' data will be saved in:
            /xytest_data/{time}-{test_name}/PTL{ptlid}/*.*
    '''

    timefmt = '%Y-%m-%dT%H:%M:%S%z'
    timefmtpath = '%Y_%m_%d-%H_%M_%S%z'
    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
        datefmt=timefmt)

    @property
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
        # set up log files and loggers for each petal
        self.logs = {}
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
        # idx = pd.IndexSlice
        # df.loc[idx[:, '01', 0], 'timestamp']
        # df.loc[idx[0, '01', [0,1,2,3]], ['timestamp', 'cycle']]
        # df.loc[0, '01', :5][['timestamp', 'cycle']]

    def export_move_data(self):
        '''must have writte self.posids_ptl, a dict keyed by ptlid'''
        self.movedf.to_pickle(os.path.join(self.dir, 'move_df.pkl'),
                              compression='gzip')
        self.movedf.to_csv(os.path.join(self.dir, 'move_df.csv'))
        for ptlid in self.ptlids:
            os.makedirs(self.dirs[ptlid], exist_ok=True)
            def makepath(fn): return os.path.join(self.dirs[ptlid], fn)
            for posid in self.posids_ptl[ptlid]:  # write move data csv
                df_pos = self.movedf.loc[idx[:, posid], :].droplevel(1)
                df_pos.to_pickle(makepath(f'{posid}_df.pkl'),
                                 compression='gzip')
                df_pos.to_csv(makepath(f'{posid}_df.csv'))
            with open(makepath(f'ptl_{ptlid}_export.log'), 'w') as handle:
                self.logs[ptlid].seek(0)
                copyfileobj(self.logs[ptlid], handle)  # write final logs

    def dump_as_one_pickle(self):
        with open(os.path.join(self.dir, 'data_dump.pkl'), 'wb') as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)
