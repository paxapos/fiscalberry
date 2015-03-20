
var config = require('config');
var WebSocketClient = require('websocket').client;

var temp = require('temp'),
    fs   = require('fs'),
    util = require('util'),
    exec = require('child_process').exec;





/** Client MACADDRESS **/
var clientUuid;


var retry = 0;
var maxRetry = 9999999999999;
var retryMsTime = 3000;

var timeout = null;

function retryConnect ( ) {
    if ( !timeout && retry < maxRetry ) {
        console.info("Intentando conexion %s (maximos intentos: %s)", retry+1, maxRetry );
        timeout = setTimeout( connectClient, retryMsTime );
    } else {
        console.info("Se alcanzaró la cantidad maxima de intentos (%s)... saliendo", maxRetry );
    }
}



function handleJob ( data ) {
    process.on('uncaughtException', function(err) {
      console.log('Caught exception: ' + err);
    });

    var job = JSON.parse( data.utf8Data );


    temp.open('fiscalberry', function(err, info) {
      if (err) throw err;
      fs.write(info.fd, job.text);
      fs.close(info.fd, function(err) {
        if (err) throw err;
        exec("lp -d " + job.printer.alias + " " + info.path, function(err, stdout) {
              if (err) throw err;
              console.info (stdout.trim() );
            });
       

      });
    });



   
   

}

function connectClient () {
    timeout = true;
    retry++;

    var client = new WebSocketClient();
     
    client.on('connectFailed', retryConnect);
     
    client.on('connect', function(connection) {
        retry = 0;

        console.log('WebSocket Client Connected');
        
        connection.on('error', retryConnect );
        connection.on('close', retryConnect );

        connection.on('message', handleJob );
    });


    client.connect( 'ws://'+ config.get('Host.name') +':'+ config.get('Host.port'), config.get("Host.protocol"), clientUuid);
    timeout = false;
}



require('getmac').getMac(function(err,macAddress){
    if (err)  throw err;
    clientUuid = macAddress;
    console.info("El UUID de este cliente es: "+clientUuid);

    retryConnect();

});



 

//do something when app is closing
//process.on('exit', exitHandler.bind(null,{cleanup:true}));

//catches ctrl+c event
//process.on('SIGINT', exitHandler.bind(null, {exit:true}));

//catches uncaught exceptions
//process.on('uncaughtException', exitHandler.bind(null, {exit:true}));