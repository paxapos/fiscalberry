import json
from kivy.logger import Logger
import socketio
from kivy.clock import Clock
from Traductores.TraductoresHandler import TraductoresHandler, TraductorException



sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2, logger=False, engineio_logger=False)

def start_socketio_client(fiscalberryApp):

    if sio.connected:
        Logger.info("Ya conectado al servidor")
        return sio

    @sio.event(namespace='/paxaprinter')
    def connect_paxaprinter(sid, data):
        fiscalberryApp.connected = True
        
        Clock.schedule_once(lambda dt: setattr(fiscalberryApp, 'connected', True))
        

        Logger.info("SocketIO: Conectado al NAMESPACEEEE !!! IOIOI")
        
        def handleJoin(*args, **kwargs):
            Logger.info(f"Joined!!!!!!!! OKK {args} {kwargs}")
            fiscalberryApp.log_widget.add_log(f"Joined!!!!!!!! OKK {args} {kwargs}")

            Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
                "Joineado al ROOM %s", args[0]))                

        sio.emit("join", data=fiscalberryApp.uuid,
            namespace='/paxaprinter', callback=handleJoin)


    @sio.event()
    def connect():
        Logger.info("SocketIO: Conectado al servidor * * * * !!!! OOOOKKK")
        fiscalberryApp.connected = True
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            f"Conectado al servidor sid: {sio.sid}"))

        def handleJoin(*args, **kwargs):
            Logger.info(f"Joined!!!!!!!! OKK {args} {kwargs}")
            fiscalberryApp.log_widget.add_log(f"Joined!!!!!!!! OKK {args} {kwargs}")

            Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
                "Joineado al ROOM %s", args[0]))                

        sio.emit("join", data=fiscalberryApp.uuid,
            namespace='/paxaprinter', callback=handleJoin)

    @sio.event
    def disconnect():
        fiscalberryApp.connected = False
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            "Desconectado del servidor"))
        Logger.warning("SocketIO: Desconectado del servidor")            

    @sio.event
    def connect_error(data):
        fiscalberryApp.connected = False
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            f"Error de conexión: {data}"))
        Logger.error(f"SocketIO: Error de conexión - {data}")            

    # mostrar log con cada evento o mensaje recibido
    @sio.on('message', namespace='/paxaprinter')
    def on_message(data):
        fiscalberryApp.log_widget.add_log(f"Mensaje recibido: {data}")
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            f"Mensaje recibido: {data}"))            

    @sio.on('*', namespace='*')
    def any_event_any_namespace(event, namespace, sid, data):
        Logger.info(f"Any event {event} nsp: {namespace} sid: {sid} data:{data}")            

    
    @sio.on('*')
    def any_event(*kargs, **kwargs):
        Logger.info(f"Any event {kargs}")            

    @sio.on('my_event', namespace='/paxaprinter')
    def on_my_event(data):
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            f"Evento recibido: {data}"))            

    @sio.event
    def reconnecting():
        fiscalberryApp.connected = False
        Clock.schedule_once(lambda dt: fiscalberryApp.update_label(
            "Intentando reconectar..."))
        Logger.info("SocketIO: Intentando reconectar...")            

    @sio.on('command', namespace='/paxaprinter')
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
        sio.connect(fiscalberryApp.sioServerUrl, transports=['websocket'],  namespaces=[
            "/paxaprinter"], headers={"x-uuid": fiscalberryApp.uuid})
    except Exception as e:
        Logger.error(f"Error al conectar con el servidor: {e}")
        fiscalberryApp.add_log(f"Error al conectar con el servidor: {e}")
        return
    
    return sio

    
    
