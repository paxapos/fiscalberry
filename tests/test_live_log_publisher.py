import threading

from fiscalberry.common.rabbitmq.live_log_publisher import LiveLogMqttPublisher


class FakeResult:
    def __init__(self, rc=0):
        self.rc = rc


class FakeClient:
    """Cliente paho falso: registra llamadas y permite simular el on_connect."""

    def __init__(self, client_id, clean_session, protocol):
        self.client_id = client_id
        self.clean_session = clean_session
        self.credentials = None
        self.connect_args = None
        self.published = []
        self.loop_started = False
        self.disconnected = False
        self.on_connect = None
        self.on_disconnect = None

    def username_pw_set(self, user, password):
        self.credentials = (user, password)

    def reconnect_delay_set(self, min_delay, max_delay):
        pass

    def tls_set(self, ca_certs=None):  # pragma: no cover - sin TLS en estos tests
        pass

    def connect_async(self, host, port, keepalive):
        self.connect_args = (host, port, keepalive)

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_started = False

    def disconnect(self):
        self.disconnected = True

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        return FakeResult(0)


def _publisher(credentials, connect_timeout=0.2):
    created = []

    def factory(client_id, clean_session, protocol):
        client = FakeClient(client_id, clean_session, protocol)
        created.append(client)
        return client

    publisher = LiveLogMqttPublisher(
        "uuid-1",
        credentials_provider=lambda: credentials,
        tls_config_provider=lambda: {"use_tls": False},
        client_factory=factory,
        connect_timeout=connect_timeout,
    )
    return publisher, created


CREDS = {"host": "broker.test", "port": "1883", "user": "fiscalberry", "password": "secreto"}


def test_sin_credenciales_no_crea_conexion_y_cuenta_como_perdido():
    publisher, created = _publisher(credentials=None)

    assert publisher.publish("fiscalberry/logs/t/uuid-1/s", "{}") is False
    assert created == []


def test_usa_un_client_id_propio_distinto_del_de_impresion_y_errores():
    publisher, created = _publisher(CREDS)
    publisher.publish("fiscalberry/logs/t/uuid-1/s", "{}")

    client = created[0]
    # El consumer usa fiscalberry-{uuid} y los errores fiscalberry-errors-...:
    # repetir alguno haria que el broker patee esa conexion.
    assert client.client_id == "fiscalberry-logs-uuid-1"
    assert client.clean_session is True
    assert client.credentials == ("fiscalberry", "secreto")
    assert client.connect_args == ("broker.test", 1883, 30)
    assert client.loop_started is True


def test_publica_cuando_el_broker_confirma_la_conexion():
    publisher, created = _publisher(CREDS, connect_timeout=2)

    def conectar_en_un_rato():
        while not created:
            pass
        created[0].on_connect(created[0], None, {}, 0)

    hilo = threading.Thread(target=conectar_en_un_rato)
    hilo.start()
    assert publisher.publish("fiscalberry/logs/t/uuid-1/s", '{"a":1}', 0) is True
    hilo.join()
    assert created[0].published == [("fiscalberry/logs/t/uuid-1/s", '{"a":1}', 0)]


def test_sin_confirmacion_del_broker_devuelve_false():
    publisher, created = _publisher(CREDS, connect_timeout=0.1)

    assert publisher.publish("fiscalberry/logs/t/uuid-1/s", "{}") is False
    assert created[0].published == []


def test_conexion_rechazada_no_publica():
    publisher, created = _publisher(CREDS, connect_timeout=0.1)
    publisher._ensure_client()
    created[0].on_connect(created[0], None, {}, 5)  # 5 = no autorizado

    assert publisher.publish("fiscalberry/logs/t/uuid-1/s", "{}") is False


def test_close_cierra_y_la_proxima_sesion_reconecta():
    publisher, created = _publisher(CREDS)
    publisher._ensure_client()
    created[0].on_connect(created[0], None, {}, 0)
    assert publisher.is_connected()

    publisher.close()

    assert created[0].disconnected is True
    assert created[0].loop_started is False
    assert not publisher.is_connected()

    publisher._ensure_client()
    assert len(created) == 2
