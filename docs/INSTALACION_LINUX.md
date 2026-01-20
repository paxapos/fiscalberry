# Guía de Instalación de Fiscalberry en Linux

Manual de instalación para usuarios finales en Linux Mint / Ubuntu.

---

## Requisitos Previos

```bash
sudo apt install python3-pip python3-venv git libcups2-dev build-essential
```

---

## 1. Instalación

### 1.1 Crear el entorno virtual (accesible para todos los usuarios)

```bash
sudo python3 -m venv /opt/fiscalberry-env
```

### 1.2 Clonar el repositorio

```bash
# Si ya existe una versión anterior, hacer backup
sudo cp -r /opt/fiscalberry /opt/fiscalberry_backup_$(date +%Y%m%d)

# Clonar el repositorio
sudo rm -rf /opt/fiscalberry
sudo git clone https://github.com/paxapos/fiscalberry.git /opt/fiscalberry
```

### 1.3 Instalar Fiscalberry

```bash
sudo /opt/fiscalberry-env/bin/pip install /opt/fiscalberry
```

### 1.4 Verificar la instalación

```bash
ls -la /opt/fiscalberry-env/bin/ | grep fiscal
```

Deberías ver:

- `fiscalberry_cli`
- `fiscalberry_gui`

---

## 2. Crear el Lanzador Global

Para que todos los usuarios puedan ejecutar `fiscalberry` desde cualquier terminal:

```bash
sudo tee /usr/local/bin/fiscalberry << 'EOF'
#!/bin/bash
source /opt/fiscalberry-env/bin/activate
/opt/fiscalberry-env/bin/fiscalberry_cli "$@"
EOF

sudo chmod +x /usr/local/bin/fiscalberry
```

---

## 3. Configurar como Servicio (Inicio Automático)

### 3.1 Crear el archivo de servicio

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
```

### 3.2 Habilitar e iniciar el servicio

```bash
# Recargar systemd
sudo systemctl daemon-reload

# Habilitar inicio automático
sudo systemctl enable fiscalberry

# Iniciar el servicio
sudo systemctl start fiscalberry

# Verificar estado
sudo systemctl status fiscalberry
```

---

## 4. Crear Acceso Directo en el Menú

```bash
sudo tee /usr/share/applications/fiscalberry.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Fiscalberry
Comment=Sistema de impresión fiscal
Exec=/usr/local/bin/fiscalberry
Icon=printer
Terminal=true
Categories=Office;Finance;
StartupNotify=true
EOF
```

---

## 5. Comandos Útiles

| Acción                  | Comando                              |
| ----------------------- | ------------------------------------ |
| Iniciar servicio        | `sudo systemctl start fiscalberry`   |
| Detener servicio        | `sudo systemctl stop fiscalberry`    |
| Reiniciar servicio      | `sudo systemctl restart fiscalberry` |
| Ver estado              | `sudo systemctl status fiscalberry`  |
| Ver logs en tiempo real | `sudo journalctl -u fiscalberry -f`  |
| Ejecutar manualmente    | `fiscalberry`                        |

---

## 6. Actualizar Fiscalberry

```bash
cd /opt/fiscalberry
sudo git pull
sudo /opt/fiscalberry-env/bin/pip install --upgrade /opt/fiscalberry
sudo systemctl restart fiscalberry
```

---

## 7. Desinstalar

```bash
sudo systemctl stop fiscalberry
sudo systemctl disable fiscalberry
sudo rm /etc/systemd/system/fiscalberry.service
sudo rm /usr/local/bin/fiscalberry
sudo rm /usr/share/applications/fiscalberry.desktop
sudo rm -rf /opt/fiscalberry-env
sudo rm -rf /opt/fiscalberry
sudo systemctl daemon-reload
```

---

## Solución de Problemas

### Error: "GLIBC_2.38 not found"

Si usás un ejecutable precompilado y aparece este error, tu sistema operativo es muy antiguo. Usá la instalación desde código fuente (este manual).

### Error: "pycups" no compila

Instalá las dependencias de desarrollo:

```bash
sudo apt install libcups2-dev build-essential python3-dev
```

### El servicio no inicia

Verificá los logs:

```bash
sudo journalctl -u fiscalberry -n 50
```

---

## Notas

- El archivo de configuración se guarda en `~/.config/Fiscalberry/config.ini` del usuario que ejecuta el servicio
- Si el servicio corre como root, el config estará en `/root/.config/Fiscalberry/config.ini`
