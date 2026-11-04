# Calendario litúrgico automático — canal «ADF - LTG - Ordo»

Publica cada día en el canal de Telegram la celebración del Ordo ADF, con imagen y síntesis biográfica.
Calcula todo solo, año tras año: Pascua y fiestas móviles, tiempos litúrgicos, domingos, precedencia,
traslados de solemnidades y I Vísperas. No hay que programar mensajes a mano.

## Horarios

- **00:10**: mensaje del día.
- **18:00 del día anterior**: cuando el día siguiente tiene I Vísperas (domingos, solemnidades y fiestas del Señor en domingo)
  y estas prevalecen sobre las Vísperas del día en curso (NUALC 61). Las Vísperas del 24 de diciembre son siempre de Navidad.

## Calendarios nacionales (versión universal)

Cuando el calendario de Argentina o de Paraguay difiere del general (CRG + ADF), ese día salen mensajes separados,
uno tras otro: «**En Argentina:**», «**En Paraguay:**», «**Otros países:**» (o combinados: «En Paraguay y otros países:»).
Si todos coinciden, sale un solo mensaje sin encabezado. Se configura en `config.toml` → `regiones`.

## Qué se publica

Solemnidades, fiestas, domingos, memorias obligatorias, Miércoles de Ceniza, Semana Santa, Triduo, Octavas de Navidad y Pascua,
ferias del 17 al 24 de diciembre (con la antífona «O»), memorias libres («puede celebrarse…») y conmemoraciones en Cuaresma.
Las ferias sin celebración no se publican. Todo esto se ajusta en `config.toml`.

## Puesta en marcha (una sola vez, unos 15 minutos)

1. **Bot de Telegram.** En Telegram, abrir `@BotFather` → `/newbot` → elegir nombre. Guardar el *token* que devuelve.
   Agregar el bot como **administrador** del canal con permiso de publicar.
2. **ID del canal.** Si el canal es público, sirve `@nombre_del_canal`. Si es privado: reenviar un mensaje del canal a
   `@userinfobot` (o similar) y copiar el número que empieza con `-100`.
3. **Repositorio.** Crear una cuenta en github.com (gratis), luego *New repository* → nombre `ordo-telegram` →
   **Private** → *Create*. En *Add file → Upload files* arrastrar todo el contenido de esta carpeta (incluida la carpeta `.github`).
4. **Secretos.** En el repositorio: *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = el token del paso 1
   - `TELEGRAM_CHAT_ID` = el ID del canal del paso 2
   - `TELEGRAM_CHAT_ID_PRUEBA` = (opcional) un chat o canal de prueba, para ensayar sin publicar en el canal real
5. **Prueba.** *Actions → Publicar en el canal → Run workflow*, escribir una fecha (p. ej. `2026-12-08`) y ejecutar.
   El mensaje llega al chat de prueba. Si no configuraste uno, llega al canal real.
6. Listo. Desde ese momento corre solo todos los días.

> Las imágenes se toman de la carpeta pública de Drive «04. Santoral» por su ID. Si un archivo deja de ser público,
> el mensaje se publica igual, sin imagen.

## Cómo modificar

| Quiero… | Dónde |
|---|---|
| Corregir un nombre, título, grado, color o biografía | `data/santoral.csv` (se abre con Excel o Google Sheets; guardar como CSV UTF-8) |
| Elegir la imagen de cada fecha | abrir `elegir_imagenes.html` en el navegador, elegir y «Descargar mi selección»; luego `python herramientas/aplicar_seleccion.py seleccion_imagenes.csv` (o enviar el archivo a Claude) |
| Fijar una imagen concreta para un santo | columna `imagen_fija` de `data/santoral.csv` (pegar el ID de Drive) |
| Agregar imágenes alternativas | columna `imagenes` (IDs separados por espacio); se rota una distinta cada año |
| Agregar una nota a un día (antífona, indicación) | columna `nota` (admite `<i>` y `<b>`) |
| Imágenes y textos de fiestas móviles y domingos (Sagrado Corazón, Pascua, domingos de cada tiempo…) | `data/moviles.csv` |
| Regiones, Bautismo, traslados, qué se publica, horarios | `config.toml` |

El ID de Drive es la parte larga del enlace: `https://drive.google.com/file/d/`**`1lTO8b8mfgMIOfn3bLiT-vpcWoA8j7jmp`**`/view`.

### Columnas de `santoral.csv`

- `fecha`: MM-DD.
- `grado`: Solemnidad, Fiesta, Memoria obligatoria, Memoria libre, Conmemoración.
- `precedencia`: número de la Tabla de los días litúrgicos (NUALC 59). Menor = más importante.
  Referencia: 3 Natividad/Epifanía · 4 solemnidades del Señor · 5 solemnidades de la Virgen · 6 solemnidades de santos (CRG) ·
  7 Fieles Difuntos · 8 solemnidades propias · 9 fiestas del Señor · 11 fiestas de la Virgen · 12 fiestas de santos (CRG) ·
  13 fiestas propias · 15 memorias obligatorias (CRG) · 16 memorias obligatorias propias · 17 memorias libres.
- `regiones`: vacío = siempre. `ARG` = solo si ARG está en `config.toml`. `!PGY` = siempre, salvo en PGY.

## Reglas que aplica el motor

- Domingos de Adviento, Cuaresma y Pascua prevalecen sobre toda solemnidad, que pasa al lunes.
- Solemnidad impedida → día libre más próximo. San José en Semana Santa → sábado antes de Ramos.
  Anunciación en Semana Santa u Octava de Pascua → lunes después del II Domingo de Pascua.
  Si dos solemnidades coinciden, se traslada la de fecha fija.
- Las fiestas impedidas se omiten (salvo la Sagrada Familia, que pasa al 30 de diciembre).
- Memorias en Cuaresma, del 17 al 24 de diciembre y en la Octava de Navidad → conmemoración.
  En Miércoles de Ceniza, Semana Santa y Octava de Pascua → se omiten.
- Salterio: semana calculada según el Tiempo.

## Comandos (para quien quiera ejecutarlo en una computadora)

```
pip install -r requirements.txt
python -m ordo dia 2027-08-15         # ver qué se celebra y el mensaje
python -m ordo vista-previa 2027      # genera vista_previa_2027.html con todo el año
```

`herramientas/build_data.py` regenera `santoral.csv` desde las planillas originales. Solo hace falta si se rehace la base completa.
