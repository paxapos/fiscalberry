
from common.ComandosHandler import ComandosHandler
import sys
from common.printer_detector import listar_impresoras

'''
si ejecuto el script sin argumentos que me de un listado de opciones y ayuda de uso
estre ecript se ejecuta con 2 argumentos, el primero es es el tipo de comando a enviar y
las opciones son
- remito1
- remito2
- facturaA
- facturaB
- cierreCaja
- comanda

y el segundo parametro es el nombre de la impresora a la que se le envia el comando, es opcional
si no se especifica se envia a la impresora Dummy
'''



# Ejemplo de uso
impresoras = listar_impresoras()
print("Impresoras instaladas:", impresoras)

class ComandosEnum:
    REMITO1 = "remito1"
    REMITO2 = "remito2"
    FACTURAA = "facturaA"
    FACTURAB = "facturaB"
    CIERRECAJA = "cierreCaja"
    COMANDA1 = "comanda1"



if len(sys.argv) == 1:
    print("Listado de opciones y ayuda de uso:")
    for i, comando in enumerate(ComandosEnum.__dict__.keys()):
        if not comando.startswith("__"):
            print(f"{i+1}. {comando}")
    sys.exit()

comando = sys.argv[1]

#si no se especifica la comandera, se envia a la comandera Dummy, si se especifica
#se envia a la comandera especificada
if len(sys.argv) > 2:
    comandera = sys.argv[2]
else:
    comandera = 'Dummy'



comandosDisponibles = {}
comandosDisponibles[ComandosEnum.REMITO1] = {'printRemito': {
            'encabezado': {'imprimir_fecha_remito': ''}, 
            'items': [
                {'alic_iva': '21.00', 'qty': 6, 'ds': "None", 'importe': 50, 'order': '0'},
                ], 
            'setTrailer': [
                'Mozo: Ludmila', 'Mesa: 33'
                ]}, 
        'printerName': 'File'
        }

comandosDisponibles[ComandosEnum.REMITO2] =  {'printRemito': {'encabezado': {'imprimir_fecha_remito': ''}, 'items': [
                {'alic_iva': '21.00', 'qty': '1', 'ds': 'Producto', 'importe': 1, 'order': None},
                {'alic_iva': '21.00', 'qty': '1', 'ds': None, 'importe': '2200', 'order': None}],
                          'setTrailer': ['Mozo: Cena Show', 'Mesa: prueba']}, 'printerName': 'dummy'}

comandosDisponibles[ComandosEnum.FACTURAB] = {'printFacturaElectronica': {'encabezado': {'nombre_comercio': 'Paxapoga', 'razon_social': 'Riotorno SRL', 'cuit_empresa': '30715582593', 'domicilio_comercial': 'Beruti 4643', 'tipo_responsable': 'Resp. Inscripto', 'inicio_actividades': '', 'tipo_comprobante': '"B"', 'tipo_comprobante_codigo': '006', 'numero_comprobante': '0010-00011795', 'fecha_comprobante': '2024-08-29', 'documento_cliente': '0', 'nombre_cliente': '', 'domicilio_cliente': '', 'nombre_tipo_documento': 'Sin identificar', 'cae': '74353157058451', 'cae_vto': '2024-09-08', 'importe_total': '1.00', 'importe_neto': '4876.86', 'importe_iva': '1024.14', 'moneda': 'PES', 'ctz': 1, 'tipoDocRec': 99, 'tipoCodAut': 'E'}, 'items': [{'alic_iva': 0.21, 'importe': 1, 'ds': 'Producto', 'qty': 1}], 'pagos': [], 'setTrailer': ['Mozo: Cena Show', 'Mesa: prueba']}, 'printerName': comandera}

comandosDisponibles[ComandosEnum.FACTURAA] = {"printFacturaElectronica": {"encabezado": {"nombre_comercio": "Riotorno SRL", "razon_social": "Riotorno SRL", "cuit_empresa": "30715582593", "domicilio_comercial": "una calle 2232", "tipo_responsable": "Resp. Inscripto", "inicio_actividades": None, "tipo_comprobante": '"A"', "tipo_comprobante_codigo": "001", "numero_comprobante": "0010-00000016", "fecha_comprobante": "2024-09-02", "documento_cliente": "33709585229", "nombre_cliente": "Google Arg. SRL", "domicilio_cliente": "", "nombre_tipo_documento": "CUIT", "cae": "74363194522383", "cae_vto": "2024-09-12", "importe_total": "2000.00", "importe_neto": "1652.88", "importe_iva": "347.12", "moneda": "PES", "ctz": 1, "tipoDocRec": 99, "tipoCodAut": "E"}, "items": [{"alic_iva": 164.88, "importe": 950, "ds": "DAIQUIRI S/A MARACUYA", "qty": 1}, {"alic_iva": 164.88, "importe": 950, "ds": "DAIQUIRI S/A FRUTILLA", "qty": 1}, {"alic_iva": 8.68, "importe": 50, "ds": "producto en otra impresora", "qty": 2}], "pagos": [], "setTrailer": ["Mozo: Riotorno SRL", "Mesa: 2"]}, "printerName": comandera}

comandosDisponibles[ComandosEnum.COMANDA1] = {'printComanda': {'comanda': {'id': '629', 'created': '2024-09-02 08:48:20', 'observacion': 'observacion general', 'entradas': [{'nombre': 'cerveza con variante', 'cant': '1', 'sabores': ['(1) IMPERIAL RUBIA TIRADA ', '(3) Imperial Rubia Tirada x Lt']}], 'platos': [{'nombre': 'OLD FASHIONED', 'cant': '2'}, {'nombre': 'BOULEVARDIER', 'cant': '1'}, {'nombre': 'WHITE RUSSIAN', 'cant': '1'}, {'nombre': 'PISCO SOUR', 'cant': '1'}, {'nombre': 'MOJITO DE FRUTOS ROJOS', 'cant': '1'}, {'nombre': 'DAIQUIRI S/A FRUTILLA', 'cant': '1'}, {'nombre': 'DAIQUIRI S/A MARACUYA', 'cant': '1', 'observacion': 'un detalle del producto'}, {'nombre': 'producto en otra impresora', 'cant': '2'}]}, 'setTrailer': [' ', 'Mozo: Riotorno SRL', 'Mesa: 112', ' ']}, 'printerName': comandera}



comandoHandler = ComandosHandler()


# si comando tiene el nombre all, ejecutar todos
if comando == "all":
    for comando in comandosDisponibles:
        comandoHandler.send_command(comandosDisponibles.get(comando))
    sys.exit()
    
    
# si comando existe en el listado de comandos disponibles, envio el comando a
# la impresora
if comando in comandosDisponibles:
    comandoHandler.send_command(comandosDisponibles.get(comando))
else:
    print(f"El comando {comando} no existe en la lista de comandos disponibles")
    sys.exit()

