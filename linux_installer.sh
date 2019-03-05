#!/bin/bash
echo "para instalar es necesario ser superusuario "
sudo su 


apt-get install python-pip build-essential python-dev python-imaging python-setuptools libjpeg-dev nmap
pip install --upgrade pip
pip install -r requirements.txt

echo -n "Crear daemond fiscalberry-server-rc (y/n)? (default no)"
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
    sudo systemctl enable fiscalberry.service
    sudo systemctl start fiscalberry.service
    echo "Se inicializo el servicio "
  else
    echo "Finalizó todo correctamente sin instalar el daemond ni el servicio. Deberá iniciarlos manualmente."
  fi
fi
