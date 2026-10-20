"""
common.py - Utilidades compartidas por el PoC de botnet.

Protocolo de control (C2 -> zombis) sobre UDP broadcast:
  Mensaje JSON:
    {
      "cmd": "http_load_test",
      "target_ip": "192.168.1.50",
      "target_port": 9999,
      "duration": 10,       # segundos (se acota a MAX_DURATION)
      "rps": 20,            # solicitudes/seg por cliente (se acota a [1, MAX_RPS])
      "size": 512,          # bytes del cuerpo HTTP (se acota a [1, MAX_SIZE])
      "token": "lab-demo"   # identificador de la campaña (evita ejecuciones cruzadas)
    }

NOTA DE SEGURIDAD / ALCANCE DEL LABORATORIO
-------------------------------------------
Esto es una prueba educativa de carga HTTP para la asignatura de Hacking Etico.

`is_lab_target()` es un GUARDARRAIL, no un aislamiento: solo acepta objetivos
IPv4 en rangos privados / loopback / link-local. Esto evita apuntar a Internet por
error, pero una IP privada puede pertenecer a otra maquina de vuestra red; el
aislamiento REAL lo da ejecutar esto en la red cerrada del laboratorio y contra
maquinas que controles tu mismo.
"""

import ipaddress

CONTROL_PORT = 50000          # puerto UDP donde los zombis escuchan ordenes
CAMPAIGN_TOKEN = "lab-demo"   # token compartido de la campana

# Topes de seguridad para acotar la simulacion (evitan un flood sin limites).
MAX_DURATION = 60             # segundos maximos de una prueba
MAX_RPS = 100                 # solicitudes HTTP/seg maximas por zombi
MAX_SIZE = 1472              # bytes maximos del cuerpo de cada solicitud HTTP
HTTP_PATH = "/load-test"      # endpoint fijo del servidor HTTP de laboratorio


def clamp(value: int, low: int, high: int) -> int:
    """Acota un entero al rango [low, high]."""
    return max(low, min(high, value))


def is_lab_target(ip_str: str) -> bool:
    """True solo si es una IPv4 privada / loopback / link-local.

    Guardarrail para mantener el PoC dentro del laboratorio. Rechaza IPv6
    (los sockets del PoC son IPv4) y cualquier direccion global/publica.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.version != 4:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local
