#!/usr/bin/env python3
# coding=utf-8

from multiprocessing import freeze_support

from FiscalberryApp import FiscalberryApp


if __name__ == "__main__":
	freeze_support()
	fbserver = FiscalberryApp()

	