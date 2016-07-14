

(function($){

	Fiscalberry = function ( host, port, uri  ) {


		var ws;

		var __def = new $.Deferred();
		



		/**
		*
		*	Conecta con el web socket
		*
		**/
		this.connect = function( host, port, uri ) {
			if ( typeof uri == 'undefined' ) {
				uri = "/ws";
			}

			var url = "ws://" + host + ":" + port + uri;

			// create websocket instance
			ws = new WebSocket(url);

			__def.resolve(this);

			return ws;
		}


		/**
		*
		*	Solo se ejecutara una vez el listener y luego se destruira
		*
		**/
		this.onceOpen = function ( fn ) {
			__def.done(function(){
				ws.addEventListener("open", fn, false);
				ws.removeEventListener("open", fn, false);
			})
		}


		/**
		*
		*	Listeners
		*
		**/
		this.onOpen = function( fn ) {
			__def.done(function(){
				return ws.addEventListener("open", fn);
			});
		}

		this.onClose = function( fn ) {
			__def.done(function(){
				return ws.addEventListener("close", fn);
			});
		}

		this.onMsg = function( fn ) {
			__def.done(function(){
				return ws.addEventListener("message", fn);
			});
		}

		this.onError = function( fn ) {
			__def.done(function(){
				return ws.addEventListener("error", fn);
			});
		}


		/**
		*
		*	Envia mensaje por medio del web socket conactado
		*
		**/
		this.send = function() {
			var fnargs = arguments;
			__def.done(function(){
				return ws.send.apply(ws, fnargs)
			});
		}
		

		if ( typeof host != 'undefined'
				&& typeof port != 'undefined'
			) {
			ws = this.connect(host, port);
		}


		

		return __def.promise( this );

	}
		 
})(jQuery);
