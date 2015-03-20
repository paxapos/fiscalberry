var _ 				= require('underscore');
var config 			= require('config');


function Site ( nSite, client ) {
	/** un sitio puede tener muchas impresoras **/
	this.printers = [];
	this.client = client;
	this.alias = "";
	_.extend( this, nSite);

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
exports.createSite = function ( site, client ) {
	var newSite = new Site ( site, client );	
	return newSite;
};


