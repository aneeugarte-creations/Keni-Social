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
  AlignStartHorizontal,
  AlignStartVertical,
  BringToFront,
  Copy,
  Maximize,
  Minus,
  Plus,
  SendToBack,
  Trash2,
} from "lucide-react";
import { type DragEvent as DragEventReact, useEffect, useRef, useState } from "react";
import { Layer, Line, Rect, Stage, Transformer } from "react-konva";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, CapaTexto, Documento } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";
import { useImagen } from "./useImagen";

const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);
const ZOOM_MIN = 0.2;
const ZOOM_MAX = 4;

function FondoNodo({ fondo, w, h }: { fondo: Documento["fondo"]; w: number; h: number }) {
  const img = useImagen(fondo.tipo === "imagen" ? fondo.imagen?.media_id : null);
  if (fondo.tipo === "color") return <Rect x={0} y={0} width={w} height={h} fill={fondo.color} listening={false} />;
  if (fondo.tipo === "degradado" && fondo.degradado) {
    return (
      <Rect
        x={0} y={0} width={w} height={h} listening={false}
        fillLinearGradientStartPoint={{ x: 0, y: 0 }}
        fillLinearGradientEndPoint={{ x: 0, y: h }}
        fillLinearGradientColorStops={[0, fondo.degradado.desde, 1, fondo.degradado.hasta]}
      />
    );
  }
  if (fondo.tipo === "imagen" && img) {
    return <Rect x={0} y={0} width={w} height={h} listening={false} fillPatternImage={img} fillPatternScale={{ x: w / img.width, y: h / img.height }} />;
  }
  return <Rect x={0} y={0} width={w} height={h} fill="#111315" listening={false} />;
}

export function Lienzo({ maxAncho = 620, maxAlto = 760 }: { maxAncho?: number; maxAlto?: number }) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const { w, h } = documento.formato;

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

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [guias, setGuias] = useState<{ x: number | null; y: number | null }>({ x: null, y: null });
  const [arrastrando, setArrastrando] = useState(false);
  const [rectSel, setRectSel] = useState<{ x: number; y: number; w: number } | null>(null);
  const [editando, setEditando] = useState<{ id: string; x: number; y: number; w: number; fontPx: number } | null>(null);
  const [textoEdit, setTextoEdit] = useState("");

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const capaSel = documento.capas.find((c) => c.id === seleccion) ?? null;
  const ratioFijo = capaSel ? RATIO_FIJO.has(capaSel.tipo) : false;

  // Adjunta el Transformer al nodo seleccionado.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    const nodo = seleccion ? stage.findOne<Konva.Node>(`#${seleccion}`) : null;
    tr.nodes(nodo ? [nodo] : []);
    tr.getLayer()?.batchDraw();
  }, [seleccion, documento, zoom]);

  // Rect en pantalla de la capa seleccionada (para la barra flotante). Recalcula al cambiar
  // selección/documento/zoom (tras soltar un arrastre el documento cambia y se recoloca).
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !seleccion) {
      setRectSel(null);
      return;
    }
    const nodo = stage.findOne<Konva.Node>(`#${seleccion}`);
    if (!nodo) {
      setRectSel(null);
      return;
    }
    const r = nodo.getClientRect();
    setRectSel({ x: r.x, y: r.y, w: r.width });
  }, [seleccion, documento, zoom]);

  // Atajos de teclado (ignora si se está escribiendo en un input/textarea).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const st = store.getState();
      const sel = st.seleccion;
      const meta = e.metaKey || e.ctrlKey;
      if (meta && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) st.rehacer();
        else st.deshacer();
        return;
      }
      if (e.key === "Escape") return st.seleccionar(null);
      if (!sel) return;
      const capa = st.documento.capas.find((c) => c.id === sel);
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); return st.quitar(sel); }
      if (meta && (e.key === "d" || e.key === "D")) { e.preventDefault(); return st.duplicar(sel); }
      if (meta && e.key === "]") { e.preventDefault(); return st.traerAlFrente(sel); }
      if (meta && e.key === "[") { e.preventDefault(); return st.enviarAlFondo(sel); }
      if (capa && e.key.startsWith("Arrow")) {
        e.preventDefault();
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        st.actualizar(sel, { x: capa.x + dx, y: capa.y + dy } as Partial<Capa>);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store]);

  // Zoom con ctrl/cmd + rueda (centrado en el cursor no es crítico aquí: ajustamos el factor).
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    if (!(e.evt.ctrlKey || e.evt.metaKey)) return;
    e.evt.preventDefault();
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z * (e.evt.deltaY < 0 ? 1.1 : 0.9))));
  };

  // SMART GUIDES al arrastrar.
  const onDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const nodo = e.target;
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

  const ajustarZoom = () => setZoom(1);

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

  const acciones: { icono: typeof Trash2; titulo: string; onClick: () => void }[] = seleccion
    ? [
        { icono: AlignStartVertical, titulo: "Alinear izquierda", onClick: () => store.getState().alinear(seleccion, "izq") },
        { icono: AlignCenterVertical, titulo: "Centrar horizontal", onClick: () => store.getState().alinear(seleccion, "centroH") },
        { icono: AlignEndVertical, titulo: "Alinear derecha", onClick: () => store.getState().alinear(seleccion, "der") },
        { icono: AlignStartHorizontal, titulo: "Alinear arriba", onClick: () => store.getState().alinear(seleccion, "arriba") },
        { icono: AlignCenterHorizontal, titulo: "Centrar vertical", onClick: () => store.getState().alinear(seleccion, "centroV") },
        { icono: AlignEndHorizontal, titulo: "Alinear abajo", onClick: () => store.getState().alinear(seleccion, "abajo") },
        { icono: BringToFront, titulo: "Traer al frente", onClick: () => store.getState().traerAlFrente(seleccion) },
        { icono: SendToBack, titulo: "Enviar al fondo", onClick: () => store.getState().enviarAlFondo(seleccion) },
        { icono: Copy, titulo: "Duplicar", onClick: () => store.getState().duplicar(seleccion) },
        { icono: Trash2, titulo: "Borrar", onClick: () => store.getState().quitar(seleccion) },
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
          onDragStart={() => setArrastrando(true)}
          onDragMove={onDragMove}
          onDragEnd={() => { setArrastrando(false); setGuias({ x: null, y: null }); }}
        >
          <Layer>
            <FondoNodo fondo={documento.fondo} w={w} h={h} />
            {capas.map((capa) => (
              <CapaNodo
                key={capa.id}
                capa={capa}
                seleccionada={capa.id === seleccion}
                onSelect={() => store.getState().seleccionar(capa.id)}
                onChange={(cambios) => store.getState().actualizar(capa.id, cambios)}
                onGesto={() => store.getState().comenzarGesto()}
              />
            ))}
          </Layer>
          <Layer listening={false}>
            {documento.formato.safe_top > 0 && <Rect x={0} y={documento.formato.safe_top} width={w} height={1} fill="#22d3ee" opacity={0.4} />}
            {documento.formato.safe_bottom > 0 && <Rect x={0} y={h - documento.formato.safe_bottom} width={w} height={1} fill="#22d3ee" opacity={0.4} />}
            {guias.x !== null && <Line points={[guias.x, 0, guias.x, h]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
            {guias.y !== null && <Line points={[0, guias.y, w, guias.y]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
          </Layer>
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled
              keepRatio={ratioFijo}
              enabledAnchors={ratioFijo ? ["top-left", "top-right", "bottom-left", "bottom-right"] : undefined}
              ignoreStroke
              boundBoxFunc={(o, n) => (n.width < 8 || n.height < 8 ? o : n)}
            />
          </Layer>
        </Stage>
      </div>

      {/* Barra de acciones flotante sobre la capa seleccionada. */}
      {rectSel && !arrastrando && !editando && (
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
        <button title="Alejar" onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z * 0.9))} className="rounded p-1 hover:bg-accent">
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button title="Ajustar" onClick={ajustarZoom} className="rounded px-1 text-xs tabular-nums hover:bg-accent">
          {Math.round(zoom * 100)}%
        </button>
        <button title="Acercar" onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z * 1.1))} className="rounded p-1 hover:bg-accent">
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button title="Ajustar a la pantalla" onClick={ajustarZoom} className="rounded p-1 hover:bg-accent">
          <Maximize className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
    </div>
  );
}
