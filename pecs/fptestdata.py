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
import sys
from datetime import datetime, timezone
from io import StringIO
from shutil import make_archive
import pandas as pd
import logging
sys.path.append(os.path.abspath('../petal/'))
from posschedstats import PosSchedStats
import posconstants as pc


class FPTestData:

    timefmt = '%Y-%m-%dT%H:%M:%S%z'
    timefmtpath = '%Y_%m_%d-%H_%M_%S%z'
    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
        datefmt=timefmt)

    def __init__(self, test_name, petal_cfgs, test_cfg):

        self.test_name = f'{test_name}'
        self.test_time = datetime.now(timezone.utc).astimezone().isoformat(
                timespec='seconds')
        self.test_cfg = test_cfg  # one test configuration object
        self.simulate = test_cfg['simulate']
        self.petal_cfgs = petal_cfgs
        self.ptlids = petal_cfgs.keys()
        # create save dir for all files: logs, tables, pickels, gzips
        self.dir = os.path.join(
            pc.dirs['xytest_data'],
            f"{self.test_time.strftime(self.timefmtpath)}-{test_name}")
        self.dirs = {ptlid: os.path.join(self.dir, f'PTL_{ptlid}')
                     for ptlid in self.ptlids}
        # set up log files and loggers for each petal
        self.logs = {}
        self.log_paths = {}
        self.loggers = {}
        for ptlid in self.ptlids:
            self.log_paths[ptlid] = os.path.join(self.dirs[ptlid],
                                                 f'PTL_{ptlid}.log')
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
            logger.info(f'Petalconstants code version: {pc.code_version}')
            self._log_cfg(logger, petal_cfgs[ptlid])  # write configs to logs
            self._log_cfg(logger, test_cfg)
            self.logs[ptlid] = log  # assign logs and loggers to attributes
            self.loggers[ptlid] = logger
        self.logger.info('Simulation mode on: {self.simulate}')

    @staticmethod
    def _log_cfg(logger, config):
        '''ConfigObj module has an outstanding bug that hasn't been fixed.
        It can only write to real files and not in-memory virtual viles,
        such as StringIO objects, although its documentation claims support.
        We have to write by lines here.
        '''
        logger.debug('=== Config file dump: {config.filename} ===')
        for line in config.write(outfile=None):
            logger.debug(line)

    def logger(self):
        '''must call methods for particular logger levels below
        input message can be a string of list of strings
        '''
        def _log(self, lvl, msg):
            if type(msg) is list:
                map(_log, msg)
            elif type(msg) is list:
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
