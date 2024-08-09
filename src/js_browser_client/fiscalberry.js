// Polyfill isArray()
if (!Array.isArray) {
    Array.isArray = function (arg) {
        return Object.prototype.toString.call(arg) === '[object Array]';
    };
}


(function ($) {

    var $fb, // singleton object
        __def, // deferred obect
        __conected = false;

    /** Singleton, devuelve siempre la instancia $fb **/
    Fiscalberry = function (host, port, uri, ssl) {
        // WebSocket instance
        var ws;

        if (typeof host == 'undefined' || !host) {
            host = "localhost"; // default fiscalberry host
        }

        if (typeof port == 'undefined') {
            port = 12000; // default fiscalberry port
        }

        if (typeof ssl == 'undefined' || ssl == false ) {
            ssl = false; // default fiscalberry SSL
        }

        // real Fiscalberry object that will be returned as instance
        if (!$fb) {
            $fb = $({});
            __def = new $.Deferred();
            $fb.promise = __def.promise();
        }


        /**
         *    Indica si esta conectado o no con el websocket
         *    @return Boolean true si esta conectado, false si no lo esta
         **/
        $fb.isConnected = function () {
            return __conected;
        };


        /**
         *
         *    Maneja todos los mensajes del webcocket
         *    envia un evento
         *    Evento "message"
         *    @param response es el objeto json que viene del websocket
         **/
        function handleWSMessage(response) {
            var evName = "message";
            var e = jQuery.Event(evName, {data: response});
            $fb.trigger(evName, e);
        }


        /**
         *
         *    Maneja los mensajes que vienen del websocket
         *    y cuando es del tipo msg envia un trigger
         *    Evento "fb:msg"
         *    @param response es el objeto json que viene del websocket
         **/
        function handleFbMsg(response) {
            var evName = "fb:msg";
            if (response.hasOwnProperty("msg")) {
                var data = {"data": response['msg']};
                var e = jQuery.Event(evName, data);
                $fb.trigger(evName, e);

                for (var key in response['msg']) {
                    evName = "fb:msg:" + key;
                    data = {"data": response['msg'][key]};
                    e = jQuery.Event(evName, data);

                    $fb.trigger(evName, e);
                }
            }
        }


        /**
         *
         *    Maneja los mensajes que vienen del websocket
         *    y cuando es del tipo msg envia un trigger
         *    Evento "fb:msg"
         *    @param response es el objeto json que viene del websocket
         **/
        function handleFbErr(response) {
            var evName = "fb:err";
            if (response.hasOwnProperty("err")) {
                var data = {"data": response['err']};
                var e = jQuery.Event(evName, data);
                $fb.trigger(evName, e);
            }
        }


        /**
         *
         *    Maneja los mensajes que vienen del websocket
         *    y cuando es del tipo rta envia un trigger
         *    Evento "fb:rta"
         *    @param response es el objeto json que viene del websocket
         **/
        function handleFbRta(response) {
            var evName = "fb:rta";
            var actionName;
            if (response.hasOwnProperty("rta")) {
                var data = {"data": response['rta']};
                var e = jQuery.Event(evName, data);
                $fb.trigger(evName, e);

                function logRta(rtarespo) {
                    if (rtarespo.hasOwnProperty("action")) {
                        actionName = rtarespo['action'];
                        evName = "fb:rta:" + actionName;
                        data = {"data": rtarespo['rta']};
                        e = jQuery.Event(evName, data);

                        $fb.trigger(evName, e);
                    }
                }

                if (Array.isArray(response['rta'])) {
                    for (var i = response['rta'].length - 1; i >= 0; i--) {
                        logRta(response['rta'][i]);
                    }
                } else {
                    logRta(response['rta']);
                }
            }
        }

        /**
         *
         *    Conecta con el web socket
         *    creando una nueva instancia ws
         *    @return WebSocket instance
         **/
        $fb.connect = function (host, port, uri, ssl) {
            if (typeof port == 'undefined') {
                port = 12000; // default fiscalberry server port
            }

            if (typeof uri == 'undefined') {
                uri = "/ws";
            }


            if (typeof ssl == 'undefined' || ssl == false ) {
                ssl = false; // default fiscalberry SSL
            } else {
                ssl = true;
            }

            var wsURI = 'ws';
            if ( ssl ) {
                wsURI = 'wss';
            }
            var url = wsURI+"://" + host + ":" + port + uri;

            ws = new WebSocket(url);
            ws.addEventListener('open', function (e) {
                __def.resolve(ws);
                $fb.trigger('open');
                __conected = true;
            });
            
            ws.addEventListener('error', function (e) {
                __def.reject(e);
                $fb.trigger('error');
                __conected = false;
            });

            ws.addEventListener('close', function () {
                $fb.trigger('close');
                __conected = false;
            });

            // solo responde si me vino un JSON válido, caso contrario lo omite
            ws.addEventListener('message', function (ev) {
                var response = JSON.parse(ev.data);

                if (typeof response == 'object') {

                    handleWSMessage(response);
                    handleFbMsg(response);
                    handleFbRta(response);
                    handleFbErr(response);

                }

            });


            return ws;
        };


        /**
         *
         *    Envia mensaje por medio del web socket conectado
         *
         **/
        $fb.send = function () {
            var fnargs = arguments;
            try {
                var jsonstr;
                if ( typeof fnargs[0] == 'string' ) {
                    jsonstr = fnargs[0];
                } else {
                    jsonstr = JSON.stringify(fnargs[0]);
                }
                JSON.parse(jsonstr);
                return ws.send.apply(ws, fnargs);
            } catch (e) {
                return $.error(e);
            }
        };


        if (arguments.length > 0) {
            ws = $fb.connect(host, port, uri);
        }


        return $fb;

    }

})(jQuery);
