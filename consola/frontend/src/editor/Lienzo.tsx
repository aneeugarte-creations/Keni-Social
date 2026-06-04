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
  Grid3x3,
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
import type { Capa, CapaImagen, CapaTexto, Documento } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo } from "./documento";
import type { StoreEditor } from "./store";
import { useEditor, useStoreEditor } from "./usarEditor";
import { useImagen } from "./useImagen";

const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);
const ZOOM_MIN = 0.2;
const ZOOM_MAX = 4;

// Portapapeles de capas (módulo, para copiar/pegar incluso entre pestañas del workspace). Guarda
// TODA la selección múltiple, no solo la capa primaria.
let _portapapeles: Capa[] = [];

function FondoNodo({ fondo, w, h }: { fondo: Documento["fondo"]; w: number; h: number }) {
  const img = useImagen(fondo.tipo === "imagen" ? fondo.imagen?.media_id : null);
  if (fondo.tipo === "color") return <Rect x={0} y={0} width={w} height={h} fill={fondo.color} listening={false} />;
  if (fondo.tipo === "degradado" && fondo.degradado) {
    // Respeta el ÁNGULO del degradado (mismo helper/convención que el render y las capas):
    // default 180 = vertical (↓), sin cambio visual respecto al comportamiento previo.
    const g = puntosGradiente(w, h, fondo.degradado.angulo);
    return (
      <Rect
        x={0} y={0} width={w} height={h} listening={false}
        fillLinearGradientStartPoint={g.start}
        fillLinearGradientEndPoint={g.end}
        fillLinearGradientColorStops={[0, fondo.degradado.desde, 1, fondo.degradado.hasta]}
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

export function Lienzo({
  maxAncho = 620,
  maxAlto = 760,
  reencuadreId = null,
  onSalirReencuadre,
}: {
  maxAncho?: number;
  maxAlto?: number;
  reencuadreId?: string | null;
  onSalirReencuadre?: () => void;
}) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const { w, h } = documento.formato;
  // Capa en modo reencuadre (solo imágenes): arrastrar mueve el FOCO, la rueda hace ZOOM.
  const capaReencuadre = reencuadreId ? documento.capas.find((c) => c.id === reencuadreId && c.tipo === "imagen") ?? null : null;

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
  // Cuadrícula + snap (12 columnas del ancho). Toggle desde los controles de zoom.
  const [grid, setGrid] = useState(false);
  const paso = Math.max(8, Math.round(w / 12));

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
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
    // En reencuadre se ocultan los tiradores (la interacción es mover el foco / zoom).
    const nodos = capaReencuadre
      ? []
      : seleccionMulti
          .map((id) => stage.findOne<Konva.Node>(`#${id}`))
          .filter((n): n is Konva.Node => !!n);
    tr.nodes(nodos);
    tr.getLayer()?.batchDraw();
  }, [seleccionMulti, documento, zoom, capaReencuadre]);

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
        if (reencuadreId) return onSalirReencuadre?.();
        return st.seleccionar(null);
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
  }, [store, reencuadreId, onSalirReencuadre]);

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
    const objX: number[] = [0, w / 2, w];
    const objY: number[] = [0, h / 2, h];
    for (const c of documento.capas) {
      if (c.id === capa.id) continue;
      objX.push(c.x, c.x + c.w / 2, c.x + c.w);
      objY.push(c.y, c.y + c.h / 2, c.y + c.h);
    }
    const x = nodo.x(), y = nodo.y();
    const bx = [x, x + capa.w / 2, x + capa.w];
    const by = [y, y + capa.h / 2, y + capa.h];
    let lx: number | null = null, ly: number | null = null;
    for (let i = 0; i < 3 && lx === null; i++) for (const t of objX) if (Math.abs(bx[i] - t) <= umbral) { nodo.x(x + (t - bx[i])); lx = t; break; }
    for (let i = 0; i < 3 && ly === null; i++) for (const t of objY) if (Math.abs(by[i] - t) <= umbral) { nodo.y(y + (t - by[i])); ly = t; break; }
    // Snap a la cuadrícula en los ejes que NINGÚN objeto haya fijado.
    if (grid) {
      if (lx === null) nodo.x(Math.round(nodo.x() / paso) * paso);
      if (ly === null) nodo.y(Math.round(nodo.y() / paso) * paso);
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
                onChange={(cambios) => store.getState().actualizar(capa.id, cambios)}
                onGesto={() => store.getState().comenzarGesto()}
              />
            ))}
          </Layer>
          <Layer listening={false}>
            {grid &&
              Array.from({ length: Math.floor(w / paso) }, (_, i) => (
                <Line key={`gx${i}`} points={[(i + 1) * paso, 0, (i + 1) * paso, h]} stroke="#ffffff" strokeWidth={1 / escala} opacity={0.12} />
              ))}
            {grid &&
              Array.from({ length: Math.floor(h / paso) }, (_, i) => (
                <Line key={`gy${i}`} points={[0, (i + 1) * paso, w, (i + 1) * paso]} stroke="#ffffff" strokeWidth={1 / escala} opacity={0.12} />
              ))}
            {/* Guías de zona segura: solo con la cuadrícula activa (antes confundían siempre visibles). */}
            {grid && documento.formato.safe_top > 0 && <Rect x={0} y={documento.formato.safe_top} width={w} height={1} fill="#22d3ee" opacity={0.4} />}
            {grid && documento.formato.safe_bottom > 0 && <Rect x={0} y={h - documento.formato.safe_bottom} width={w} height={1} fill="#22d3ee" opacity={0.4} />}
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

      {/* Barra de acciones flotante sobre la capa seleccionada. */}
      {rectSel && !arrastrando && !editando && !capaReencuadre && (
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

      {/* Controles de zoom. */}
      <div className="absolute bottom-2 right-2 z-10 flex items-center gap-0.5 rounded-md border border-border bg-popover/90 p-0.5 shadow">
        <button
          title="Cuadrícula y ajuste a rejilla"
          onClick={() => setGrid((g) => !g)}
          className={`rounded p-1 hover:bg-accent ${grid ? "bg-accent text-foreground" : ""}`}
        >
          <Grid3x3 className="h-3.5 w-3.5" />
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
