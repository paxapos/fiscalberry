var mysql 			= require('mysql');
var config 			= require('config');
var _ 				= require('underscore');
var EventEmitter    = require('events').EventEmitter;
var mysqlCliCon			= require('./mysql_cli_con');
var site			= require('./fiscalberry_site');




function MySqlConnection () {

	// extender Eventos
	EventEmitter.call(this);

	this.intervalFetch	  =	null;

	this._mysqlConnection = mysql.createConnection({
	  host     : config.get('Database.host'),
	  user     : config.get('Database.user'),
	  password : config.get('Database.pass'),
	  multipleStatements: true
	});	  
	
}



/*
MySqlCliCon.prototype.addUuid = function ( clientUuid ) {
		this._clients.push( clientUuid );
		EventEmitter.emit("client:added", clientUuid);
	};
*/


MySqlConnection.prototype.end = function () {
		this._mysqlConnection.end();
	};

MySqlConnection.prototype.endMysqlConnection = function () {
		this.emit("end");
	};




/**
* @param web socket connection newWs
* @param string uuid 
*
**/
MySqlConnection.prototype.addClient = function ( newWs, uuid ) {
		var newcli = mysqlCliCon.createNew( newWs, uuid, this._mysqlConnection );		

		return newcli;
};




var connSingleton = null;

exports.createConnection = function () {
	if ( connSingleton === null ) {
		connSingleton = new MySqlConnection;
	}
	
	return connSingleton;
}
