
var http = require('http');
var config = require('config');


console.log("iniciando");

var req = http.request({
	host: config.get("Host.name"),
	port: config.get("Host.port"),
	path: "get-js-client",
	method: "GET",
	headers: {'custom': 'fiscalberry-client-base'}
}, function ( response ) {
	console.log("se envio request");
	console.log(response);

	var str = ''
	response.on('data', function (chunk) {
	    str += chunk;
	    console.info("VINOOO "+str);
	});

	response.on('end', function () {
	    console.log(str);
	    console.log("TERMINIOOOOOO "+str);
	});


}).on('error', function(e) {
  console.log("--- - - -- -Got error: " + e.message);
}).end();

/*
http.get({
	host: config.get("Host.name"),
	port: config.get("Host.port"),
	path: "get-js-client"		
}, function(res) {
  console.log("Got response: " + res.statusCode);
}).on('error', function(e) {
  console.log("Got error: " + e.message);
});

*/