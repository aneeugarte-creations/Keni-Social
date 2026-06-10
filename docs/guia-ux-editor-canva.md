# Guía de diseño UX — Editor nivel Canva (investigación 2026-06-09)

## 1. Shell: 5 regiones + canvas, viewport completo SIN scroll de página
- Raíz: h-screen overflow-hidden flex-col. min-h-0/min-w-0 en TODOS los flex intermedios (causa nº1 de scroll roto).
- Cabecera 48-56px: logo/home, redimensionar formato, Deshacer/Rehacer, autoguardado visible ("Guardando…"→"Todos los cambios guardados"), nombre editable inline, botón primario único Compartir/Descargar. Resto ghost.
- Rail izquierdo ~72px, pestañas verticales icono+etiqueta, orden: Diseño (plantillas, SIEMPRE primera), Elementos, Texto, Marca, Subidas, Apps, Proyectos. Hover abre panel como overlay; click lo fija.
- Panel secundario ~350px colapsable (Cmd+/): búsqueda sticky arriba → chips de categoría (carrusel horizontal) → masonry 2 columnas scroll infinito. Nunca scroll horizontal ni scrollbars anidados.
- Canvas: fondo gris neutro, página blanca centrada con sombra. Zoom inicial = fit. Espacio+drag = pan. Cmd+rueda = zoom al cursor.
- Toolbar contextual ~48px ANCLADA entre cabecera y canvas, ancho completo, altura CONSTANTE, muta según selección. Sufijo fijo: Animar · Transparencia · Posición · ⋯. Sin selección: color de página, márgenes, duración.
- Barra inferior ~40px: páginas x/N, slider zoom + % (menú: 10-500%, Fit, 100%), vista cuadrícula, fullscreen, ayuda.
- Modo vídeo: + Timeline 120-160px sobre la barra inferior.

## 2. Bounding box (lo que más nivel da)
- Borde 1-2px acento que envuelve EXACTO los píxeles renderizados (imagen ya recortada, texto sin padding fantasma). Rota con el elemento. Handles en overlay, nunca en el bitmap.
- 4 esquinas = círculo blanco borde gris (~12px visual, hit-area ≥24px) = escala PROPORCIONAL por defecto (sin Shift).
- 4 laterales = píldora (~16×6px): en imagen RECORTA desde ese borde (no estira); en texto cambia ancho de caja (reflow).
- Rotación: handle debajo del bbox centrado a ~24-32px, etiqueta "45°", snap suave a 0/45/90.
- Etiqueta flotante W×H px durante resize; grados durante rotación. Elementos pequeños: ocultar laterales.
- Cursores correctos por handle (nwse/nesw/ns/ew-resize, move, grab/grabbing).
- Doble clic en imagen = modo CROP: original atenuado fuera del marco, arrastrar/escalar imagen dentro, Hecho/Cancelar, Enter confirma, Esc cancela. Crop nunca destruye píxeles (modelo {src, cropX, cropY, cropW, cropH} normalizado).
- Snapping: guías magenta a bordes/centros de página y de otros elementos + espaciado igual con etiqueta px. Umbral ~5px de PANTALLA (dividir por zoom). Ctrl suspende snap durante el arrastre. Marquee en zona vacía. Multi-selección Shift+click.

## 3. Plantillas
- Panel Diseño: búsqueda sticky + chips categoría + masonry 2 col + scroll infinito. Hover: elevación + autoplay si animada. Aplicar = 1 clic; slots con ROL explícito (titular, kicker, foto, logo, fecha) para conservar contenido al cambiar plantilla.
- Selector: marca (UnoTV/Claro Sports) → categoría → formato.
- Formatos: IG cuadrado 1080×1080, IG retrato 1080×1350, Story/Reel/TikTok 1080×1920 (zona segura central), X 1600×900, FB 1200×630, miniatura YT 1280×720, cabecera X 1500×500. Overlay de zonas seguras por plataforma.
- Catálogo categorías noticias (UnoTV): ultima-hora/breaking, titular-del-dia, cita-declaracion, lo-que-sabemos (carrusel), dato-cifra, alerta-sismo-clima, efemerides, esquela, en-vivo, encuesta.
- Catálogo deportes (Claro Sports): marcador-final, marcador-en-vivo, previa-partido, alineacion, calendario-jornada, tabla-posiciones/medallero, fichaje (OFICIAL vs RUMOR), jugador-del-partido/stat, record-hito, promo-programa/countdown.

## 4. Vídeo: mismo shell, mismo documento
- Un vídeo = mismo documento multi-página; página = escena/clip (default 5s). El modo vídeo SOLO añade timeline + player. NO otra app.
- Timeline: regla de tiempo + playhead arrastrable; clips como tarjetas con thumbnail, ancho ∝ duración; drag reordena; asas de trim en bordes; S = split en playhead; + entre clips = transición; pista audio con waveform; zoom propio del timeline; Espacio = play/pause.
- Misma plantilla sirve para imagen y vídeo: elementos con animationIn/Out {type,duration,delay}, página con duration. Render estático ignora animación.

## 5. Detalles de nivel
- Atajos: T/R/C/L crear, Cmd+Z/Cmd+Shift+Z, Cmd+D duplicar, Cmd+G grupo, Cmd+]/[ capa, flechas 1px/Shift 10px, Del, Esc (cierra crop→deselecciona→cierra panel, en ese orden), Cmd+0 100%, Alt+Cmd+0 fit, Cmd+/ colapsa panel, Espacio play/pan, S split, Alt+Shift+T tidy up.
- Hover en elemento del canvas: contorno fino acento ANTES del click. Thumbnails: scale 1.02-1.05 ~150ms.
- Tooltips en TODO icono con atajo ("Duplicar ⌘D"), delay 500ms, instantáneo entre hermanos.
- Autosave debounce 1-2s, estado visible, error visible con reintento. Nunca "Guardar" como única vía.
- Drag/resize 60fps: durante gesto solo transform (rAF), commit al soltar. Transiciones 150-250ms, nada >300ms.
- Accesibilidad: aria-label en toolbar, foco visible, atajos no capturan en inputs, prefers-reduced-motion.
