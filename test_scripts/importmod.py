import importlib
#from importlib import import_module


driverName = "Hasar"
module = __import__("..Drivers."+driverName+"Driver", globals(), locals(), [driverName+"Driver"], 0)

#class_ = getattr(module, driverName+"Driver")
#instance = class_()