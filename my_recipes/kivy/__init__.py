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
        
                # Archivos .pyx que contienen referencias a 'long'
        # Lista completa obtenida con: find kivy-2.3.0 -name "*.pyx" -exec grep -l "\blong\b" {} \;
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
            'kivy/graphics/opengl.pyx',
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
                
                # Patrón 4: Reemplazar (int, long) por (int,)
                content = re.sub(
                    r'\(\s*int\s*,\s*long\s*\)',
                    '(int,)',
                    content
                )
                
                # Patrón 5: Reemplazar [int, long] por [int]
                content = re.sub(
                    r'\[\s*int\s*,\s*long\s*\]',
                    '[int]',
                    content
                )
                
                if content != original_content:
                    info(f"🔧 Parcheando {rel_path}")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    modified_files += 1
                    info(f"   ✓ Archivo parcheado correctamente")
                else:
                    info(f"🔧 Procesando {rel_path}")
                    info(f"   ℹ No se encontraron referencias a 'long'")
                    
            except FileNotFoundError:
                # El archivo puede no existir en esta versión de Kivy
                warning(f"⚠ Archivo no encontrado: {rel_path}")
            except Exception as e:
                warning(f"❌ Error al parchear {rel_path}: {e}")
        
        info("=" * 60)
        if modified_files > 0:
            info(f"✅ Fix completado: {modified_files} archivo(s) modificado(s)")
        else:
            info("ℹ No se requirieron modificaciones")
        info("=" * 60)
    
    def prebuild_arch(self, arch):
        """
        Hook ejecutado antes de compilar para cada arquitectura
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
