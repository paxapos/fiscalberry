var _ 				= require('underscore');
var EventEmitter    = require('events').EventEmitter;
var Util             = require('util');


function Job ( job, printer ) {
	_.extend( this, job);
	this.printer = printer;

	return this;
}


exports.createJob = function ( jobs, printerMaps, pmapPrefix ) {
	if ( !_.isArray(jobs) ) {
		jobs = [jobs];
	}
	var newJobsList = [];
	jobs.forEach(function( j ) {
		var printer = printerMaps [ pmapPrefix + j.site_alias + j.printer_id ];
		newJobs = new Job( j, printer );
		newJobsList.push(newJobs);
	});
	return newJobsList;

}

