# Impresora USB en Windows que "cambia de puerto" y deja de imprimir

## Qué pasa

Windows crea un puerto virtual (`USB001`, `USB002`, …) por cada vez que
"descubre" la impresora. Si la impresora no tiene número de serie USB (muchas
térmicas, entre ellas Hasar), Windows la identifica por el lugar físico donde
está enchufada. Ante un microcorte, el ahorro de energía USB o un cambio de
driver, la vuelve a descubrir y le da un puerto **nuevo**. La cola de la
impresora queda en el puerto viejo, que ya no existe, y los trabajos se traban.

No es un error de Fiscalberry: lo provoca Windows. Pero antes Fiscalberry no
se daba cuenta: el trabajo quedaba trabado en Windows y lo daba por impreso.

## Qué hace Fiscalberry ahora (driver `Win32Raw`)

1. **Antes de imprimir**, si la cola apunta a un puerto USB muerto y la misma
   impresora apareció en otro puerto:
   - mueve la cola al puerto nuevo (necesita el permiso del paso 4 del script), o
   - si no tiene permiso, imprime por otra cola de la misma impresora que ya
     esté en el puerto nuevo (la "Copia 1" que a veces crea Windows).
2. **Después de imprimir** espera a que el trabajo salga de la cola de Windows.
   Si se traba, lo cancela (para que no salga duplicado) y lo reintenta más
   tarde. El ticket no se pierde.
3. **En pantalla** muestra qué pasa y qué hacer, en palabras simples, separando
   si el problema es de la impresora (papel, tapa, apagada, cable) o de la
   computadora (Windows perdió la impresora, impresora pausada). También lo
   publica por MQTT como `PRINTER_PROBLEM`, con `context.mensaje_usuario`
   listo para mostrar.

Si una impresora puntual se comporta raro con la verificación, se puede apagar:

```ini
[Paxaprinter]
verificar_impresion_windows = false
```

## Dejar Windows configurado (una vez, como administrador)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\configurar_impresora_usb.ps1 -Impresora "Nombre de la cola"
```

El script:

- apaga la suspensión selectiva de USB y el apagado de dispositivos USB por
  ahorro de energía;
- evita que Windows Update reemplace drivers;
- da a los usuarios del equipo permiso de **Administrar esta impresora** sobre
  esa cola, para que Fiscalberry pueda corregir el puerto solo;
- lista los puertos USB de impresora que conoce Windows y en cuál está la cola.

Además:

- Enchufar la impresora siempre en el mismo puerto, atrás de la PC (no al
  frente, ni a un hub o alargue), con un cable corto y en buen estado.
- Si el listado muestra muchos puertos "desconectada" de la misma impresora,
  Windows la está re-detectando seguido: revisar cable, puerto y fuente.
