"""
common.py - Utilidades compartidas por el PoC de botnet.

Protocolo de control (C2 -> zombis) sobre UDP broadcast:
  Mensaje JSON:
    {
      "cmd": "attack",
      "target_ip": "192.168.1.50",
      "target_port": 9999,
      "duration": 10,       # segundos
      "pps": 2000,          # paquetes/seg objetivo por zombi (orientativo)
      "size": 512,          # tamaño del payload en bytes
      "token": "lab-demo"   # identificador de la campaña (evita ejecuciones cruzadas)
    }

NOTA DE SEGURIDAD / ALCANCE DEL LABORATORIO
-------------------------------------------
Esto es una Prueba de Concepto educativa para la asignatura de Hacking Etico.
Por diseno, los zombis SOLO atacan objetivos en rangos de red privados o de
loopback (RFC1918, 127.0.0.0/8, 169.254.0.0/16, etc.). Cualquier objetivo que
sea una IP publica se rechaza. Usalo unicamente en la red aislada del laboratorio
y contra maquinas que controles tu mismo.
"""

import ipaddress

CONTROL_PORT = 50000          # puerto UDP donde los zombis escuchan ordenes
CAMPAIGN_TOKEN = "lab-demo"   # token compartido de la campana


def is_lab_target(ip_str: str) -> bool:
    """Devuelve True solo si la IP pertenece a un rango privado/loopback/link-local.

    Es el guardarrail que mantiene el PoC dentro del laboratorio: impide
    apuntar accidental o intencionadamente a un objetivo de Internet.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local
