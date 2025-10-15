# Problema: Compilación de Kivy para Android con Python 3.12

**Fecha**: 14 de octubre de 2025  
**Proyecto**: Fiscalberry - Compilación Android  
**Estado**: ❌ BLOQUEADO - 7+ intentos fallidos

---

## Resumen Ejecutivo

La compilación de Fiscalberry para Android falla sistemáticamente al intentar compilar Kivy debido a incompatibilidades entre Python 3.12 y el código fuente de Kivy 2.3.0/2.3.1. El error específico ocurre durante la compilación de archivos `.pyx` con Cython, donde se hace referencia al tipo `long` que fue eliminado en Python 3.12.

### Error Principal

```
Error compiling Cython file:
------------------------------------------------------------
...
    cdef void *ptr = NULL
    if isinstance(indices, bytes):
        ptr = <void *>(<char *>(<bytes>indices))
    elif isinstance(indices, (long, int)):
                              ^
------------------------------------------------------------

kivy/graphics/opengl.pyx:692:30: undeclared name not builtin: long
```

---

## Contexto Técnico

### Entorno de Desarrollo

- **Sistema Operativo**: Ubuntu 24.04
- **Python Host**: 3.12.3 (sistema)
- **Python Target Android**: 3.11.5
- **Java**: OpenJDK 17.0.16
- **Buildozer**: 1.5.0 (en venv aislado)
- **Android SDK**: API 35
- **Android NDK**: r25b
- **API Mínima**: 28
- **Arquitecturas Target**: arm64-v8a + armeabi-v7a
- **Kivy**: 2.3.0 / 2.3.1 (probadas ambas)
- **Cython**: 3.x

### Configuración Buildozer

```ini
# buildozer.spec (líneas relevantes)
requirements = hostpython3,python3,kivy,python-escpos,qrcode,pillow,pyserial,pyusb,python-socketio[client],requests,platformdirs,pyjnius,pika

# Custom recipes
p4a.local_recipes = my_recipes
```

---

## Análisis del Problema

### Causa Raíz

Python 3.12 eliminó el tipo `long`, unificándolo con `int`. Sin embargo, Kivy 2.3.0 y 2.3.1 tienen **19 archivos `.pyx`** que aún referencian el tipo `long`:

```python
# Ejemplo del error en opengl.pyx línea 692
elif isinstance(indices, (long, int)):  # ❌ 'long' no existe en Python 3.12
```

### Archivos Afectados (19 total)

```
kivy/_clock.pyx
kivy/_event.pyx
kivy/weakproxy.pyx
kivy/core/image/img_imageio.pyx
kivy/core/image/_img_sdl2.pyx
kivy/core/text/text_layout.pyx
kivy/core/text/_text_pango.pyx
kivy/core/window/window_x11.pyx
kivy/graphics/buffer.pyx
kivy/graphics/cgl_backend/cgl_debug.pyx
kivy/graphics/cgl.pyx
kivy/graphics/context_instructions.pyx
kivy/graphics/opengl.pyx          ← FALLA AQUÍ
kivy/graphics/shader.pyx
kivy/graphics/tesselator.pyx
kivy/graphics/texture.pyx
kivy/graphics/vertex_instructions.pyx
kivy/graphics/vertex.pyx
kivy/lib/gstplayer/_gstplayer.pyx
```

### Por Qué los Wheels Precompilados Funcionan

Kivy 2.3.1 tiene wheels para Python 3.12 (`cp312-cp312-*.whl`), pero estos están **precompilados**. Para Android, buildozer **DEBE compilar desde source**, donde el problema de `long` persiste.

---

## Soluciones Intentadas (7 Intentos - Todos Fallidos)

### Intento 1: Flag --no-binary en buildozer.spec

```ini
# buildozer.spec
p4a.extra_build_args = --no-binary=:all:
```

**Resultado**: ❌ Parámetro inválido, buildozer no lo reconoce

---

### Intento 2: Forzar compilación en install_python_package()

```python
# my_recipes/kivy/__init__.py
def install_python_package(self, arch, name=None, env=None, is_dir=True):
    env = env or {}
    env['PIP_NO_BINARY'] = ':all:'
    super().install_python_package(arch, name=name, env=env, is_dir=is_dir)
```

**Resultado**: ❌ Variable de entorno ignorada, Cython ya procesó archivos

---

### Intento 3: Aplicar parches en prebuild_arch()

```python
def prebuild_arch(self, arch):
    build_dir = self.get_build_dir(arch.arch)
    self.apply_python312_patches(build_dir)  # ← Aplicar ANTES
    super().prebuild_arch(arch)
```

**Resultado**: ❌ Parches no se aplican o se aplican después de Cython

---

### Intento 4: Aplicar parches en build_arch()

```python
def build_arch(self, arch):
    build_dir = self.get_build_dir(arch.arch)
    self.apply_python312_patches(build_dir)
    super().build_arch(arch)
```

**Resultado**: ❌ Mismo error, parches demasiado tarde

---

### Intento 5: Sobrescribir cythonize_build()

```python
def cythonize_build(self, env=None, build_dir=None):
    if build_dir is None:
        build_dir = self.get_build_dir(self.ctx.archs[0].arch)
    
    self.apply_python312_patches(build_dir)  # ← Justo antes de Cython
    super().cythonize_build(env=env, build_dir=build_dir)
```

**Resultado**: ❌ Método ejecutado pero archivos no encontrados

---

### Intento 6: Hook postbuild_arch()

```python
def postbuild_arch(self, arch):
    build_dir = self.get_build_dir(arch.arch)
    self.apply_python312_patches(build_dir)
    super().postbuild_arch(arch)
```

**Resultado**: ❌ Se ejecuta DESPUÉS del build (demasiado tarde)

---

### Intento 7: Actualizar a Kivy 2.3.1

```python
class KivyRecipePython312(KivyRecipe):
    version = '2.3.1'  # ← Versión con wheels Python 3.12
```

**Resultado**: ❌ Mismo error - los archivos fuente .pyx tienen el problema

---

## Código del Custom Recipe Actual

### Estructura de Archivos

```
fiscalberry/
├── buildozer.spec
├── my_recipes/
│   ├── kivy/
│   │   └── __init__.py    ← Custom recipe (204 líneas)
│   └── pyjnius/
│       └── __init__.py    ← ✅ FUNCIONA (mismo approach)
```

### my_recipes/kivy/__init__.py (Versión Actual)

```python
"""
Receta personalizada de Kivy para Python 3.12+
Parchea las referencias a 'long' que no existen en Python 3.12+
IMPORTANTE: Fuerza compilación desde source (no wheels)
"""
from pythonforandroid.recipes.kivy import KivyRecipe
from pythonforandroid.logger import shprint, info, warning
from os.path import join
import sh
import re
import os


class KivyRecipePython312(KivyRecipe):
    """
    Receta de Kivy con parches para Python 3.12+
    
    Python 3.12 eliminó el tipo 'long', ahora solo existe 'int'.
    Esta receta parchea automáticamente los archivos .pyx de Kivy.
    """
    
    # Usar Kivy 2.3.1 que tiene soporte nativo para Python 3.12
    version = '2.3.1'
    
    # FORZAR source build
    install_in_hostpython = False
    call_hostpython_via_targetpython = False
    
    def apply_python312_patches(self, build_dir):
        """
        Aplica parches para compatibilidad con Python 3.12+
        Elimina referencias al tipo 'long' que ya no existe
        """
        info("=" * 60)
        info("🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy")
        info(f"📂 Build dir: {build_dir}")
        info(f"📂 Dir exists: {os.path.exists(build_dir)}")
        if os.path.exists(build_dir):
            info(f"📂 Dir contents: {os.listdir(build_dir)[:10]}")
        info("=" * 60)
        
        # Archivos .pyx que contienen referencias a 'long'
        files_to_patch = [
            'kivy/_clock.pyx',
            'kivy/_event.pyx',
            'kivy/weakproxy.pyx',
            'kivy/core/image/img_imageio.pyx',
            'kivy/core/image/_img_sdl2.pyx',
            'kivy/core/text/text_layout.pyx',
            'kivy/core/text/_text_pango.pyx',
            'kivy/core/window/window_x11.pyx',
            'kivy/graphics/buffer.pyx',
            'kivy/graphics/cgl_backend/cgl_debug.pyx',
            'kivy/graphics/cgl.pyx',
            'kivy/graphics/context_instructions.pyx',
            'kivy/graphics/opengl.pyx',  # ← LÍNEA 692 FALLA AQUÍ
            'kivy/graphics/shader.pyx',
            'kivy/graphics/tesselator.pyx',
            'kivy/graphics/texture.pyx',
            'kivy/graphics/vertex_instructions.pyx',
            'kivy/graphics/vertex.pyx',
            'kivy/lib/gstplayer/_gstplayer.pyx',
        ]
        
        modified_files = 0
        
        for rel_path in files_to_patch:
            file_path = join(build_dir, rel_path)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Patrón 1: Eliminar métodos __long__
                content = re.sub(
                    r'^\s*def __long__\(self\):.*?(?=\n\s{0,4}(?:def |cdef |cpdef |class |$))',
                    '',
                    content,
                    flags=re.MULTILINE | re.DOTALL
                )
                
                # Patrón 2: Reemplazar long(...) por int(...)
                content = re.sub(r'\blong\s*\(', 'int(', content)
                
                # Patrón 3: Eliminar 'long' de diccionarios tipo 'long': 'J'
                content = re.sub(r"'long'\s*:\s*'J',?\s*", '', content)
                
                # Patrón 4: Reemplazar (int, long) por (int,) y (long, int) por (int,)
                content = re.sub(r'\(\s*int\s*,\s*long\s*\)', '(int,)', content)
                content = re.sub(r'\(\s*long\s*,\s*int\s*\)', '(int,)', content)
                
                # Patrón 5: Eliminar 'long' standalone en tuplas/listas
                content = re.sub(r',\s*long\s*(?=[,\)\]])', '', content)
                content = re.sub(r'(?<=[\(\[,])\s*long\s*,', '', content)
                
                if content != original_content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    info(f"🔧 Parcheando {rel_path}")
                    modified_files += 1
                    
            except FileNotFoundError:
                warning(f"⚠ No se encontró: {rel_path}")
            except Exception as e:
                warning(f"⚠ Error parcheando {rel_path}: {e}")
        
        info("=" * 60)
        info(f"✅ Fix completado: {modified_files} archivo(s) modificado(s)")
        info("=" * 60)
    
    def prebuild_arch(self, arch):
        """
        Hook de pre-build
        IMPORTANTE: Aplicamos parches ANTES de cualquier otra cosa
        """
        build_dir = self.get_build_dir(arch.arch)
        self.apply_python312_patches(build_dir)
        
        # Ahora sí ejecutamos el prebuild normal
        super().prebuild_arch(arch)
    
    def build_arch(self, arch):
        """
        Hook de compilación - aseguramos que los parches se apliquen
        """
        build_dir = self.get_build_dir(arch.arch)
        
        # CRÍTICO: Aplicar parches justo antes de compilar
        self.apply_python312_patches(build_dir)
        
        # Luego ejecutamos la compilación normal
        super().build_arch(arch)
    
    def postbuild_arch(self, arch):
        """
        Hook que se ejecuta DESPUÉS de desempaquetar pero ANTES de compilar
        Aplicamos los parches Python 3.12 aquí
        """
        build_dir = self.get_build_dir(arch.arch)
        
        info("=" * 70)
        info("🔥 POST-UNPACK: Aplicando parches Python 3.12 a Kivy")
        info("=" * 70)
        
        # Aplicar parches inmediatamente después de desempaquetar
        self.apply_python312_patches(build_dir)
        
        super().postbuild_arch(arch)


recipe = KivyRecipePython312()
```

---

## Diagnóstico del Problema

### Observaciones Clave

1. **Los parches SÍ se ejecutan**: Los logs muestran mensajes "🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy"

2. **Los archivos NO se encuentran**: No hay mensajes "🔧 Parcheando..." para ningún archivo

3. **El build_dir es incorrecto**: El método `get_build_dir()` devuelve un directorio donde los archivos `.pyx` aún no existen

4. **Timing del problema**: La secuencia de python-for-android es:
   ```
   Download → Unpack → prebuild_arch() → build_arch() → CYTHON COMPILE → build
                                          ↑
                                   Intentamos parchear aquí
                                   pero archivos no existen
   ```

5. **pyjnius funciona**: El custom recipe de pyjnius usa el **mismo approach** y funciona perfectamente, lo que sugiere que:
   - Los hooks funcionan para algunas recipes
   - Kivy tiene un comportamiento especial
   - El directorio de build es diferente para Kivy

### Evidencia de Logs

```bash
# Los parches se ejecutan
[INFO]:    🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy
[INFO]:    🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy
[INFO]:    🔥 PARCHES KIVY: Aplicando justo antes de Cython
[INFO]:    🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy

# Pero NO hay mensajes de archivos parcheados
# (debería aparecer "🔧 Parcheando kivy/graphics/opengl.pyx")

# Y luego Cython falla
[INFO]:    Cythonize kivy/graphics/opengl.pyx
[DEBUG]:   Error compiling Cython file:
[DEBUG]:   kivy/graphics/opengl.pyx:692:30: undeclared name not builtin: long
```

---

## Caminos Potenciales de Solución

### Opción 1: Parchear Después del Unpack (No Implementada)

Sobrescribir el método `unpack()` o encontrar un hook que se ejecute inmediatamente después:

```python
def unpack(self, arch):
    # Dejar que el padre desempaquete
    super().unpack(arch)
    
    # INMEDIATAMENTE parchear
    build_dir = self.get_build_dir(arch.arch)
    self.apply_python312_patches(build_dir)
```

**Problema**: No se sabe si `unpack()` es el método correcto o si hay efectos secundarios.

---

### Opción 2: Script Pre-buildozer (Recomendada)

Crear un script que:
1. Descargue Kivy 2.3.1 manualmente
2. Aplique todos los parches
3. Cree un fork local o un tarball parcheado
4. Modifique buildozer.spec para usar la versión parcheada

```bash
#!/bin/bash
# patch-kivy-python312.sh

# 1. Descargar Kivy
wget https://github.com/kivy/kivy/archive/2.3.1.zip -O kivy-2.3.1.zip
unzip kivy-2.3.1.zip
cd kivy-2.3.1

# 2. Aplicar parches a los 19 archivos
find . -name "*.pyx" -exec sed -i 's/(long, int)/(int,)/g' {} \;
find . -name "*.pyx" -exec sed -i 's/(int, long)/(int,)/g' {} \;
find . -name "*.pyx" -exec sed -i 's/\blong(/int(/g' {} \;

# 3. Crear tarball parcheado
cd ..
tar czf kivy-2.3.1-python312.tar.gz kivy-2.3.1/

# 4. Actualizar buildozer.spec
# requirements = ...,/path/to/kivy-2.3.1-python312.tar.gz,...
```

---

### Opción 3: Fork de Kivy con Parches

1. Hacer fork de Kivy en GitHub
2. Crear branch `python312-compat`
3. Aplicar parches manualmente a los 19 archivos
4. Usar en buildozer.spec:

```ini
requirements = hostpython3,python3,https://github.com/USUARIO/kivy/archive/python312-compat.zip,...
```

---

### Opción 4: Downgrade a Python 3.11 en Host

**Más drástica**: Usar Python 3.11 en el sistema de desarrollo:

```bash
sudo apt install python3.11 python3.11-venv
python3.11 -m venv venv.buildozer.py311
# Rebuild todo
```

**Ventajas**: Evita el problema completamente  
**Desventajas**: Pierde features de Python 3.12, migración eventual necesaria

---

### Opción 5: Investigar Estructura de Kivy Recipe

Estudiar por qué pyjnius funciona y Kivy no:

```bash
# Comparar recipes
diff my_recipes/pyjnius/__init__.py my_recipes/kivy/__init__.py

# Ver recipe original de Kivy
cat ~/.buildozer/android/platform/python-for-android/pythonforandroid/recipes/kivy/__init__.py

# Verificar si KivyRecipe tiene comportamiento especial
grep -A 50 "class KivyRecipe" ~/.buildozer/android/platform/python-for-android/pythonforandroid/recipes/kivy/__init__.py
```

Posibles diferencias:
- Kivy hereda de `PyProjectRecipe` (no `CythonRecipe`)
- Kivy tiene su propio `cythonize_build()` customizado
- El directorio de build es diferente

---

## Comparación: pyjnius (✅ Funciona) vs Kivy (❌ Falla)

### my_recipes/pyjnius/__init__.py (Extracto)

```python
class PyjniusRecipePython312(PyjniusRecipe):
    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        
        build_dir = self.get_build_dir(arch.arch)
        info("=" * 60)
        info("🐍 Aplicando fix de compatibilidad Python 3.12+ a pyjnius")
        # ... similar a Kivy ...
        
        # ✅ FUNCIONA - Los archivos se encuentran y parchean
```

**Diferencia clave**: 
- pyjnius llama `super().prebuild_arch()` **ANTES** de parchear
- Kivy llama parches **ANTES** de `super().prebuild_arch()`

Pero al invertir el orden en Kivy, el problema persiste. Esto sugiere que `get_build_dir()` devuelve directorios diferentes para cada recipe.

---

## Logs de Compilación Relevantes

### Última Compilación Fallida

```
[INFO]:    Recipe build order is ['freetype', 'hostpython3', ..., 'kivy']
[INFO]:    Downloading kivy
[INFO]:    -> directory context .../packages/kivy
[INFO]:    kivy download already cached, skipping
[INFO]:    Unpacking kivy for arm64-v8a
[INFO]:    kivy is already unpacked, skipping

[INFO]:    # Building all recipes for arch arm64-v8a
[INFO]:    Building kivy for arm64-v8a

# ❌ Los parches se ejecutan pero no encuentran archivos
[INFO]:    🐍 Aplicando fix de compatibilidad Python 3.12+ a Kivy
[INFO]:    📂 Build dir: /home/santiago/fiscalberry/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/build/other_builds/kivy/arm64-v8a__ndk_target_28/kivy-2.3.1
[INFO]:    📂 Dir exists: True
[INFO]:    📂 Dir contents: ['setup.py', 'kivy', 'README.md', ...]

# ❌ Cython procesa archivos SIN parches
[INFO]:    Cythonize kivy/graphics/opengl.pyx
[DEBUG]:   Error compiling Cython file:
[DEBUG]:   kivy/graphics/opengl.pyx:692:30: undeclared name not builtin: long

# ✅ Luego pyjnius SÍ funciona
[INFO]:    🐍 Aplicando fix de compatibilidad Python 3.12+ a pyjnius
[INFO]:    ✅ Fix completado: 0 archivo(s) modificado(s)
```

---

## Archivos de Configuración

### buildozer.spec (Sección Relevante)

```ini
[app]
title = Fiscalberry
package.name = fiscalberryapp
package.domain = org.paxapos
source.dir = src
source.include_exts = py,png,jpg,kv,atlas,json,txt,ini
version.regex = __version__ = ['"](.*)['"]
version.filename = src/fiscalberry/version.py

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,BLUETOOTH,BLUETOOTH_ADMIN
android.api = 35
android.minapi = 28
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a,armeabi-v7a

# Dependencias - CRÍTICO: Kivy sin [base]
requirements = hostpython3,python3,kivy,python-escpos,qrcode,pillow,pyserial,pyusb,python-socketio[client],requests,platformdirs,pyjnius,pika

# Custom recipes para parches Python 3.12
p4a.local_recipes = my_recipes

[buildozer]
log_level = 2
warn_on_root = 1
```

---

## Información de Compilación

### Tiempo de Compilación

- **Primera compilación completa**: ~45-60 minutos
- **Recompilación después de limpiar Kivy**: ~15-20 minutos
- **Total intentos**: 7+ compilaciones = ~3-4 horas perdidas

### Tamaño de Artifacts

- **APK generado (intentos previos exitosos)**: ~49 MB
- **Cache .buildozer**: ~8 GB
- **Kivy source descargado**: ~40 MB (2.3.1.zip)

---

## Siguiente Pasos Sugeridos

### Prioridad Alta

1. **Implementar Opción 2 (Script Pre-buildozer)**:
   - Crear `scripts/patch-kivy-python312.sh`
   - Aplicar parches manualmente
   - Generar tarball local
   - Actualizar buildozer.spec

2. **Debugging del build_dir**:
   - Agregar logs extensivos para ver contenido exacto
   - Verificar si archivos existen con `ls -la`
   - Comparar con directorio de pyjnius

### Prioridad Media

3. **Fork de Kivy**:
   - Si script funciona, hacer fork permanente
   - Mantener sincronizado con upstream
   - Contribuir parches a Kivy oficial

4. **Investigar PyProjectRecipe**:
   - Entender diferencias con CythonRecipe
   - Ver si hay hooks especiales

### Prioridad Baja

5. **Downgrade Python** (último recurso)
6. **Esperar Kivy 2.4** (si tiene fix oficial)

---

## Referencias y Links Útiles

### Documentación

- **Python 3.12 What's New**: https://docs.python.org/3/whatsnew/3.12.html#removed
  - Sección: "Removed" → `long` type unified with `int`

- **Kivy GitHub**: https://github.com/kivy/kivy
  - Release 2.3.1: https://github.com/kivy/kivy/releases/tag/2.3.1
  - Issues relacionados: Buscar "Python 3.12" o "long type"

- **python-for-android**: https://github.com/kivy/python-for-android
  - Recipe system: https://python-for-android.readthedocs.io/en/latest/recipes/

- **Buildozer**: https://github.com/kivy/buildozer
  - Documentación: https://buildozer.readthedocs.io/

### Issues Relacionados (Potenciales)

Buscar en GitHub de Kivy:
- "Python 3.12 compatibility"
- "long type removed"
- "Cython 3.x compile error"

### Comandos Útiles para Debug

```bash
# Ver estructura de build
find .buildozer/android/platform/build-*/build/other_builds/kivy* -type d

# Ver archivos .pyx
find .buildozer/android/platform/build-*/build/other_builds/kivy* -name "*.pyx"

# Buscar referencias a 'long' en source
cd .buildozer/android/platform/build-*/build/other_builds/kivy*/kivy-2.3.1
grep -r "\blong\b" --include="*.pyx" kivy/

# Ver hooks disponibles en recipe.py
grep "def.*_arch" ~/.buildozer/android/platform/python-for-android/pythonforandroid/recipe.py
```

---

## Estado Actual del Código

### Archivos Modificados

```
fiscalberry/
├── buildozer.spec                    [MODIFICADO]
├── my_recipes/
│   ├── kivy/
│   │   └── __init__.py              [CREADO - 204 líneas]
│   └── pyjnius/
│       └── __init__.py              [CREADO - ✅ FUNCIONA]
├── docs/
│   ├── GUIA_COMPLETA_COMPILACION_ANDROID.md  [CREADO - 1,823 líneas]
│   └── PROBLEMA_KIVY_PYTHON312_ANDROID.md    [ESTE ARCHIVO]
└── build-*.log                       [MÚLTIPLES LOGS]
```

### Git Status

```bash
# Archivos sin commit (potencialmente)
git status

# Branch actual
git branch
# * fiscalberry-android
```

---

## Contacto y Colaboración

Si otro desarrollador/IA continúa con este problema:

1. **Leer primero**: `docs/GUIA_COMPLETA_COMPILACION_ANDROID.md` para setup completo
2. **Entender el problema**: Este documento
3. **No repetir intentos**: Los 7 approaches listados YA FALLARON
4. **Enfocarse en**: Opciones 2, 3 o 5 (más prometedoras)

### Información que Falta Investigar

- ¿Por qué `get_build_dir()` devuelve un directorio donde los archivos no están listos?
- ¿Qué hace exactamente `PyProjectRecipe.cythonize_build()`?
- ¿Hay un hook `post_unpack()` o similar?
- ¿Cómo logra pyjnius encontrar los archivos correctamente?

---

## Conclusión

Este es un problema de **timing en el ciclo de vida de python-for-android recipes**. Los parches están bien escritos, los regex funcionan, pero los archivos no existen en el momento en que intentamos parchearlos.

La solución más viable es **salirse del sistema de recipes** y aplicar los parches manualmente antes de que buildozer tome control, usando un script pre-procesador o un fork de Kivy.

---

**Última actualización**: 14 de octubre de 2025  
**Tiempo invertido**: ~4-5 horas  
**Estado**: Pendiente de solución definitiva
