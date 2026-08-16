# Guía de campo

Para el técnico que llega a un sitio. Cinco minutos, no cinco páginas.

## Antes de salir de la oficina

- Corré `./zigscan identify`. Si no ve la antena en la oficina, tampoco la va
  a ver en la casa del cliente.
- Verificá que la antena de 2.4 GHz esté enroscada en el SMA. Sin antena, todos
  los canales se ven limpios y el reporte sale mal.
- `setup.sh` ya corrió alguna vez. En sitio no hay internet confiable.

## En el sitio

**1. Abrí la consola.**

```bash
./zigscan survey
```

**2. Corré el barrido.** Seis segundos por canal, unos dos minutos en total.
Dejá la laptop cerca de donde va a vivir el coordinador, no en la puerta de
entrada: lo que te interesa es el aire del lugar donde van a estar los equipos.

**3. Leé el resultado.**

- **Canal recomendado** — el más limpio entre 15, 20, 25 y 26. Ese es el número
  que buscabas.
- **Canal más ocupado** — casi siempre es el sistema que ya está instalado. Si
  el cliente tiene un hub que se queda, ese canal está tomado.
- **Sin tráfico en ningún canal** — sospechá de la antena antes de creerlo.

**4. Si el sitio tiene un problema, no un plan.** Cuando te llamaron porque "las
luces responden lento", el barrido te dice si el canal está saturado. Si está
limpio y el problema persiste, no es RF: es la malla, el ruteo o la
alimentación, y ahí el barrido ya hizo su trabajo — descartó la causa más cara
de descartar.

## Lo que el barrido no contesta

Escucha Zigbee, no Wi-Fi. Un canal en cero significa *no hay Zigbee acá*, no *no
hay interferencia acá*. Un microondas o un AP saturado destruyen un canal que
sale vacío en el reporte. Si el sitio es denso en Wi-Fi, esto acompaña un survey
de Wi-Fi, no lo reemplaza.

Zigbee también es muy callado en reposo. Si sospechás que hay una red y el
barrido no la ve, pedile a alguien que prenda y apague una luz mientras escaneás
ese canal, o subí el tiempo por canal a 15 segundos.

## Guardar el trabajo

Las capturas quedan en `captures/`, con fecha. Guardalas junto al expediente del
trabajo: cuando dentro de seis meses el cliente diga que "siempre anduvo mal",
tenés la medición del día de la instalación.
