# Qué ve esta herramienta, y qué no

La regla, en una línea: **zigscan escucha 802.15.4 en 2.4 GHz.** Nada más.

Eso cubre Zigbee completo, deja fuera bandas enteras, y — lo más peligroso — deja
fuera sistemas que **sí están en 2.4 GHz** pero hablan otro idioma de radio. Un
canal que esta herramienta reporta vacío puede estar lleno. Vale la pena
entender exactamente dónde está el límite antes de darle un número a un cliente.

## Por marca

| Sistema | Banda | ¿Lo ve zigscan? |
|---|---|---|
| **Control4** | Zigbee, 2.4 GHz | **Sí, completo.** Beacons, equipos y marca por OUI. Confirmado en banco. |
| **SONOFF / ITead** | Zigbee, 2.4 GHz | **Sí, completo.** Confirmado en banco. |
| **Philips Hue, Aqara, SmartThings** | Zigbee, 2.4 GHz | Sí. OUI en la tabla, pendiente de confirmar en campo. |
| **Crestron infiNET EX** | 2.4 GHz, sobre 802.15.4 | **Parcial.** Comparte PHY y MAC con Zigbee, así que sus tramas se cuentan y ocupan el canal, pero sin payload Zigbee no se identifica como red. Aparece como "no es Zigbee". *Sin confirmar contra hardware.* |
| **Lutron RadioRA 2, QS, Caséta** (Clear Connect Type A) | ~434 MHz | **No.** Otra banda. No compite con Zigbee ni aparece acá. |
| **Lutron RadioRA 3, HomeWorks QSX** (Clear Connect Type X) | **2.4 GHz** | **No, y este es el punto ciego importante.** Ocupa el mismo aire que Zigbee pero con PHY propietaria, así que no genera tramas 802.15.4 que contar. El canal se ve limpio y no lo está. *Verificar antes de apoyarse en esto.* |
| **Vantage** (RadioLink) | sub-GHz | **No.** Otra banda. |
| **Savant** | según línea; parte usa Zigbee | Depende del equipo. *Sin confirmar.* |

Las filas marcadas *sin confirmar* vienen de documentación pública, no de haberlas
medido en este banco. Confirmalas antes de usarlas como argumento con un cliente
— y cuando lo hagas, actualizá esta tabla y `OUI_VENDORS` en `tools/census.py`.

## Los tres puntos ciegos

**Wi-Fi.** No genera tramas 802.15.4, así que el contador no lo ve. Por eso
zigscan lo mide aparte, con la tarjeta de la laptop, y lo dibuja sobre el
espectro. Es el único punto ciego que la herramienta ya tapa.

**Otras PHY en 2.4 GHz.** Clear Connect Type X, Bluetooth, ZigBee propietario de
algún fabricante, video senders, microondas. Ocupan aire y no producen nada que
contar. Un canal con cero tramas significa *no hay 802.15.4 acá*, nunca *no hay
interferencia acá*.

**El silencio de Zigbee.** Una red Zigbee en reposo casi no habla. Los routers
mandan link status cada ~15 s y poco más; los beacons solo aparecen cuando
alguien hace un beacon request. Un barrido de 6 s por canal puede pasar por
encima de una red real sin oírla. Si el resultado importa, barré más tiempo o
pedí que muevan una luz mientras medís.

## Lo que se puede hacer al respecto

Dos caminos, los dos abiertos con el hardware que ya tenés:

**Energy detect.** El CC1352P7 mide potencia en un canal sin importar qué
protocolo la produce. Un barrido de energía taparía los tres puntos ciegos de
arriba a la vez — es la diferencia entre "no hay Zigbee" y "no hay nada". Falta
verificar si pycatsniffer expone esa función.

**Sub-GHz.** El CatSniffer v3.x trae un SX1262 además del CC1352P7. Ese chip
cubre 433/868/915 MHz, que es donde viven Lutron Clear Connect Type A y Vantage.
Un modo sub-GHz convertiría esto en una herramienta que cubre casi todo el
parque instalado, no solo el Zigbee.
