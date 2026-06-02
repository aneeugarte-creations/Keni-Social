# Formatos de entrega de foto — full + 4:5 con extension de fondo

Fecha: 2026-05-25
Origen: sugerencia del fotografo del equipo de redes AMX (piloto UnoTV / Claro Sports), via nota de voz.
Esta nota es CONTEXTO/DECISION; la implementacion vive en este mismo repo.
Relacionada con `docs/contexto/2026-05-25-elias-reporte-semanal-deportes.md` (seccion 2:
edicion de imagenes sin Photoshop) y con `docs/estudio-imagen.md`.

---

## La necesidad

Se toma la foto (archivo original) y hay que entregarla en DOS formatos:

1. **Full**: casi el original, solo un resize pequeno, pero ajustando el PESO del archivo.
   Motivo: en eventos masivos el internet es rudimentario y el archivo grande no sube.
   Hoy se resuelve con una accion de Photoshop.
2. **4:5 (Instagram)**: a veces el sujeto no cabe completo al recortar a 4:5 por el encuadre.
   Cuando falta solo un poco —y lo que falta es solo cielo o solo el negro del fondo— se
   quiere EXTENDER ese fondo, sin tocar a los jugadores ni el retrato, para que la foto que
   se necesita quepa completa en 4:5.

---

## Decisiones tomadas (sesion 2026-05-25)

- **Extension del 4:5 = HIBRIDA.** Extender el fondo de forma determinista (clonar/estirar
  el cielo o la franja negra; no inventa pixeles). Usar IA solo si el borde no es uniforme,
  y siempre con confirmacion del fotografo. Asi se respeta la regla editorial salvo
  excepcion explicita (ver caveat abajo).
- **Peso del full = DROPDOWN seleccionable.** No un valor fijo: el fotografo elige el peso
  objetivo segun la situacion (p. ej. 1 / 2 / 3 MB + personalizado), conservando el tamano
  original (solo baja calidad/compresion hasta llegar al peso).
- **Cuando extender = AUTOMATICO CON VISTA PREVIA.** Detecta cuando el recorte cortaria al
  sujeto, propone el 4:5 con el fondo extendido, y el fotografo aprueba antes de exportar.
  Encaja con el flujo de revision humana ya existente (`revisa-imagen`).

---

## Caveat editorial (importante)

`docs/estudio-imagen.md` define como inviolable la regla §3: "la IA NO altera fotos de
noticia reales", y `estudio-imagen/generar.py` BLOQUEA aplicar IA a una foto real
(`--foto_real`). Extender el cielo con IA generativa choca de frente con esa regla.

Por eso la opcion elegida es hibrida y determinista por defecto: para cielo/negro uniformes
el estiramiento/clonado de borde NO inventa contenido y respeta §3 al 100%. Si en algun caso
hiciera falta IA (fondo con textura), se trata como EXCEPCION explicita y aprobada, no como
comportamiento por defecto. Pendiente de validar el criterio con el responsable editorial de
AMX.

---

## Mapeo a lo que ya existe en el repo

> **Nota posterior:** la skill `estudio-imagen` se **relocalizó** al motor
> `consola/src/keni_consola/motores/estudio_imagen/` (el sistema de skills se retiró); la superficie
> de usuario hoy es la página **Estudio** (`frontend/src/pages/Estudio.tsx`), no la pestaña
> "Imagenes". El mapeo de abajo es del 25-may.

- **Recorte a 4:5** y resize: ya hechos, deterministas con Pillow, en la skill
  `estudio-imagen` (`editar.py`: `recortar`, `redimensionar`). Formatos: 9:16, 4:5, 1:1, 16:9.
- **Integracion gen IA**: ya existe. Gemini (`gemini-2.5-flash-image`, "Nano Banana") en las
  skills (`estudio-imagen/generar.py`) y OpenAI `gpt-image-1` en la Consola
  (`consola/.../media.py`, endpoint `/api/media/generar`).
- **Consola**: ya hay pestana "Imagenes" (`frontend/src/pages/Imagenes.tsx`) que enruta a las
  skills de imagen; almacen de media con UUID y anti-traversal.
- **Revision humana**: skill `revisa-imagen` (checklist legal/editorial, aprobacion humana).

### Gaps a implementar _(ya implementados — ver `docs/estudio-imagen.md` §8)_
- **Compresion a peso objetivo (full)**: hoy `redimensionar` solo cambia dimensiones; NO
  ajusta calidad/peso. Falta comprimir iterando calidad JPEG/WebP hasta caer bajo el peso
  elegido, conservando tamano. Exponer el peso como parametro (dropdown en consola).
  _(hecho: `estudio-imagen/editar.py comprimir` + dropdown "Peso" en `keni.yaml`.)_
- **Extension de fondo (4:5)**: NO existe codigo. Documentado como futuro ("expandir/outpaint")
  pero sin implementar. Implementar:
  - deteccion de borde uniforme (cielo/negro) + extension deterministica (clonado/estirado);
  - deteccion de cuando el recorte 4:5 cortaria al sujeto (disparador del flujo auto);
  - vista previa para aprobacion antes de exportar;
  - fallback IA opcional, solo bajo excepcion editorial confirmada.
  _(hecho: `editar.py extender` (determinista, solo borde uniforme) + `expandir.py` (fallback IA,
  re-compone el sujeto intacto); el resto del flujo auto/vista previa en la skill.)_

---

## Decisiones pendientes
- Validar con el responsable editorial de AMX el criterio de "extender solo fondo uniforme"
  frente a la regla §3 (¿determinista siempre ok?, ¿cuando se permite IA?).
- Umbral maximo de extension (¿hasta que % por lado se permite antes de exigir revision
  manual?).
- Valores del dropdown de peso (¿1/2/3 MB + custom?) y dimension maxima del lado largo en full.
- Donde vive el control: skill CLI (`estudio-imagen`) + pestana "Imagenes" de la consola
  (lo previsto: ambos, consistente con la arquitectura actual).
- Motor para el fallback IA si se aprueba: edicion con mascara (gpt-image-1 edit / Gemini image).
