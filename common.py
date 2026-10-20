#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Utilidades compartidas por la prueba de carga HTTP del laboratorio."""

import socket
import struct


CONTROL_PORT = 50000
CAMPAIGN_TOKEN = "lab-demo"

MAX_DURATION = 60
MAX_RPS = 100
MAX_SIZE = 1472
HTTP_PATH = "/load-test"


def clamp(value, low, high):
    return max(low, min(high, value))


def is_lab_target(ip_str):
    """Acepta solo IPv4 privadas, loopback o link-local."""
    try:
        parts = ip_str.split(".")
        if len(parts) != 4 or any(not part.isdigit() for part in parts):
            return False
        octets = [int(part) for part in parts]
        if any(octet < 0 or octet > 255 for octet in octets):
            return False
        if any(part != str(octet) for part, octet in zip(parts, octets)):
            return False
        value = struct.unpack("!I", socket.inet_aton(ip_str))[0]
    except (AttributeError, TypeError, ValueError, socket.error):
        return False

    return (
        0x0A000000 <= value <= 0x0AFFFFFF
        or 0xAC100000 <= value <= 0xAC1FFFFF
        or 0xC0A80000 <= value <= 0xC0A8FFFF
        or 0x7F000000 <= value <= 0x7FFFFFFF
        or 0xA9FE0000 <= value <= 0xA9FEFFFF
    )
