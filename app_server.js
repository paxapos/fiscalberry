#!/usr/bin/env node

	var WebSocketServer = require('websocket').server;
	var http = require('http');

	var mysqlConnection = require('./lib/mysql_connection.js');	
	var config = require('config');


	var server = http.createServer(function(request, response) {
	    console.log((new Date()) + ' Received request for ' + request.url);
	    response.writeHead(404);
	    response.end();
	});
	server.listen( config.get('Host.port'), function() {
	    console.log((new Date()) + ' Server is listening on port '+config.get('Host.port'));
	});
	 
	wsServer = new WebSocketServer({
	    httpServer: server,
	    // You should not use autoAcceptConnections for production 
	    // applications, as it defeats all standard cross-origin protection 
	    // facilities built into the protocol and the browser.  You should 
	    // *always* verify the connection's origin and decide whether or not 
	    // to accept it. 
	    autoAcceptConnections: false
	});



	server.on('request', function() {
		console.info("Vino REQUESTTTTT");
	});

	var dbServer = mysqlConnection.createConnection();
	
	//return new Error("Can't divide by zero")
	 
	function originIsAllowed(origin) {
	  // put logic here to detect whether the specified origin is allowed. 
	  return true;
	}


	 
	wsServer.on('request', function(request) {
		var clienUuid = request.httpRequest.headers.origin;
	    if (!originIsAllowed(request.origin)) {
	      // Make sure we only accept requests from an allowed origin 
	      request.reject();
	      console.log((new Date()) + ' Connection from origin ' + request.origin + ' rejected UUID: '+clienUuid);
	      return;
	    }
	    
	    var connection = request.accept( config.get("Host.protocol"), request.origin);
	    console.log((new Date()) + ' Nuevo cliente: ' + clienUuid);
	    var clienteConectado = dbServer.addClient( connection, clienUuid );
	    clienteConectado.startFetchingJobs();			

	    connection.on('close', function(reasonCode, description) {
	   		clienteConectado.stopFetchingJobs();			
	   		console.info("cliente desconectado");
	    });
		
		


	});


	function exitHandler () {
		console.info(" cerrando...."); 
		//dbServer.end		wsServer.shutDown();
		server.close();
	}

	var stdin = process.openStdin();

	console.info("Type 'KILL' to close this server: "); 
	stdin.on('data', function(chunk) { 
		console.log("Got chunk: " + chunk); 
		if ( chunk == "KILL\n" || chunk == "kill\n" ) {
			exitHandler();
			process.exit();
		}

	});

	//do something when app is closing
	process.on('exit', exitHandler.bind(null,{cleanup:true}));

	//catches ctrl+c event
	//process.on('SIGINT', exitHandler.bind(null, {exit:true}));

	//catches uncaught exceptions
	//process.on('uncaughtException', exitHandler.bind(null, {exit:true}));