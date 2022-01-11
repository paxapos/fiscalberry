#!/usr/bin/env python3
import os
import argparse
import daemon
import sys
import logging
from daemon import pidfile
from FiscalberryApp import FiscalberryApp


def do_something():
    ### This does the "work" of the daemon
    fbserver = FiscalberryApp()
    fbserver.discover()
    fbserver.start()


def start_daemon(pidf, logf):
    ### This launches the daemon in its context
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler('/var/log/fiscalberry_daemon.log')
    logger.addHandler(handler)



    rootpath = os.path.dirname(os.path.abspath(__file__))
    ### XXX pidfile is a context
    with daemon.DaemonContext(
        stdout=handler.stream,
        stderr=handler.stream,
        working_directory=rootpath,
        umask=0o002,
        pidfile=pidfile.TimeoutPIDLockFile(pidf),
        files_preserve=[handler.stream]
        ) as context:
        do_something()


if __name__ == "__main__":
    

    parser = argparse.ArgumentParser(description="PaxaPos Daemon Service")
    parser.add_argument('-p', '--pid-file', default='/var/run/fiscalberry.pid')
    parser.add_argument('-l', '--log-file', default='/var/log/fiscalberry.log')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file, logf=args.log_file)