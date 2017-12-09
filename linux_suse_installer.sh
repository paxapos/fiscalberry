#!/bin/bash

zypper install python-pip build-essential python-dev python-imaging 
python-setuptools libjpeg-dev nmap
pip install pyserial
pip install python-nmap
pip install requests
pip install tornado
pip install python-escpos
pip install pyutf8
pip install python-daemon


echo "este el el hostname:"
hostname
echo "no olvides poner el hostname en el archivo /etc/hosts"
