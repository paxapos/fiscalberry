

(function($){

	var $fb, // singleton object
		__def, // deferred obect
		__conected = false;

	/** Singleton, devuelve siempre la instancia $fb **/
	Fiscalberry = function ( host, port, uri  ) {
		// WebSocket instance
		var ws;


		// real Fiscalberry object that will be returned as instance
		if ( !$fb ) {
			$fb = $({});
			__def = new $.Deferred();
			$fb.promise = __def.promise();
		}

	
		/**
		*	Indica si esta conectado o no con el websocket
		*	@return Boolean true si esta conectado, false si no lo esta
		**/
		$fb.isConnected = function() {
			return __conected;
		}
		


		/**
		*
		*	Conecta con el web socket
		*	creando una nueva instancia ws
		*	@return WebSocket instance
		**/
		$fb.connect = function( host, port, uri ) {
			if ( typeof port != 'undefined' ) {
				port = 12000; // default fiscalberry server port
			}

			if ( typeof uri == 'undefined' ) {
				uri = "/ws";
			}

			var url = "ws://" + host + ":" + port + uri;
		

			// create websocket instance
			if ( !ws ) {
				
				ws = new WebSocket(url);
				ws.onopen = function(e) {
					__def.resolve(ws);
					$fb.trigger('open');
					__conected = true;
				}
				ws.onerror = function(e) {
					__def.reject(e);
					$fb.trigger('error');
					__conected = false;
				}
				ws.onclose = function() {
					$fb.trigger('close');
					__conected = false;
				}
				ws.onmessage = function(ev) {
					console.debug(ev.data);
					$fb.trigger('message', ev ) ;
				}
			
			}

			return ws;
		}

		

		/**
		*
		*	Envia mensaje por medio del web socket conectado
		*
		**/
		$fb.send = function() {
			var fnargs = arguments;
			return ws.send.apply(ws, fnargs);
		}
		


		if ( typeof host != 'undefined' ) {
			ws = $fb.connect(host, port, uri);
		}

		
		return $fb;

	}
		 
})(jQuery);
