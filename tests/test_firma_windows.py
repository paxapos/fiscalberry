# coding=utf-8
"""
Firma Authenticode en el release de Windows (#176).

La firma en sí no se puede probar sin el servicio contratado; lo que se fija
acá es el contrato del workflow, que es lo que hace que un binario sin firmar o
con una firma inesperada no llegue nunca a un release cuando la firma es
obligatoria.
"""

import os

import pytest

yaml = pytest.importorskip("yaml")

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "build-release.yml")
VERIFY = os.path.join(REPO, "build_tools", "verify-signatures.ps1")


@pytest.fixture(scope="module")
def job():
    with open(WORKFLOW, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["jobs"]["build-windows"]


def _pasos(job):
    return {p.get("name", p.get("uses")): (i, p) for i, p in enumerate(job["steps"])}


FIRMAS = ("Sign Windows GUI", "Sign Windows CLI", "Sign Windows Installer")


def test_sin_secretos_no_se_intenta_firmar(job):
    pasos = _pasos(job)
    for nombre in FIRMAS + ("Verify Authenticode signatures",):
        _, paso = pasos[nombre]
        assert paso.get("if") == "steps.firma.outputs.signed == 'true'", nombre


def test_si_la_firma_es_obligatoria_y_faltan_secretos_el_build_falla(job):
    _, chequeo = _pasos(job)["Check Authenticode signing"]
    script = chequeo["run"]
    assert "SIGNING_REQUIRED" in script and "throw" in script
    assert "vars.WINDOWS_SIGNING_REQUIRED" in job["env"]["SIGNING_REQUIRED"]
    for secreto in ("ES_USERNAME", "ES_PASSWORD", "ES_CREDENTIAL_ID", "ES_TOTP_SECRET"):
        assert f"secrets.{secreto}" in job["env"]["SIGNING_AVAILABLE"]


def test_los_ejecutables_se_firman_antes_de_empaquetarlos(job):
    pasos = _pasos(job)
    instalador = pasos["Build Windows Installer"][0]
    zips = pasos["Package Windows Binaries"][0]
    for nombre in ("Sign Windows GUI", "Sign Windows CLI"):
        assert pasos[nombre][0] < instalador < zips, nombre
    # El setup se firma después de compilarlo y se verifica antes de probarlo.
    assert (instalador < pasos["Sign Windows Installer"][0]
            < pasos["Verify Authenticode signatures"][0]
            < pasos["Test Windows Installer"][0])


def test_se_verifican_editor_huella_y_todos_los_binarios(job):
    _, verificar = _pasos(job)["Verify Authenticode signatures"]
    script = verificar["run"]
    assert "verify-signatures.ps1" in script
    assert "vars.WINDOWS_SIGNING_SUBJECT" in script
    assert "vars.WINDOWS_SIGNING_THUMBPRINT" in script
    for binario in ("fiscalberry-gui.exe", "fiscalberry-cli.exe", "FiscalberrySetup.exe"):
        assert binario in script


def test_los_secretos_solo_van_a_la_action_de_firma(job):
    for paso in job["steps"]:
        run = paso.get("run", "")
        assert "secrets." not in run, paso.get("name")
        if "secrets." in str(paso.get("with", {})):
            assert str(paso.get("uses", "")).startswith("sslcom/esigner-codesign@"), paso.get("name")
            assert paso["with"].get("clean_logs") is True


def test_la_verificacion_exige_sello_de_tiempo_y_cadena():
    with open(VERIFY, encoding="utf-8") as fh:
        script = fh.read()
    assert 'Status -ne "Valid"' in script
    assert "TimeStamperCertificate" in script
    assert "X509Chain" in script
    assert "exit 1" in script
