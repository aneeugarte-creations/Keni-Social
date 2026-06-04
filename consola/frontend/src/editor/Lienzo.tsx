// Lienzo Konva del editor: fondo + capas (por z), con selección, arrastre con SMART GUIDES,
// Transformer con aspect-ratio (imágenes/logos), zoom (+/−/ajustar, ctrl+rueda, pinch), barra de
// acciones FLOTANTE sobre la capa seleccionada (alinear/orden/duplicar/borrar), edición de texto
// EN LÍNEA (doble clic) y atajos de teclado. Táctil de serie (Konva). El estado vive en el store.

import Konva from "konva";
import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignVerticalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  BringToFront,
  Check,
  Copy,
  Crop as CropIcon,
  Frame,
  Grid3x3,
  Magnet,
  Maximize,
  Minus,
  Move,
  Plus,
  SendToBack,
  Trash2,
} from "lucide-react";
import {
  type DragEvent as DragEventReact,
  type PointerEvent as PointerEventReact,
  type WheelEvent as WheelEventReact,
  useEffect,
  useRef,
  useState,
} from "react";
import { Layer, Line, Rect, Stage, Transformer } from "react-konva";

import { CapaNodo, puntosGradiente } from "./capas/CapaNodo";
import type { Capa, CapaImagen, CapaTexto, Crop, Documento } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo } from "./documento";
import { aplicarEstilo } from "./estilo";
import { copiarEstiloPortapapeles, estiloPortapapeles } from "./estilos-guardados";
import { type AsaRecorte, moverAsa } from "./recorte";
import type { StoreEditor } from "./store";
import { useEditor, useStoreEditor } from "./usarEditor";
import { useImagen } from "./useImagen";

const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);
const ZOOM_MIN = 0.2;
const ZOOM_MAX = 4;

// Portapapeles de capas (módulo, para copiar/pegar incluso entre pestañas del workspace). Guarda
// TODA la selección múltiple, no solo la capa primaria.
let _portapapeles: Capa[] = [];

// Tamaños de celda de la rejilla ofrecidos en los controles (px del documento). "Fina" por defecto.
const CELDAS: { px: number; etiqueta: string }[] = [
  { px: 8, etiqueta: "8" },
  { px: 16, etiqueta: "16" },
  { px: 24, etiqueta: "24" },
  { px: 32, etiqueta: "32" },
  { px: 48, etiqueta: "48" },
];

// Preferencias de los toggles de encuadre (imán/rejilla/tamaño/dentro-del-marco) en localStorage.
// Tolerante: si no hay localStorage o el valor es inválido, cae al default.
function prefBool(clave: string, def: boolean): boolean {
  try {
    const v = localStorage.getItem(clave);
    return v === null ? def : v === "1";
  } catch {
    return def;
  }
}
function prefNum(clave: string, def: number): number {
  try {
    const v = localStorage.getItem(clave);
    const n = v === null ? NaN : Number(v);
    return Number.isFinite(n) ? n : def;
  } catch {
    return def;
  }
}
function guardarPref(clave: string, valor: boolean | number): void {
  try {
    localStorage.setItem(clave, typeof valor === "boolean" ? (valor ? "1" : "0") : String(valor));
  } catch {
    /* almacenamiento no disponible: las preferencias no se persisten, sin romper. */
  }
}

// Acota una posición de un eje para que la caja [pos, pos+tam] quede dentro de [0, total]. Si la
// caja es MAYOR que el lienzo (tam > total) no se fuerzan negativos absurdos: se permite el rango
// [total - tam, 0] (la capa puede sobresalir por igual a ambos lados, centrable a mano).
function clampMarco(pos: number, tam: number, total: number): number {
  const min = Math.min(0, total - tam);
  const max = Math.max(0, total - tam);
  return Math.max(min, Math.min(max, pos));
}

function FondoNodo({ fondo, w, h }: { fondo: Documento["fondo"]; w: number; h: number }) {
  const img = useImagen(fondo.tipo === "imagen" ? fondo.imagen?.media_id : null);
  if (fondo.tipo === "color") return <Rect x={0} y={0} width={w} height={h} fill={fondo.color} listening={false} />;
  if (fondo.tipo === "degradado" && fondo.degradado) {
    // Soporta lineal/radial y multi-stop (mismo helper/convención que el render y las capas):
    // default lineal 180 = vertical (↓), sin cambio visual respecto al comportamiento previo.
    const deg = fondo.degradado;
    const stops: (number | string)[] =
      deg.stops && deg.stops.length >= 2
        ? [...deg.stops]
            .map((s) => ({ pos: Math.max(0, Math.min(1, s.pos || 0)), color: s.color }))
            .sort((a, b) => a.pos - b.pos)
            .flatMap((s) => [s.pos, s.color])
        : [0, deg.desde, 1, deg.hasta];
    if (deg.tipo === "radial") {
      const r = Math.sqrt(w * w + h * h) / 2;
      return (
        <Rect
          x={0} y={0} width={w} height={h} listening={false}
          fillRadialGradientStartPoint={{ x: w / 2, y: h / 2 }}
          fillRadialGradientEndPoint={{ x: w / 2, y: h / 2 }}
          fillRadialGradientStartRadius={0}
          fillRadialGradientEndRadius={r}
          fillRadialGradientColorStops={stops}
        />
      );
    }
    const g = puntosGradiente(w, h, deg.angulo);
    return (
      <Rect
        x={0} y={0} width={w} height={h} listening={false}
        fillLinearGradientStartPoint={g.start}
        fillLinearGradientEndPoint={g.end}
        fillLinearGradientColorStops={stops}
      />
    );
  }
  if (fondo.tipo === "imagen" && img) {
    return <Rect x={0} y={0} width={w} height={h} listening={false} fillPatternImage={img} fillPatternScale={{ x: w / img.width, y: h / img.height }} />;
  }
  return <Rect x={0} y={0} width={w} height={h} fill="#111315" listening={false} />;
}

// Capa HTML transparente sobre la imagen en reencuadre. Arrastrar mueve el FOCO (qué parte de la
// foto se ve en el marco) y la rueda ajusta el ZOOM. Todo el gesto cuenta como un paso de
// deshacer. El mapeo de arrastre es "una anchura de marco = recorrido completo del foco": natural
// y acotado (arrastrar a la derecha muestra más del lado izquierdo).
function ReframeOverlay({
  capa,
  escala,
  store,
}: {
  capa: CapaImagen;
  escala: number;
  store: StoreEditor;
}) {
  const drag = useRef<{ fx: number; fy: number; px: number; py: number } | null>(null);
  const gestoActivo = useRef(false);
  const finZoom = useRef<number | undefined>(undefined);

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id) as CapaImagen | undefined;

  const onPointerDown = (e: PointerEventReact) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c) return;
    drag.current = { fx: c.foco[0] ?? 0.5, fy: c.foco[1] ?? 0.5, px: e.clientX, py: e.clientY };
  };
  const onPointerMove = (e: PointerEventReact) => {
    if (!drag.current) return;
    const dx = (e.clientX - drag.current.px) / (capa.w * escala);
    const dy = (e.clientY - drag.current.py) / (capa.h * escala);
    const fx = Math.max(0, Math.min(1, drag.current.fx - dx));
    const fy = Math.max(0, Math.min(1, drag.current.fy - dy));
    store.getState().actualizar(capa.id, { foco: [fx, fy] } as Partial<Capa>, false);
  };
  const onPointerUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };
  const onWheel = (e: WheelEventReact) => {
    e.preventDefault();
    comenzar();
    const c = actual();
    if (!c) return;
    const z = Math.max(1, Math.min(6, (c.zoom || 1) * (e.deltaY < 0 ? 1.06 : 0.94)));
    store.getState().actualizar(capa.id, { zoom: z } as Partial<Capa>, false);
    // Cierra el gesto (un paso de deshacer) tras una ráfaga de rueda.
    window.clearTimeout(finZoom.current);
    finZoom.current = window.setTimeout(() => { gestoActivo.current = false; }, 350);
  };

  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      className="absolute cursor-move touch-none ring-2 ring-primary"
      style={{ left: capa.x * escala, top: capa.y * escala, width: capa.w * escala, height: capa.h * escala }}
    />
  );
}

// Capa HTML sobre la imagen en MODO RECORTE (crop visual). Muestra la imagen COMPLETA dentro de la
// caja (object-contain), atenúa lo que queda FUERA del recorte y dibuja un rectángulo con 8
// tiradores (4 esquinas + 4 lados) + área central para mover. Arrastrar actualiza `capa.crop` en
// fracciones 0..1 de la FUENTE (= fracciones de la imagen mostrada, que se ve entera). Todo el
// gesto cuenta como UN paso de deshacer (como el reencuadre).
function CropOverlay({
  capa,
  escala,
  store,
}: {
  capa: CapaImagen;
  escala: number;
  store: StoreEditor;
}) {
  const img = useImagen(capa.objeto || null);
  const drag = useRef<{ asa: AsaRecorte; crop: Crop; px: number; py: number } | null>(null);
  const gestoActivo = useRef(false);

  const W = capa.w * escala;
  const H = capa.h * escala;
  // La imagen completa se muestra con `contain` dentro de la caja: rect mostrado (letterbox) en px.
  let imgW = W, imgH = H, imgL = 0, imgT = 0;
  if (img && img.width > 0 && img.height > 0) {
    const k = Math.min(W / img.width, H / img.height);
    imgW = img.width * k;
    imgH = img.height * k;
    imgL = (W - imgW) / 2;
    imgT = (H - imgH) / 2;
  }
  const crop: Crop = capa.crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 };
  // Rectángulo de recorte en px DENTRO de la imagen mostrada.
  const rx = imgL + crop.cx * imgW;
  const ry = imgT + crop.cy * imgH;
  const rw = crop.cw * imgW;
  const rh = crop.ch * imgH;

  const comenzar = () => {
    if (!gestoActivo.current) {
      store.getState().comenzarGesto();
      gestoActivo.current = true;
    }
  };
  const actual = () => store.getState().documento.capas.find((c) => c.id === capa.id) as CapaImagen | undefined;

  const onDown = (asa: AsaRecorte) => (e: PointerEventReact) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    comenzar();
    const c = actual();
    if (!c) return;
    drag.current = { asa, crop: c.crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 }, px: e.clientX, py: e.clientY };
  };
  const onMove = (e: PointerEventReact) => {
    if (!drag.current || imgW <= 0 || imgH <= 0) return;
    const dfx = (e.clientX - drag.current.px) / imgW;
    const dfy = (e.clientY - drag.current.py) / imgH;
    const next = moverAsa(drag.current.crop, drag.current.asa, dfx, dfy);
    store.getState().actualizar(capa.id, { crop: next } as Partial<Capa>, false);
  };
  const onUp = () => {
    drag.current = null;
    gestoActivo.current = false;
  };

  // Definición de los 8 tiradores: posición (en px relativos a la caja) y cursor.
  const asas: { asa: AsaRecorte; x: number; y: number; cursor: string }[] = [
    { asa: "nw", x: rx, y: ry, cursor: "nwse-resize" },
    { asa: "n", x: rx + rw / 2, y: ry, cursor: "ns-resize" },
    { asa: "ne", x: rx + rw, y: ry, cursor: "nesw-resize" },
    { asa: "e", x: rx + rw, y: ry + rh / 2, cursor: "ew-resize" },
    { asa: "se", x: rx + rw, y: ry + rh, cursor: "nwse-resize" },
    { asa: "s", x: rx + rw / 2, y: ry + rh, cursor: "ns-resize" },
    { asa: "sw", x: rx, y: ry + rh, cursor: "nesw-resize" },
    { asa: "w", x: rx, y: ry + rh / 2, cursor: "ew-resize" },
  ];

  return (
    <div
      onPointerMove={onMove}
      onPointerUp={onUp}
      className="absolute touch-none"
      style={{ left: capa.x * escala, top: capa.y * escala, width: W, height: H }}
    >
      {/* Imagen COMPLETA (sin recortar) de referencia. */}
      {img && (
        <img
          src={img.src}
          alt=""
          draggable={false}
          className="pointer-events-none absolute select-none"
          style={{ left: imgL, top: imgT, width: imgW, height: imgH }}
        />
      )}
      {/* Atenuación del exterior del recorte: 4 bandas translúcidas (arriba/abajo/izq/der). */}
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: 0, width: W, height: Math.max(0, ry) }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: ry + rh, width: W, height: Math.max(0, H - (ry + rh)) }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: 0, top: ry, width: Math.max(0, rx), height: rh }} />
      <div className="pointer-events-none absolute bg-black/55" style={{ left: rx + rw, top: ry, width: Math.max(0, W - (rx + rw)), height: rh }} />
      {/* Rectángulo de recorte: marco + área de arrastre (mover todo). */}
      <div
        onPointerDown={onDown("mover")}
        className="absolute cursor-move ring-2 ring-primary"
        style={{ left: rx, top: ry, width: rw, height: rh }}
      />
      {/* Tiradores. */}
      {asas.map((a) => (
        <div
          key={a.asa}
          onPointerDown={onDown(a.asa)}
          className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-primary bg-background shadow"
          style={{ left: a.x, top: a.y, cursor: a.cursor }}
        />
      ))}
    </div>
  );
}

export function Lienzo({
  maxAncho = 620,
  maxAlto = 760,
  reencuadreId = null,
  onSalirReencuadre,
  recorteId = null,
  onSalirRecorte,
  onStage,
}: {
  maxAncho?: number;
  maxAlto?: number;
  reencuadreId?: string | null;
  onSalirReencuadre?: () => void;
  // Capa imagen en MODO RECORTE visual (crop con tiradores). Mutuamente excluyente con reencuadre.
  recorteId?: string | null;
  onSalirRecorte?: () => void;
  // Expone el Stage de Konva + la escala actual al padre (para muestrear píxeles, p.ej. legibilidad).
  onStage?: (stage: Konva.Stage | null, escala: number) => void;
}) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const { w, h } = documento.formato;
  // Capa en modo reencuadre (solo imágenes): arrastrar mueve el FOCO, la rueda hace ZOOM.
  const capaReencuadre = reencuadreId ? documento.capas.find((c) => c.id === reencuadreId && c.tipo === "imagen") ?? null : null;
  // Capa en modo RECORTE visual (solo imágenes): tiradores que editan `crop`. Excluyente con reencuadre.
  const capaRecorte = recorteId ? documento.capas.find((c) => c.id === recorteId && c.tipo === "imagen") ?? null : null;
  // Cualquier modo de edición de imagen oculta los tiradores normales del Transformer.
  const modoImagen = capaReencuadre ?? capaRecorte;

  // Mide el espacio disponible para AJUSTAR el lienzo (responsive: llena el ancho en móvil y el
  // centro en escritorio). Cae a las props si aún no se ha medido.
  const medirRef = useRef<HTMLDivElement | null>(null);
  const [disp, setDisp] = useState<{ w: number; h: number }>({ w: maxAncho, h: maxAlto });
  useEffect(() => {
    const el = medirRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setDisp({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const baseFit = Math.min(disp.w / w, disp.h / h, 1);

  const [zoom, setZoom] = useState(1);
  const escala = baseFit * zoom;
  // ENCUADRE — controles independientes (preferencias persistidas en localStorage):
  //   · imán: ajuste magnético a objetos + bordes/centro del lienzo + márgenes. Por defecto ON
  //     (antes estaba siempre activo). Apagado => sin snap a objetos/márgenes.
  //   · grid: rejilla visual + snap a línea de rejilla POR UMBRAL (no redondeo duro; entre líneas
  //     el movimiento es libre). El imán tiene PRIORIDAD sobre la rejilla.
  //   · tamCelda: tamaño de celda de la rejilla en px del documento (fina/media/gruesa).
  //   · dentroMarco: al mover/transformar, acota la caja para que no se salga del lienzo.
  const [iman, setIman] = useState(() => prefBool("keni.encuadre.iman", true));
  const [grid, setGrid] = useState(() => prefBool("keni.encuadre.grid", false));
  const [tamCelda, setTamCelda] = useState(() => prefNum("keni.encuadre.celda", 16));
  const [dentroMarco, setDentroMarco] = useState(() => prefBool("keni.encuadre.dentro", false));
  useEffect(() => guardarPref("keni.encuadre.iman", iman), [iman]);
  useEffect(() => guardarPref("keni.encuadre.grid", grid), [grid]);
  useEffect(() => guardarPref("keni.encuadre.celda", tamCelda), [tamCelda]);
  useEffect(() => guardarPref("keni.encuadre.dentro", dentroMarco), [dentroMarco]);
  // Paso de la rejilla: tamaño de celda configurable (mín. 4px), no w/12.
  const paso = Math.max(4, Math.round(tamCelda));
  // Márgenes (encuadre) del formato: lados con default 0 (retrocompat con formatos sin laterales).
  const safeTop = documento.formato.safe_top || 0;
  const safeBottom = documento.formato.safe_bottom || 0;
  const safeLeft = documento.formato.safe_left || 0;
  const safeRight = documento.formato.safe_right || 0;
  const hayMargenes = safeTop > 0 || safeBottom > 0 || safeLeft > 0 || safeRight > 0;

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  // Publica el Stage + la escala al padre cuando cambian (para muestreo de píxeles externo).
  useEffect(() => {
    onStage?.(stageRef.current, escala);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escala, documento, onStage]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Arrastre múltiple: posiciones iniciales de todas las capas seleccionadas al empezar a mover.
  const multiDrag = useRef<{ dragId: string; ini: Map<string, { x: number; y: number }> } | null>(null);
  const [guias, setGuias] = useState<{ x: number | null; y: number | null }>({ x: null, y: null });
  const [arrastrando, setArrastrando] = useState(false);
  const [rectSel, setRectSel] = useState<{ x: number; y: number; w: number } | null>(null);
  const [editando, setEditando] = useState<{ id: string; x: number; y: number; w: number; fontPx: number } | null>(null);
  const [textoEdit, setTextoEdit] = useState("");

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const capaSel = documento.capas.find((c) => c.id === seleccion) ?? null;
  const ratioFijo = capaSel ? RATIO_FIJO.has(capaSel.tipo) : false;
  // El grupo solo se mueve (resize/rotación se hacen desagrupando).
  const esGrupo = capaSel?.tipo === "grupo";

  // Las webfonts (catálogo + tipografías de marca) cargan async; Konva pinta con la fuente
  // disponible en ese instante. Redibuja cuando el navegador termina de cargar fuentes para que
  // el texto deje de caer a la fuente de respaldo.
  useEffect(() => {
    if (typeof document === "undefined" || !("fonts" in document)) return;
    const redibujar = () => stageRef.current?.getLayers().forEach((l) => l.batchDraw());
    document.fonts.ready.then(redibujar);
    document.fonts.addEventListener?.("loadingdone", redibujar);
    return () => document.fonts.removeEventListener?.("loadingdone", redibujar);
  }, []);

  // Adjunta el Transformer a TODAS las capas seleccionadas.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    // En reencuadre/recorte se ocultan los tiradores (la interacción es propia del modo).
    const nodos = modoImagen
      ? []
      : seleccionMulti
          .map((id) => stage.findOne<Konva.Node>(`#${id}`))
          .filter((n): n is Konva.Node => !!n);
    tr.nodes(nodos);
    tr.getLayer()?.batchDraw();
  }, [seleccionMulti, documento, zoom, modoImagen]);

  // Rect en pantalla que ENVUELVE la selección (para la barra flotante). Unión de las capas
  // seleccionadas; recalcula al cambiar selección/documento/zoom.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || seleccionMulti.length === 0) {
      setRectSel(null);
      return;
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity;
    for (const id of seleccionMulti) {
      const nodo = stage.findOne<Konva.Node>(`#${id}`);
      if (!nodo) continue;
      const r = nodo.getClientRect();
      minX = Math.min(minX, r.x);
      minY = Math.min(minY, r.y);
      maxX = Math.max(maxX, r.x + r.width);
    }
    if (minX === Infinity) {
      setRectSel(null);
      return;
    }
    setRectSel({ x: minX, y: minY, w: maxX - minX });
  }, [seleccionMulti, documento, zoom]);

  // Atajos de teclado (ignora si se está escribiendo en un input/textarea).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      // No dispares atajos si el foco está en un campo editable o un <select> (con un select
      // enfocado, las flechas cambian la opción y Backspace no debe borrar la capa).
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable || t.closest("[contenteditable]"))) return;
      const st = store.getState();
      const sel = st.seleccion;
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) st.rehacer();
        else st.deshacer();
        return;
      }
      // Zoom: ⌘0 ajusta a pantalla (escala = baseFit => zoom 1), ⌘+ acerca, ⌘− aleja.
      if (meta && e.key === "0") { e.preventDefault(); return setZoom(1); }
      if (meta && (e.key === "+" || e.key === "=")) {
        e.preventDefault();
        return setZoom((z) => Math.min(ZOOM_MAX, z * 1.1));
      }
      if (meta && (e.key === "-" || e.key === "_")) {
        e.preventDefault();
        return setZoom((z) => Math.max(ZOOM_MIN, z * 0.9));
      }
      if (e.key === "Escape") {
        if (recorteId) return onSalirRecorte?.();
        if (reencuadreId) return onSalirReencuadre?.();
        return st.seleccionar(null);
      }
      // Copiar/pegar ESTILO (⌘⌥C / ⌘⌥V): subconjunto de estilo de la capa, no la capa entera.
      // Va ANTES de ⌘C/⌘V (que copian capas) porque añade Alt.
      if (meta && e.altKey && (e.key === "c" || e.key === "C" || e.code === "KeyC")) {
        e.preventDefault();
        const capa = st.documento.capas.find((c) => c.id === st.seleccion);
        if (capa) copiarEstiloPortapapeles(capa);
        return;
      }
      if (meta && e.altKey && (e.key === "v" || e.key === "V" || e.code === "KeyV")) {
        e.preventDefault();
        const estilo = estiloPortapapeles();
        if (!estilo) return;
        const ids = st.seleccionMulti.length ? st.seleccionMulti : st.seleccion ? [st.seleccion] : [];
        const objetivos = st.documento.capas.filter((c) => ids.includes(c.id));
        if (!objetivos.length) return;
        st.comenzarGesto();
        for (const c of objetivos) {
          const cambios = aplicarEstilo(c, estilo);
          if (Object.keys(cambios).length) st.actualizar(c.id, cambios, false);
        }
        return;
      }
      if (meta && (e.key === "a" || e.key === "A")) {
        e.preventDefault();
        return st.seleccionarMuchas(st.documento.capas.map((c) => c.id));
      }
      if (meta && (e.key === "g" || e.key === "G")) {
        e.preventDefault();
        if (e.shiftKey) {
          const c = st.documento.capas.find((x) => x.id === st.seleccion);
          if (c?.tipo === "grupo") st.desagrupar(c.id);
        } else {
          st.agrupar();
        }
        return;
      }
      if (!sel) return;
      const capa = st.documento.capas.find((c) => c.id === sel);
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); return st.quitarMulti(); }
      if (meta && (e.key === "c" || e.key === "C")) {
        // Copia TODA la selección múltiple (alineado con ⌘D duplicarMulti), no solo la primaria.
        const ids = st.seleccionMulti.length ? st.seleccionMulti : sel ? [sel] : [];
        const capas = st.documento.capas.filter((c) => ids.includes(c.id));
        if (capas.length) _portapapeles = capas.map((c) => structuredClone(c));
        return;
      }
      if (meta && (e.key === "v" || e.key === "V")) {
        if (!_portapapeles.length) return;
        e.preventDefault();
        let z = Math.max(0, ...st.documento.capas.map((c) => c.z));
        const t0 = Date.now().toString(36);
        const copias = _portapapeles.map((c, i) => ({
          ...structuredClone(c),
          id: `${c.tipo}-${t0}-${i}-${Math.floor(performance.now())}`,
          x: c.x + 24,
          y: c.y + 24,
          z: ++z,
        })) as Capa[];
        for (const copia of copias) st.agregar(copia);
        st.seleccionarMuchas(copias.map((c) => c.id));
        return;
      }
      if (meta && (e.key === "d" || e.key === "D")) { e.preventDefault(); return st.duplicarMulti(); }
      if (meta && e.key === "]") { e.preventDefault(); return st.traerAlFrente(sel); }
      if (meta && e.key === "[") { e.preventDefault(); return st.enviarAlFondo(sel); }
      if (capa && e.key.startsWith("Arrow")) {
        e.preventDefault();
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        const ids = st.seleccionMulti.length > 1 ? st.seleccionMulti : [sel];
        st.aplicarPosiciones(
          ids
            .map((id) => st.documento.capas.find((c) => c.id === id))
            .filter((c): c is Capa => !!c)
            .map((c) => ({ id: c.id, x: c.x + dx, y: c.y + dy })),
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store, reencuadreId, onSalirReencuadre, recorteId, onSalirRecorte]);

  // Zoom con ctrl/cmd + rueda (centrado en el cursor no es crítico aquí: ajustamos el factor).
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    if (!(e.evt.ctrlKey || e.evt.metaKey)) return;
    e.evt.preventDefault();
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z * (e.evt.deltaY < 0 ? 1.1 : 0.9))));
  };

  const onDragStart = (e: Konva.KonvaEventObject<DragEvent>) => {
    setArrastrando(true);
    const id = e.target.id();
    const st = store.getState();
    if (st.seleccionMulti.length > 1 && st.seleccionMulti.includes(id)) {
      const ini = new Map<string, { x: number; y: number }>();
      for (const sid of st.seleccionMulti) {
        const n = stageRef.current?.findOne<Konva.Node>(`#${sid}`);
        if (n) ini.set(sid, { x: n.x(), y: n.y() });
      }
      multiDrag.current = { dragId: id, ini };
    } else {
      multiDrag.current = null;
    }
  };

  const onDragEnd = () => {
    setArrastrando(false);
    setGuias({ x: null, y: null });
    const md = multiDrag.current;
    if (md) {
      const stage = stageRef.current;
      const pos: { id: string; x: number; y: number }[] = [];
      md.ini.forEach((_p, sid) => {
        const n = stage?.findOne<Konva.Node>(`#${sid}`);
        if (n) pos.push({ id: sid, x: n.x(), y: n.y() });
      });
      store.getState().aplicarPosiciones(pos);
      multiDrag.current = null;
    }
  };

  // SMART GUIDES al arrastrar (y MOVER en grupo si hay selección múltiple).
  const onDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const nodo = e.target;
    const md = multiDrag.current;
    if (md && md.dragId === nodo.id()) {
      const start = md.ini.get(nodo.id());
      if (start) {
        const dx = nodo.x() - start.x;
        const dy = nodo.y() - start.y;
        const stage = stageRef.current;
        md.ini.forEach((p, sid) => {
          if (sid === nodo.id()) return;
          const n = stage?.findOne<Konva.Node>(`#${sid}`);
          if (n) {
            n.x(p.x + dx);
            n.y(p.y + dy);
          }
        });
      }
      setGuias({ x: null, y: null });
      return;
    }
    const capa = documento.capas.find((c) => c.id === nodo.id());
    if (!capa) return;
    const umbral = 6 / escala;
    let lx: number | null = null, ly: number | null = null;
    // IMÁN (si está activo): snap a objetos + bordes/centro del lienzo + 4 líneas de margen. Tiene
    // PRIORIDAD sobre la rejilla. Apagado => sin guías ni ajuste magnético.
    if (iman) {
      const objX: number[] = [0, w / 2, w];
      const objY: number[] = [0, h / 2, h];
      // Líneas de margen como objetivos de snap (x = safe_left y w - safe_right; y análogo).
      if (safeLeft > 0) objX.push(safeLeft);
      if (safeRight > 0) objX.push(w - safeRight);
      if (safeTop > 0) objY.push(safeTop);
      if (safeBottom > 0) objY.push(h - safeBottom);
      for (const c of documento.capas) {
        if (c.id === capa.id) continue;
        objX.push(c.x, c.x + c.w / 2, c.x + c.w);
        objY.push(c.y, c.y + c.h / 2, c.y + c.h);
      }
      const x = nodo.x(), y = nodo.y();
      const bx = [x, x + capa.w / 2, x + capa.w];
      const by = [y, y + capa.h / 2, y + capa.h];
      for (let i = 0; i < 3 && lx === null; i++) for (const t of objX) if (Math.abs(bx[i] - t) <= umbral) { nodo.x(x + (t - bx[i])); lx = t; break; }
      for (let i = 0; i < 3 && ly === null; i++) for (const t of objY) if (Math.abs(by[i] - t) <= umbral) { nodo.y(y + (t - by[i])); ly = t; break; }
    }
    // Snap a la rejilla POR UMBRAL (no redondeo duro): solo cuando el borde superior-izquierdo está
    // cerca de una línea de rejilla, y en los ejes que el imán NO haya fijado. Entre líneas el
    // movimiento es libre y no pelea con el imán.
    if (grid) {
      if (lx === null) {
        const linea = Math.round(nodo.x() / paso) * paso;
        if (Math.abs(nodo.x() - linea) <= umbral) nodo.x(linea);
      }
      if (ly === null) {
        const linea = Math.round(nodo.y() / paso) * paso;
        if (Math.abs(nodo.y() - linea) <= umbral) nodo.y(linea);
      }
    }
    // MANTENER DENTRO DEL MARCO: acota la caja al lienzo. Si la capa es mayor que el lienzo en un
    // eje, no se fuerzan negativos absurdos (se permite el rango [w - cw, 0], que queda invertido).
    if (dentroMarco) {
      nodo.x(clampMarco(nodo.x(), capa.w, w));
      nodo.y(clampMarco(nodo.y(), capa.h, h));
    }
    setGuias({ x: lx, y: ly });
  };

  // Doble clic en una capa de texto -> edición en línea.
  const abrirEdicionTexto = (id: string) => {
    const stage = stageRef.current;
    const capa = documento.capas.find((c) => c.id === id);
    if (!stage || !capa || capa.tipo !== "texto") return;
    const nodo = stage.findOne<Konva.Node>(`#${id}`);
    if (!nodo) return;
    const r = nodo.getClientRect();
    setTextoEdit((capa as CapaTexto).texto);
    setEditando({ id, x: r.x, y: r.y, w: Math.max(120, r.width), fontPx: (capa as CapaTexto).tamano * escala });
    store.getState().seleccionar(id);
  };

  const cerrarEdicion = (guardar: boolean) => {
    if (editando && guardar) store.getState().actualizar(editando.id, { texto: textoEdit } as Partial<Capa>);
    setEditando(null);
  };

  // "Ajustar a pantalla" = el lienzo entero cabe en el espacio disponible. Como `escala = baseFit *
  // zoom` y `baseFit` ya encaja el documento, ajustar a pantalla equivale a zoom=1.
  const ajustarPantalla = () => setZoom(1);
  // "100%" = un píxel del documento ocupa un píxel de pantalla, i.e. escala efectiva 1 => zoom =
  // 1/baseFit (acotado al rango permitido).
  const zoomReal = () => setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, 1 / baseFit)));

  // Soltar un activo arrastrado desde la Biblioteca: lo inserta como capa DONDE se suelta.
  const onDrop = (e: DragEventReact<HTMLDivElement>) => {
    const raw = e.dataTransfer.getData("application/x-keni-activo");
    if (!raw) return;
    e.preventDefault();
    let asset: { objeto: string; tipo: string };
    try {
      asset = JSON.parse(raw);
    } catch {
      return;
    }
    const cont = scrollRef.current;
    if (!cont || !asset.objeto) return;
    const rect = cont.getBoundingClientRect();
    const dx = (e.clientX - rect.left + cont.scrollLeft) / escala;
    const dy = (e.clientY - rect.top + cont.scrollTop) / escala;
    const st = store.getState();
    const z = Math.max(0, ...st.documento.capas.map((c) => c.z)) + 1;
    if (asset.tipo === "logo") {
      const cw = 320, ch = 120;
      st.agregar(nuevaCapaLogo(asset.objeto, { x: Math.round(dx - cw / 2), y: Math.round(dy - ch / 2), w: cw, h: ch, z }));
    } else {
      const cw = Math.round(documento.formato.w * 0.4);
      st.agregar(nuevaCapaImagen(asset.objeto, { x: Math.round(dx - cw / 2), y: Math.round(dy - cw / 2), w: cw, h: cw, z }));
    }
    const nuevas = st.documento.capas;
    st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
  };

  // Con "Mantener dentro del marco" activo, acota x/y de un cambio (arrastre/transform end) para que
  // la caja resultante no salga del lienzo. Usa las dimensiones del propio cambio si las trae (p.ej.
  // tras redimensionar), si no las de la capa. Sin el toggle, devuelve el cambio tal cual.
  const acotarCambios = (capa: Capa, cambios: Partial<Capa>): Partial<Capa> => {
    if (!dentroMarco) return cambios;
    const cw = (cambios as { w?: number }).w ?? capa.w;
    const ch = (cambios as { h?: number }).h ?? capa.h;
    const out = { ...cambios } as Partial<Capa> & { x?: number; y?: number };
    if (typeof out.x === "number") out.x = clampMarco(out.x, cw, w);
    if (typeof out.y === "number") out.y = clampMarco(out.y, ch, h);
    return out;
  };

  const multi = seleccionMulti.length > 1;
  const alinearFn = (modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => {
    const st = store.getState();
    if (multi) st.alinearMulti(modo);
    else if (seleccion) st.alinear(seleccion, modo);
  };
  const acciones: { icono: typeof Trash2; titulo: string; onClick: () => void }[] =
    seleccionMulti.length > 0
      ? [
          { icono: AlignStartVertical, titulo: "Alinear izquierda", onClick: () => alinearFn("izq") },
          { icono: AlignCenterVertical, titulo: "Centrar horizontal", onClick: () => alinearFn("centroH") },
          { icono: AlignEndVertical, titulo: "Alinear derecha", onClick: () => alinearFn("der") },
          { icono: AlignStartHorizontal, titulo: "Alinear arriba", onClick: () => alinearFn("arriba") },
          { icono: AlignCenterHorizontal, titulo: "Centrar vertical", onClick: () => alinearFn("centroV") },
          { icono: AlignEndHorizontal, titulo: "Alinear abajo", onClick: () => alinearFn("abajo") },
          ...(seleccionMulti.length > 2
            ? [
                { icono: AlignHorizontalDistributeCenter, titulo: "Distribuir horizontal", onClick: () => store.getState().distribuir("h") },
                { icono: AlignVerticalDistributeCenter, titulo: "Distribuir vertical", onClick: () => store.getState().distribuir("v") },
              ]
            : []),
          ...(!multi && seleccion
            ? [
                { icono: BringToFront, titulo: "Traer al frente", onClick: () => store.getState().traerAlFrente(seleccion) },
                { icono: SendToBack, titulo: "Enviar al fondo", onClick: () => store.getState().enviarAlFondo(seleccion) },
              ]
            : []),
          { icono: Copy, titulo: "Duplicar", onClick: () => store.getState().duplicarMulti() },
          { icono: Trash2, titulo: "Borrar", onClick: () => store.getState().quitarMulti() },
        ]
      : [];

  return (
    <div ref={medirRef} className="flex h-full w-full items-center justify-center overflow-hidden">
    <div className="relative" style={{ width: baseFit * w, height: baseFit * h }}>
      <div
        ref={scrollRef}
        className="h-full w-full overflow-auto rounded-md border border-border shadow-sm"
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("application/x-keni-activo")) e.preventDefault();
        }}
        onDrop={onDrop}
      >
       <div
         className="relative"
         style={{
           width: w * escala,
           height: h * escala,
           // Tablero de ajedrez (GIMP/Adobe) DETRÁS del Stage: donde el documento es transparente
           // (alfa < 1) se ve a través del canvas Konva. Solo editor; el PNG exportado es transparente.
           backgroundImage:
             "linear-gradient(45deg,#c8c8c8 25%,transparent 25%),linear-gradient(-45deg,#c8c8c8 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#c8c8c8 75%),linear-gradient(-45deg,transparent 75%,#c8c8c8 75%)",
           backgroundSize: "16px 16px",
           backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
           backgroundColor: "#fff",
         }}
       >
        <Stage
          ref={stageRef}
          width={w * escala}
          height={h * escala}
          scaleX={escala}
          scaleY={escala}
          onMouseDown={(e) => { if (e.target === e.target.getStage()) store.getState().seleccionar(null); }}
          onWheel={onWheel}
          onDblClick={(e) => { const id = e.target.id?.(); if (id) abrirEdicionTexto(id); }}
          onDblTap={(e) => { const id = e.target.id?.(); if (id) abrirEdicionTexto(id); }}
          onDragStart={onDragStart}
          onDragMove={onDragMove}
          onDragEnd={onDragEnd}
        >
          <Layer>
            <FondoNodo fondo={documento.fondo} w={w} h={h} />
            {capas.map((capa) => (
              <CapaNodo
                key={capa.id}
                capa={capa}
                seleccionada={capa.id === seleccion}
                onSelect={(e) => {
                  const add = e.evt.shiftKey || e.evt.metaKey || e.evt.ctrlKey;
                  const st = store.getState();
                  if (add) st.alternar(capa.id);
                  else if (!st.seleccionMulti.includes(capa.id)) st.seleccionar(capa.id);
                }}
                onChange={(cambios) => store.getState().actualizar(capa.id, acotarCambios(capa, cambios))}
                onGesto={() => store.getState().comenzarGesto()}
              />
            ))}
          </Layer>
          <Layer listening={false}>
            {/* Rejilla FINA con el `paso` configurable (opacidad suave). */}
            {grid &&
              Array.from({ length: Math.max(0, Math.ceil(w / paso) - 1) }, (_, i) => (
                <Line key={`gx${i}`} points={[(i + 1) * paso, 0, (i + 1) * paso, h]} stroke="#ffffff" strokeWidth={1 / escala} opacity={0.1} />
              ))}
            {grid &&
              Array.from({ length: Math.max(0, Math.ceil(h / paso) - 1) }, (_, i) => (
                <Line key={`gy${i}`} points={[0, (i + 1) * paso, w, (i + 1) * paso]} stroke="#ffffff" strokeWidth={1 / escala} opacity={0.1} />
              ))}
            {/* MÁRGENES (encuadre): 4 líneas de guía. Se muestran cuando hay márgenes definidos (>0) y
                el imán está activo (para snap visible), o cuando la rejilla está activa. */}
            {(iman || grid) && hayMargenes && (
              <>
                {safeTop > 0 && <Rect x={0} y={safeTop} width={w} height={1 / escala} fill="#22d3ee" opacity={0.45} />}
                {safeBottom > 0 && <Rect x={0} y={h - safeBottom} width={w} height={1 / escala} fill="#22d3ee" opacity={0.45} />}
                {safeLeft > 0 && <Rect x={safeLeft} y={0} width={1 / escala} height={h} fill="#22d3ee" opacity={0.45} />}
                {safeRight > 0 && <Rect x={w - safeRight} y={0} width={1 / escala} height={h} fill="#22d3ee" opacity={0.45} />}
              </>
            )}
            {guias.x !== null && <Line points={[guias.x, 0, guias.x, h]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
            {guias.y !== null && <Line points={[0, guias.y, w, guias.y]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
          </Layer>
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled={!esGrupo}
              resizeEnabled={!esGrupo}
              keepRatio={ratioFijo}
              enabledAnchors={esGrupo ? [] : ratioFijo ? ["top-left", "top-right", "bottom-left", "bottom-right"] : undefined}
              ignoreStroke
              boundBoxFunc={(o, n) => (n.width < 8 || n.height < 8 ? o : n)}
            />
          </Layer>
        </Stage>
        {capaReencuadre && (
          <ReframeOverlay
            capa={capaReencuadre as CapaImagen}
            escala={escala}
            store={store}
          />
        )}
        {capaRecorte && (
          <CropOverlay
            capa={capaRecorte as CapaImagen}
            escala={escala}
            store={store}
          />
        )}
       </div>
      </div>

      {/* Banner de reencuadre. */}
      {capaReencuadre && (
        <div className="absolute left-1/2 top-2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md">
          <Move className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Arrastra la foto · rueda para zoom</span>
          <button
            onClick={() => onSalirReencuadre?.()}
            className="ml-1 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
          >
            <Check className="h-3.5 w-3.5" /> Listo
          </button>
        </div>
      )}

      {/* Banner de recorte (crop visual). */}
      {capaRecorte && (
        <div className="absolute left-1/2 top-2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-border bg-popover/95 px-3 py-1.5 text-xs shadow-md">
          <CropIcon className="h-3.5 w-3.5 text-muted-foreground" />
          <span>Arrastra los tiradores para recortar</span>
          <button
            onClick={() => onSalirRecorte?.()}
            className="ml-1 flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-primary-foreground"
          >
            <Check className="h-3.5 w-3.5" /> Listo
          </button>
        </div>
      )}

      {/* Barra de acciones flotante sobre la capa seleccionada. */}
      {rectSel && !arrastrando && !editando && !modoImagen && (
        <div
          className="absolute z-10 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 shadow-md"
          style={{ left: Math.max(0, rectSel.x), top: Math.max(0, rectSel.y - 38) }}
        >
          {acciones.map((a, i) => (
            <button key={i} title={a.titulo} onClick={a.onClick} className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
              <a.icono className="h-4 w-4" />
            </button>
          ))}
        </div>
      )}

      {/* Edición de texto en línea. */}
      {editando && (
        <textarea
          autoFocus
          value={textoEdit}
          onChange={(e) => setTextoEdit(e.target.value)}
          onBlur={() => cerrarEdicion(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); cerrarEdicion(true); }
            if (e.key === "Escape") { e.preventDefault(); cerrarEdicion(false); }
          }}
          className="absolute z-20 resize-none rounded border border-primary bg-background/95 p-1 leading-tight shadow"
          style={{ left: editando.x, top: editando.y, width: editando.w, fontSize: Math.max(11, Math.min(40, editando.fontPx)) }}
        />
      )}

      {/* Controles de ENCUADRE + zoom. Imán, rejilla (+ tamaño de celda) y "dentro del marco" son
          toggles INDEPENDIENTES; sus preferencias se guardan en localStorage. */}
      <div className="absolute bottom-2 right-2 z-10 flex items-center gap-0.5 rounded-md border border-border bg-popover/90 p-0.5 shadow">
        <button
          title="Imán: ajustar a objetos, bordes y márgenes"
          onClick={() => setIman((v) => !v)}
          className={`rounded p-1 hover:bg-accent ${iman ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Magnet className="h-3.5 w-3.5" />
        </button>
        <button
          title="Rejilla y ajuste a rejilla"
          onClick={() => setGrid((g) => !g)}
          className={`rounded p-1 hover:bg-accent ${grid ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Grid3x3 className="h-3.5 w-3.5" />
        </button>
        {grid && (
          <select
            title="Tamaño de celda de la rejilla (px)"
            value={tamCelda}
            onChange={(e) => setTamCelda(Number(e.target.value))}
            className="rounded bg-transparent px-0.5 text-xs tabular-nums outline-none hover:bg-accent"
          >
            {CELDAS.map((c) => (
              <option key={c.px} value={c.px}>{c.etiqueta}px</option>
            ))}
          </select>
        )}
        <button
          title="Mantener las capas dentro del marco"
          onClick={() => setDentroMarco((v) => !v)}
          className={`rounded p-1 hover:bg-accent ${dentroMarco ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Frame className="h-3.5 w-3.5" />
        </button>
        <div className="mx-0.5 h-4 w-px bg-border" />
        <button title="Alejar" onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z * 0.9))} className="rounded p-1 hover:bg-accent">
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button title="100% (tamaño real, ⌘0 ajusta a pantalla)" onClick={zoomReal} className="rounded px-1 text-xs tabular-nums hover:bg-accent">
          {Math.round(escala * 100)}%
        </button>
        <button title="Acercar (⌘+)" onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z * 1.1))} className="rounded p-1 hover:bg-accent">
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button title="Ajustar a la pantalla (⌘0)" onClick={ajustarPantalla} className="rounded p-1 hover:bg-accent">
          <Maximize className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
    </div>
  );
}
