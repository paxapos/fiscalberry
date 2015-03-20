var _ 				= require('underscore');



/**
* @param web socket connection newWs
* @param string uuid 
*
**/
function Client ( curWsConnection, uuid) {
	/** Web Socket COnnection **/
	this.wsConnection = curWsConnection;

	/** ID unico por cliente */
	this.uuid = uuid;

	/** array de sitios **/
	this.sites = [];


	return this;
}


/**
*
*	Agrega uno o un array de sitios
*
*
**/
Client.prototype.addSite = function ( newSite ) {

	if ( !_.isArray(newSite) ) {
	newSite = [newSite];
	}

	var self = this;

	newSite.forEach(function( ns ) {
		ns.client = self;
		self.sites.push(ns);
	});

	return this.sites;
}

Client.prototype.notifyNewJobCbk = function ( data ) {
	// remove circular data
	var printer = data.printer;

	var sendJob = {
		"site_alias"	: data.site_alias,
		"text"			: data.text,
		"printer"		: {
			"id"		: data.printer.id,
			"name"		: data.printer.name,
			"alias"		: data.printer.alias,
			"driver"	: data.printer.driver,
			"driver_model": data.printer.driver_model,
			"output"	: data.printer.output
		}
	};

	this.wsConnection.sendUTF(  JSON.stringify(sendJob) );
}


Client.prototype.addPrintJob = function ( data ) {
		this.wsConnection.sendUTF( "'" + JSON.stringify(data) + "'");
}



exports.createNew = function ( curWsConnection, uuid ) {
	return new Client( curWsConnection, uuid );
};

