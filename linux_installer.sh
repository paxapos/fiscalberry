#!/bin/bash
echo "para instalar es necesario ser superusuario "


apt-get install python-pip build-essential python-dev libjpeg-dev nmap
pip install --upgrade pip
pip install -r requirements.txt


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
  echo "Finalizó todo correctamente sin instalar el daemond ni el servicio. Deberá iniciarlos manualmente."
fi
