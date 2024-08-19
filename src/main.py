import asyncio
from socket_io_app.socket_io_app import SocketIoApp
from fiscalberry_logger import getLogger

Logger = getLogger()

if __name__ == '__main__':
    try:
        SocketIoApp().run()
    except Exception as e:
        Logger.error(f'Error: {e}')
        Logger.exception('Exception occurred:')

