import asyncio
from ui.FiscalberryUiApp import MainApp





async def main() -> None:
    def startSocketIOClient():
        MainApp().sioHandler.start()

    def startKivyApp():
        MainApp().run()
        
    # Crear tareas asincrónicas
    start_task = asyncio.create_task(startSocketIOClient())
    additional_tasks = asyncio.create_task(startKivyApp())
    
    # Esperar a que ambas tareas terminen
    await asyncio.gather(start_task, additional_tasks)

if __name__ == '__main__':
    main()

