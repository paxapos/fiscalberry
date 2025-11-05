import platform

def listar_impresoras():
    sistema_operativo = platform.system()
    impresoras = []

    if sistema_operativo == "Linux":
        import subprocess

        resultado = subprocess.run(['lpstat', '-e'], stdout=subprocess.PIPE)
        impresoras = resultado.stdout.decode('utf-8').splitlines()
    elif sistema_operativo == "Windows":
        import win32print

        impresoras = [printer[2] for printer in win32print.EnumPrinters(2)]
    else:
        raise NotImplementedError("Sistema operativo no soportado")

    return impresoras