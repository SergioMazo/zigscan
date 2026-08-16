# zigscan

<p align="center">
  <img src="assets/zigscan-icon-readme.png" width="160" alt="Icono de la aplicación ZigScan">
</p>

**Herramienta de site survey Zigbee para integradores de AV.** Conectás el
CatSniffer, corrés un comando, y te contesta la pregunta que realmente tenés en
sitio: *¿en qué canal Zigbee conviene dejar este sistema, en esta casa?*

Analizadores de espectro de 2.4 GHz hay muchos. Lo que no hay son herramientas
que hablen Zigbee: que cuenten tramas 802.15.4 por canal, te muestren cuáles ya
tienen la malla de otro encima, y te digan cuál está limpio. Ese hueco es la
razón de que esto exista.

ZigScan no es simplemente otro sniffer Zigbee. Es una herramienta de
diagnóstico RF y site survey para integradores AV: **Field** entrega una
respuesta operacional y **Analysis** permite bajar a frames y PCAP cuando hace
falta ver la evidencia.

![Field recomendando el canal Zigbee 20](docs/images/field-survey.png)

## Dos capas, una respuesta

### Field

Field barre los canales Zigbee 11-26 y combina el tráfico recibido con la
ocupación de canales Wi-Fi del sitio. Muestra PAN y redes detectadas, evidencia
OUI/vendor, RSSI, estado de permit-join, recomendación de canal y diagnóstico de
retransmisiones.

![Diagnóstico y guía de señal](docs/images/diagnosis.png)

### Analysis

Analysis ofrece captura dirigida, PCAP crudo, inspección de frames, RSSI
individual, comandos MAC, ACK, origen/destino y continuidad del análisis en
Wireshark.

![Captura dirigida y análisis de PCAP](docs/images/analysis.png)

![Inspección de MAC Command, ACK y RSSI](docs/images/analysis-frames.png)

> **The radio never transmits.**
>
> ZigScan no se une, empareja, inyecta ni transmite dentro de la red Zigbee. El
> CatSniffer funciona como receptor pasivo durante los surveys y las capturas.

---

## Qué te dice

Un barrido te da, para cada uno de los 16 canales Zigbee de 2.4 GHz:

- **Cuántas tramas 802.15.4** escuchó la antena mientras estuvo parada ahí
- **Si se superpone con Wi-Fi**, usando los AP, anchos de canal y canales que
  macOS reporta en el sitio
- **Un canal recomendado**: el más tranquilo entre 15, 20, 25 y 26, que son los
  cuatro canales Zigbee que caen en los huecos que deja el Wi-Fi

La consola muestra lo mismo como un gráfico que podés voltear y enseñarle al
cliente, más una vista de tramas decodificadas para cuando querés saber *quién*
está en un canal y no solo qué tan ocupado está.

## Qué NO es

Ser honesto acá importa más que la lista de features, porque una conclusión
equivocada cuesta una visita:

- **Escucha Zigbee, no Wi-Fi.** La antena es un receptor 802.15.4. Un canal con
  cero tramas significa "acá no hay Zigbee", **no** significa "acá no hay
  interferencia". Un microondas, un transmisor de video o un AP saturado
  arruinan un canal que esta herramienta reporta vacío.
- **El CatSniffer no mide Wi-Fi ni energía RF arbitraria.** La superposición
  Wi-Fi sale del escaneo de la Mac, no de la radio 802.15.4. No ve interferentes
  que no sean Wi-Fi, como microondas o transmisores de video; en un sitio denso,
  acompañalo con un survey de espectro.
- **Zigbee es callado en reposo.** Un barrido corto sobre un canal con red real
  puede marcar cero. Si necesitás certeza, barré más tiempo, o que alguien
  prenda y apague una luz mientras escaneás.
- **Nunca transmite.** El firmware de survey es un receptor pasivo: no puede
  unirse, emparejar ni molestar la red que estás midiendo. Por eso se puede
  correr dentro del sistema vivo de un cliente.

## Hardware

| Pieza | Notas |
|---|---|
| [Electronic Cats CatSniffer](https://github.com/ElectronicCats/CatSniffer) v3.x | RP2040 + CC1352P7. Es la radio que escucha. |
| Antena de 2.4 GHz en el puerto SMA | Fácil de olvidar, y olvidarla se ve idéntico a un sitio limpio. |

El CC1352P7 tiene que estar con **firmware sniffer de TI**. `./zigscan
identify` te dice qué tiene puesto. Ver [docs/HARDWARE.md](docs/HARDWARE.md).

Desarrollado y probado en **macOS**. La detección del puerto serie es específica
de macOS (`/dev/cu.usbmodem*`); soportar Linux es un cambio chico que todavía
nadie necesitó.

## Documentación

| Documento | Qué es |
|---|---|
| [docs/MANUAL.md](docs/MANUAL.md) | El manual completo: firmware, instalación, cómo leer resultados, qué hacer cuando algo no cuadra. |
| [docs/FIELD-GUIDE.md](docs/FIELD-GUIDE.md) | Una página para el técnico en sitio. |
| [docs/RF-BANDS.md](docs/RF-BANDS.md) | Qué ve la herramienta por marca, y sus tres puntos ciegos. |
| [docs/HARDWARE-OPTIONS.md](docs/HARDWARE-OPTIONS.md) | Qué antena comprar, y qué otros sniffers pueden alimentarla. |
| [docs/HARDWARE.md](docs/HARDWARE.md) | Roles de firmware, flasheo y la trampa de la antena. |

## Instalación

Requisitos: **macOS**, Python 3.9+, git, y un CatSniffer v3.x de Electronic Cats.
Nada más — `setup.sh` arma un entorno virtual aislado y baja el toolchain de
Electronic Cats en un commit fijo. No toca paquetes del sistema.

```bash
git clone https://github.com/SergioMazo/zigscan.git
cd zigscan
./setup.sh
./zigscan identify     # confirmá la antena y su firmware
./zigscan survey       # abrí la consola
```

**Un CatSniffer nuevo no llega con el firmware de sniffer.** `setup.sh` no
flashea nada a propósito: escribir la imagen de sniffer es una puerta de un solo
sentido por serie, y hacérselo a una antena que es el coordinador de alguien
cuesta una visita. `./zigscan identify` te dice qué tiene puesto; el
[manual](docs/MANUAL.md) §3 explica las dos etapas.

> Correlo una vez, en la oficina, con internet. Después la herramienta trabaja
> offline, que es justamente la idea: en una obra rara vez hay red usable, y
> pedir la clave del Wi-Fi del cliente para hacer un survey queda mal.

## Uso

```bash
./zigscan survey
```

Abre la consola en `http://127.0.0.1:8477`. Todo es local; no se sube nada a
ningún lado.

Desde la terminal, si preferís:

```bash
./zigscan identify        # qué está conectado y con qué firmware
./zigscan scan 6          # barre 16 canales, 6 s cada uno (~2 min)
./zigscan capture 15 60   # graba el canal 15 durante 60 s a un pcap
./zigscan report file.pcap
```

## Licencia

GPL-3.0, heredada del toolchain de Electronic Cats sobre el que corre. Ver
[CREDITS.md](CREDITS.md) y [LICENSE](LICENSE).
