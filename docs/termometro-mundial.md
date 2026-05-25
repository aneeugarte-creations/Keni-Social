# Termómetro mundial

El **Termómetro mundial** es el posteo de **galería** que sale a primera hora con las
**5–8 noticias internacionales** más importantes de la coyuntura, **una por región**
(Asia, Europa, América Latina, EEUU, Medio Oriente…). En vez de armarlo a mano cada
mañana, el equipo le pasa las notas del día, una IA las **jerarquiza** (por relevancia
internacional, impacto y frescura), elige el top, las reparte por región en slides y
entrega el **copy del posteo** ya tropicalizado a México, listo para revisar y publicar.

Tres piezas, una sola idea:

1. **La skill** `termometro-mundial` — el cerebro: jerarquiza y arma la galería + copy.
2. **La página de la Consola** — para armarlo a mano cuando quieras.
3. **El cron `keni-termometro`** — para que a las 7:00 ya esté hecho, sin abrir nada.

Como el resto de skills de copy, **el humano aprueba**: la salida es un borrador
verificado (abre con el veredicto ✅/⚠️/❌), nunca una publicación automática.

## La skill `termometro-mundial`

Vive en `skills-copy/.claude/skills/termometro-mundial/` (`SKILL.md` + `keni.yaml`).
Salida tipo **documento** (una galería + caption, no una variante por red). Entradas:

- **Noticias del día** (`noticias`): la materia prima. La skill **no inventa nada** fuera
  de aquí; solo jerarquiza y reparte lo que se le pasa.
- **Número de slides** (`numero`): entre 5 y 8 (def. 8).
- **Regiones** (`regiones`): CSV; vacío = reparto por defecto priorizando la diversidad.
- **Fecha** (`fecha`): para la portada; vacío = hoy.

Carga el contexto editorial (`reglas-legales`, `plataformas`, `tropicalizacion`, la ficha
de marca) para angular el tono, tropicalizar y marcar riesgos por slide.

## En la Consola

**Trabajo → Termómetro mundial.** Dos paneles:

- **Configuración**: número de slides, regiones, **hora** del cron y **marca** por defecto.
  Se guarda local (`~/.config/keni-social/termometro.json`) y la comparten la página y el
  cron.
- **Armar el termómetro de hoy**: elige marca/slides/fecha, pega las noticias (o pulsa
  **Traer del RSS** para volcar los titulares recientes de tus feeds) y **Generar**. Corre
  en segundo plano con el progreso en vivo; al terminar puedes **guardar como publicación**.

### Endpoints

- `GET  /api/termometro` — config guardada + si la skill está instalada + marcas + regiones.
- `PUT  /api/termometro/config` — guarda `{numero, regiones, hora, marca}`.
- `POST /api/termometro/generar` — lanza la generación (`{marca, noticias, numero?, regiones?,
  fecha?}`) reutilizando el motor de Skills; responde con `{generacion}` y se sondea en
  `GET /api/generaciones/{id}`.

## Generación programada (cron 07:00)

A las 7:00 normalmente no hay nadie con la Consola abierta, así que el CLI **`keni-termometro`**
hace lo mismo **sin servidor** y de forma síncrona, pensado para `cron`/`launchd`:

1. Lee la config guardada (marca, número, regiones) — la misma que la web.
2. Reúne las noticias del día de los **feeds RSS activos** (el "rastreo") o de un archivo.
3. Corre la skill y deja el resultado en el **historial** (Consola → Generar copy → Historial),
   donde el community lo encuentra al llegar. No publica nada: es un borrador.

```bash
keni-termometro                          # usa la config guardada + RSS
keni-termometro --marca claro-sports     # fuerza la marca
keni-termometro --noticias-file hoy.txt  # noticias de un archivo (en vez de RSS)
keni-termometro --dry-run                # imprime el prompt y NO llama a claude
```

Requisitos: tener instalada la consola (`pipx install keni-consola` o el entorno del repo,
que registra el comando `keni-termometro`), Claude Code (`claude`) en el `PATH`, y una
**marca** configurada. Usa rutas absolutas en el cron (no hay `PATH` de login).

### macOS (launchd)

`~/Library/LaunchAgents/io.kenitech.termometro.plist` (ajusta las rutas y la `Hour`/`Minute`
a tu config):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>io.kenitech.termometro</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/TU_USUARIO/.local/bin/keni-termometro</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key> <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>   <integer>7</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>  <string>/tmp/keni-termometro.log</string>
  <key>StandardErrorPath</key><string>/tmp/keni-termometro.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/io.kenitech.termometro.plist   # activar
launchctl start io.kenitech.termometro                               # probar ya
```

### Linux (crontab)

```cron
# m h  dom mon dow  comando   (todos los días a las 07:00)
0 7 * * *  /home/TU_USUARIO/.local/bin/keni-termometro >> /tmp/keni-termometro.log 2>&1
```

## Fuente de noticias

- **RSS** (por defecto): da de alta feeds en **Fuentes**. El cron toma los feeds activos
  (los de la marca elegida + los generales) y aplica sus filtros incluir/excluir.
- **Archivo** (`--noticias-file`): para curaduría 100 % manual. Una nota por línea.

Si no hay feeds con items ni archivo, el cron no llama a la IA: avisa y termina (no inventa
noticias).

## Privacidad y criterio editorial

- Todo es **local**: la config vive en tu máquina; la generación corre con tu Claude Code.
- La skill **no inventa**: solo jerarquiza y reparte las notas que se le dan.
- La salida es un **borrador verificado** (veredicto + auto-verificación). El humano revisa
  y publica.
