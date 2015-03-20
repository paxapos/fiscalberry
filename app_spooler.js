var temp = require('temp'),
    fs   = require('fs'),
	http = require('http'),
    exec = require('child_process').exec;



var interval = null;


function printToFiscal () {
	var dev_name = "fiscalprinter";

	// Automatically track and cleanup files at exit
	temp.track();

	// Fake data
	var myData = "foo\nbar\nfoo\nbaz";

	// Process the data (note: error handling omitted)
	temp.open('myprefix', function(err, info) {
	  if (!err) {
	    fs.write(info.fd, myData);
	    fs.close(info.fd, function(err) {
	      exec("grep foo '" + info.path + "' | wc -l", function(err, stdout) {
	        util.puts(stdout.trim());
	      });
	    });
	  }
	});

}


