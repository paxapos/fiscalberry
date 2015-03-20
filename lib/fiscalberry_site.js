var _ 				= require('underscore');
var config 			= require('config');
var mysqlConnection = require('./mysql_connection.js');	

function Site ( nSite ) {
	/** un sitio puede tener muchas impresoras **/
	this.printers = [];


	_.extend( this, nSite );
	
	this.mysqlConnection = mysqlConnection.createConnection( this.getDbTenant() )._mysqlConnection;

	return this;
};

Site.prototype.getDbTenant = function () {
	return config.get('Database.dbname') + "_" +this.alias ;
};

Site.prototype.addPrinter 	= function ( printer ) {
	this.printers.push(printer);
	printer.site = this;
}

Site.prototype.addPrinters 	= function ( printers ) {
	_.each(printers, this.addPrinter, this);
	return this.printers;
};


/**
*
*	@param object site
*
**/
exports.createSite = function ( site ) {
	var newSite = new Site ( site );	
	return newSite;
};


