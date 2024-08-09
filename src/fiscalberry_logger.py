
import logging
import logging.config
import os


root = os.path.dirname(os.path.abspath(__file__))
loginFile = root+'/logging.ini'
if os.path.isfile(loginFile):
    logging.config.fileConfig(loginFile)
    

def getLogger():
    return logging.getLogger()