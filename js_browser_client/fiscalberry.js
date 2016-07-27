

(function($){

	var $fb, // singleton object
		__def, // deferred obect
		__conected = false;

	/** Singleton, devuelve siempre la instancia $fb **/
	Fiscalberry = function ( host, port, uri  ) {
		// WebSocket instance
		var ws;

		if ( typeof port == 'undefined' ) {
			port = 12000; // default fiscalberry port
		}


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
			console.log(arguments);
			if ( typeof port == 'undefined' ) {
				port = 12000; // default fiscalberry server port
			}

			if ( typeof uri == 'undefined' ) {
				uri = "/ws";
			}

			var url = "ws://" + host + ":" + port + uri;
		
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

			// solo responde si me vino un JSON válido, caso contrario lo omite
			ws.onmessage = function(ev) {
				var response=jQuery.parseJSON(ev.data);

				if(typeof response =='object')
				{
					var e = jQuery.Event( "message", { data: response } );
					$fb.trigger('message', e ) ;
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
		


		if ( arguments.length > 0 ) {
			ws = $fb.connect(host, port, uri);
		}

		
		return $fb;

	}
		 
})(jQuery);
