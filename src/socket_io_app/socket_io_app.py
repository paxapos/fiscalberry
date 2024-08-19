from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.clock import Clock
from dotenv import load_dotenv
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException
from kivy.logger import Logger
import Configberry
import socketio
import os
import threading

load_dotenv()


class SocketIoApp(App):
    
    connected: bool = False
    
    def __init__(self, **kwargs):
        super(SocketIoApp, self).__init__(**kwargs)
        self.sio = None

        # load APP config
        configberry = Configberry.Configberry()
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        self.uuid = configberry.config.get("SERVIDOR", "uuid")

        self.sioServerUrl = serverUrl if serverUrl else os.environ.get("SIO_SERVER_URL")

    def build(self):
        self.icon_path = os.path.dirname(__file__)

        return self.root


    def update_label(self, text):
        self.label.text = text

    def store_new_host(self, host):
        Logger.info(f"SocketIoApp: vino para guardar sio_host:: {host} antes estaba {self.sioServerUrl}")
        if host != self.sioServerUrl:
            Logger.info(f"SocketIoApp: se guarda nuevo sio_host:: {host}")
            configberry.writeKeyForSection("SERVIDOR", "sio_host", host)


    def connect_to_server(self, instance):
        self.start_socketio_client()

    def start_socketio_client(self):
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2)


        @self.sio.event
        def connect():
            self.connected = True
            Clock.schedule_once(lambda dt: self.update_label(f"Conectado al servidor sid: {sio.sid}"))

            def handleJoin(*args, **kwargs):
                Logger.info(f"Joined!!!!!!!! OKK {args} {kwargs}")
                Clock.schedule_once(lambda dt: self.update_label("Joineado al ROOM %s", args[0]))

            self.sio.emit("join", data=self.uuid, namespace='/paxaprinter', callback=handleJoin)


        @self.sio.event
        def disconnect():
            self.connected = False
            Clock.schedule_once(lambda dt: self.update_label("Desconectado del servidor"))
            Logger.warning("SocketIO: Desconectado del servidor")

        @self.sio.event
        def connect_error(data):
            self.connected = False
            Clock.schedule_once(lambda dt: self.update_label(f"Error de conexión: {data}"))
            Logger.error(f"SocketIO: Error de conexión - {data}")

        @self.sio.on('my_event', namespace='/paxaprinter')
        def on_my_event(data):
            Clock.schedule_once(lambda dt: self.update_label(f"Evento recibido: {data}"))

        @self.sio.event
        def reconnecting():
            self.connected = False
            Clock.schedule_once(lambda dt: self.update_label("Intentando reconectar..."))
            Logger.info("SocketIO: Intentando reconectar...")


        @self.sio.on('command', namespace='/paxaprinter')
        def on_command(comando):
            print(f"message received with {comando}")

            response = {}
            Logger.info(f"Request \n -> {comando}")
            try:
                if isinstance(comando, str):
                    jsonMes = json.loads(comando, strict=False)
                else:
                    jsonMes = comando
                traductor = TraductoresHandler()
                response = traductor.json_to_comando(jsonMes)
            except TypeError as e:
                errtxt = "Error parseando el JSON %s" % e
                Logger.exception(errtxt)
                response["err"] = errtxt
            except TraductorException as e:
                errtxt = "Traductor Comandos: %s" % str(e)
                Logger.exception(errtxt)
                response["err"] = errtxt
            except KeyError as e:
                errtxt = "El comando no es valido para ese tipo de impresora: %s" % e
                Logger.exception(errtxt)
                response["err"] = errtxt
            except Exception as e:
                errtxt = repr(e) + "- " + str(e)
                Logger.exception(errtxt)
                response["err"] = errtxt

            Logger.info("Response \n <- %s" % response)
            return response



        try:
            self.sio.connect(self.sioServerUrl, namespaces=["/paxaprinter"], headers={"x-uuid":self.uuid})
            Logger.info(f"SocketIoApp: Iniciado SioClient en {self.sioServerUrl} con uuid {self.uuid}")
            #return self.sio.wait()

            # Start the socketio thread
            socketio_thread = threading.Thread(target=lambda: self.sio.wait())
            socketio_thread.daemon = True
            socketio_thread.start()

        except socketio.exceptions.ConnectionError as e:
            Logger.error(f"SocketIoApp: Socketio Connection error: {e}")
            self.sio.disconnect()
        except Exception as e:
            Logger.error(f"SocketIoApp: An unexpected error occurred:: {e}")
        finally:
            self.sio.disconnect()

    def on_start(self):
        # Iniciar con el ícono rojo por defecto
        Logger.info("SocketIoApp: Iniciando la aplicación")

        # Conectarse automáticamente al iniciar la aplicación
        #self.connect_to_server()

