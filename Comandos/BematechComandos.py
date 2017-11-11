# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import unicodedata
from ComandoInterface import ComandoInterface, ComandoException, ValidationError, FiscalPrinterError, formatText
from ConectorDriverComando import ConectorDriverComando
from datetime import datetime
import time


class PrinterException(Exception):
    pass


class BematechComandos(ComandoInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorReceipt"

    INICIAR = 0x40  # @
    RETORNO_DE_CARRO = 0x0D
    CORTAR_PAPEL = 0x69  # i
    CORTAR_PAPEL_PARCIAL = 0x6D  # m
    ENFATIZADO_ON = 0x45
    ENFATIZADO_OFF = 0x46
    SUPERSCRIPT_ON = 0x53
    SUPERSCRIPT_ON_TOP = 0x00
    SUPERSCRIPT_ON_BOTTOM = 0x01
    SUPERSCRIPT_OFF = 0x54
    DOBLE_ANCHO_ON = 0x0E
    DOBLE_ANCHO_OFF = 0x14
    DOBLE_ALTO_LINE = 0x56  # toda la linea
    DOBLE_ALTO = 0x64  # por caracter
    DOBLE_ALTO_ON = 0x01
    DOBLE_ALTO_OFF = 0x00
    ITALIC_ON = 0x34
    ITALIC_OFF = 0x35
    BUZZER = 0x28
    ALIGN = 0x61
    ALIGN_LEFT = 0x00
    ALIGN_CENTER = 0x01
    ALIGN_RIGHT = 0x02
    TEXT = 0x02

    AVAILABLE_MODELS = []

    def __init__(self, path=None, driver="ReceipDirectJet", *args):
        "path indica la IP o puerto donde se encuentra la impresora"

        ComandoInterface.__init__(args)

        self.conector = ConectorDriverComando(self, driver, path)

    def init_defaults(self):
        self._sendCommand(self.INICIAR)

    def cortar_papel(self):
        self._sendCommand(self.CORTAR_PAPEL_PARCIAL)

    def doble_alto_x_linea(self, text):
        self._sendCommand(self.DOBLE_ALTO_LINE, text + chr(self.TEXT))

    def doble_alto(self, text):
        self._sendCommand(self.DOBLE_ALTO, [chr(self.DOBLE_ALTO_ON)])
        self._sendCommand("", text)
        self._sendCommand(self.DOBLE_ALTO, [chr(self.DOBLE_ALTO_OFF)])

    def doble_ancho(self, text):
        self._sendCommand(self.DOBLE_ANCHO_ON)
        self._sendCommand("", text)
        self._sendCommand(self.DOBLE_ANCHO_OFF)

    def super_script(self, text):
        self._sendCommand(self.SUPERSCRIPT_ON)
        self._sendCommand(self.SUPERSCRIPT_ON_TOP)
        self._sendCommand("", text)
        self._sendCommand(self.SUPERSCRIPT_OFF)

    def sub_script(self, text):
        self._sendCommand(self.SUPERSCRIPT_ON)
        self._sendCommand(self.SUPERSCRIPT_ON_BOTTOM)
        self._sendCommand("", text)
        self._sendCommand(self.SUPERSCRIPT_OFF)

    def italic(self, text):
        self._sendCommand(self.ITALIC_ON)
        self._sendCommand("", text)
        self._sendCommand(self.ITALIC_OFF)

    def buzzer_on(self):
        self._sendCommand(self.BUZZER, [chr(0x41), chr(0x04), "001991"])

    def buzzer_off(self):
        self._sendCommand(self.BUZZER, [chr(0x41), chr(0x04), "000111"])

    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException, e:
            logging.getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
                                   (str(e), commandString))

    def align_left(self, texto):
        self._sendCommand(self.ALIGN)
        self._sendCommand(self.ALIGN_LEFT, [texto])

    def align_center(self, texto):
        self._sendCommand(self.ALIGN)
        self._sendCommand(self.ALIGN_CENTER, [texto])

        # volver a alinear a la izquierda
        self._sendCommand(self.ALIGN)
        self._sendCommand(self.ALIGN_LEFT)

    def align_right(self, texto):
        self._sendCommand(self.ALIGN)
        self._sendCommand(self.ALIGN_RIGHT, [texto])

        # volver a alinear a la izquierda
        self._sendCommand(self.ALIGN)
        self._sendCommand(self.ALIGN_LEFT)

    def print_mesa_mozo(self, mesa, mozo):
        self.doble_alto_x_linea("Mesa: %s" % mesa);
        self.doble_alto_x_linea("Mozo: %s" % mozo);

    def printRemito(self, mesa, items, cliente=None):
        return True

    def printComanda(self, comanda, mesa, mozo, entrada, platos):
        "observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"

        fecha = time.mktime(time.strptime(comanda['created'], '%Y-%m-%d %H:%M:%S'))

        def print_plato(plato):
            "Imprimir platos"
            self.sendCommand(self.TEXT, "%s) %s \n" % (plato['cant'], plato['nombre']))
            if 'observacion' in plato:
                self.sendCommand(self.TEXT, "OBS: " % plato['observacion'])
            if 'sabores' in plato:
                self.sendCommand(self.TEXT, "(")
                for sabor in plato['sabores']:
                    self.sendCommand(self.TEXT, sabor)
                self.sendCommand(self.TEXT, ")")

        self.buzzer_on()
        self.buzzer_off()
        self.align_center("Comanda #%s" % comanda['id'])
        self.align_center(str(fecha))

        if 'observacion' in comanda:
            self.align_center(self.doble_alto_x_linea("OBSERVACION"))
            self._sendCommand(self.TEXT, comanda['observacion'])
            self._sendCommand(self.TEXT, "\n\n")

        if 'entradas' in comanda:
            self.align_center(self.doble_alto_x_linea("ENTRADA"))
            self._sendCommand(self.TEXT, "\n")

            for entrada in comanda['entradas']:
                print_plato(entrada)

        if 'platos' in comanda:
            self.align_center(self.doble_alto_x_linea("- PRINCIPAL -"))
            self._sendCommand(self.TEXT, "\n")

            for plato in comanda['platos']:
                print_plato(plato)

        # plato principal
        self.print_mesa_mozo(mesa, mozo)

        self._sendCommand(self.TEXT, "\n")
        self._sendCommand(self.TEXT, "\n")
        self._sendCommand(self.TEXT, "\n")
        self._sendCommand(self.TEXT, "\n")
        self.cortar_papel()

    def __del__(self):
        try:
            self.close()
        except:
            pass
