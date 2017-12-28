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

echo -n "Instalar el servicio fiscalberry.service (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	cp fiscalberry.service /etc/systemd/system/
    cd /etc/systemd/system/
	sudo systemctl start fiscalberry.service
    echo "Se inicializo el servicio "
else
    echo "Finalizó todo correctamente sin instalar el servicio. Deberá iniciarlo manualmente."
fi

echo "este el el hostname:"
hostname
echo "no olvides poner el hostname en el archivo /etc/hosts"
