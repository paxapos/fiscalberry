"""
Nivel de privilegio de la cuenta de Windows, sin pedir nada (#185; lo usará
#178 para decidir, ANTES de mostrar el cartel de UAC, si la persona lo puede
aprobar).

- `admin_con_uac`: administrador con UAC (token filtrado). Un "Sí" en el
  cartel de Windows alcanza.
- `admin_elevado`: el proceso ya corre como administrador.
- `admin_sin_uac`: administrador con UAC desactivado.
- `estandar`: cuenta estándar. El cartel pediría la contraseña de otro
  usuario: no se le muestra.
- `desconocido` / `no_aplica` (no es Windows).

TokenElevationType (advapi32) dice si el token es filtrado, completo o
"default"; en el caso default, IsUserAnAdmin distingue administrador sin UAC
de cuenta estándar.
"""

import sys

PRIVILEGE_ADMIN_UAC = "admin_con_uac"
PRIVILEGE_ELEVATED = "admin_elevado"
PRIVILEGE_ADMIN_NO_UAC = "admin_sin_uac"
PRIVILEGE_STANDARD = "estandar"
PRIVILEGE_UNKNOWN = "desconocido"
PRIVILEGE_NOT_APPLICABLE = "no_aplica"

DESCRIPTIONS = {
    PRIVILEGE_ADMIN_UAC: "administrador con UAC (puede aprobar el cartel de Windows)",
    PRIVILEGE_ELEVATED: "administrador, ya elevado",
    PRIVILEGE_ADMIN_NO_UAC: "administrador con UAC desactivado",
    PRIVILEGE_STANDARD: "cuenta estándar (no puede aprobar el cartel de Windows)",
    PRIVILEGE_UNKNOWN: "no se pudo saber",
    PRIVILEGE_NOT_APPLICABLE: "no aplica (no es Windows)",
}

TOKEN_QUERY = 0x8
TOKEN_ELEVATION_TYPE = 18
ELEVATION_DEFAULT = 1
ELEVATION_FULL = 2
ELEVATION_LIMITED = 3


class _WindowsApi:
    """Lo mínimo de advapi32/shell32 para leer el token del proceso."""

    def __init__(self):
        import ctypes
        from ctypes import byref, c_uint32, c_void_p

        self._ct = ctypes
        self._byref = byref
        self._u32 = c_uint32
        self._vp = c_void_p
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.shell = ctypes.WinDLL("shell32")
        self.kernel.GetCurrentProcess.restype = c_void_p
        self.advapi.OpenProcessToken.argtypes = [c_void_p, c_uint32, c_void_p]
        self.advapi.GetTokenInformation.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32, c_void_p]
        self.kernel.CloseHandle.argtypes = [c_void_p]

    def elevation_type(self):
        token = self._vp()
        if not self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), TOKEN_QUERY,
                                            self._byref(token)):
            raise OSError(self._ct.get_last_error(), "OpenProcessToken falló")
        try:
            tipo = self._u32(0)
            largo = self._u32(0)
            if not self.advapi.GetTokenInformation(token, TOKEN_ELEVATION_TYPE, self._byref(tipo),
                                                   4, self._byref(largo)):
                raise OSError(self._ct.get_last_error(), "GetTokenInformation falló")
            return tipo.value
        finally:
            self.kernel.CloseHandle(token)

    def is_admin(self):
        return bool(self.shell.IsUserAnAdmin())


def detect_privilege(api=None, platform=None):
    """Uno de PRIVILEGE_*. Nunca lanza."""
    platform = sys.platform if platform is None else platform
    if platform != "win32" and api is None:
        return PRIVILEGE_NOT_APPLICABLE
    try:
        api = api or _WindowsApi()
        tipo = api.elevation_type()
        if tipo == ELEVATION_LIMITED:
            return PRIVILEGE_ADMIN_UAC
        if tipo == ELEVATION_FULL:
            return PRIVILEGE_ELEVATED
        if tipo == ELEVATION_DEFAULT:
            return PRIVILEGE_ADMIN_NO_UAC if api.is_admin() else PRIVILEGE_STANDARD
    except Exception:
        pass
    return PRIVILEGE_UNKNOWN
