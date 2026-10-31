# coding=utf-8
"""
Identificador de un trabajo de impresión, el mismo para MQTT y Socket.IO.

El spooler deduplica por este id (reentregas QoS1 "al menos una vez"). Antes
cada transporte lo calculaba distinto: MQTT hasheaba el body crudo y Socket.IO
el JSON ordenado, así que el mismo ticket sin jobId tenía dos ids
(paxapos/fiscalberry#216).
"""

import hashlib
import json


def compute_job_id(ticket):
    """`jobId` del ticket si viene; si no, sha1 del JSON normalizado."""
    if isinstance(ticket, dict) and ticket.get("jobId"):
        return str(ticket["jobId"])
    payload = json.dumps(ticket, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
