# Botnet PoC — Laboratorio de Tecnologías Emergentes (Hacking Ético 2026/2027)

Prueba de concepto **educativa** del escenario *Botnet* (diapositiva 6). Simula una
botnet sencilla para experimentar con seguridad ofensiva **en un laboratorio aislado**:

- Un **comandante (C2)** envía por **UDP broadcast** una orden de ataque con la víctima
  `(IP, puerto)` y la `duración`.
- Los **zombis** escuchan ese broadcast y, al recibir la orden, generan tráfico UDP
  contra la víctima.
- En la **víctima** se analiza el tráfico con **Wireshark / IO Graphs** y se compara
  el efecto con **1, 2 y 3 zombis**.

**Grupo:** Gorka Villalba, Jon Urkidi, Fran Martin, Alejandro Martinez, Gorka Bidaurratzaga.

> ⚠️ **Alcance y ética.** Esto se usa **solo** en la red del laboratorio y contra
> máquinas propias. El código incluye un guardarrail: los zombis y el comandante
> **rechazan cualquier objetivo que no sea una IP privada / loopback** (RFC1918,
> 127.0.0.0/8, 169.254.0.0/16). Dirigir tráfico de este tipo contra sistemas ajenos
> es un ataque de denegación de servicio y es ilegal.

## Archivos

| Archivo         | Rol                                                                 |
|-----------------|---------------------------------------------------------------------|
| `common.py`     | Protocolo, puerto de control y el guardarrail `is_lab_target()`.    |
| `commander.py`  | C2: manda la orden de ataque por broadcast.                         |
| `zombie.py`     | Bot: escucha el broadcast y ataca a la víctima.                     |
| `victim.py`     | Víctima: receptor UDP que mide pps / KB/s y nº de orígenes.         |

Solo necesitas **Python 3** (biblioteca estándar; sin dependencias externas).

## Topología de la demo

```
                 (UDP broadcast, puerto 50000)
   +-----------+        orden de ataque         +-----------+
   | COMMANDER | ------------------------------> |  ZOMBIE 1 | --\
   |   (C2)    | ------------------------------> |  ZOMBIE 2 | ---> === tráfico UDP ===> +---------+
   +-----------+ ------------------------------> |  ZOMBIE 3 | --/                        | VÍCTIMA |
                                                 +-----------+                            +---------+
```

Lo ideal: 3–5 máquinas (VMs) en la misma LAN/subred para que el broadcast llegue a
todas. Si solo tienes una máquina para la demo, puedes lanzar varios `zombie.py` en
la misma máquina (usan loopback/subred) — igualmente verás cómo escala el tráfico.

## Puesta en marcha

### Opción A — varias máquinas en la misma subred (ideal)

1. **Víctima** (p.ej. `192.168.1.50`):
   ```bash
   python victim.py --port 9999
   ```
2. **Cada zombi** (una máquina cada uno):
   ```bash
   python zombie.py --id zombie-1
   python zombie.py --id zombie-2
   python zombie.py --id zombie-3
   ```
3. **Comandante** (cualquier máquina de la LAN). Usa el **broadcast de tu subred**
   (p.ej. `192.168.1.255`) para que la orden llegue a todos:
   ```bash
   python commander.py --target 192.168.1.50 --port 9999 --duration 10 \
                       --broadcast 192.168.1.255 --pps 2000 --size 512
   ```

### Opción B — todo en una sola máquina (para probar / backup)

```bash
# Terminal 1
python victim.py --port 9999
# Terminales 2..4
python zombie.py --id zombie-1
python zombie.py --id zombie-2
python zombie.py --id zombie-3
# Terminal 5 (loopback)
python commander.py --target 127.0.0.1 --port 9999 --duration 10 --broadcast 127.255.255.255
```

## Guion de la presentación (1 → 2 → 3 zombis)

La clave de la demo es **repetir el mismo ataque sumando zombis** y enseñar en Wireshark
cómo crece el tráfico de forma proporcional.

1. Arranca `victim.py` y deja su consola a la vista (muestra pps y KB/s en tiempo real).
2. Abre **Wireshark** en la víctima, filtrando el tráfico del ataque (ver abajo).
3. **1 zombi:** arranca `zombie-1`, lanza el `commander.py` (10 s). Anota pps/KB/s.
4. **2 zombis:** arranca `zombie-2`, repite el `commander.py`. El tráfico ~duplica.
5. **3 zombis:** arranca `zombie-3`, repite. El tráfico ~triplica.
6. Enseña el **IO Graph** acumulado: tres escalones crecientes = efecto de la botnet.

> Consejo: usa `--duration 10` y espera unos segundos entre rondas, así en el IO Graph
> se ven tres "mesetas" separadas y es muy visual.

## Análisis en Wireshark / IO Graphs

Wireshark distingue **dos tipos de filtro** con sintaxis distinta — no los mezcles:

**Filtro de VISUALIZACIÓN** (display filter — `Analyze ▸ Display Filters`, la barra
verde superior). Sintaxis con `==` y `&&`:

```
udp.port == 9999 && ip.dst == 192.168.1.50
```

**Filtro de CAPTURA** (capture filter — `Capture ▸ Options`, antes de capturar; sintaxis
BPF, distinta):

```
udp port 9999 and dst host 192.168.1.50
```

Para la demo basta con el filtro de visualización; el de captura solo si quieres reducir
el volumen capturado de entrada.

**IO Graph** (`Statistics ▸ I/O Graph`):

- Eje Y: prueba con **Packets** y con **Bytes** (`SUM(frame.len)`).
- Intervalo: `100 ms` o `1 s`.
- Añade una gráfica por nº de orígenes si quieres, o deja una sola y verás los escalones.
- Para contar zombis distintos:
  - **Máquinas distintas** (ideal): `Statistics ▸ Endpoints ▸ IPv4` → nº de IPs origen.
  - **Varios zombis en el mismo PC** (opción B): comparten IP, así que cuenta por
    **endpoint (IP + puerto de origen)**: `Statistics ▸ Conversations ▸ UDP`. El
    `victim.py` ya muestra esta columna "zombis" (endpoints `IP:puerto` distintos).

Qué mostrar/explicar:
- Con N zombis, los **pps y los bytes/s son ~N veces** los de 1 zombi.
- La víctima recibe tráfico de **varios orígenes** simultáneos (naturaleza distribuida):
  N IPs si son N máquinas, o N endpoints `IP:puerto` si levantas varios zombis por máquina.
- El `victim.py` corrobora numéricamente lo mismo que el IO Graph (columnas `IPs` y `zombis`).

## Posibles preguntas del profesor y contramedidas

El profe suele preguntar por la **contramedida** de la técnica. Para un flood UDP como este:

- **Rate limiting / policing** en el router o firewall (limitar pps por origen).
- **Filtrado de broadcast**: los switches/segmentación de red evitan que el canal de
  control por broadcast llegue a toda la red (VLANs, deshabilitar broadcast innecesario).
- **Ingress/egress filtering (BCP38)**: evita spoofing de IP de origen.
- **Firewall sin estado para UDP**: cerrar/filtrar puertos UDP no usados; `udp` solo
  a servicios legítimos.
- **Detección**: IDS/IPS (Snort/Suricata) con umbrales de pps, y en escala real
  servicios anti-DDoS (scrubbing) que absorben el volumen.
- **A nivel botnet**: detectar y bloquear el **canal C2** (aquí, tráfico anómalo a
  UDP/50000 por broadcast) corta las órdenes antes de que haya ataque.

## Parámetros útiles

- `--duration` segundos de ataque.
- `--pps` paquetes/seg objetivo por zombi (sube/baja la intensidad de forma controlada).
- `--size` tamaño del payload en bytes (relaciona pps con ancho de banda).
- `--broadcast` dirección de broadcast de tu subred (muy importante en red real).
- `--control-port` puerto del canal C2 (por defecto 50000).

**Topes de seguridad** (en `common.py`): la simulación está acotada —
`MAX_DURATION=60s`, `MAX_PPS=20000`, `MAX_SIZE=1472B`. Tanto el comandante como los
zombis recortan cualquier valor a estos límites; `pps<=0` no desactiva las pausas, se
fuerza a 1. Es una simulación «suavizada», no un flood sin límites.
