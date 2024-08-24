import asyncio
from fiscalberry_app.fiscalberry_app import FiscalberryApp
from fiscalberry_logger import getLogger

Logger = getLogger()

if __name__ == '__main__':
    try:
        FiscalberryApp().run()
    except Exception as e:
        Logger.error(f'Error: {e}')
        Logger.exception('Exception occurred:')

