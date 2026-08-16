# Manual de zigscan

Para el técnico que la va a usar en sitio. Si solo querés el resumen de campo,
está en [FIELD-GUIDE.md](FIELD-GUIDE.md) y cabe en una página.

---

## 1. Qué hace y qué no

zigscan contesta una pregunta: **¿en qué canal Zigbee conviene dejar este
sistema, en esta casa?** Y contesta una segunda cuando ya hay un problema:
**¿las luces van lentas por interferencia o por la malla?**

Lo hace escuchando. La antena nunca transmite, así que se puede correr dentro
del sistema vivo de un cliente sin tocarlo.

**Lo que no ve.** Escucha 802.15.4, que es Zigbee. No ve Wi-Fi (eso lo mide
aparte con la tarjeta de la laptop), no ve Bluetooth, no ve Lutron Clear Connect
Type X, y no ve nada fuera de 2.4 GHz. Un canal con cero tramas significa *acá no
hay Zigbee*, **nunca** *acá no hay interferencia*. Está todo detallado en
[RF-BANDS.md](RF-BANDS.md) y conviene leerlo una vez antes de la primera visita.

---

## 2. Qué necesitás

| | |
|---|---|
| Antena | Electronic Cats CatSniffer v3.x |
| Antena de 2.4 GHz | Enroscada en el SMA. Sin ella, todo se ve limpio y el reporte sale mal. |
| Firmware | TI sniffer en el CC1352P7 — ver §3, **la antena no viene lista de fábrica** |
| Laptop | macOS (hoy). Para Windows ver [HARDWARE-OPTIONS.md](HARDWARE-OPTIONS.md). |

---

## 3. El firmware: la antena no llega lista

Un CatSniffer nuevo **no trae el firmware de sniffer**. Hay que ponérselo, y son
dos etapas porque son dos chips:

1. **RP2040** (el que habla USB) necesita `SerialPassthroughwithboot`. Se pone
   arrastrando un archivo: doble clic rápido al botón `reset1`, aparece un disco
   llamado `RPI-RP2`, se copia el `.uf2` adentro y la placa se reinicia sola.
2. **CC1352P7** (la radio) necesita `sniffer_fw`. Esto va por serie, con
   `catnip_uploader`.

**Verificá antes de asumir:**

```bash
./zigscan identify
```

Si dice `TI sniffer firmware — answered the @S ping live`, está lista. Si dice
`coordinator` o `unknown`, falta flashearla.

### Tres advertencias que cuestan dinero

**No llames a `cc2538-bsl` a mano.** El bootloader del CC1352 en esta placa no se
abre con un flag: el sketch del RP2040 escucha una cadena mágica (`<boot>`) a
921600 baudios y maneja los pines él mismo. `catnip_uploader` hace la secuencia
completa. Inventarse el handshake es como se brickea la radio — ya pasó una vez
en este proyecto.

**La etapa 1 tiene que estar primero.** Cualquier otro sketch en el RP2040 ignora
la cadena mágica, y entonces el flasheo de la radio no encuentra bootloader.

**El firmware de sniffer es una puerta de un solo sentido.** Flashear *hacia*
sniffer funciona. Flashear *desde* sniffer por serie **no**: `cc2538-bsl` nunca
sincroniza, porque la build de TI deja la ROM en un estado del que no se sale por
UART. Volver atrás requiere SWD y una sonda. Por eso zigscan nunca flashea solo,
ni siquiera cuando detecta el firmware equivocado: te avisa y te deja decidir.

Si la antena que vas a usar también es el coordinador de una instalación,
**no la flashees**. Comprá una segunda.

---

## 4. Instalación

### Para técnicos: el .dmg

1. Abrí `zigscan.dmg` y arrastrá **zigscan** a Aplicaciones.
2. **La primera vez, clic derecho sobre la app → Abrir**, y confirmá. Doble clic
   no funciona la primera vez y no está roto: macOS bloquea aplicaciones sin
   firmar de Apple. Es una sola vez.
3. La app levanta el servicio y abre tu navegador por defecto sola.

No hay nada más que instalar. No necesita Python, ni Homebrew, ni permisos de
administrador, y una vez instalada trabaja sin internet — que es el punto,
porque en obra no hay red confiable y pedir la clave del cliente para hacer un
survey queda mal.

**Tus capturas quedan en `~/Documents/zigscan/captures`**, no dentro de la
aplicación. Sobreviven si actualizás o borrás la app, y las podés adjuntar al
expediente del trabajo desde Finder.

Para cerrar el servicio, salí de la app (Cmd-Q) como con cualquier otra.

### Para el que quiera el código

```bash
git clone https://github.com/<owner>/zigscan.git
cd zigscan
./setup.sh
```

`setup.sh` crea el entorno, baja el toolchain de Electronic Cats en un commit
fijo, e instala lo que hace falta. No toca el firmware. Con eso quedan
disponibles los comandos de terminal de la §5.

---

## 5. Uso

### La consola

```bash
./zigscan survey
```

Abre `http://127.0.0.1:8477`. Todo es local; no se sube nada a ningún lado.

Arriba a la derecha, el punto verde y el nombre del puerto confirman que la
antena está viva. Si el punto está rojo, no hay antena — revisá el cable y que
ninguna máquina virtual la haya secuestrado (Parallels lo hace solo).

El botón **ES / EN** cambia el idioma y se recuerda.

Cada panel tiene un **`?`**: ahí está qué mide ese panel, qué **no** puede ver, y
qué hacer con el resultado. Si dudás de un número, ese es el primer lugar.

### Modo Campo

El número grande arriba es la respuesta: **el canal que hay que usar**. Debajo
dice por qué.

- **Ocupación de 2.4 GHz** — cada barra es un canal; la altura son las tramas
  escuchadas. Las bandas moradas son el Wi-Fi real de la casa. Las barras
  punteadas son canales **sin medir**, que no es lo mismo que limpios.
- **Quién ya está en el aire** — las redes que ya funcionan ahí, con marca cuando
  se puede leer.
- **Wi-Fi en sitio** — las tres bandas. Solo 2.4 GHz le compite a Zigbee; 5 y 6
  van porque el mismo técnico suele estar instalando el Wi-Fi.
- **Diagnóstico** — interferencia contra malla.
- **Cómo leer la señal** — qué significa cada dBm en términos de distancia.

### Modo Análisis

Para cuando querés ver debajo del resultado: capturar un canal concreto, leer las
tramas decodificadas, o llevarte el `.pcap` a Wireshark.

### Desde la terminal

```bash
./zigscan scan 6          # barre los 16 canales, 6 s cada uno (~2 min)
./zigscan census          # quién está en el aire
./zigscan verdict         # interferencia o malla
./zigscan wifi            # Wi-Fi medido, todas las bandas
./zigscan capture 15 60   # graba el canal 15 durante 60 s
./zigscan identify        # qué antena hay y con qué firmware
```

---

## 6. Cómo leer los resultados

### El canal recomendado

Sale de los canales **15, 20, 25 y 26**, que son los cuatro que caen en los
huecos que deja el Wi-Fi 1 / 6 / 11. Entre esos, gana el que tenga menos Wi-Fi
encima, después el que no tenga una red conocida, y después el más tranquilo.

zigscan **no recomienda un canal que no midió**. Si ves "sin barrido", es que
todavía no hay datos, no que esté todo limpio.

### La señal

| Lectura | Significa |
|---|---|
| −45 dBm | Está en esta casa, cerca del punto de medición |
| −62 dBm | Dentro de la casa, a distancia normal de trabajo |
| −78 dBm | Lejos, otra planta, o del vecino. Poco confiable |
| −92 dBm | Al límite de lo audible. Casi seguro no es de esta instalación |

Sirve sobre todo para descartar: si una red aparece a −90, probablemente no es
problema del cliente.

### El diagnóstico

| Dice | Qué hacer |
|---|---|
| **Interferencia** | Mover la red a un canal limpio. |
| **No es RF, es la malla** | Cambiar de canal no arregla nada. Mirá distancia, repetidores, ruteo, equipos con corriente. |
| **Al límite** | Funciona sin margen. Arreglalo antes de que agreguen más equipos. |
| **El RF está sano** | El aire no es el problema. Revisá hub, integración, automatizaciones. |
| **No hay tráfico suficiente** | Capturá más tiempo, o en el horario del que se queja el cliente. |

El cuarto caso vale tanto como los otros: **probar que el RF no es el problema**
es lo que evita perder un día persiguiéndolo.

### Permit-join abierto

Si una red aparece con esa etiqueta roja, está aceptando equipos nuevos de
cualquiera en rango. Es un hallazgo de seguridad y conviene decírselo al cliente.

---

## 7. Cuando algo no cuadra

**No aparece la antena.** Revisá que ninguna VM la tenga tomada — Parallels la
reclama sola en cuanto arranca una máquina, y entonces macOS ni siquiera crea el
puerto. `./zigscan identify` te dice quién la tiene.

**El barrido da cero en todos los canales.** En orden de probabilidad:

1. La antena de 2.4 GHz no está enroscada.
2. La red está en reposo. Zigbee callado es normal — pedí que prendan y apaguen
   una luz mientras barrés, o subí el tiempo por canal a 15 segundos.
3. El firmware no es el de sniffer (`./zigscan identify`).

**El censo no muestra la marca.** Es lo esperable en una red ya formada: todo va
con direcciones cortas de 16 bits, que no llevan fabricante. La marca solo se ve
cuando un equipo se une a la red. Si necesitás identificarla, capturá mientras
emparejan algo.

**Una red aparece y desaparece entre barridos.** Normal si está al límite de la
señal. Mirá el dBm antes de reportarla.

---

## 8. Guardar el trabajo

Las capturas quedan en `captures/`, con fecha. Guardalas junto al expediente del
trabajo: cuando dentro de seis meses el cliente diga que "siempre anduvo mal",
tenés la medición del día de la instalación.

Ojo con la privacidad: un `.pcap` contiene tráfico de la red del cliente, y una
captura tomada durante un emparejamiento incluye el intercambio de llaves. No los
publiques ni los mandes fuera sin pensarlo.
