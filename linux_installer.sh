#!/bin/bash

if (($EUID != 0)); then
  if [[ -t 1 ]]; then
    sudo "$0" "$@"
  else
    exec 1>output_file
    gksu "$0 $@"
  fi
  exit
fi

apt-get install python-pip build-essential python-dev python-imaging python-serial python-setuptools libjpeg-dev
pip install pyserial
pip install tornado
pip install python-escpos

cp fiscalberry-server-rc /etc/init.d/
sed "s@WRITEPATHHERE@$(pwd)@" fiscalberry-server-rc > /etc/init.d/fiscalberry-server-rc

echo -n "Crear daemond fiscalberry-server-rc (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	sudo update-rc.d fiscalberry-server-rc defaults
    echo "Se configuró el daemond"
else
    echo "Finalizó todo correctamente sin instalar el daemond. Deberá iniciarlo manualmente."
fi