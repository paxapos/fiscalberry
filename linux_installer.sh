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

apt-get install python-pip build-essential python-dev python-imaging python-setuptools libjpeg-dev nmap
pip install pyserial
pip install python-nmap
pip install requests
pip install tornado
pip install python-escpos
pip install pyutf8
pip install PyJWT

echo -n "Crear daemond fiscalberry-server-rc (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	cp fiscalberry-server-rc /etc/init.d/
	sed "s@WRITEPATHHERE@$(pwd)@" fiscalberry-server-rc > /etc/init.d/fiscalberry-server-rc
	sudo update-rc.d fiscalberry-server-rc defaults
  echo "Se configuró el daemond"
else
  echo -n "Instalar el servicio fiscalberry.service (y/n)? "
  read answer
  if echo "$answer" | grep -iq "^y" ;then
    sudo cp fiscalberry.service /etc/systemd/system/
    cd /etc/systemd/system/
    sudo systemctl start fiscalberry.service
    echo "Se inicializo el servicio "
  else
    echo "Finalizó todo correctamente sin instalar el daemond ni el servicio. Deberá iniciarlos manualmente."
  fi
fi
