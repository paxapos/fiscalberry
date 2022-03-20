import json
import logging
import socketio

clients = {}
sio = socketio.AsyncServer(async_mode='tornado', async_handlers=True)
password = None

async def getDisconnectedClients():
    return list({client for client, data in clients.items() if not data['connected']})

async def flushDisconnectedClients():
    disconnected = await getDisconnectedClients()
    for client in disconnected:
        clients.pop(client)
    return {"action": f"flushDisconnectedClients ({len(disconnected)})", "rta": disconnected}

async def disconnectByUuid(uuid):
    await sio.disconnect(await getSidByUuid(uuid))

async def disconnectAll():
    for data in clients.values():
        if data['connected']:
            await sio.disconnect(data['sid'])
    return {"action": f"disconnectAll ({len(clients)})", "rta":list(clients.keys())}

async def handleCommandRta(rta):
    rta = {"rta":rta}
    logging.getLogger("SocketIOServer").info(f"Response \n <- {rta}")

async def popBySid(sid):
        clients.pop(await getUuidBySid(sid))
        logging.getLogger("SocketIOServer").info(clients)

async def setDisconnectedState(sid):
    clients[await getUuidBySid(sid)]['connected'] = False

async def getConnectionState(uuid):
    return clients[uuid]['connected']

async def getSidByUuid(uuid):
    return clients[uuid]['sid']

async def getUuidBySid(sid):
    return next((uuid for uuid, data in clients.items() if data['sid'] == sid))

async def listClients():
    print("\n")
    logging.getLogger("SocketIOServer").info(f"   {'N°'.ljust(3, ' ')}|{'UUID'.center(25,' ')}|{'SID'.center(22, ' ')}|{'HOST'.center(16, ' ')}|{'CONNECTED?'.center(10, ' ')}")
    logging.getLogger("SocketIOServer").info("-"*83)
    listed = []
    for idx, (key, data) in enumerate(clients.items()):
        index = f"{idx + 1}".ljust(3," ")
        uuid= f"{key}".center(25, " ")
        sid = f"{data['sid']}".center(22, " ")
        addr = f"{data['addr']}".center(16, " ")
        connected = f"{str(data['connected'])}".center(10, " ")
        logging.getLogger("SocketIOServer").info(f"   {index}|{uuid}|{sid}|{addr}|{connected}")
        listed.append(key)
    return listed

async def getClientConfig(uuid):
    command = {"getActualConfig": f"{password}"}
    return await sendCommand(command, uuid)

async def addClient(sid, env:dict):
    uuid = env['HTTP_X_UUID']
    addr = env['REMOTE_ADDR']
    clients[uuid] = {"sid":sid,"addr":addr, "connected": True}

async def sendCommand(command, uuid):
    command = json.dumps(command)
    try:
        sid = await getSidByUuid(uuid)
        if not await getConnectionState(uuid):
            logging.getLogger("SocketIOServer").error(f"Fiscalberry con la UUID '{uuid}' se encuentra desconectada")
            return False

        logging.getLogger("SocketIOServer").info(command)
        await sio.emit("command", data = command, to = sid, callback = handleCommandRta)
        return True

    except KeyError as e:
        logging.getLogger("SocketIOServer").error(f"Fiscalberry con la UUID '{uuid}' no se encuentra asociada")
        return False


########## EVENT HANDLERS

@sio.event
async def connect(sid, env):
    if env['HTTP_X_PWD'] == password:
        logging.getLogger("SocketIOServer").info(f"Nueva Conexión: {sid} {env['HTTP_X_UUID']}")
        sio.start_background_task(addClient, sid, env)
        return True
    else:
        logging.getLogger("SocketIOServer").info(f"Se rechazó la conexión de {env['HTTP_X_UUID']} por no contar con la contraseña correcta")
        return False

@sio.event
async def disconnect(sid):
    # await popBySid(sid)
    await setDisconnectedState(sid)
    logging.getLogger("SocketIOServer").info("Desconectado %s", sid)

@sio.event
async def closeConnection(sid):
    await sio.disconnect(sid)