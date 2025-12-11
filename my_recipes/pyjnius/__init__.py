from pythonforandroid.recipes.pyjnius import PyjniusRecipe
from pythonforandroid.util import current_directory
from os.path import join
import re
import glob


class PyjniusRecipePython312(PyjniusRecipe):
    """
    Pyjnius recipe with Python 3.12 compatibility fix.
    Removes all references to 'long' type which doesn't exist in Python 3.12+
    """
    
    version = '1.6.1'
    
    def fix_python312_long_type(self, filepath):
        """Elimina todas las referencias al tipo 'long' de Python 2.x"""
        print(f"🔧 Procesando {filepath}")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Fix 1: Reemplazar tuplas (int, long) por solo int
        # Ejemplo: isinstance(x, (int, long)) -> isinstance(x, int)
        content = re.sub(
            r'isinstance\((\w+),\s*\(int,\s*long\)\)',
            r'isinstance(\1, int)',
            content
        )
        
        # Fix 2: Reemplazar "isinstance(x, long)" por "False"
        content = re.sub(
            r'isinstance\((\w+),\s*long\)',
            r'False',
            content
        )
        
        # Fix 3: Eliminar 'long' como clave de diccionario (línea completa)
        # Ejemplo: {int: 'I', long: 'J', float: 'F'} -> {int: 'I', float: 'F'}
        content = re.sub(
            r'\s*long:\s*[\'"][^\'"]+[\'"]\s*,?\s*\n',
            r'\n',
            content
        )
        
        # Fix 4: Eliminar 'long' como clave de diccionario (inline)
        content = re.sub(
            r',\s*long:\s*[\'"][^\'"]+[\'"]\s*',
            r'',
            content
        )
        
        # Fix 6: Simplificar "or False" en expresiones lógicas
        content = re.sub(
            r'\s+or\s+False\s*',
            r'',
            content
        )
        
        # Fix 7: Limpiar "(False and ...)"
        content = re.sub(
            r'\(\s*False\s+and\s+[^)]+\)',
            r'False',
            content
        )
        
        # Fix 8: Limpiar "or (False)"
        content = re.sub(
            r'or\s+\(\s*False\s*\)',
            r'',
            content
        )
        
        if content != original_content:
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"   ✓ Archivo parcheado correctamente")
            return True
        else:
            print(f"   ℹ No se encontraron referencias a 'long'")
            return False
    
    def apply_patches(self, arch):
        """
        Override para NO aplicar patches.
        El fix de Python 3.12 se hace en prebuild_arch programáticamente.
        """
        print("[PYJNIUS] Skipping patch application (handled by prebuild_arch)")
        # NO llamar a super().apply_patches(arch)
        pass
    
    def get_recipe_env(self, arch):
        """
        Override para remover SDL2 de las bibliotecas de link.
        webview bootstrap NO tiene SDL2.
        """
        env = super().get_recipe_env(arch)
        
        # Remover SDL2 de LDFLAGS y LDLIBS si existe
        if 'LDFLAGS' in env:
            env['LDFLAGS'] = env['LDFLAGS'].replace('-lSDL2', '').strip()
        
        if 'LDLIBS' in env:
            env['LDLIBS'] = env['LDLIBS'].replace('-lSDL2', '').strip()
        
        print(f"[PYJNIUS] LDFLAGS after SDL2 removal: {env.get('LDFLAGS', 'N/A')}")
        print(f"[PYJNIUS] LDLIBS after SDL2 removal: {env.get('LDLIBS', 'N/A')}")
        
        return env
    
    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        
        print("=" * 60)
        print("🐍 Aplicando fix de compatibilidad Python 3.12+ a pyjnius")
        print("=" * 60)
        
        with current_directory(self.get_build_dir(arch.arch)):
            # Buscar todos los archivos .pxi en el directorio jnius
            pxi_files = glob.glob('jnius/*.pxi')
            
            if not pxi_files:
                print("⚠ ADVERTENCIA: No se encontraron archivos .pxi")
                return
            
            fixed_count = 0
            for pxi_file in pxi_files:
                if self.fix_python312_long_type(pxi_file):
                    fixed_count += 1
            
            print("=" * 60)
            print(f"✅ Fix completado: {fixed_count} archivo(s) modificado(s)")
            print("=" * 60)


recipe = PyjniusRecipePython312()
