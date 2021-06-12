# -*- coding: iso-8859-1 -*-

from Comandos.EpsonComandos import EpsonComandos
import logging
from ComandoInterface import formatText

logger = logging.getLogger(__name__)


class EpsonPanamaComandos(EpsonComandos):
    

    docTypes = {
        "RUC": 'C',
        "SIN_CALIFICADOR": ' ',
    }

    ivaTypes = {
    	"CONSUMIDOR_FINAL": 'F',
        "RESPONSABLE_INSCRIPTO": 'I',
        "RESPONSABLE_NO_INSCRIPTO": 'R',
        "EXENTO": 'E',
        "NO_RESPONSABLE": 'N',        
        "RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'R',
        "RESPONSABLE_MONOTRIBUTO": 'M',
        "MONOTRIBUTISTA_SOCIAL": 'M',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'F',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'F',
        "NO_CATEGORIZADO": 'F',
    }



    docTypeNames = {
        "DOC_TYPE_CUIT": "CUIT",
        "DOC_TYPE_LIBRETA_ENROLAMIENTO": 'L.E.',
        "DOC_TYPE_LIBRETA_CIVICA": 'L.C.',
        "DOC_TYPE_DNI": 'DNI',
        "DOC_TYPE_PASAPORTE": 'PASAP',
        "DOC_TYPE_CEDULA": 'CED',
        "DOC_TYPE_SIN_CALIFICADOR": 'S/C'
    }

    def __addItemParams(self, description, quantityStr, priceUnitStr, ivaStr, sign, bultosStr):
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")
        logger.info("ASIHUAISHAIUHSIAUHSIAUHSIHAIUSHAUISHIUAHSIASHIuhAPISHU")

        return [formatText(description[-1][:20]),
                                   quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0" * 8]

    def _openBillCreditTicketParams(self, isCreditNote, ivaType, name, docType, address):
        return [  isCreditNote and "M" or "T",  # Ticket NC o Factura
                  "C",  # Tipo de Salida - Ignorado
                  type,  # Tipo de FC (A/B/C)
                  "1",  # Copias - Ignorado
                  "P",  # Tipo de Hoja - Ignorado
                  "17",  # Tamaño Carac - Ignorado
                  "E",  # Responsabilidad en el modo entrenamiento - Ignorado
                  ivaType,  # Iva Comprador
                  formatText(name[:40]),  # Nombre
                  formatText(name[40:80]),  # Segunda parte del nombre - Ignorado
                  formatText(docType) or (isCreditNote and "-" or ""), # Tipo de Doc. - Si es NC obligado pongo algo
                  doc or (isCreditNote and "-" or ""),  # Nro Doc - Si es NC obligado pongo algo
                  "N",  # No imprime leyenda de BIENES DE USO
                  formatText(address[:self.ADDRESS_SIZE] or "-"),  # Domicilio
                  formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]),  # Domicilio 2da linea
                  formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]),  # Domicilio 3ra linea
                  (isCreditNote or (ivaType != "F")) and "-" or "",
                  # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                  "",  # Remito segunda linea
                  "C",  # No somos una farmacia
                  ]