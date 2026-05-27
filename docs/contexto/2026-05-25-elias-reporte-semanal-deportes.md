# Sesion Elias — Reporte semanal de deportes + imagenes

Fecha: 2026-05-25
Origen: comentarios de Elias en sesion (equipo de redes AMX, Claro Sports).
Esta nota es CONTEXTO/DECISION. La implementacion vive en el repo `~/projects/keni-social`.

Dos iniciativas salieron de la sesion:
1. Automatizar el reporte semanal que hoy se arma a mano en Canva.
2. Edicion/creacion de imagenes sin Photoshop, con una linea visual consistente.

---

## 1. Reporte semanal de Claro Sports (hoy manual en Canva -> automatizar)

Hoy el equipo arma cada semana una presentacion en Canva, a mano. Queremos que se
genere automatica, tal cual se hace hoy.

### Que lleva el reporte (en orden)

1. **Mejores piezas de la semana**
   - Top 3 de Instagram
   - Top 3 de TikTok
   - Top 3 de Facebook
   - Criterio: visualizaciones e interacciones
   - Por cada pieza: visualizaciones, interacciones y el link
2. **Promocion de cuentas hermanas**
   - Algunos posteos de **Claro Sports TV** y **Csport Golf** hechos durante la semana
   - Objetivo: seguir dando promocion a esas dos cuentas
3. **Temas editoriales de la proxima semana**
   - Principales eventos: cuales son y que vamos a hacer de cada uno
   - Eventos/transmisiones propias: que vamos a tener y como lo vamos a hacer

### Fuentes de informacion (hoy manual)
- Curaduria manual segun los gustos del publico.
- Recurrentes (si o si): futbol, tenis, basquetbol, beisbol. Especificamente
  **transmisiones deportivas**, no programas deportivos.
- Ocasionales: eventos que creen que pueden interesar, p. ej. UFC (no recurrente).

### Formato
- Presentacion en **Canva** (no PowerPoint).

### Mapeo a lo que ya existe en el repo
- **Datos de las mejores piezas** -> MCP `keni-metricas`. El modelo `Pieza` ya trae
  `plataforma`, `visualizaciones`, `interacciones` y `url`: justo los campos que pide
  Elias. La data esta.
- **Top 3 por plataforma** -> GAP menor. Hoy `mejores_piezas(cuenta, rango, n)` junta
  todas las plataformas, ordena por `engagement_pct` y devuelve el top N **global**
  (agregador.py:155). Falta: agrupar top 3 por cada plataforma (IG / TikTok / FB por
  separado) y ordenar por visualizaciones + interacciones, no solo engagement.
- **Claro Sports TV y Csport Golf** -> GAP. NO estan configuradas como cuentas en el
  MCP (hoy: claro_sports, unotv, nacion_gamer, piso_15, fundacion). Hay que darlas de
  alta.
- **Seccion editorial de la proxima semana** -> skill `calendario-editorial`. La
  curaduria sigue siendo humana (gustos del publico); la herramienta asiste el formato.
- **Salida en Canva** -> GAP grande. Hoy el sistema exporta Markdown / CSV / JSON; no
  hay integracion con Canva. Es la decision principal pendiente.

### Decisiones pendientes
- **Formato de salida**: como producir la presentacion. Opciones: (a) Canva API +
  plantilla de marca, (b) generar el deck (PPTX/PDF) desde plantilla propia y subirlo,
  (c) seguir armando en Canva pero alimentar los datos/links ya listos. Definir con Elias.
- **Top 3 por plataforma**: extender `mejores_piezas` (param para agrupar por plataforma)
  y revisar el criterio de orden (visualizaciones + interacciones).
- **Alta de cuentas** Claro Sports TV y Csport Golf en el MCP (handles + credenciales).

---

## 2. Edicion y creacion de imagenes (sin Photoshop, linea visual consistente)

Lo que pidio Elias:
- Que la edicion se haga **automatica**, sin tener que pasar por Photoshop.
- Creacion de imagenes con IA con una **linea visual propia y consistente**: no el look
  oscuro tipo ChatGPT, sino un patron fijo, que todas salgan igual (identidad de marca,
  los mismos patrones).

### Mapeo a lo que ya existe
- Skills `estudio-imagen` (Fase 1) + `revisa-imagen`. Ver `docs/estudio-imagen.md`.
- La "linea / mismos patrones" se logra mejor con **composicion deterministica por
  plantilla** (Pillow): overlays, placas, recortes, marca de agua — identicos cada vez.
  Eso es exactamente lo que pide Elias.
- IA generativa solo para elementos **no documentales** (fondos, ilustraciones, placas),
  nunca alterando fotos reales de noticia/deporte (linea roja editorial ya definida en
  `docs/estudio-imagen.md`).

### Decisiones pendientes
- Definir la "linea" visual de Claro Sports como plantilla(s) deterministica(s) + (si
  aplica) un estilo IA para graficos que no sean foto.
- Motor IA: el diseno actual apunta a Google Gemini ("Nano Banana") por API.

---

## Estado (2026-05-25): reporte implementado

Decision tomada: salida = **deck propio (PPTX/PDF)**, no Canva.

Hecho en el repo, rama `feat/reporte-deportes` (CI local en verde, 429 tests):
- Alta de Claro Sports TV y Csport Golf como cuentas de la muestra.
- Top 3 POR plataforma (IG / TikTok / FB) por visualizaciones + interacciones, con link
  (`FuenteMuestra.mejores_por_plataforma`).
- Nuevo CLI `keni-reporte-deck`: arma las 3 secciones (mejores piezas, promocion de
  cuentas hermanas, agenda de la proxima semana) y renderiza un `.pptx` de marca.
  `python-pptx` es dependencia opcional (`[deck]`), no carga el MCP/consola.
- Agenda editorial por TOML (curaduria manual): `agenda-editorial.ejemplo.toml`.
- Doc: `docs/reporte-deportes.md`.

Mergeado a `main` (commit a86ec1d) y pusheado.

### Integracion en la consola (commit ae3920a, en `main`)
Pagina "Reporte deportes" en keni-consola:
- Backend `consola/api/reporte_deportes.py`: GET /opciones, POST /preview, POST
  /export.pptx (descarga binaria). python-pptx pasa a dependencia de la consola.
- Frontend `pages/ReporteDeportes.tsx`: selector de rango + nº de piezas, editor de
  la agenda (eventos principales + transmisiones propias), previsualizacion de las
  mejores piezas por plataforma y promocion de cuentas hermanas, y descarga del .pptx.
- Verificado en vivo (server real): los 3 endpoints + SPA OK; 636 tests consola en verde.

Pendiente:
1. Exportacion PDF nativa sin depender de LibreOffice.
2. Plantilla(s) de imagen para la linea visual de Claro Sports (ver estudio-imagen).
