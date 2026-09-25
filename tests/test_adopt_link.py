# coding=utf-8
"""
El link de vinculación nunca puede quedar sin identificador.

Caso real: el config.ini del celular se quedó sin uuid, la pantalla armó
`https://beta.paxapos.com/adopt/` y el botón "Abrir vinculación" llevó a una
pantalla de error del servidor:

    [ArgumentCountError] Too few arguments to function
    PaxaprinteresController::adopt(), 0 passed and exactly 1 expected
    Request URL: /adopt/

El QR quedaba en blanco por lo mismo. Desde el lado del usuario no había forma
de saber qué pasaba: el botón se veía igual que siempre.
"""

import pytest

from fiscalberry.ui.adopt_screen import link_de_adopcion_valido


@pytest.mark.parametrize("url", [
    "https://beta.paxapos.com/adopt/",
    "https://beta.paxapos.com/adopt",
    "https://beta.paxapos.com/adopt///",
    "",
    None,
])
def test_rechaza_links_sin_uuid(url):
    assert link_de_adopcion_valido(url) is False


@pytest.mark.parametrize("url", [
    "https://beta.paxapos.com/adopt/263ae979-f969-4630-bc49-3bb44e04f86c",
    "https://paxapos.com/adopt/abc-123",
    "https://dev2.paxapos.com/adopt/263ae979-f969-4630-bc49-3bb44e04f86c/",
])
def test_acepta_links_con_uuid(url):
    assert link_de_adopcion_valido(url) is True
