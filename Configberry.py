import ConfigParser
import os

CONFIG_FILE_NAME = "config.ini"

class Configberry:

	config = ConfigParser.ConfigParser()

	def __init__(self):
		self.config.read(CONFIG_FILE_NAME)

		self.__create_config_if_not_exists()


	def items(self):
		self.config.read(CONFIG_FILE_NAME)
		return self.config.items()


	def sections(self):
		self.config.read(CONFIG_FILE_NAME)

		return  self.config.sections()


	def writeSectionWithKwargs(self, printerName, kwargs):
		self.config = ConfigParser.RawConfigParser()
		self.config.read(CONFIG_FILE_NAME)
		if not self.config.has_section(printerName):
			self.config.add_section(printerName)

			for param in kwargs:
				self.config.set(printerName, param, kwargs[param])
			with open(CONFIG_FILE_NAME, 'w') as configfile:
				self.config.write(configfile)

		return 1;


	def __create_config_if_not_exists(self):
		if not os.path.isfile(CONFIG_FILE_NAME):
			savedPath = os.getcwd()
			newpath = os.path.dirname(os.path.realpath(__file__))
			os.chdir(newpath)
			os.chdir("../")
			import shutil
			newpath += "/config.ini.install"
			shutil.copy (newpath, CONFIG_FILE_NAME)
			os.chdir(savedPath)


	def get_config_for_printer(self, printerName):
		dictConf = {s:dict(self.config.items(s)) for s in self.config.sections()}

		return dictConf[printerName]