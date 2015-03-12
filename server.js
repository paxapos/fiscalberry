#!/usr/bin/env node

	var WebSocketServer = require('websocket').server;
	var http = require('http');
	var mysql = require('mysql');



	var config = require('config');


	var clients = [];

	 
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
	 
	function originIsAllowed(origin) {
	  // put logic here to detect whether the specified origin is allowed. 
	  return true;
	}


	function removeClient ( rmClient ) {
		clients.forEach( function (connection) {
			connection.sendUTF( message.utf8Data);
		});
	}

	function broadcast ( message ) {
		clients.forEach( function (connection) {
			connection.sendUTF( message.utf8Data);
		});
	}
	 
	wsServer.on('request', function(request) {
		console.log(request);
	    if (!originIsAllowed(request.origin)) {
	      // Make sure we only accept requests from an allowed origin 
	      request.reject();
	      console.log((new Date()) + ' Connection from origin ' + request.origin + ' rejected.');
	      return;
	    }
	    
	    var connection = request.accept('echo-protocol', request.origin);
	    clients.push( connection );
	    console.log((new Date()) + ' Connection accepted.');
	    
	    connection.on('close', function(reasonCode, description) {
	        console.log((new Date()) + ' Peer ' + connection.remoteAddress + ' disconnected.');
	        removeClient( connection );
	    });
	});


	function exitHandler () {
		wsServer.shutDown();
		server.close();
	}

	var stdin = process.openStdin();

	console.info("Type 'KILL' to close this server: "); 
	stdin.on('data', function(chunk) { 
		console.log("Got chunk: " + chunk); 
		if ( chunk == "KILL" || chunk == "kill" ) {
			console.info(" cerrando...."); 
			exitHandler();
			process.exit();
		}
	});

	//do something when app is closing
	process.on('exit', exitHandler.bind(null,{cleanup:true}));

	//catches ctrl+c event
	process.on('SIGINT', exitHandler.bind(null, {exit:true}));

	//catches uncaught exceptions
	process.on('uncaughtException', exitHandler.bind(null, {exit:true}));