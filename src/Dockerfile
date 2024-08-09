FROM python:3-slim-bullseye

WORKDIR /usr/src/app
EXPOSE 12000


COPY requirements.txt ./
COPY . .
RUN ls
RUN pip install -r requirements.txt


CMD [ "python", "server.py" ]

ENV CONFIG_FILE_PATH="./"


# luego buildear la imagen esta
# docker build -t fiscalberry2 . 

#para buildear asw
# docker build -t yoalevilar/fiscalberry:3 . --no-cache

# y ejecutarlo asi:
# en la carpeta openvpn guardar todos los archivos de config para conectar con openvpn server
# docker run -d --name fiscalberry --privileged --env=CONFIG_FILE_PATH=/fiscalberry --volume=C:\fiscalberry:/fiscalberry -p 12000:12000 --restart=always yoalevilar/fiscalberry:3