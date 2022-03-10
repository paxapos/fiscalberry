#!/bin/bash
echo "Para instalar es necesario ser superusuario"

apt install python3-dev build-essential libjpeg-dev nmap python3-pip
pip3 install --upgrade pip
pip3 install -r requirements.txt


echo -n "Instalar el servicio fiscalberry.service (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
  sudo cp fiscalberry.service /etc/systemd/system/
  cd /etc/systemd/system/
  sudo systemctl enable fiscalberry.service
  echo "Se instaló todo OK para iniciar servicio ahora "
  echo "ejecutar systemctl start fiscalberry.service"
  echo "caso contrario se iniciara cuando reinicie la PC"
else
  echo "Finalizó todo correctamente sin instalar el Daemon ni el servicio. Deberá iniciarlos manualmente."
fi
