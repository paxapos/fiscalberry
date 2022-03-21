#!/bin/bash
echo "Para instalar es necesario ser superusuario"

apt install python3-dev build-essential libjpeg-dev nmap python3-pip
pip3 install --upgrade pip
pip3 install -r requirements.txt


echo -n "Instalar el servicio fiscalberry.service (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
  echo "Instalar con SocketIO:"
  echo "n - Sin SocketIO"
  echo "1 - Server"
  echo "2 - Client"
  read -p "Ingrese la opción: " answersio
  case "$answersio" in
    n|N) sudo cp fiscalberry.service /etc/systemd/system/ ;;
    1) sudo cp fiscalberry-sios.service /etc/systemd/system/fiscalberry.service ;;
    2) sudo cp fiscalberry-sioc.service /etc/systemd/system/fiscalberry.service ;;
  esac
  cd /etc/systemd/system/
  sudo systemctl enable fiscalberry.service
  echo "Se instaló todo OK para iniciar servicio ahora "
  echo "ejecutar systemctl start fiscalberry.service"
  echo "caso contrario se iniciara cuando reinicie la PC"
else
  echo "Finalizó todo correctamente sin instalar el Daemon ni el servicio. Deberá iniciarlos manualmente."
fi
