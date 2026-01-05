# -*- coding: utf-8 -*-
"""
Detector de errores específicos de impresoras.

Este módulo detecta y clasifica errores comunes de impresoras:
- Falta de papel
- Tapa abierta
- Papel atascado
- Errores de comunicación
- Errores de hardware
"""

import re
from typing import Optional, Dict, Any, Tuple
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.rabbitmq.error_publisher import publish_error

logger = getLogger()


class PrinterErrorType:
    """Tipos de errores de impresora"""
    PAPER_OUT = "PAPER_OUT"
    PAPER_LOW = "PAPER_LOW"
    COVER_OPEN = "COVER_OPEN"
    PAPER_JAM = "PAPER_JAM"
    COMMUNICATION_ERROR = "COMMUNICATION_ERROR"
    OFFLINE = "PRINTER_OFFLINE"
    HARDWARE_ERROR = "HARDWARE_ERROR"
    CUTTER_ERROR = "CUTTER_ERROR"
    TEMPERATURE_ERROR = "TEMPERATURE_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"
    UNKNOWN = "UNKNOWN_PRINTER_ERROR"


class PrinterErrorDetector:
    """
    Detector de errores específicos de impresoras mediante análisis de mensajes y excepciones.
    """
    
    # Patrones de detección de errores en español
    ERROR_PATTERNS = {
        PrinterErrorType.PAPER_OUT: [
            r'poco papel|sin papel|no hay papel|paper out|out of paper|no paper',
            r'falta papel|papel agotado|end of paper',
        ],
        PrinterErrorType.PAPER_LOW: [
            r'papel bajo|low paper|poco papel para comprobantes',
            r'warning.*paper|papel.*warning',
        ],
        PrinterErrorType.COVER_OPEN: [
            r'tapa abierta|cover open|lid open|carcasa abierta',
            r'cerrar tapa|close.*cover|close.*lid',
        ],
        PrinterErrorType.PAPER_JAM: [
            r'papel atascado|paper jam|atasco|papel trabado',
            r'jam.*paper|obstrucción',
        ],
        PrinterErrorType.COMMUNICATION_ERROR: [
            r'error de comunicación|communication error|timeout',
            r'no response|sin respuesta|connection.*failed|conexión.*fallida',
            r'device not found|dispositivo no encontrado|puerto.*cerrado',
            r'usb.*error|serial.*error|bluetooth.*error|network.*error',
        ],
        PrinterErrorType.OFFLINE: [
            r'offline|fuera de línea|desconectada|not connected',
            r'printer.*not.*ready|impresora.*no.*lista',
        ],
        PrinterErrorType.CUTTER_ERROR: [
            r'error.*cortador|cutter error|guillotina',
            r'corte.*fallido|cutting.*error',
        ],
        PrinterErrorType.TEMPERATURE_ERROR: [
            r'temperatura|temperature|sobrecalentamiento|overheating',
            r'cabezal.*caliente|head.*hot',
        ],
        PrinterErrorType.MEMORY_ERROR: [
            r'memoria.*llena|memory.*full|buffer.*full',
            r'sin memoria|out of memory',
        ],
        PrinterErrorType.HARDWARE_ERROR: [
            r'error de hardware|hardware error|fallo del dispositivo',
            r'device.*error|error del dispositivo',
        ],
    }
    
    @classmethod
    def detect_error_type(cls, error_message: str, exception: Optional[Exception] = None) -> Tuple[str, str]:
        """
        Detecta el tipo de error basándose en el mensaje y la excepción.
        
        Args:
            error_message: Mensaje de error a analizar
            exception: Excepción original si está disponible
            
        Returns:
            Tuple[str, str]: (tipo_error, descripción_usuario_friendly)
        """
        if not error_message:
            return PrinterErrorType.UNKNOWN, "Error desconocido"
        
        # Convertir a minúsculas para búsqueda case-insensitive
        msg_lower = error_message.lower()
        
        # Verificar cada patrón
        for error_type, patterns in cls.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, msg_lower, re.IGNORECASE):
                    description = cls._get_user_friendly_description(error_type)
                    logger.info(f"Error detectado: {error_type} - {description}")
                    return error_type, description
        
        # Analizar tipo de excepción si está disponible
        if exception:
            exception_type = type(exception).__name__.lower()
            
            if 'timeout' in exception_type or 'connection' in exception_type:
                return PrinterErrorType.COMMUNICATION_ERROR, "Error de comunicación con la impresora"
            elif 'usb' in exception_type or 'serial' in exception_type:
                return PrinterErrorType.COMMUNICATION_ERROR, "Error en la conexión física de la impresora"
            elif 'bluetooth' in exception_type:
                return PrinterErrorType.COMMUNICATION_ERROR, "Error en la conexión Bluetooth"
        
        return PrinterErrorType.UNKNOWN, f"Error no clasificado: {error_message[:100]}"
    
    @classmethod
    def _get_user_friendly_description(cls, error_type: str) -> str:
        """
        Retorna una descripción profesional según el tipo de error.
        
        Args:
            error_type: Tipo de error detectado
            
        Returns:
            str: Descripción profesional del error
        """
        descriptions = {
            PrinterErrorType.PAPER_OUT: "Sin papel en la impresora",
            PrinterErrorType.PAPER_LOW: "Nivel de papel bajo",
            PrinterErrorType.COVER_OPEN: "Tapa de la impresora abierta",
            PrinterErrorType.PAPER_JAM: "Papel atascado",
            PrinterErrorType.COMMUNICATION_ERROR: "Error de comunicación con la impresora",
            PrinterErrorType.OFFLINE: "Impresora desconectada",
            PrinterErrorType.CUTTER_ERROR: "Error en el mecanismo de corte",
            PrinterErrorType.TEMPERATURE_ERROR: "Error de temperatura en el cabezal",
            PrinterErrorType.MEMORY_ERROR: "Memoria de la impresora llena",
            PrinterErrorType.HARDWARE_ERROR: "Error de hardware de la impresora",
            PrinterErrorType.UNKNOWN: "Error desconocido de la impresora",
        }
        return descriptions.get(error_type, "Error de impresora")
    
    @classmethod
    def detect_and_publish_error(cls, error_message: str, 
                                 exception: Optional[Exception] = None,
                                 context: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """
        Detecta el tipo de error y lo publica a RabbitMQ automáticamente.
        
        Args:
            error_message: Mensaje de error
            exception: Excepción original
            context: Contexto adicional
            
        Returns:
            Tuple[str, str]: (tipo_error, descripción)
        """
        error_type, description = cls.detect_error_type(error_message, exception)
        severity = cls.get_severity(error_type)
        
        # Agregar información al contexto
        full_context = context or {}
        full_context.update({
            "detected_error_type": error_type,
            "severity": severity,
            "original_message": error_message,
        })
        
        # Publicar error clasificado
        try:
            publish_error(
                error_type=error_type,
                error_message=description,
                context=full_context,
                exception=exception
            )
            logger.info(f"Error detectado y publicado: {error_type} [{severity}]")
        except Exception as e:
            logger.error(f"Error al publicar error detectado: {e}")
        
        return error_type, description
    
    @classmethod
    def get_severity(cls, error_type: str) -> str:
        """
        Obtiene la severidad del error para clasificación.
        
        Args:
            error_type: Tipo de error
            
        Returns:
            str: Nivel de severidad (CRITICAL, ERROR, WARNING)
        """
        severity_map = {
            PrinterErrorType.PAPER_OUT: "ERROR",
            PrinterErrorType.PAPER_LOW: "WARNING",
            PrinterErrorType.COVER_OPEN: "ERROR",
            PrinterErrorType.PAPER_JAM: "ERROR",
            PrinterErrorType.COMMUNICATION_ERROR: "CRITICAL",
            PrinterErrorType.OFFLINE: "CRITICAL",
            PrinterErrorType.CUTTER_ERROR: "ERROR",
            PrinterErrorType.TEMPERATURE_ERROR: "WARNING",
            PrinterErrorType.MEMORY_ERROR: "ERROR",
            PrinterErrorType.HARDWARE_ERROR: "CRITICAL",
            PrinterErrorType.UNKNOWN: "ERROR",
        }
        return severity_map.get(error_type, "ERROR")


def analyze_printer_response(response: Any, printer_name: str = "unknown") -> Optional[Dict[str, Any]]:
    """
    Analiza la respuesta de una impresora buscando mensajes de estado o error.
    
    Args:
        response: Respuesta de la impresora (dict, list, str)
        printer_name: Nombre de la impresora
        
    Returns:
        Optional[Dict[str, Any]]: Información del error si se detecta alguno
    """
    try:
        # Extraer mensajes si la respuesta es un dict con key 'msg'
        messages = []
        
        if isinstance(response, dict):
            if 'msg' in response:
                messages = response['msg'] if isinstance(response['msg'], list) else [response['msg']]
            elif 'error' in response:
                messages = [response['error']]
            elif 'err' in response:
                messages = [response['err']]
        
        elif isinstance(response, list):
            messages = response
        
        elif isinstance(response, str):
            messages = [response]
        
        # Analizar cada mensaje
        for msg in messages:
            if not msg or not isinstance(msg, str):
                continue
            
            # Detectar tipo de error
            error_type, description = PrinterErrorDetector.detect_error_type(msg)
            
            # Si se detectó un error específico (no UNKNOWN), reportarlo
            if error_type != PrinterErrorType.UNKNOWN:
                logger.warning(f"Printer '{printer_name}' reported: {description}")
                
                # Publicar el error
                publish_error(
                    error_type=error_type,
                    error_message=description,
                    context={
                        "printer_name": printer_name,
                        "original_message": msg,
                        "detected_from": "printer_response"
                    }
                )
                
                return {
                    "error_type": error_type,
                    "description": description,
                    "severity": PrinterErrorDetector.get_severity(error_type),
                    "original_message": msg
                }
        
        return None
        
    except Exception as e:
        logger.error(f"Error analyzing printer response: {e}")
        return None
