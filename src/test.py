
from common.ComandosHandler import ComandosHandler
import sys

comandera = sys.argv[1]

data = {'printRemito': {
            'encabezado': {'imprimir_fecha_remito': ''}, 
            'items': [
                {'alic_iva': '21.00', 'qty': 6, 'ds': "None", 'importe': 50, 'order': '0'},
                ], 
            'setTrailer': [
                'Mozo: Ludmila', 'Mesa: 33'
                ]}, 
        'printerName': 'File'
        }

data2 =  {'printRemito': {'encabezado': {'imprimir_fecha_remito': ''}, 'items': [
                {'alic_iva': '21.00', 'qty': '1', 'ds': 'Producto', 'importe': 1, 'order': None}, 
                {'alic_iva': '21.00', 'qty': '1', 'ds': None, 'importe': '2200', 'order': None}], 
                          'setTrailer': ['Mozo: Cena Show', 'Mesa: prueba']}, 'printerName': 'dummy'}


fiscal = {'printFacturaElectronica': {'encabezado': {'nombre_comercio': 'Paxapoga', 'razon_social': 'Riotorno SRL', 'cuit_empresa': '30715582593', 'domicilio_comercial': 'Beruti 4643', 'tipo_responsable': 'Resp. Inscripto', 'inicio_actividades': '', 'tipo_comprobante': '"B"', 'tipo_comprobante_codigo': '006', 'numero_comprobante': '0010-00011795', 'fecha_comprobante': '2024-08-29', 'documento_cliente': '0', 'nombre_cliente': '', 'domicilio_cliente': '', 'nombre_tipo_documento': 'Sin identificar', 'cae': '74353157058451', 'cae_vto': '2024-09-08', 'importe_total': '1.00', 'importe_neto': '4876.86', 'importe_iva': '1024.14', 'moneda': 'PES', 'ctz': 1, 'tipoDocRec': 99, 'tipoCodAut': 'E'}, 'items': [{'alic_iva': 0.21, 'importe': 1, 'ds': 'Producto', 'qty': 1}], 'pagos': [], 'setTrailer': ['Mozo: Cena Show', 'Mesa: prueba']}, 'printerName': comandera}

comandoHandler = ComandosHandler()

comandoHandler.send_command(fiscal)

