#!/usr/bin/env python3
"""
p4a hook to inject foregroundServiceType into AndroidManifest.xml

This is required for Android 14+ (API 34+) where foreground services
MUST declare their type in the manifest.

Hook runs after the manifest is generated but before APK packaging.
"""

import os
import re
from pathlib import Path


def after_apk_build(toolchain):
    """
    Hook llamado después de generar el APK.
    No es el lugar correcto, pero lo dejamos por compatibilidad.
    """
    pass


def before_apk_build(toolchain):
    """
    Hook llamado ANTES de empaquetar el APK.
    Aquí modificamos el AndroidManifest.xml.
    """
    # Obtener dist_dir desde el toolchain
    dist_dir = toolchain.dist_dir if hasattr(toolchain, 'dist_dir') else None
    
    if not dist_dir:
        # Intentar obtener desde el contexto
        try:
            dist_dir = toolchain.ctx.dist_dir
        except:
            pass
    
    if not dist_dir:
        print("[p4a_hook] ⚠ No se pudo obtener dist_dir del toolchain")
        return
    
    manifest_path = Path(dist_dir) / "AndroidManifest.xml"
    
    if not manifest_path.exists():
        print(f"[p4a_hook] AndroidManifest.xml no encontrado en {manifest_path}")
        return
    
    print(f"[p4a_hook] Modificando AndroidManifest.xml para foregroundServiceType...")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest_content = f.read()
    
    # Buscar el service de Fiscalberry y agregar foregroundServiceType
    # El service se llama ServiceFiscalberryservice (generado por buildozer)
    # 
    # Tipos de foreground service:
    # - dataSync (1) = para RabbitMQ/SocketIO
    # - connectedDevice (16) = para impresoras Bluetooth
    # Combined: dataSync|connectedDevice = 17 (0x11)
    
    # Verificar si ya tiene foregroundServiceType
    if 'android:foregroundServiceType' in manifest_content:
        print("[p4a_hook] foregroundServiceType ya existe en el manifest")
        return
    
    # Patrón para encontrar el service element
    service_pattern = r'(<service[^>]*android:name="[^"]*[Ss]ervice[Ff]iscalberry[^"]*"[^>]*)(>)'
    
    # Agregar foregroundServiceType al service
    replacement = r'\1 android:foregroundServiceType="dataSync|connectedDevice"\2'
    
    new_content, count = re.subn(service_pattern, replacement, manifest_content)
    
    if count > 0:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[p4a_hook] ✓ foregroundServiceType agregado a {count} service(s)")
    else:
        print("[p4a_hook] ⚠ No se encontró el service para modificar")
        print("[p4a_hook] Buscando services en manifest...")
        
        # Debug: mostrar todos los services
        services = re.findall(r'<service[^>]*>', manifest_content)
        for svc in services:
            print(f"[p4a_hook]   - {svc[:100]}...")


# Hook alternativo para p4a más reciente
def before_apk_assemble(toolchain):
    """Alias para before_apk_build"""
    before_apk_build(toolchain)
