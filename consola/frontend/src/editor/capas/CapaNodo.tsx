// Render interactivo de UNA capa como nodo Konva. Es el "proxy" editable del lienzo: el archivo
// final lo hornea el servidor con `dibujarDocumento` (fidelidad exacta de fuentes/cover/degradados).
// Aquí priorizamos manipulación directa (seleccionar, arrastrar, escalar, rotar).

import Konva from "konva";
import { useEffect, useReducer, useRef } from "react";
import { Ellipse, Group, Image as KonvaImage, Line, Rect, Shape, Text, TextPath } from "react-konva";

import { MAPA_MEZCLA } from "../../lib/placa/dibujar.mjs";
import type { Capa, CapaGrupo, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto, Forma, RellenoDegradado } from "../documento";
import { copyMuestra, fotoMuestra } from "../muestra";
import { useImagen } from "../useImagen";

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
}

const ALIN: Record<string, string> = {
  izquierda: "left",
  centro: "center",
  derecha: "right",
  justificado: "justify",
};

// Puntos inicial/final de un degradado lineal sobre una caja w×h según `angulo` (grados), con la
// MISMA convención que `gradienteLineal` de dibujar.mjs: 0°=↑, 90°=→, 180°=↓ (vertical), 270°=←.
// Konva usa puntos relativos al nodo (origen 0,0), así que el centro de la caja es (w/2,h/2).
export function puntosGradiente(w: number, h: number, angulo = 180) {
  const a = (angulo * Math.PI) / 180;
  const ux = Math.sin(a), uy = -Math.cos(a);
  const cx = w / 2, cy = h / 2;
  const semi = (Math.abs(w * ux) + Math.abs(h * uy)) / 2;
  return {
    start: { x: cx - ux * semi, y: cy - uy * semi },
    end: { x: cx + ux * semi, y: cy + uy * semi },
  };
}

// Paradas [pos, color, pos, color, …] de un degradado para Konva (`fill*GradientColorStops`).
// Usa `stops` (multi-parada) si viene, si no desde/hasta (espejo de `paradasDegradado` del render).
function colorStopsKonva(deg: RellenoDegradado): (number | string)[] {
  if (deg.stops && deg.stops.length >= 2) {
    return [...deg.stops]
      .map((s) => ({ pos: Math.max(0, Math.min(1, s.pos || 0)), color: s.color }))
      .sort((a, b) => a.pos - b.pos)
      .flatMap((s) => [s.pos, s.color]);
  }
  return [0, deg.desde, 1, deg.hasta];
}

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

// Resuelve las familias LÓGICAS del documento ("sans"/"condensada") a fuentes reales, para que
// el editor (Konva) pinte con la MISMA tipografía que el export del servidor (Barlow / Barlow
// Condensed por defecto). Cualquier otra familia (nombre real) se pasa tal cual.
function familiaReal(familia: string | undefined): string {
  if (familia === "sans") return "Barlow";
  if (familia === "condensada") return "Barlow Condensed";
  return familia || "Barlow";
}

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  props: any;
}) {
  const ref = useRef<Konva.Image | null>(null);
  // Imagen EFECTIVA = sub-rect fuente recortado (crop, fracciones 0..1 -> px). El cover/contain y el
  // `crop` de Konva (px de la imagen) se calculan sobre ese sub-rect. Espejo de `rectFuente`.
  const iwTotal = img.width || 1;
  const ihTotal = img.height || 1;
  const cx = crop ? Math.max(0, Math.min(1, crop.cx)) : 0;
  const cy = crop ? Math.max(0, Math.min(1, crop.cy)) : 0;
  const cw = crop ? Math.max(0, Math.min(1 - cx, crop.cw)) : 1;
  const ch = crop ? Math.max(0, Math.min(1 - cy, crop.ch)) : 1;
  const usaCrop = crop != null && cw > 0 && ch > 0 && (cx > 0 || cy > 0 || cw < 1 || ch < 1);
  const iw = usaCrop ? cw * iwTotal : iwTotal;
  const ih = usaCrop ? ch * ihTotal : ihTotal;
  const base = ajuste === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const escala = base * (zoom > 0 ? zoom : 1);
  const dw = iw * escala;
  const dh = ih * escala;
  const ix = (w - dw) * (foco[0] ?? 0.5);
  const iy = (h - dh) * (foco[1] ?? 0.5);
  const cropPx = usaCrop
    ? { crop: { x: cx * iwTotal, y: cy * ihTotal, width: cw * iwTotal, height: ch * ihTotal } }
    : {};

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
  }, [filtros, dw, dh, img]);

  // Recorte de la caja según la forma (espejo del clip de `dibujarImagenEnCaja`): catálogo completo
  // de formas (elipse, polígonos, estrella, flecha…) o rect simple/redondeado. Para "rect" sin
  // radio usamos clipX/Y/W/H (camino rápido idéntico al de antes).
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
  return (
    <Group {...props} {...recorte}>
      {/* Zona sensible al puntero del tamaño de la caja: la imagen interior va con listening=false,
          así que sin este Rect el Group no recibiría clic/arrastre (no se podían mover las fotos).
          opacity 0 = invisible en escena pero presente en el hit graph de Konva. */}
      <Rect x={0} y={0} width={w} height={h} fill="#000000" opacity={0} />
      <KonvaImage ref={ref} image={img} x={ix} y={iy} width={dw} height={dh} listening={false} {...cropPx} />
      {duo && (
        <>
          <Rect x={0} y={0} width={w} height={h} fill={duo.luz} globalCompositeOperation="multiply" listening={false} />
          <Rect x={0} y={0} width={w} height={h} fill={duo.sombra} globalCompositeOperation="lighten" listening={false} />
        </>
      )}
    </Group>
  );
}

function textoMuestra(c: CapaTexto, muestraCopy = false): string {
  // En "Vista con muestra (copy)" los bindings usan copy de ejemplo (titular largo, pleca "EN VIVO"
  // por defecto, o el que el equipo edite) para ver saltos de línea y auto-encogido — aunque la capa
  // ya tenga `texto`. Fuera de ese modo, comportamiento de hoy: respeta `texto` y cae a un
  // placeholder genérico si está vacío.
  const ejemplo = muestraCopy ? copyMuestra(c.binding) : null;
  const base = ejemplo
    ? ejemplo
    : c.binding === "copy_in"
      ? c.texto || "Titular de ejemplo"
      : c.binding === "etiqueta_default"
        ? c.texto || "PLECA"
        : c.texto;
  return c.mayusculas ? base.toUpperCase() : base;
}

export function CapaNodo({ capa, seleccionada, onSelect, onChange, onGesto, interactivo = true, muestraFoto = false, muestraCopy = false }: CapaNodoProps) {
  // Hook SIEMPRE llamado (regla de hooks); null para capas sin imagen.
  const objetoImg = capa.tipo === "imagen" ? capa.objeto : capa.tipo === "logo" ? capa.media_id : null;
  const img = useImagen(objetoImg);
  // Fuerza un redibujo del lienzo cuando la foto de muestra (generada async en cliente) ya está
  // lista, para que el hueco la pinte sin esperar a otra interacción.
  const [, redibujar] = useReducer((n: number) => n + 1, 0);

  const comun = {
    id: capa.id,
    x: capa.x,
    y: capa.y,
    rotation: capa.rotacion,
    opacity: capa.opacidad,
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
            onChange({ x: e.target.x(), y: e.target.y() });
          },
        }
      : {}),
  };

  // Transform genérico: convierte escala -> w/h (y tamaño de fuente en textos), resetea escala.
  const onTransformEnd = (e: Konva.KonvaEventObject<Event>) => {
    const nodo = e.target;
    const sx = nodo.scaleX();
    const sy = nodo.scaleY();
    nodo.scaleX(1);
    nodo.scaleY(1);
    const base: Partial<Capa> = {
      x: nodo.x(),
      y: nodo.y(),
      rotacion: nodo.rotation(),
    } as Partial<Capa>;
    if (capa.tipo === "texto") {
      // "La caja es inamovible, que encoja el texto": al redimensionar una capa de texto
      // dibujamos la CAJA (ancho Y alto). El texto se auto-encoge en el render para caber; NO
      // crecemos el tamaño de fuente con la escala vertical. Persistimos `h` (no solo `w`), lo que
      // activa el modo caja (h>0) para esta capa.
      onChange({
        ...base,
        w: Math.max(16, capa.w * sx),
        h: Math.max(16, capa.h > 0 ? capa.h * sy : (capa as CapaTexto).tamano * (capa as CapaTexto).interlineado * sy),
      } as Partial<Capa>);
    } else {
      onChange({
        ...base,
        w: Math.max(8, capa.w * sx),
        h: Math.max(8, capa.h * sy),
      } as Partial<Capa>);
    }
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
      const nodoImg = <NodoImagenAjustada img={imgEfectiva} w={c.w} h={c.h} ajuste={c.ajuste} foco={c.foco} zoom={c.zoom} filtros={c.filtros} forma={c.forma} radio={c.radio} radios={c.radios} crop={c.crop} props={props} />;
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
        return <NodoImagenAjustada img={img} w={c.w} h={c.h} ajuste="contain" foco={[0.5, 0.5]} filtros={null} props={props} />;
      }
      return (
        <Group {...props}>
          <Rect width={c.w} height={c.h} fill={c.wordmark.fondo} cornerRadius={6} />
          <Text
            text={c.wordmark.texto || "LOGO"}
            width={c.w}
            height={c.h}
            align="center"
            verticalAlign="middle"
            fontFamily={familiaReal(c.wordmark.familia)}
            fontSize={Math.round(c.h * 0.42)}
            fontStyle={c.wordmark.peso >= 600 ? "bold" : "normal"}
            fill={c.wordmark.color}
          />
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
            text={textoMuestra(c, muestraCopy)}
            fontFamily={familiaReal(c.familia)}
            fontSize={c.tamano}
            fontStyle={c.peso >= 600 ? "bold" : "normal"}
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
          text={textoMuestra(c, muestraCopy)}
          width={c.w}
          height={enCaja ? c.h : undefined}
          verticalAlign={enCaja ? (c.valign === "centro" ? "middle" : c.valign === "abajo" ? "bottom" : "top") : undefined}
          fontFamily={familiaReal(c.familia)}
          fontSize={c.tamano}
          fontStyle={c.peso >= 600 ? "bold" : "normal"}
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
        <Group {...props}>
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
        return (
          <Ellipse
            {...props}
            x={c.x + c.w / 2}
            y={c.y + c.h / 2}
            radiusX={c.w / 2}
            radiusY={c.h / 2}
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
      if (c.forma !== "rect") {
        return (
          <Shape
            {...props}
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
      const band = Math.max(1, c.h * c.alto_frac);
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
      return (
        <Rect
          {...props}
          y={c.y + c.h - band}
          width={c.w}
          height={band}
          listening={!capa.bloqueada}
          fillLinearGradientStartPoint={{ x: 0, y: 0 }}
          fillLinearGradientEndPoint={{ x: 0, y: band }}
          fillLinearGradientColorStops={stops}
        />
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
