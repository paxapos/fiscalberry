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
    
    CRÍTICO: Sobrescribe install_python_package para forzar
    compilación desde source, evitando wheels precompilados.
    """
    
    # Usar Kivy 2.3.1 que tiene soporte nativo para Python 3.12
    version = '2.3.1'

    # Sin patches heredados: la KivyRecipe base trae 'use_cython.patch', pero p4a
    # lo busca relativo a ESTE recipe (my_recipes/kivy/) donde no existe → el build
    # Android fallaba con "Can't open patch file .../use_cython.patch". Este recipe
    # ya hace su propio parcheo (apply_python312_patches) y fuerza source build, así
    # que la lista de patches va vacía.
    patches = []

    # FORZAR source build
    install_in_hostpython = False
    call_hostpython_via_targetpython = False
    
    def install_python_package(self, arch, name=None, env=None, is_dir=True):
        """
        Sobrescribimos este método para forzar --no-binary
        """
        info("=" * 60)
        info(f"🔧 Instalando {self.name} DESDE SOURCE (no wheels)")
        info("=" * 60)
        
        # Forzar instalación desde source con pip
        if name is None:
            name = self.name
        
        # Agregar --no-binary al entorno pip
        if env is None:
            env = self.get_recipe_env(arch)
        
        # Llamar al método padre pero con flags adicionales
        # que fuerzan compilación desde source
        import os
        old_pip_flags = os.environ.get('PIP_NO_BINARY', '')
        try:
            os.environ['PIP_NO_BINARY'] = ':all:'
            super().install_python_package(arch, name, env, is_dir)
        finally:
            if old_pip_flags:
                os.environ['PIP_NO_BINARY'] = old_pip_flags
            else:
                os.environ.pop('PIP_NO_BINARY', None)
    
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
        
        # ESTRATEGIA DINÁMICA: Buscar TODOS los .pyx con 'long'
        files_to_patch = []
        
        if os.path.exists(build_dir):
            info("🔍 Buscando archivos .pyx con 'long'...")
            for root, dirs, files in os.walk(build_dir):
                for filename in files:
                    if filename.endswith('.pyx'):
                        file_path = os.path.join(root, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                # Buscar patterns típicos de 'long'
                                if '(long,' in content or ', long)' in content or 'long(' in content or ': long' in content:
                                    files_to_patch.append(file_path)
                                    info(f"   📌 {os.path.relpath(file_path, build_dir)}")
                        except Exception as e:
                            pass
            
            info(f"📊 Total: {len(files_to_patch)} archivos a parchear")
        
        modified_files = 0
        
        for file_path in files_to_patch:
            try:
                rel_name = os.path.relpath(file_path, build_dir)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Patrón 1: Eliminar método __long__ completo
                # def __long__(self):\n    return long(...)
                content = re.sub(
                    r'^\s*def __long__\(self\):.*?(?=\n\s{0,4}(?:def |cdef |cpdef |class |$))',
                    '',
                    content,
                    flags=re.MULTILINE | re.DOTALL
                )
                
                # Patrón 2: Reemplazar llamadas a long() por int()
                content = re.sub(r'\blong\s*\(', 'int(', content)
                
                # Patrón 3: Eliminar 'long' de diccionarios de conversión
                # Ejemplo: long: 'J', -> (eliminado)
                content = re.sub(
                    r',?\s*long\s*:\s*[\'"][^\'"]+[\'"]\s*,?\s*',
                    '',
                    content
                )
                
                # Patrón 4a: Reemplazar (long, int) por (int,) - ORDEN LONG PRIMERO
                content = re.sub(
                    r'\(\s*long\s*,\s*int\s*\)',
                    '(int,)',
                    content
                )
                
                # Patrón 4b: Reemplazar (int, long) por (int,) - ORDEN INT PRIMERO
                content = re.sub(
                    r'\(\s*int\s*,\s*long\s*\)',
                    '(int,)',
                    content
                )
                
                # Patrón 4c: Reemplazar (long,) por (int,) - SOLO LONG
                content = re.sub(
                    r'\(\s*long\s*,\s*\)',
                    '(int,)',
                    content
                )
                
                # Patrón 5a: Reemplazar [long, int] por [int]
                content = re.sub(
                    r'\[\s*long\s*,\s*int\s*\]',
                    '[int]',
                    content
                )
                
                # Patrón 5b: Reemplazar [int, long] por [int]
                content = re.sub(
                    r'\[\s*int\s*,\s*long\s*\]',
                    '[int]',
                    content
                )
                
                if content != original_content:
                    info(f"🔧 Parcheando {rel_name}")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    modified_files += 1
                    info(f"   ✅ Archivo parcheado correctamente")
                else:
                    info(f"   ℹ {rel_name}: Sin cambios necesarios")
                    
            except FileNotFoundError:
                warning(f"⚠ Archivo no encontrado: {file_path}")
            except Exception as e:
                warning(f"❌ Error al parchear {file_path}: {e}")
        
        info("=" * 60)
        if modified_files > 0:
            info(f"✅ Fix completado: {modified_files} archivo(s) modificado(s)")
        else:
            info("ℹ No se requirieron modificaciones")
        info("=" * 60)
    
    def prebuild_arch(self, arch):
        """
        Hook ejecutado antes de compilar para cada arquitectura
        CRÍTICO: Primero dejamos que el padre prepare TODO, luego parcheamos
        """
        # Primero el padre desempaqueta y prepara archivos
        super().prebuild_arch(arch)
        
        # AHORA los archivos están listos, aplicamos parches
        build_dir = self.get_build_dir(arch.arch)
        info("=" * 70)
        info("🔥 POST-PREBUILD: Archivos listos, aplicando parches")
        info("=" * 70)
        self.apply_python312_patches(build_dir)
    
    def build_cython_components(self, arch):
        """
        MOMENTO CRÍTICO: Este método se ejecuta JUSTO ANTES de que Cython compile
        Sobrescribimos para aplicar parches en el último momento posible
        """
        build_dir = self.get_build_dir(arch.arch)
        
        info("=" * 70)
        info("🔥 PRE-CYTHON: Último momento - parcheando antes de Cython")
        info(f"📂 Build dir: {build_dir}")
        
        # Listar archivos para debug
        if os.path.exists(build_dir):
            pyx_files = []
            for root, dirs, files in os.walk(build_dir):
                for f in files:
                    if f.endswith('.pyx'):
                        pyx_files.append(os.path.relpath(os.path.join(root, f), build_dir))
            info(f"📄 Archivos .pyx encontrados: {len(pyx_files)}")
            if pyx_files:
                info(f"� Primeros 5: {pyx_files[:5]}")
        info("=" * 70)
        
        # Aplicar parches AHORA, justo antes de Cython
        self.apply_python312_patches(build_dir)
        
        # Ahora sí, ejecutar Cython con archivos parcheados
        super().build_cython_components(arch)
    
    def cythonize_build(self, env=None, build_dir=None):
        """
        MOMENTO CRÍTICO: Kivy sobrescribe este método y define el build_dir REAL
        Nosotros lo sobrescribimos DE NUEVO para parchear en el directorio correcto
        """
        # Si no nos pasan build_dir, Kivy usa 'kivy' como subdirectorio
        if build_dir is None:
            base_dir = self.get_build_dir(self.ctx.archs[0].arch)
            build_dir = join(base_dir, 'kivy')
        
        info("=" * 70)
        info("🔥 CYTHONIZE_BUILD: Parcheando en directorio REAL de Cython")
        info(f"📂 Build dir que usará Cython: {build_dir}")
        info(f"📂 Existe: {os.path.exists(build_dir)}")
        
        if os.path.exists(build_dir):
            # Listar .pyx en este directorio específico
            pyx_files = []
            for root, dirs, files in os.walk(build_dir):
                pyx_files.extend([f for f in files if f.endswith('.pyx')])
            info(f"📄 Archivos .pyx encontrados: {len(pyx_files)}")
            
            # Verificar si opengl.pyx tiene 'long'
            opengl_path = join(build_dir, 'graphics', 'opengl.pyx')
            if os.path.exists(opengl_path):
                with open(opengl_path, 'r') as f:
                    content = f.read()
                    has_long = '(long,' in content or ', long)' in content
                    info(f"📄 opengl.pyx existe, tiene 'long': {has_long}")
        info("=" * 70)
        
        # PARCHEAR en el directorio REAL
        self.apply_python312_patches(build_dir)
        
        # Ahora sí, llamar al cythonize_build de Kivy
        super().cythonize_build(env=env, build_dir=build_dir)


recipe = KivyRecipePython312()
