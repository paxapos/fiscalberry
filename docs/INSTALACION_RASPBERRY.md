# Guía de Instalación de Fiscalberry en Raspberry Pi (modo CLI)

Manual de instalación para Raspberry Pi (Raspberry Pi OS / Debian ARM) corriendo
Fiscalberry **headless** (sin interfaz gráfica), como servicio de systemd.

> **¿Por qué desde código fuente y no un ejecutable?**
> Los binarios precompilados que se publican en *Releases* (`fiscalberry-linux-*`,
> `fiscalberry-windows-*`) se generan con PyInstaller en runners **x86_64**, y
> PyInstaller **no hace cross-compile**: ese binario no corre en la arquitectura
> **ARM** de la Raspberry. Por eso en Raspberry el camino soportado es instalar
> desde código (`pip install`) y correr el **CLI**. Es liviano (no necesita Kivy,
> SDL ni entorno gráfico) y es justo el escenario para el que nació el proyecto.

---

## Requisitos Previos

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git libcups2-dev build-essential python3-dev
```

> En Raspberry Pi `python-escpos[all]` y `pycups` se compilan localmente; por eso
> hacen falta `build-essential`, `python3-dev` y `libcups2-dev`.

---

## 1. Instalación

### 1.1 Crear el entorno virtual (accesible para todos los usuarios)

```bash
sudo python3 -m venv /opt/fiscalberry-env
```

### 1.2 Clonar el repositorio (branch v3.0.x)

```bash
sudo rm -rf /opt/fiscalberry
sudo git clone --branch v3.0.x https://github.com/paxapos/fiscalberry.git /opt/fiscalberry
```

### 1.3 Instalar Fiscalberry (solo dependencias CLI, sin Kivy)

```bash
sudo /opt/fiscalberry-env/bin/pip install --upgrade pip
sudo /opt/fiscalberry-env/bin/pip install "/opt/fiscalberry[cli]"
```

> El extra `[cli]` instala únicamente las dependencias de consola
> (`requirements.cli.txt`): nada de Kivy. La instalación es más rápida y chica.

### 1.4 Verificar la instalación

```bash
ls -la /opt/fiscalberry-env/bin/ | grep fiscal
```

Deberías ver al menos `fiscalberry_cli`.

---

## 2. Crear el Lanzador Global

```bash
sudo tee /usr/local/bin/fiscalberry << 'EOF'
#!/bin/bash
/opt/fiscalberry-env/bin/fiscalberry_cli "$@"
EOF

sudo chmod +x /usr/local/bin/fiscalberry
```

La **primera vez** corré `fiscalberry` a mano para vincular el dispositivo
(el CLI muestra el link/QR de adopción contra Paxapos). Una vez adoptado,
la configuración queda en `~/.config/Fiscalberry/config.ini` y ya podés
dejarlo como servicio.

---

## 3. Configurar como Servicio (Inicio Automático)

```bash
sudo tee /etc/systemd/system/fiscalberry.service << 'EOF'
[Unit]
Description=Fiscalberry Server
Wants=network-online.target
After=network.target network-online.target

[Service]
Restart=always
RestartSec=10
Type=simple
ExecStart=/opt/fiscalberry-env/bin/fiscalberry_cli

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable fiscalberry
sudo systemctl start fiscalberry
sudo systemctl status fiscalberry
```

> El config se lee del `$HOME` del usuario que corre el servicio. Si corre como
> `root`, será `/root/.config/Fiscalberry/config.ini`. Adoptá el dispositivo con
> el **mismo usuario** que después correrá el servicio.

---

## 4. Comandos Útiles

| Acción                  | Comando                              |
| ----------------------- | ------------------------------------ |
| Iniciar servicio        | `sudo systemctl start fiscalberry`   |
| Detener servicio        | `sudo systemctl stop fiscalberry`    |
| Reiniciar servicio      | `sudo systemctl restart fiscalberry` |
| Ver estado              | `sudo systemctl status fiscalberry`  |
| Ver logs en tiempo real | `sudo journalctl -u fiscalberry -f`  |
| Ejecutar / adoptar      | `fiscalberry`                        |

---

## 5. Actualizar Fiscalberry

```bash
cd /opt/fiscalberry
sudo git pull
sudo /opt/fiscalberry-env/bin/pip install --upgrade "/opt/fiscalberry[cli]"
sudo systemctl restart fiscalberry
```

---

## 6. Desinstalar

```bash
sudo systemctl stop fiscalberry
sudo systemctl disable fiscalberry
sudo rm /etc/systemd/system/fiscalberry.service
sudo rm /usr/local/bin/fiscalberry
sudo rm -rf /opt/fiscalberry-env /opt/fiscalberry
sudo systemctl daemon-reload
```

---

## Notas

- Misma lógica que la [instalación Linux](./INSTALACION_LINUX.md); esta guía solo
  ajusta lo específico de ARM (sin binario, sin Kivy, branch `v3.0.x`).
- Para impresoras de red, asegurate de que la Raspberry y la impresora estén en la
  misma LAN/intranet. Para USB, el usuario del servicio debe tener permisos sobre el
  dispositivo (grupo `lp`/`dialout` según el caso).
