// Render interactivo de UNA capa como nodo Konva. Es el "proxy" editable del lienzo: el archivo
// final lo hornea el servidor con `dibujarDocumento` (fidelidad exacta de fuentes/cover/degradados).
// Aquí priorizamos manipulación directa (seleccionar, arrastrar, escalar, rotar).

import Konva from "konva";
import { useEffect, useReducer, useRef } from "react";
import { Ellipse, Group, Image as KonvaImage, Line, Rect, Shape, Text, TextPath } from "react-konva";

import { MAPA_MEZCLA } from "../../lib/placa/dibujar.mjs";
import type { Capa, CapaGrupo, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto, Forma, RellenoDegradado } from "../documento";
import { bandaOverlay } from "../documento";
import { fotoMuestra } from "../muestra";
import { useImagen } from "../useImagen";

import { colorStopsKonva, puntosGradiente } from "./degradado";
import { geometriaImagenEnCaja } from "./geometriaImagen";
import { textoMuestra } from "./textoMuestra";
import { estiloFuente, familiaReal, medirTexto } from "./tipografia";

// Traza, en COORDS LOCALES (0..w, 0..h), la silueta de `forma` — espejo EXACTO de `pathForma`
// (dibujar.mjs) con origen en (0,0). Lo usan el clip de la imagen y el dibujo del marco en Konva,
// para que la previa coincida con el export del servidor. "rect" sin radio == rectángulo simple.
function pathFormaLocal(
  ctx: Konva.Context,
  forma: Forma | "linea" | undefined,
  w: number,
  h: number,
  radio = 0,
  radios?: [number, number, number, number],
) {
  const cx = w / 2, cy = h / 2;
  const poligono = (n: number, rot = -Math.PI / 2) => {
    for (let i = 0; i < n; i++) {
      const a = rot + (i * 2 * Math.PI) / n;
      const px = cx + (w / 2) * Math.cos(a);
      const py = cy + (h / 2) * Math.sin(a);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  };
  switch (forma) {
    case "elipse":
      ctx.ellipse(cx, cy, w / 2, h / 2, 0, 0, Math.PI * 2);
      return;
    case "triangulo":
      ctx.moveTo(cx, 0);
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      return;
    case "rombo":
      ctx.moveTo(cx, 0);
      ctx.lineTo(w, cy);
      ctx.lineTo(cx, h);
      ctx.lineTo(0, cy);
      ctx.closePath();
      return;
    case "pentagono":
      poligono(5);
      return;
    case "hexagono":
      poligono(6);
      return;
    case "estrella": {
      const puntas = 5;
      for (let i = 0; i < puntas * 2; i++) {
        const a = -Math.PI / 2 + (i * Math.PI) / puntas;
        const rf = i % 2 === 0 ? 1 : 0.5;
        const px = cx + (w / 2) * rf * Math.cos(a);
        const py = cy + (h / 2) * rf * Math.sin(a);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      return;
    }
    case "flecha": {
      const yTop = h * 0.3, yBot = h * 0.7;
      const xCabeza = w * 0.6;
      ctx.moveTo(0, yTop);
      ctx.lineTo(xCabeza, yTop);
      ctx.lineTo(xCabeza, 0);
      ctx.lineTo(w, cy);
      ctx.lineTo(xCabeza, h);
      ctx.lineTo(xCabeza, yBot);
      ctx.lineTo(0, yBot);
      ctx.closePath();
      return;
    }
    default: {
      // Esquinas: `radios` (cuádruple [tl,tr,br,bl]) manda sobre el `radio` uniforme. Espejo de
      // `rutaRect`/`radiosEsquina` de dibujar.mjs.
      const lim = Math.min(w / 2, h / 2);
      const r4 = (radios && radios.length === 4 ? radios : [radio, radio, radio, radio]).map((r) =>
        Math.max(0, Math.min(r || 0, lim)),
      );
      const [tl, tr, br, bl] = r4;
      if (tl || tr || br || bl) {
        ctx.moveTo(tl, 0);
        ctx.arcTo(w, 0, w, h, tr);
        ctx.arcTo(w, h, 0, h, br);
        ctx.arcTo(0, h, 0, 0, bl);
        ctx.arcTo(0, 0, w, 0, tl);
        ctx.closePath();
      } else {
        ctx.rect(0, 0, w, h);
      }
    }
  }
}

// ¿Es una forma "redonda"/no-rectangular cuyo realce de selección debe seguir su silueta?
function formaNoRect(forma: Forma | undefined, radio = 0, radios?: [number, number, number, number]): boolean {
  return (forma != null && forma !== "rect") || radio > 0 || (radios != null && radios.some((r) => r > 0));
}

export interface CapaNodoProps {
  capa: Capa;
  seleccionada: boolean;
  onSelect: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onChange: (cambios: Partial<Capa>) => void;
  onGesto: () => void;
  // Hijas de un grupo: no son arrastrables ni transformables por separado (el grupo manda).
  interactivo?: boolean;
  // "Vista con muestra": INDEPENDIENTES. `muestraFoto` rellena el hueco de foto con la foto de
  // muestra; `muestraCopy` rellena los bindings de texto con el copy de ejemplo. Solo PRESENTACIÓN;
  // no mutan la capa ni afectan al export.
  muestraFoto?: boolean;
  muestraCopy?: boolean;
  // Pinta la capa INVISIBLE (opacity 0) manteniendo el nodo vivo: la edición de texto en línea la
  // sustituye por su editable WYSIWYG sin que el Transformer pierda el marco de selección.
  oculta?: boolean;
}

const ALIN: Record<string, string> = {
  izquierda: "left",
  centro: "center",
  derecha: "right",
  justificado: "justify",
};

// Props de relleno Konva para un degradado (lineal o radial, multi-stop). Espejo de
// Path SVG de un ARCO para el texto curvo de Konva (`TextPath`), en coords LOCALES de la capa. Es
// una APROXIMACIÓN de la previa: el export del servidor (`dibujarTextoCurvo`) manda en la pieza
// final. `radio` px (+ = arco hacia arriba/sonrisa, - = hacia abajo). El ancla horizontal queda en
// la vertical de la caja según `align`; el arco abarca el ancho de la caja `w`.
function pathArco(radio: number, w: number, ancla: "left" | "center" | "right"): string {
  const r = Math.abs(radio);
  const arriba = radio > 0;
  // Centro del círculo: en la vertical del ancla horizontal (izq/centro/der de la caja). En y, por
  // debajo del borde superior (y=0) si el arco va hacia arriba; por encima si va hacia abajo.
  const cx = ancla === "center" ? w / 2 : ancla === "right" ? w : 0;
  const cy = arriba ? r : -r;
  // Mitad del ángulo barrido (cuerda ≈ ancho de la caja). Acotado a casi medio círculo.
  const half = Math.min(Math.PI * 0.95, (w / 2) / r);
  // Eje vertical del centro (parte superior del círculo si "arriba", inferior si no).
  const base = arriba ? -Math.PI / 2 : Math.PI / 2;
  let start: number;
  let end: number;
  if (ancla === "center") { start = base - half; end = base + half; }
  else if (ancla === "right") { start = base - 2 * half; end = base; }
  else { start = base; end = base + 2 * half; }
  // En "arriba" recorremos de izquierda a derecha (ángulo creciente); en "abajo" también, pero el
  // sentido del barrido del arco SVG (`sweep`) cambia para que el texto no quede invertido.
  const px = (a: number) => cx + r * Math.cos(a);
  const py = (a: number) => cy + r * Math.sin(a);
  const x0 = px(start), y0 = py(start);
  const x1 = px(end), y1 = py(end);
  const sweep = arriba ? 1 : 0;
  return `M ${x0} ${y0} A ${r} ${r} 0 0 ${sweep} ${x1} ${y1}`;
}

// `construirDegradado`: radial centrado en la caja, radio = mitad de la diagonal. Coords locales.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function rellenoDegradadoKonva(deg: RellenoDegradado, w: number, h: number): Record<string, any> {
  const stops = colorStopsKonva(deg);
  if (deg.tipo === "radial") {
    const r = Math.sqrt(w * w + h * h) / 2;
    return {
      fillRadialGradientStartPoint: { x: w / 2, y: h / 2 },
      fillRadialGradientEndPoint: { x: w / 2, y: h / 2 },
      fillRadialGradientStartRadius: 0,
      fillRadialGradientEndRadius: r,
      fillRadialGradientColorStops: stops,
    };
  }
  const g = puntosGradiente(w, h, deg.angulo);
  return {
    fillLinearGradientStartPoint: g.start,
    fillLinearGradientEndPoint: g.end,
    fillLinearGradientColorStops: stops,
  };
}

// `familiaReal` y `estiloFuente` (peso numérico real + cursiva, espejo del `fuenteCss` del
// servidor) viven en `tipografia.ts` para poder testearlos sin montar Konva.

type Filtros = CapaImagen["filtros"];

// Imagen AJUSTADA a una caja SIN deformar: la caja (`Group`) recorta y la imagen se escala
// preservando su proporción — `cover` la llena (desborde recortado), `contain` la encaja. El
// `Group` es el nodo interactivo (drag/transform); la imagen interior aplica los filtros Konva
// (WYSIWYG; el export del servidor usa los mismos, exactos).
function NodoImagenAjustada({
  img,
  w,
  h,
  ajuste,
  foco,
  zoom = 1,
  filtros,
  forma,
  radio,
  radios,
  crop,
  flipH,
  flipV,
  props,
}: {
  img: HTMLImageElement;
  w: number;
  h: number;
  ajuste: "cover" | "contain";
  foco: [number, number];
  zoom?: number;
  filtros: Filtros;
  forma?: Forma;
  radio?: number;
  radios?: [number, number, number, number];
  crop?: CapaImagen["crop"];
  flipH?: boolean;
  flipV?: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: any;
}) {
  const ref = useRef<Konva.Image | null>(null);
  // Geometría del ajuste (cover/contain + foco + zoom + crop): destino, rect VISIBLE dentro de la
  // caja y sub-rect FUENTE equivalente (helper puro, espejo de `dibujarImagenEnCaja`). El
  // KonvaImage pinta SOLO el rect visible (con crop de fuente exacto, mismos píxeles que la foto):
  // el bbox de un Group en Konva IGNORA el clip, así que pintar el destino entero hacía que el
  // Transformer (marco de selección) saliera más ancho/alto que la foto cuando cover/zoom
  // desbordaban la caja. Así el marco abraza EXACTAMENTE la foto renderizada, como Canva.
  const g = geometriaImagenEnCaja(img.width, img.height, w, h, ajuste, foco, zoom, crop);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    // El duotono no es un filtro CSS nativo de Konva; lo aproximamos con un tinte (capa de color
    // encima, ver más abajo). Aquí solo cuentan brillo/contraste/saturación/desenfoque.
    const duotono = filtros?.duotono ?? null;
    if (!filtros || (filtros.brillo === 1 && filtros.contraste === 1 && filtros.saturacion === 1 && !filtros.desenfoque && !duotono)) {
      node.filters([]);
      node.clearCache();
      node.getLayer()?.batchDraw();
      return;
    }
    const lista: (typeof Konva.Filters.Brighten)[] = [];
    if (filtros.brillo != null && filtros.brillo !== 1) lista.push(Konva.Filters.Brighten);
    if (filtros.contraste != null && filtros.contraste !== 1) lista.push(Konva.Filters.Contrast);
    if (filtros.saturacion != null && filtros.saturacion !== 1) lista.push(Konva.Filters.HSL);
    if (filtros.desenfoque) lista.push(Konva.Filters.Blur);
    // Duotono: pasamos la foto a gris (Grayscale) para que el tinte superior la mapee por luminancia
    // (aproximación; el export del servidor manda en la pieza final).
    if (duotono) lista.push(Konva.Filters.Grayscale);
    node.filters(lista);
    node.brightness((filtros.brillo ?? 1) - 1);
    node.contrast(((filtros.contraste ?? 1) - 1) * 100);
    node.saturation((filtros.saturacion ?? 1) - 1);
    node.blurRadius(filtros.desenfoque ?? 0);
    try {
      node.cache();
    } catch {
      /* imagen aún sin dimensiones: se reintenta en el próximo render */
    }
    node.getLayer()?.batchDraw();
    // El cache de filtros congela el CONTENIDO del nodo: re-cachear cuando cambian el tamaño
    // visible o el sub-rect de fuente (foco/zoom/crop pueden mover la fuente sin mover el destino).
  }, [filtros, img, g.vw, g.vh, g.sx, g.sy, g.sw, g.sh]);

  // Recorte de la caja según la forma (espejo del clip de `dibujarImagenEnCaja`): catálogo completo
  // de formas (elipse, polígonos, estrella, flecha…) o rect simple/redondeado. Para "rect" sin
  // radio usamos clipX/Y/W/H (camino rápido).
  const r = radio ?? 0;
  const recorte =
    formaNoRect(forma, r, radios)
      ? {
          clipFunc: (ctx: Konva.Context) => {
            ctx.beginPath();
            pathFormaLocal(ctx, forma, w, h, r, radios);
          },
        }
      : { clipX: 0, clipY: 0, clipWidth: w, clipHeight: h };
  // Tinte DUOTONO (aproximación Konva): dos Rects con la forma de la caja, "multiply" con `luz` y
  // "lighten" con `sombra`, sobre la foto en gris. El export del servidor (dibujar.mjs) es la
  // verdad; aquí basta una previa razonable. Recortado por el clip del Group (mismo path).
  const duo = filtros?.duotono ?? null;
  // VOLTEO (flip): espejo alrededor del CENTRO de la caja. Va en un Group INTERIOR (no en el nodo
  // interactivo de `props`) para no contaminar el `scaleX/Y` que el Transformer usa al redimensionar
  // (con un scale -1 fijo en el nodo, `onTransformEnd` calcularía un w/h negativo). El recorte por
  // forma (clip) vive en este Group interior para voltearse junto al contenido (espejo del motor:
  // `aplicarFlip` envuelve clip+foto). offset = w/h cuando se invierte el eje, así el espejo gira
  // sobre el centro y la caja [0,w]×[0,h] sigue cubierta. Espejo de `aplicarFlip` en `dibujar.mjs`.
  const sx = flipH ? -1 : 1;
  const sy = flipV ? -1 : 1;
  const flip = sx !== 1 || sy !== 1
    ? { scaleX: sx, scaleY: sy, offsetX: sx === -1 ? w : 0, offsetY: sy === -1 ? h : 0 }
    : {};
  // ¿La caja delimitadora debe ABRAZAR el contenido visible (Canva)? Solo cuando la capa es un
  // rectángulo simple sin duotono: con forma/esquinas la silueta ocupa la caja entera (el realce
  // de selección la sigue) y el tinte duotono pinta toda la caja, igual que el export. Con `cover`
  // el rect visible YA es la caja; esto solo cambia el caso `contain` letterboxed, donde el marco
  // y el área clicable se ciñen a la foto (el letterbox vacío deja de capturar clics, como Canva).
  const abrazaPublicacion = !formaNoRect(forma, r, radios);
  const hit = abrazaPublicacion && !duo
    ? { x: g.vx, y: g.vy, width: g.vw, height: g.vh }
    : { x: 0, y: 0, width: w, height: h };
  return (
    <Group {...props}>
      <Group {...recorte} {...flip}>
        {/* Zona sensible al puntero del tamaño del CONTENIDO visible (o de la caja, si la silueta
            la ocupa entera): la imagen interior va con listening=false, así que sin este Rect el
            Group no recibiría clic/arrastre (no se podían mover las fotos). opacity 0 = invisible
            en escena pero presente en el hit graph de Konva. */}
        <Rect {...hit} fill="#000000" opacity={0} />
        <KonvaImage
          ref={ref}
          image={img}
          x={g.vx}
          y={g.vy}
          width={g.vw}
          height={g.vh}
          listening={false}
          crop={{ x: g.sx, y: g.sy, width: g.sw, height: g.sh }}
        />
        {duo && (
          <>
            <Rect x={0} y={0} width={w} height={h} fill={duo.luz} globalCompositeOperation="multiply" listening={false} />
            <Rect x={0} y={0} width={w} height={h} fill={duo.sombra} globalCompositeOperation="lighten" listening={false} />
          </>
        )}
      </Group>
    </Group>
  );
}

// `textoMuestra` (texto pintado, con la normalización espejo del export) vive en
// `textoMuestra.ts` para poder testearlo sin montar Konva.

export function CapaNodo({ capa, seleccionada, onSelect, onChange, onGesto, interactivo = true, muestraFoto = false, muestraCopy = false, oculta = false }: CapaNodoProps) {
  // Hook SIEMPRE llamado (regla de hooks); null para capas sin imagen.
  const objetoImg = capa.tipo === "imagen" ? capa.objeto : capa.tipo === "logo" ? capa.media_id : null;
  const img = useImagen(objetoImg);
  // Fuerza un redibujo del lienzo cuando la foto de muestra (generada async en cliente) ya está
  // lista, para que el hueco la pinte sin esperar a otra interacción.
  const [, redibujar] = useReducer((n: number) => n + 1, 0);

  // — Texto LEGADO (h<=0) con ancla "abajo": el contrato del export (dibujar.mjs, camino h<=0)
  // interpreta `y` como borde INFERIOR del bloque (top = y - blockH). Konva siempre dibuja hacia
  // abajo desde `y`, así que desplazamos el CONTENIDO con offsetY = alto del bloque renderizado:
  // el nodo conserva las coords almacenadas (drag/transform siguen escribiendo el contrato) y la
  // rotación pivota en (x,y), igual que el export. Con chip el offset va en el Group envolvente y
  // suma el padding superior (espejo del blockH del export, que incluye pad_y arriba y abajo).
  // Sin lista de deps: el alto depende del wrap que Konva acaba de calcular en este render.
  const nodoTextoRef = useRef<Konva.Text | null>(null);
  const grupoChipRef = useRef<Konva.Group | null>(null);
  useEffect(() => {
    const nodo = grupoChipRef.current ?? nodoTextoRef.current;
    if (!nodo) return;
    const c = capa as CapaTexto;
    const anclaAbajo = capa.tipo === "texto" && c.h <= 0 && c.ancla === "abajo" && !(c.curva && c.curva.radio);
    const texto = grupoChipRef.current ? grupoChipRef.current.findOne<Konva.Text>("Text") : nodoTextoRef.current;
    const off = anclaAbajo && texto ? texto.height() + (c.chip ? (c.chip.pad_y ?? 14) : 0) : 0;
    if (nodo.offsetY() !== off) {
      nodo.offsetY(off);
      nodo.getLayer()?.batchDraw();
    }
  });

  // El wordmark del logo se mide con canvas 2D (`measureText`) durante el RENDER: si la webfont
  // entra después, el chip quedaría medido con la fuente de respaldo. Re-render al cargar fuentes.
  useEffect(() => {
    if (capa.tipo !== "logo" || typeof document === "undefined" || !("fonts" in document)) return;
    let vivo = true;
    const f = () => {
      if (vivo) redibujar();
    };
    document.fonts.ready.then(f).catch(() => {});
    document.fonts.addEventListener?.("loadingdone", f);
    return () => {
      vivo = false;
      document.fonts.removeEventListener?.("loadingdone", f);
    };
  }, [capa.tipo]);

  const comun = {
    id: capa.id,
    x: capa.x,
    y: capa.y,
    rotation: capa.rotacion,
    opacity: oculta ? 0 : capa.opacidad,
    // Modo de fusión (espejo de `dibujarCapa`): sin `mezcla` => "source-over" (idéntico al legado).
    globalCompositeOperation: (MAPA_MEZCLA[capa.mezcla ?? "normal"] ??
      "source-over") as GlobalCompositeOperation,
    draggable: interactivo && !capa.bloqueada,
    onMouseDown: onSelect,
    onTap: onSelect,
    listening: interactivo,
    ...(interactivo
      ? {
          onDragStart: onGesto,
          onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => {
            // `currentTarget` (el nodo al que está atado el handler = el NODO de la capa, el que
            // Konva arrastra) y NO `target` (la forma bajo el puntero). Importa en las capas
            // envueltas en Group cuyo contenido visible es un HIJO: al arrastrar el overlay
            // agarras su Rect-banda hijo (local y = h - banda); `target.y()` horneaba ESE desfase
            // como y del modelo y la banda salía volando +(h - banda) fuera del lienzo. Para una
            // capa de UNA sola forma, currentTarget === target (sin cambio).
            onChange({ x: e.currentTarget.x(), y: e.currentTarget.y() });
          },
        }
      : {}),
  };

  // Transform genérico: convierte escala -> w/h (y caja en textos), resetea escala.
  const onTransformEnd = (e: Konva.KonvaEventObject<Event>) => {
    const nodo = e.target;
    const sx = nodo.scaleX();
    const sy = nodo.scaleY();
    // Sin transformación PENDIENTE en el nodo no se hornea nada: tras el RECORTE LATERAL de una
    // imagen (Lienzo) la caja y el crop ya fueron al store por frame y el nodo queda limpio
    // (escala 1, attrs == capa); hornear aquí duplicaría el paso de deshacer. También cubre el
    // mero clic en un tirador sin arrastre (que en texto sin caja activaría el modo caja).
    if (sx === 1 && sy === 1 && nodo.x() === capa.x && nodo.y() === capa.y && nodo.rotation() === capa.rotacion) {
      return;
    }
    // Defensa: una caja degenerada (línea con h=0) puede producir una matriz singular dentro del
    // Transformer de Konva y dejar attrs NaN; jamás se hornean valores no finitos al documento.
    if (![sx, sy, nodo.x(), nodo.y(), nodo.rotation()].every(Number.isFinite)) return;
    nodo.scaleX(1);
    nodo.scaleY(1);
    const base: Partial<Capa> = {
      x: nodo.x(),
      y: nodo.y(),
      rotacion: nodo.rotation(),
    } as Partial<Capa>;
    // ROTACIÓN PURA o movimiento sin escala (sx=sy=1): solo posición/rotación, sin pasar por el
    // horneado de w/h y sus MÍNIMOS. Ese horneado rotaría una línea (h=0) escribiendo h=8 (queda
    // diagonal) y un texto sin caja a modo caja de UNA línea (encogido + "…" en el export).
    if (sx === 1 && sy === 1) {
      onChange(base);
      return;
    }
    if (capa.tipo === "texto") {
      const c = capa as CapaTexto;
      // Texto EN ARCO: una sola línea sin caja (el export ignora h con curva activa); persistir
      // h>0 lo reinterpretaría como modo caja al quitar la curva. Solo ancho + posición/rotación.
      if (c.curva && c.curva.radio) {
        onChange({ ...base, w: Math.max(16, c.w * sx) } as Partial<Capa>);
        return;
      }
      // "La caja es inamovible, que encoja el texto": al redimensionar una capa de texto
      // dibujamos la CAJA (ancho Y alto). El texto se auto-encoge en el render para caber; NO
      // crecemos el tamaño de fuente con la escala vertical.
      if (c.h > 0) {
        onChange({ ...base, w: Math.max(16, c.w * sx), h: Math.max(16, c.h * sy) } as Partial<Capa>);
        return;
      }
      // Resize solo HORIZONTAL (sy=1, tiradores laterales) de un texto en modo línea: el texto
      // re-envuelve al nuevo ancho y SIGUE sin caja — activar el modo caja era un efecto
      // colateral que encogía/truncaba el export sin que el usuario tocara el alto.
      if (sy === 1) {
        onChange({ ...base, w: Math.max(16, c.w * sx) } as Partial<Capa>);
        return;
      }
      // Conversión modo LÍNEA (h<=0) -> modo CAJA: persistir h ACTIVA la caja. El alto parte del
      // bloque REALMENTE renderizado por Konva (todas las líneas envueltas, no UNA sola, que
      // dejaría el export encogido a tam_min y truncado con "…"). Con ancla "abajo" la `y`
      // almacenada era el borde INFERIOR y el modo caja la interpreta como SUPERIOR: se rebasa
      // y = y - h' (offset rotado con el pivote (x,y), igual que el export) y se fija
      // valign "abajo" para que el bloque no salte de sitio al exportar.
      const nodoTxt = nodo instanceof Konva.Group ? nodo.findOne<Konva.Text>("Text") : nodo;
      const hBloque = nodoTxt instanceof Konva.Text
        ? nodoTxt.height() + (c.chip ? (c.chip.pad_y ?? 14) * 2 : 0)
        : c.tamano * c.interlineado;
      const hN = Math.max(16, hBloque * sy);
      const wN = Math.max(16, c.w * sx);
      if (c.ancla === "abajo") {
        const rad = (nodo.rotation() * Math.PI) / 180;
        onChange({
          x: nodo.x() + hN * Math.sin(rad),
          y: nodo.y() - hN * Math.cos(rad),
          rotacion: nodo.rotation(),
          w: wN,
          h: hN,
          valign: "abajo",
        } as Partial<Capa>);
        return;
      }
      onChange({ ...base, w: wN, h: hN } as Partial<Capa>);
      return;
    }
    // La LÍNEA es VECTORIAL: el export dibuja de (x,y) a (x+w,y+h) y h = 0 o NEGATIVA son estados
    // válidos del contrato. El mínimo de 8px del camino genérico la volvía diagonal (h=8) o la
    // invertía (h<0) al escalarla dentro de una multi-selección.
    if (capa.tipo === "marco" && (capa as CapaMarco).forma === "linea") {
      onChange({ ...base, w: capa.w * sx, h: capa.h * sy } as Partial<Capa>);
      return;
    }
    onChange({
      ...base,
      w: Math.max(8, capa.w * sx),
      h: Math.max(8, capa.h * sy),
    } as Partial<Capa>);
  };

  const props = { ...comun, onTransformEnd };

  // Visibilidad: ocultar una capa es solo una AYUDA DE EDICIÓN (ver fondos/transparencias detrás),
  // así que NO se dibuja en el editor pero SÍ aparece en la imagen FINAL (el render del servidor
  // ignora `visible`, ver `dibujarDocumento(..., final:true)`). EXCEPCIÓN: en "Vista con muestra" el
  // HUECO DE FOTO (`es_foto`) oculto SÍ se pinta con la muestra, para diseñar viéndolo. Así el hueco
  // que nace oculto no ensucia el lienzo con su placeholder gris cuando la muestra está apagada.
  // OJO: SOLO el hueco `es_foto`, no cualquier imagen vacía: si no, una imagen vacía OCULTA de z alto
  // se forzaría a pintar y taparía el diseño (pleca/titular) con la muestra opaca al activarla.
  const esHuecoImg = capa.tipo === "imagen" && (capa as CapaImagen).es_foto === true;
  if (capa.visible === false && !(muestraFoto && esHuecoImg)) return null;

  switch (capa.tipo) {
    case "imagen": {
      const c = capa as CapaImagen;
      // "Vista con muestra": SOLO el hueco de foto (`es_foto`) se RELLENA con la muestra para ver
      // recorte/encuadre/forma/filtros/duotono/sombra. Solo visual; el dato sigue vacío. La imagen
      // real (objeto cargado) manda; la muestra es fallback. No se rellena cualquier imagen vacía:
      // una imagen vacía por encima del diseño taparía la pleca/titular con la muestra opaca.
      const esHueco = c.es_foto === true;
      const imgEfectiva = img ?? (muestraFoto && esHueco ? fotoMuestra(() => redibujar()) : null);
      if (!imgEfectiva) {
        return <Rect {...props} width={c.w} height={c.h} fill="#2a2d31" stroke="#4b5158" dash={[8, 8]} />;
      }
      const nodoImg = <NodoImagenAjustada img={imgEfectiva} w={c.w} h={c.h} ajuste={c.ajuste} foco={c.foco} zoom={c.zoom} filtros={c.filtros} forma={c.forma} radio={c.radio} radios={c.radios} crop={c.crop} flipH={c.flip_h} flipV={c.flip_v} props={props} />;
      // Realce de selección que SIGUE LA FORMA: el Transformer de Konva usa su bbox rect (sus
      // tiradores definen la caja), pero cuando la imagen NO es un rect simple el contorno azul
      // punteado debe cuadrar con su silueta. Solo visual (listening=false). Trazamos el mismo path
      // del catálogo (coords locales) con un Shape, posicionado/rotado como la capa.
      const formaRedonda = formaNoRect(c.forma, c.radio ?? 0, c.radios);
      const realceSel =
        seleccionada && interactivo && formaRedonda ? (
          <Shape
            x={c.x}
            y={c.y}
            rotation={c.rotacion}
            stroke="#3b82f6"
            strokeWidth={2}
            dash={[6, 4]}
            listening={false}
            sceneFunc={(ctx, shape) => {
              ctx.beginPath();
              pathFormaLocal(ctx, c.forma, c.w, c.h, c.radio ?? 0, c.radios);
              ctx.strokeShape(shape);
            }}
          />
        ) : null;
      // Sombra de la imagen: el Group de la imagen se recorta a su caja (la sombra no escaparía del
      // clip), así que la proyecta una silueta SIN listening dibujada detrás (igual que el render).
      // La silueta sigue la FORMA (mismo path del catálogo) para que la sombra cuadre con la foto.
      if (c.sombra) {
        return (
          <>
            <Shape
              x={c.x}
              y={c.y}
              rotation={c.rotacion}
              opacity={c.opacidad}
              fill="#000000"
              listening={false}
              shadowColor={c.sombra.color}
              shadowOffsetX={c.sombra.dx}
              shadowOffsetY={c.sombra.dy}
              shadowBlur={c.sombra.desenfoque ?? 0}
              shadowOpacity={c.sombra.opacidad ?? 1}
              shadowEnabled
              sceneFunc={(ctx, shape) => {
                ctx.beginPath();
                pathFormaLocal(ctx, c.forma, c.w, c.h, c.radio ?? 0, c.radios);
                ctx.fillShape(shape);
              }}
            />
            {nodoImg}
            {realceSel}
          </>
        );
      }
      if (realceSel) {
        return (
          <>
            {nodoImg}
            {realceSel}
          </>
        );
      }
      return nodoImg;
    }
    case "logo": {
      const c = capa as CapaLogo;
      if (c.tipo_logo === "imagen" && img) {
        // Logo: SIEMPRE encajar (contain) — nunca deformar.
        return <NodoImagenAjustada img={img} w={c.w} h={c.h} ajuste="contain" foco={[0.5, 0.5]} filtros={null} flipH={c.flip_h} flipV={c.flip_v} props={props} />;
      }
      // VOLTEO del wordmark: igual que la imagen, en un Group INTERIOR (no toca el scale del
      // Transformer). El motor (`aplicarFlip`) voltea `dibujarLogo` completo (también el wordmark)
      // alrededor del centro de la CAJA w×h (no del chip): mismos offsets que el export.
      const sx = c.flip_h ? -1 : 1;
      const sy = c.flip_v ? -1 : 1;
      const flipWm = sx !== 1 || sy !== 1
        ? { scaleX: sx, scaleY: sy, offsetX: sx === -1 ? c.w : 0, offsetY: sy === -1 ? c.h : 0 }
        : {};
      // WORDMARK: chip ceñido al TEXTO, espejo del export (`dibujarLogo`): fondo de
      // (anchoMedido + 2·20) × (tam + 2·12) SIN radio, anclado a la esquina sup-izq de la caja,
      // texto en (20,12) con baseline top y tam = round(0.42·h). La caja w×h es la capa (h
      // gobierna `tam` al redimensionar). Texto vacío => "LOGO" atenuado como ayuda de edición
      // (el export no pinta nada): divergencia consciente, señalada con la opacidad.
      const textoWm = (c.wordmark.texto || "").trim();
      const tamWm = Math.round(c.h * 0.42);
      const anchoWm = medirTexto(
        textoWm || "LOGO",
        `${c.wordmark.peso || 700} ${tamWm}px "${familiaReal(c.wordmark.familia)}"`,
      );
      return (
        <Group {...props}>
          <Group {...flipWm} opacity={textoWm ? 1 : 0.6}>
            <Rect width={anchoWm + 40} height={tamWm + 24} fill={c.wordmark.fondo} />
            <Text
              text={textoWm || "LOGO"}
              x={20}
              y={12}
              fontFamily={familiaReal(c.wordmark.familia)}
              fontSize={tamWm}
              // Peso numérico real, como el export (`dibujarLogo`: `${wm.peso || 700} …px`).
              fontStyle={String(c.wordmark.peso || 700)}
              fill={c.wordmark.color}
            />
          </Group>
        </Group>
      );
    }
    case "texto": {
      const c = capa as CapaTexto;
      // TEXTO CURVO (texto en arco): si la capa trae `curva.radio != 0`, lo aproximamos con un
      // `TextPath` de Konva sobre un arco SVG. El export del servidor (`dibujarTextoCurvo`) manda en
      // la pieza final; aquí solo damos una previa razonable (sin caja/valign/wrap en este modo).
      if (c.curva && c.curva.radio) {
        const ancla = c.alineacion === "centro" ? "center" : c.alineacion === "derecha" ? "right" : "left";
        return (
          <TextPath
            {...props}
            data={pathArco(c.curva.radio, c.w, ancla)}
            // Alineación SOBRE el path: sin ella Konva tiende el texto desde el INICIO del arco
            // (que abarca todo el ancho de la caja) y centro/derecha quedaban corridos respecto
            // al export (`dibujarTextoCurvo` ancla el texto MEDIDO a la vertical del ancla). El
            // path de "center" es simétrico a esa vertical y el de "right" termina en ella, así
            // center/right de Konva reproducen la regla del export. Justificado no existe en
            // arco: cae a izquierda, como el export.
            align={ancla}
            text={textoMuestra(c, muestraCopy)}
            fontFamily={familiaReal(c.familia)}
            fontSize={c.tamano}
            fontStyle={estiloFuente(c)}
            fill={c.color}
            letterSpacing={c.interletra || 0}
            stroke={c.contorno?.color}
            strokeWidth={c.contorno?.grosor ?? 0}
            fillAfterStrokeEnabled
            shadowColor={c.sombra?.color}
            shadowOffsetX={c.sombra?.dx}
            shadowOffsetY={c.sombra?.dy}
            shadowBlur={c.sombra?.desenfoque ?? 0}
            shadowOpacity={c.sombra?.opacidad ?? 1}
            shadowEnabled={!!c.sombra}
          />
        );
      }
      // En modo CAJA (h>0) respetamos el alto y la alineación vertical dentro de ella. El
      // auto-encogido de fuente NO se replica en Konva (la "vista real" la rinde el servidor con
      // dibujar.mjs); aquí basta con honrar caja + valign.
      const enCaja = c.h > 0;
      // Relleno: degradado (lineal o radial, multi-stop) o color sólido. Mismos puntos/paradas que
      // el render del servidor (`construirDegradado`).
      const gradTexto = c.relleno_degradado
        ? rellenoDegradadoKonva(c.relleno_degradado, c.w, enCaja ? c.h : c.tamano * c.interlineado)
        : null;
      const nodoTexto = (
        <Text
          {...(c.chip ? {} : props)}
          // El ref mide el bloque renderizado (y recibe el offsetY de ancla "abajo", ver efecto
          // arriba). Con chip, el nodo interactivo es el Group: el ref de medida va en el Text
          // interior y el del offset en el Group.
          ref={c.chip ? undefined : nodoTextoRef}
          text={textoMuestra(c, muestraCopy)}
          width={c.w}
          height={enCaja ? c.h : undefined}
          verticalAlign={enCaja ? (c.valign === "centro" ? "middle" : c.valign === "abajo" ? "bottom" : "top") : undefined}
          fontFamily={familiaReal(c.familia)}
          fontSize={c.tamano}
          fontStyle={estiloFuente(c)}
          // SUBRAYADO y TACHADO end-to-end: Konva pinta la línea bajo cada línea de texto
          // ("underline") y/o a media altura ("line-through", combinables); el export replica su
          // geometría exacta (`dibujarDecoracionLinea` en dibujar.mjs). El texto en arco
          // (TextPath, arriba) NO los recibe: el export tampoco los pinta (paridad previa==final).
          textDecoration={[c.subrayado ? "underline" : "", c.tachado ? "line-through" : ""].filter(Boolean).join(" ")}
          fill={gradTexto ? undefined : c.color}
          {...(gradTexto ?? {})}
          align={ALIN[c.alineacion] ?? "left"}
          lineHeight={c.interlineado}
          letterSpacing={c.interletra || 0}
          stroke={c.contorno?.color}
          strokeWidth={c.contorno?.grosor ?? 0}
          fillAfterStrokeEnabled
          shadowColor={c.sombra?.color}
          shadowOffsetX={c.sombra?.dx}
          shadowOffsetY={c.sombra?.dy}
          shadowBlur={c.sombra?.desenfoque ?? 0}
          shadowOpacity={c.sombra?.opacidad ?? 1}
          shadowEnabled={!!c.sombra}
        />
      );
      if (!c.chip) return nodoTexto;
      // CHIP/pleca: el servidor pinta un fondo por línea detrás del texto (`dibujarChipLinea`).
      // Aquí lo aproximamos a nivel de CAJA: un Rect detrás del texto con el padding (pad_x/pad_y)
      // y el radio del chip. Aproximación; el export del servidor manda en la pieza final.
      const padX = c.chip.pad_x ?? 24;
      const padY = c.chip.pad_y ?? 14;
      const altoTexto = enCaja ? c.h : c.tamano * c.interlineado;
      // Posición del chip dentro del Group (coordenadas relativas a la capa). Aproxima el ancho con
      // la caja de texto; el render real lo ajusta al ancho de cada línea.
      return (
        <Group {...props} ref={grupoChipRef}>
          <Rect
            x={-padX}
            y={-padY}
            width={c.w + padX * 2}
            height={altoTexto + padY * 2}
            fill={c.chip.color}
            cornerRadius={c.chip.radio || 0}
            listening={false}
          />
          {nodoTexto}
        </Group>
      );
    }
    case "marco": {
      const c = capa as CapaMarco;
      if (c.forma === "linea") {
        return (
          <Line
            {...props}
            points={[0, 0, c.w, c.h]}
            stroke={c.borde?.color ?? "#FFFFFF"}
            strokeWidth={c.borde?.grosor ?? 4}
          />
        );
      }
      // Relleno: degradado (lineal o radial, multi-stop) o color sólido. La sombra de la forma usa
      // los shadow* de Konva según `c.sombra`. Mismos puntos/paradas que `construirDegradado`.
      const rellenoMarco = c.relleno_degradado
        ? rellenoDegradadoKonva(c.relleno_degradado, c.w, c.h)
        : { fill: c.relleno ?? undefined };
      const sombraMarco = c.sombra
        ? {
            shadowColor: c.sombra.color,
            shadowOffsetX: c.sombra.dx,
            shadowOffsetY: c.sombra.dy,
            shadowBlur: c.sombra.desenfoque ?? 0,
            shadowOpacity: c.sombra.opacidad ?? 1,
            shadowEnabled: true,
          }
        : {};
      if (c.forma === "elipse") {
        // Konva posiciona la ELIPSE por su CENTRO (y el export rota la elipse alrededor del
        // centro, "igual que Konva": paridad de pivote, ver dibujarCapa). El modelo almacena la
        // esquina sup-izq, así que los writebacks son DEDICADOS y convierten centro -> esquina:
        // los genéricos guardarían el centro como x/y y la capa saltaría +w/2,+h/2 en cada gesto
        // (incluido el clic seco en un tirador, que burlaría la guarda de no-op al comparar el
        // centro del nodo con la esquina del modelo).
        const ex = c.x + c.w / 2;
        const ey = c.y + c.h / 2;
        return (
          <Ellipse
            {...props}
            x={ex}
            y={ey}
            radiusX={c.w / 2}
            radiusY={c.h / 2}
            onDragEnd={(e: Konva.KonvaEventObject<DragEvent>) => {
              onChange({ x: e.target.x() - c.w / 2, y: e.target.y() - c.h / 2 });
            }}
            onTransformEnd={(e: Konva.KonvaEventObject<Event>) => {
              const nodo = e.target;
              const sx = nodo.scaleX();
              const sy = nodo.scaleY();
              // Guarda de no-op del camino genérico, comparando contra el CENTRO del modelo.
              if (sx === 1 && sy === 1 && nodo.x() === ex && nodo.y() === ey && nodo.rotation() === c.rotacion) return;
              if (![sx, sy, nodo.x(), nodo.y(), nodo.rotation()].every(Number.isFinite)) return;
              nodo.scaleX(1);
              nodo.scaleY(1);
              const wN = Math.max(8, c.w * sx);
              const hN = Math.max(8, c.h * sy);
              // El centro es el punto FIJO en ambas representaciones (también con rotación):
              // esquina del modelo = centro - (w/2, h/2) SIN rotar.
              onChange({ x: nodo.x() - wN / 2, y: nodo.y() - hN / 2, w: wN, h: hN, rotacion: nodo.rotation() });
            }}
            {...rellenoMarco}
            {...sombraMarco}
            stroke={c.borde?.color}
            strokeWidth={c.borde?.grosor}
          />
        );
      }
      // Formas del catálogo (triángulo, rombo, polígonos, estrella, flecha): un Shape con sceneFunc
      // que traza el MISMO path que el render (coords locales). El degradado/sombra/borde se aplican
      // vía los props de Konva (fillLinearGradient*, shadow*, stroke*). El relleno/borde lo ejecuta
      // `fillStrokeShape`. Rect simple/redondeado mantiene el Rect nativo (cornerRadius).
      // width/height fijan el getSelfRect del Shape: el Transformer abraza la caja [0,w]×[0,h] de la
      // forma y aparecen sus tiradores (un Shape sin tamaño da bbox 0×0 y no se puede redimensionar).
      if (c.forma !== "rect") {
        return (
          <Shape
            {...props}
            width={c.w}
            height={c.h}
            {...rellenoMarco}
            {...sombraMarco}
            stroke={c.borde?.color}
            strokeWidth={c.borde?.grosor}
            sceneFunc={(ctx, shape) => {
              ctx.beginPath();
              pathFormaLocal(ctx, c.forma, c.w, c.h, c.radio ?? 0, c.radios);
              ctx.fillStrokeShape(shape);
            }}
          />
        );
      }
      return (
        <Rect
          {...props}
          width={c.w}
          height={c.h}
          cornerRadius={c.radios ?? c.radio}
          {...rellenoMarco}
          {...sombraMarco}
          stroke={c.borde?.color}
          strokeWidth={c.borde?.grosor}
        />
      );
    }
    case "overlay": {
      const c = capa as CapaOverlay;
      // Banda visible con la fórmula COMPARTIDA (floor incluido, espejo exacto del export).
      const band = bandaOverlay(c);
      // Rampa de legibilidad FIEL al servidor (`dibujarOverlayInferior`): ~11 paradas con la curva
      // t^1.5 sobre el alfa máximo (def 238/255). Separamos el RGB del posible alfa de 8 dígitos de
      // `c.color` (un `${c.color}00` lo corrompería) para componer cada parada como rgba(...).
      const m = /^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(c.color || "#111315");
      const rgb = m ? m[1] : "111315";
      const aHex = m && m[2] ? parseInt(m[2], 16) / 255 : 1;
      const r = parseInt(rgb.slice(0, 2), 16);
      const g = parseInt(rgb.slice(2, 4), 16);
      const b = parseInt(rgb.slice(4, 6), 16);
      const aMax = ((c.alpha ?? 238) / 255) * aHex;
      const stops: (number | string)[] = [];
      for (let i = 0; i <= 10; i++) {
        const t = i / 10;
        stops.push(t, `rgba(${r},${g},${b},${aMax * Math.pow(t, 1.5)})`);
      }
      // El nodo Konva es un GROUP en (c.x, c.y) — el ORIGEN DEL MODELO — con la banda como Rect
      // HIJO en coords locales (y = h - band, contrato del export: la y almacenada es el tope de
      // la CAJA y la banda vive pegada a su fondo). Con el Group, origen del nodo == origen del
      // modelo: onDragEnd/onTransformEnd y su guarda son correctos, el multi-arrastre vuelca
      // coords válidas y la ROTACIÓN pivota en (x,y) como el export.
      // ARRIBA: la banda se pega al tope (y local 0) y el gradiente se invierte (opaco en el borde
      // superior -> transparente hacia dentro); ABAJO (def): banda al fondo (y local h-band), opaco
      // abajo. Las paradas van transparente(0)->opaco(1), así que el punto OPACO es el borde pegado.
      const arriba = c.lado === "arriba";
      return (
        <Group {...props} listening={interactivo && !capa.bloqueada}>
          <Rect
            y={arriba ? 0 : c.h - band}
            width={c.w}
            height={band}
            fillLinearGradientStartPoint={arriba ? { x: 0, y: band } : { x: 0, y: 0 }}
            fillLinearGradientEndPoint={arriba ? { x: 0, y: 0 } : { x: 0, y: band }}
            fillLinearGradientColorStops={stops}
          />
        </Group>
      );
    }
    case "grupo": {
      // El grupo se arrastra como bloque: las hijas se pintan en coordenadas ABSOLUTAS (igual que
      // en el servidor) y el nodo Group vive en (0,0). Al soltar, se hornea el desplazamiento en
      // las coordenadas absolutas de cada hija (y en la bbox del grupo) y se resetea el nodo.
      const c = capa as CapaGrupo;
      const onDragEndGrupo = (e: Konva.KonvaEventObject<DragEvent>) => {
        const node = e.target;
        const dx = node.x();
        const dy = node.y();
        node.position({ x: 0, y: 0 });
        onChange({
          x: c.x + dx,
          y: c.y + dy,
          capas: c.capas.map((s) => ({ ...s, x: s.x + dx, y: s.y + dy })),
        } as Partial<Capa>);
      };
      return (
        <Group
          id={c.id}
          x={0}
          y={0}
          opacity={c.opacidad}
          globalCompositeOperation={(MAPA_MEZCLA[c.mezcla ?? "normal"] ?? "source-over") as GlobalCompositeOperation}
          draggable={!c.bloqueada}
          onMouseDown={onSelect}
          onTap={onSelect}
          onDragStart={onGesto}
          onDragEnd={onDragEndGrupo}
        >
          {c.capas.map((sub) => (
            <CapaNodo key={sub.id} capa={sub} seleccionada={false} onSelect={onSelect} onChange={() => {}} onGesto={onGesto} interactivo={false} />
          ))}
        </Group>
      );
    }
    default:
      return null;
  }
}
