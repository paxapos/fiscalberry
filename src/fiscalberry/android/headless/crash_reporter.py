"""
Crash Reporter - Telemetría Production

Envía reportes de crash al servidor. Usa SOLO stdlib para máxima confiabilidad.
"""
import sys
import os
import traceback
import json
import urllib.request
import urllib.error
from datetime import datetime


def send_crash_report(crash_data, timeout=5):
    """
    Envía reporte de crash usando urllib (stdlib only).
    
    Args:
        crash_data: Dict con info del crash
        timeout: Timeout en segundos
    
    Returns:
        bool: True si envió correctamente
    """
    try:
        url = os.environ.get(
            'FISCALBERRY_CRASH_URL',
            'https://beta.paxapos.com/api/v1/crashes'
        )
        
        data = json.dumps(crash_data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Fiscalberry-AndroidCLI/2.0'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            if status in (200, 201):
                print(f"[CRASH_REPORTER] ✓ Report sent (status {status})", file=sys.stderr)
                return True
            else:
                print(f"[CRASH_REPORTER] ✗ Server returned {status}", file=sys.stderr)
                return False
                
    except urllib.error.URLError as e:
        print(f"[CRASH_REPORTER] ✗ Network error: {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[CRASH_REPORTER] ✗ Failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def setup_crash_reporting():
    """
    Configura hook global para capturar excepciones no manejadas.
    DEBE llamarse ANTES de cualquier otro import.
    """
    original_excepthook = sys.excepthook
    
    def crash_excepthook(exc_type, exc_value, exc_traceback):
        # Skip KeyboardInterrupt
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        crash_report = {
            'type': exc_type.__name__,
            'message': str(exc_value),
            'traceback': ''.join(traceback.format_tb(exc_traceback)),
            'timestamp_utc': datetime.utcnow().isoformat() + 'Z',
            'device_id': os.environ.get('FISCALBERRY_UUID', 'unknown'),
            'python_version': sys.version,
            'platform': sys.platform,
            'process_id': os.getpid(),
        }
        
        # Log a stderr (logcat capturará)
        print("\n" + "="*70, file=sys.stderr)
        print("FISCALBERRY UNHANDLED EXCEPTION", file=sys.stderr)
        print("="*70, file=sys.stderr)
        print(json.dumps(crash_report, indent=2), file=sys.stderr)
        print("="*70 + "\n", file=sys.stderr)
        
        # Intentar enviar (timeout 3s)
        send_crash_report(crash_report, timeout=3)
        
        # Llamar hook original
        original_excepthook(exc_type, exc_value, exc_traceback)
        
        # Morir
        print("[CRASH_REPORTER] Terminating process", file=sys.stderr)
        os._exit(1)
    
    sys.excepthook = crash_excepthook
    print("[CRASH_REPORTER] ✓ Enabled", file=sys.stderr)
