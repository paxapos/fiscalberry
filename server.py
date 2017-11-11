#!/usr/bin/env python
# coding=utf-8


from FiscalberryApp import FiscalberryApp

if __name__ == "__main__":
    # chdir otherwise will not work fine in rc service

    fbserver = FiscalberryApp()
    fbserver.start()
