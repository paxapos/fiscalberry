#!/usr/bin/env python
# coding=utf-8

import tornado.ioloop
import signal
import os.path
import logging
from FiscalberryApp import FiscalberryApp
from threading import Thread




if __name__ == "__main__":
	# chdir otherwise will not work fine in rc service
	
	fbserver = FiscalberryApp()
