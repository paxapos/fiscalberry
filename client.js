

var config = require('config');


 // identificador Unico de la PC
var MACADDRESS;

require('getmac').getMac(function(err,macAddress){
    if (err)  throw err;
	MACADDRESS = macAddress;
});


var WebSocketClient = require('websocket').client;
 
var client = new WebSocketClient();
 
client.on('connectFailed', function(error) {
    console.log('Connect Error: ' + error.toString());
});
 
client.on('connect', function(connection) {
    console.log('WebSocket Client Connected');
    connection.on('error', function(error) {
        console.log("Connection Error: " + error.toString());
    });
    connection.on('close', function() {
        console.log('echo-protocol Connection Closed');
    });
    connection.on('message', function(message) {
        if (message.type === 'utf8') {
            console.log("Received: '" + message.utf8Data + "'");
        }
    });
    
    
});
 
client.connect( 'ws://'+ config.get('Host.name') +':'+ config.get('Host.port') +'/FOLDERLOCO/MALALOCA:macaracasaca', 'echo-protocol', 'mamasita:no-no-no-no-no-si');