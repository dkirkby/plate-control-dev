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
from io import StringIO
from shutil import make_archive
import logging
sys.path.append(os.path.abspath('../petal/'))
from posschedstats import PosSchedStats
import posconstants as pc


class FPTestData:

    log_formatter = logging.Formatter(  # log format for each line
        fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
        datefmt='%Y/%m/%d %H:%M:%S')

    def __init__(self, test_name, petal_cfgs, test_cfg):

        self.test_name = f'{test_name}'
        self.test_cfg = test_cfg  # one test configuration object
        self.petal_ids = [str(petal_cfg['ptl_id']) for petal_cfg in petal_cfgs]
        self.dir = pc.dirs['xytest_data']

        # set up log files and loggers for each petal
        self.petal_cfgs = {}
        self.logs = {}
        self.logger = {}
        for i, petal_id in enumerate(self.petal_ids):
            self.petal_cfgs[petal_id] = petal_cfgs[i]
            # create virtual file object for storing log entries
            # using stringio because it supports write() and flush()
            log = StringIO(newline='\n')
            # craete a new logger for each petal by unique logger name
            logger = logging.getLogger(f'PTL_{petal_id}')
            logger.handlers = []  # clear handlers that might exisit already
            logger.setLevel(logging.DEBUG)  # log everything, DEBUG level up
            fh = logging.StreamHandler(stream=self.log)  # pseudo-file handler
            ch = logging.StreamHandler()  # console handler, higher log level
            ch.setLevel(logging.INFO)  # only stdout INFO or more severe logs
            ch.setFormatter(self.log_formatter)
            fh.setFormatter(self.log_formatter)
            logger.addHandler(ch)
            logger.addHandler(fh)
            # write configs to logs first
            logger.info(f'Logger initialised for PTL_{petal_id} ===')
            self._log_cfg(logger, petal_cfgs[i])
            self._log_cfg(logger, test_cfg)
            # assign logger to self.loggers attribute
            self.logs[petal_id] = log
            self.loggers[petal_id] = logger

    @staticmethod
    def _log_cfg(logger, config):
        '''ConfigObj module has an outstanding bug that hasn't been fixed.
        It can only write to real files and not in-memory virtual viles,
        such as StringIO objects, although its documentation claims support.
        We have to write by lines here.
        '''
        logger.debug('=== Config file: {config.filename} ===')
        for line in config.write(outfile=None):
            logger.debug(line)

