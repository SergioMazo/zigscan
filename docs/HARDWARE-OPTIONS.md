# Qué antena comprarle a cada técnico

## La respuesta corta

**Otro CatSniffer v3.x por técnico.** Es el único radio que zigscan maneja hoy de
punta a punta, y equipar al equipo con el mismo modelo significa un solo
procedimiento de firmware, un solo manual y un solo conjunto de errores conocidos.

Ahora, la respuesta larga importa, porque hay una separación en la herramienta
que abre opciones.

## La herramienta está partida en dos, y solo una mitad depende del radio

**La captura** habla con el CatSniffer a través de `pycatsniffer` de Electronic
Cats. Eso es específico de ese hardware.

**El análisis** — el censo de redes, el diagnóstico de interferencia, el gráfico
de espectro — no toca el radio: lee archivos `.pcap` y decodifica 802.15.4. Eso
es genérico.

Verificado, no supuesto: convertimos una captura al formato estándar de Wireshark
(linktype 195, sin la cabecera propia de TI) y el censo siguió encontrando la
red, las dos marcas y el permit-join abierto. Lo único que se pierde es el canal
y el RSSI, porque esos datos viven en la cabecera de TI y no en el estándar.

**Consecuencia práctica:** cualquier sniffer que produzca un `.pcap` de 802.15.4
sirve **hoy** para la mitad de análisis, sin escribir una línea de código:

```bash
./zigscan census  captura-de-otro-sniffer.pcap
./zigscan verdict captura-de-otro-sniffer.pcap
```

Lo que cada radio nuevo necesitaría para la **captura en vivo** es un backend
propio. No es configuración, es código.

## Opciones de radio

| Radio | Precio aprox. | Captura en vivo desde zigscan | Notas |
|---|---|---|---|
| **CatSniffer v3.x** (Electronic Cats) | ~US$60-70 | **Sí, hoy** | CC1352P7 + RP2040 + SX1262. El SX1262 abre la puerta a sub-GHz más adelante (Lutron Type A, Vantage). |
| **nRF52840 Dongle** (Nordic) | ~US$10-20 | No — backend nuevo | Nordic publica *nRF Sniffer for 802.15.4*, que se integra a Wireshark. Barato y muy disponible. Sus pcap ya se pueden analizar con zigscan. |
| **CC2652 USB** (Sonoff ZBDongle-**P**, zzh!, TubesZB) | ~US$20-35 | No — backend nuevo | Se les puede poner firmware de sniffer de TI. Muy comunes en el mundo Zigbee. |
| **TI LAUNCHXL-CC26X2R1 / CC1352P** | ~US$40-50 | No — backend nuevo | Placas oficiales de TI, mismo firmware de sniffer. La referencia si querés comparar contra SmartRF Packet Sniffer 2. |
| **CC2531** | ~US$10 | No | Obsoleto. USB lento y pierde tramas con tráfico alto. No lo compres para trabajo nuevo. |
| **Sonoff ZBDongle-E** (EFR32MG21) | ~US$25 | No | Es Silicon Labs, no TI. Sniffear requiere el toolchain de Silabs. Sirve como **coordinador**, que es otro trabajo. |

## Recomendación por escenario

**Un técnico que solo hace surveys** → CatSniffer v3.x. Funciona el día uno.

**Varios técnicos, presupuesto ajustado** → un CatSniffer para el que hace los
surveys, y nRF52840 Dongles para los demás: capturan con Wireshark y te mandan el
`.pcap`, que vos analizás con zigscan. Es el camino barato y funciona ya.

**Quieren cubrir Lutron RA2 / Vantage** → CatSniffer, por el SX1262. Ningún otro
de esta lista llega a sub-GHz. Falta escribir ese modo.

## No uses la antena del coordinador

Si una instalación tiene un CatSniffer haciendo de coordinador, **no lo flashees
para sniffear**. El firmware de sniffer es una puerta de un solo sentido por
serie: se entra, no se sale sin SWD y una sonda. Comprá una segunda antena; es
más barato que la visita para recuperar la primera.

## Sobre el firmware al comprar

Un CatSniffer nuevo **no llega con el firmware de sniffer puesto**. Lo sabemos
porque el de este proyecto se flasheó en dos etapas el 2026-08-06 y quedó
registrado. Asumí que cada antena nueva necesita el mismo procedimiento, y
verificá con `./zigscan identify` antes de salir a un trabajo. El procedimiento
completo está en el [MANUAL](MANUAL.md) §3.
