import usb.core
import usb.util
import libusb

from escpos import escpos,constants
from Drivers.ReceiptUSBDriver import ReceiptUSBDriver
import sys



printer = ReceiptUSBDriver("0x20d1", "0x7008")
printer.start()
printer.text("Hello World\n")
#printer.qr("https://www.afip.gob.ar/fe/qr/?p="+"gusadgsdguysgd", ec=constants.QR_ECLEVEL_H, size=8, model=constants.QR_MODEL_2 , native=False, center=True, impl='bitImageRaster')
printer.qr("https://www.afip.gob.ar/fe/qr/?p="+"gusadgsdguysgd", ec=constants.QR_ECLEVEL_Q, size=3, model=constants.QR_MODEL_2 , native=True)
printer.cut()
printer.end()

printer.QR_ECLEVEL_Q 

