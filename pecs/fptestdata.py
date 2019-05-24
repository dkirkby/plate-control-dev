# -*- coding: utf-8 -*-
"""
Created on Thu May 23 22:18:28 2019

@author: Duan Yutong

Store xy test, anti-collision data in a class for debugging

"""
from io import StringIO
import logging
# sys.path.append(os.path.abspath('../petal/'))
# from posschedstats import PosSchedStats


class FPTestData:

    def __init__(self, test_name, petal_id):

        # set uplogging
        name = f'{test_name} - {petal_id}'
        # create virtual file stream for storing entries
        self.log = StringIO(f'Logger initialised for {name}', newline='\n')
        self.logger = logging.getLogger(name)
        self.logger.handlers = []  # clear handlers that might exisit
        self.logger.setLevel(logging.DEBUG)  # log everything from DEBUG level
        fh = logging.StreamHandler(stream=self.log)  # pseudo-file handler
        ch = logging.StreamHandler()  # console handler with higher log level
        ch.setLevel(logging.INFO)  # only show INFO or mroe severe logs stdout
        formatter = logging.Formatter(  # log format for each line
            fmt='%(asctime)s %(name)s [%(levelname)s]: %(message)s',
            datefmt='%Y/%m/%d %H:%M:%S')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        self.logger.addHandler(ch)
        self.logger.addHandler(fh)
        