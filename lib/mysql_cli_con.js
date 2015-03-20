var config 			= require('config');
var _ 				= require('underscore');
var client			= require('./fiscalberry_client');
var site			= require('./fiscalberry_site');
var job				= require('./fiscalberry_job');
var EventEmitter    = require('events').EventEmitter;
var Util             = require('util');
var array             = require('array');



Util.inherits(MySqlCliCon, EventEmitter);

function MySqlCliCon ( newClient, mysqlcon ) {
	

	// extender Eventos
	EventEmitter.call(this);


	this.client 			= newClient;

	this._mysqlConnection 	= mysqlcon;


	/** KEY print_IDNUMBER para mappear ID de impresoras **/
	this.printerMapPrefix 	= "printer_";
	
	this.printerMaps 		= {}


	// cola de nuevos trabajos de impresion
	this.newJobs			= array();
	var self = this;

	this.newJobs.on('add', function (){
		var job = self.newJobs.shift();
		self.notifyNewJobCbk( job );
	} );

	
	// inicializacion
	this.loadSitePrinters( this.client );	
	

	return this;
}



MySqlCliCon.prototype.deleteFromDB = function ( job ) {
	 	var mcon = this._mysqlConnection;
 		mcon.query( 'DELETE FROM `printer_jobs` WHERE id = ' + job.id, function(err, rows, fields) {
 			console.info("Job ID %s borrado de la BD "+ config.get('Database.dbname'), job.id);
		  if (err) throw err;			 
		});	
	};


MySqlCliCon.prototype.mysqlSearchForPrintJobs = function () {
	 	var self = this;
	 	var mcon = this._mysqlConnection;
		var pMaps = this.printerMaps;
		var pMapPrefix = this.printerMapPrefix;

 		mcon.query('SELECT * FROM printer_jobs WHERE site_alias IN (' + self.__getSiteAliasListForSql() + ')', function(err, rows, fields) {
		  if (err) throw err;
		  if ( rows.length ) {
			  job.createJob( rows, pMaps, pMapPrefix ).forEach(function(j) {
			  		console.info("metiendo nuevo job");
			  		self.newJobs.push(j);
			  		self.deleteFromDB ( j );
			  });
		  } else {
		  	console.info("No se encontraron JOBS en la BD");
		  }
		});	
	};

MySqlCliCon.prototype.__getSiteAliasListForSql = function () {
	var siteString = '';
	console.info("El cliente tiene %s sitios", this.client.sites.length);
	_.each( this.client.sites, function (s) {
		siteString += "'" + s.alias + "'" + ",";
	});
	return siteString.slice(0, siteString.length - 1 );;
}




MySqlCliCon.prototype.notifyNewJobCbk = function () {
	this.client.notifyNewJobCbk.apply(this.client, arguments);
}





/**
*
*	Le pone al objeto Client los Sitios y a cada Sitio le coloca las Impresoras configuradas
*	Los sitios son tomados de la base de datos filtrando el UUID de cada cliente
*
**/
MySqlCliCon.prototype.loadSitePrinters = function () {

	var mcon = this._mysqlConnection;

	var newClient = this.client;

	/** KEY print_IDNUMBER para mappear ID de impresoras **/
	var printerMapPrefix = this.printerMapPrefix ;
	var printerMaps = this.printerMaps;


	mcon.query('SELECT * FROM sites WHERE machine_uuid = ?', [newClient.uuid], function(err, rows, fields) {
		if (err) throw err;		  
		console.info(rows);
		_.each(rows, function( siteObj ) {
			var newSite = site.createSite( siteObj );
			newClient.addSite( newSite );
			loadPrintersPerSite( newSite );
		}, this);
	});




	function loadPrintersPerSite ( site ) {
console.info(site);
		site.mysqlConnection.query('SELECT * FROM printers',  function(err, printrows, fields) {
			if (err) throw err;		  
			console.info("cargando %s impresoras de %s para tenant %s", printrows.length, site.alias, site.getDbTenant());
			console.log(printrows);
			// vincular las impresoras con el sitio
			var printers = site.addPrinters( printrows );

			// mapp printers
			_.each( printers, function(p) {
				console.info(p.name);
				printerMaps[ printerMapPrefix + site.alias + p.id ] = p;
			});

		});
	}
};

	

MySqlCliCon.prototype.stopFetchingJobs = function () {
		clearInterval( this.intervalFetch );
	};


MySqlCliCon.prototype.startFetchingJobs = function () {
		var ms = config.get('Database.intervalFetch');
		this.intervalFetch = setInterval( this.mysqlSearchForPrintJobs.bind(this), ms);		
	};


/**
* @param web socket connection newWs
* @param string uuid 
* @param mysqlConnection object
*
**/
exports.createNew = function ( newWs, uuid, mysqlConnection ) {

		var newClient = client.createNew( newWs, uuid );

		var mysqlCon = new MySqlCliCon( newClient, mysqlConnection );


		return mysqlCon;
	};


