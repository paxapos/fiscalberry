# APK Estable - Fiscalberry CLI

## Ubicación Permanente

**Desktop:** `~/Desktop/fiscalberry_apks_estables/fiscalberry-cli-2.0.1-STABLE-20251211.apk`

## Info

- **Build:** 2025-12-11 00:45
- **Tamaño:** 44 MB
- **Arqs:** ARM64-v8a + ARMv7a

## ✅ Probado Exitosamente

- SocketIO: ✅ Conectado
- RabbitMQ: ✅ Consumer funcionando
- Canvas: ✅ No se bloquea en pause/resume
- Background: ✅ Mantiene conexiones

## Configuración

```
Bootstrap: sdl2 (no webview)
Main: src/android_cli/main.py
Service: android_cli/android_service.py
Recipes: my_recipes (pyjnius Python 3.12 fix)
```

## Instalación

```bash
adb install -r fiscalberry-cli-2.0.1-STABLE-20251211.apk
```
