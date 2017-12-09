#!/usr/bin/env python2.7
import os
import argparse
import daemon
from daemon import pidfile
from FiscalberryApp import FiscalberryApp



def do_something(fbrry):
    ### This does the "work" of the daemon
    while True:
        fbrry.start()


def start_daemon(pidf, fbrry):
    ### This launches the daemon in its context

    rootpath = os.path.dirname(__file__)
    ### XXX pidfile is a context
    with daemon.DaemonContext(
        working_directory=rootpath,
        umask=0o002,
        pidfile=pidfile.TimeoutPIDLockFile(pidf),
        ) as context:
        do_something(fbrry)


if __name__ == "__main__":
    fbserver = FiscalberryApp()

    parser = argparse.ArgumentParser(description="Example daemon in Python")
    parser.add_argument('-p', '--pid-file', default='/var/run/fiscalberry.pid')

    args = parser.parse_args()

    start_daemon(pidf=args.pid_file, fbrry=fbserver)