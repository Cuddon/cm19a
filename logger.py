#!/bin/python

import logging,  datetime

#LOG_FILENAME = 'AVC_deviceManager.log'

def start_logging(modulename = 'main',  logfilename = "pythonlogger.log",  display = "N"):
    """Starts the logging service an returns the logging instance
        LEVELS:
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL}
    """

    logging.basicConfig(filename = logfilename, filemode = "w",
                    level = logging.DEBUG,
                    format = '%(asctime)s, %(levelname)s, %(message)s', 
                    datefmt = '%a %d %b %Y %H:%M:%S')

    logger = logging.getLogger(modulename)
    now = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    logger.info('---- Starting logging at: %s ----' % now)

    return logger
