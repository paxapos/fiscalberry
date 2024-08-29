# -*- coding: UTF-8 -*-
from escpos.constants import *

#for printer.set()
CENTER = "center"
LEFT = "left"
RIGHT = "right"

FONT_A = "a"
FONT_B = "b"

NORMAL = "normal"
BOLD = "bold"
UNDERLINED = "underline"
BOLD_UNDERLINED = "BU"

#for individual text formatting
UNDERLINED_ON = '\x1b\x2d\x01'
UNDERLINED2_ON = '\x1b\x2d\x02'
UNDERLINED_OFF = '\x1b\x2d\x00'

BOLD_ON = '\x1b\x45\x01'
BOLD_OFF = '\x1b\x45\x00'

PARTIAL_CUT = "PART"
