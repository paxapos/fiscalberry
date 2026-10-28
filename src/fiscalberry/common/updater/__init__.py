"""
Auto-actualización multiplataforma.

La lógica de decidir QUÉ versión corresponde, bajarla y verificarla es común a
todas las plataformas; lo único que cambia es el último paso —aplicarla—, que
en cada sistema operativo se hace distinto. Ver `appliers.py`.

Regla central (ver `service.py`): el dispositivo no busca "una versión mayor",
busca **tener instalado exactamente lo que dice el último release**. Si un
release se borra porque salió mal, GitHub vuelve a apuntar al anterior y la
flota entera baja sola. Borrar el release ES el botón de pánico.
"""
