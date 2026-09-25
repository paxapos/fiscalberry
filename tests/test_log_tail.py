# coding=utf-8
"""
Tests de readLogTail.

La UI refresca los logs cada segundo en su hilo principal. Leer el archivo
entero (hasta 1 MB antes de rotar) y volcarlo en un Label de Kivy genera una
textura gigante en cada refresco: en Android eso tumbaba la app al arrancar.
Estos tests fijan que solo se lea el final.
"""

from fiscalberry.common.fiscalberry_logger import readLogTail


def test_devuelve_solo_el_final(tmp_path):
    log = tmp_path / "fiscalberry.log"
    log.write_text("".join(f"linea {i}\n" for i in range(100000)), encoding="utf-8")
    assert log.stat().st_size > 100_000

    cola = readLogTail(max_bytes=4096, path=str(log))

    assert len(cola.encode("utf-8")) <= 4096
    assert "linea 99999" in cola, "debe contener el final del archivo"
    assert "linea 0\n" not in cola, "no debe contener el principio"


def test_archivo_chico_se_devuelve_entero(tmp_path):
    log = tmp_path / "fiscalberry.log"
    log.write_text("una sola linea\n", encoding="utf-8")

    assert readLogTail(max_bytes=4096, path=str(log)) == "una sola linea\n"


def test_descarta_la_primera_linea_cortada(tmp_path):
    log = tmp_path / "fiscalberry.log"
    log.write_text("AAAA\n" * 1000, encoding="utf-8")

    cola = readLogTail(max_bytes=52, path=str(log))

    # No debe empezar a mitad de una línea.
    assert cola.startswith("AAAA")


def test_bytes_invalidos_no_explotan(tmp_path):
    log = tmp_path / "fiscalberry.log"
    log.write_bytes(b"linea ok\n\xff\xfe basura binaria\n")

    cola = readLogTail(max_bytes=4096, path=str(log))
    assert "linea ok" in cola


def test_sin_archivo_devuelve_vacio(tmp_path):
    assert readLogTail(path=str(tmp_path / "no-existe.log")) == ""
