'''
basado en
https://github.com/vesellov/android-twisted-service/blob/master/src/service/main.py

'''
import time
from jnius import autoclass
from android import AndroidService

import time


# importo el modulo que se encarga de la comunicacion con el servidor
from fiscalberry_sio import FiscalberrySio
from common.discover import send_discover_in_thread
from common.Configberry import Configberry


# Obtener el directorio de datos de la aplicación
import android
data_dir = android.get_external_storage_path()

from twisted.internet import reactor
from twisted.internet import protocol
from twisted.web import server, resource

from common.fiscalberry_logger import getLogger
logger = getLogger()

from twisted.internet.defer import setDebugging
setDebugging(True)

from twisted.python.log import startLogging
startLogging(sys.stdout)



def set_auto_restart_service(restart=True):
    logger.info('set_auto_restart_service restart=%r', restart)
    from jnius import autoclass
    Service = autoclass('org.kivy.android.PythonService').mService
    Service.setAutoRestartService(restart)
    

def set_foreground():
    logger.info('set_foreground')
    from jnius import autoclass
    channel_id = 'com.paxapos.fiscalberry.Fiscalberryserver'
    Context = autoclass(u'android.content.Context')
    Intent = autoclass(u'android.content.Intent')
    PendingIntent = autoclass(u'android.app.PendingIntent')
    AndroidString = autoclass(u'java.lang.String')
    NotificationBuilder = autoclass(u'android.app.Notification$Builder')
    NotificationManager = autoclass(u'android.app.NotificationManager')
    NotificationChannel = autoclass(u'android.app.NotificationChannel')
    notification_channel = NotificationChannel(
        channel_id, AndroidString('TwistedSample Channel'.encode('utf-8')), NotificationManager.IMPORTANCE_HIGH)
    Notification = autoclass(u'android.app.Notification')
    service = autoclass('org.kivy.android.PythonService').mService
    PythonActivity = autoclass(u'org.kivy.android.PythonActivity')
    notification_service = service.getSystemService(
        Context.NOTIFICATION_SERVICE)
    notification_service.createNotificationChannel(notification_channel)
    app_context = service.getApplication().getApplicationContext()
    notification_builder = NotificationBuilder(app_context, channel_id)
    title = AndroidString("Fiscalberry".encode('utf-8'))
    message = AndroidString("Aplicación corriendo en background".encode('utf-8'))
    app_class = service.getApplication().getClass()
    notification_intent = Intent(app_context, PythonActivity)
    notification_intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP |
        Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK)
    notification_intent.setAction(Intent.ACTION_MAIN)
    notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
    intent = PendingIntent.getActivity(service, 0, notification_intent, 0)
    notification_builder.setContentTitle(title)
    notification_builder.setContentText(message)
    notification_builder.setContentIntent(intent)
    Drawable = autoclass(u"{}.R$drawable".format(service.getPackageName()))
    icon = getattr(Drawable, 'icon')
    notification_builder.setSmallIcon(icon)
    notification_builder.setAutoCancel(True)
    new_notification = notification_builder.getNotification()
    service.startForeground(1, new_notification)
    logger.info('set_foreground DONE : %r' % service)

class Fiscalberryservice():
    
    def __init__(self):
        self.service = AndroidService('Fiscal Service', 'Running')
        self.service.start_in_thread('Fiscal Service Running')
        self.run()

    def start(self):
        configberry = Configberry()
        serverUrl = configberry.config.get("SERVIDOR", "sio_host", fallback="")
        uuid = configberry.config.get("SERVIDOR", "uuid")
        send_discover_in_thread()
        sio = FiscalberrySio(serverUrl, uuid)
        sio.start_print_server()
        
    def stop(self):
        self.service.stop()

if __name__ == '__main__':
    fbs = FiscalberryService()
    
    argument = os.environ.get('PYTHON_SERVICE_ARGUMENT', 'null')
    argument = json.loads(argument) if argument else None
    argument = {} if argument is None else argument
    logger.info('argument=%r', argument)
    if argument.get('stop_service'):
        logger.info('service to be stopped')
        fbs.stop()
        return
    try:
        set_foreground()
        set_auto_restart_service()
        logger.info('starting fiscalberry sockeit io client')
        fbs.start() # aca bloquea con sio.wait()
        logger.info('finalizo socket io client')
        set_auto_restart_service(False)
    except Exception:
        logger.exception('Exception in main()')
        # avoid auto-restart loop
        set_auto_restart_service(False)
