// Lienzo Konva del editor: fondo + capas (por z), con selección, arrastre con SMART GUIDES,
// Transformer con aspect-ratio (imágenes/logos), zoom (+/−/ajustar, ctrl+rueda, pinch), barra de
// acciones FLOTANTE sobre la capa seleccionada (alinear/orden/duplicar/borrar), edición de texto
// EN LÍNEA (doble clic) y atajos de teclado. Táctil de serie (Konva). El estado vive en el store.
//
// Este fichero es el componente PRINCIPAL: mantiene el estado/refs/efectos sensibles al orden y los
// manejadores de interacción (drag/resize/zoom), y COMPONE los sub-componentes extraídos a
// `editor/lienzo/`: FondoNodo, ReframeOverlay, CropOverlay, banners de modo, barra de acciones y
// controles de encuadre. Helpers de geometría/preferencias y constantes viven en `lienzo/lib`.

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
  Copy,
  SendToBack,
  Trash2,
} from "lucide-react";
import {
  type DragEvent as DragEventReact,
  useEffect,
  useRef,
  useState,
} from "react";
import { Layer, Line, Rect, Stage, Transformer } from "react-konva";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, CapaImagen, CapaTexto } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

import { BannerRecorte, BannerReencuadre } from "./lienzo/BannersModo";
import { type AccionLienzo, BarraAcciones } from "./lienzo/BarraAcciones";
import { ControlesEncuadre } from "./lienzo/ControlesEncuadre";
import { CropOverlay } from "./lienzo/CropOverlay";
import { FondoNodo } from "./lienzo/FondoNodo";
import {
  RATIO_FIJO,
  ZOOM_MAX,
  ZOOM_MIN,
  clampMarco,
  guardarPref,
  prefBool,
  prefNum,
} from "./lienzo/lib";
import { ReframeOverlay } from "./lienzo/ReframeOverlay";
import { useArrastreCapas } from "./lienzo/useArrastreCapas";
import { useAtajosTeclado } from "./lienzo/useAtajosTeclado";

export function Lienzo({
  maxAncho = 620,
  maxAlto = 760,
  reencuadreId = null,
  onSalirReencuadre,
  recorteId = null,
  onSalirRecorte,
  muestra = false,
  onStage,
}: {
  maxAncho?: number;
  maxAlto?: number;
  reencuadreId?: string | null;
  onSalirReencuadre?: () => void;
  // Capa imagen en MODO RECORTE visual (crop con tiradores). Mutuamente excluyente con reencuadre.
  recorteId?: string | null;
  onSalirRecorte?: () => void;
  // "Vista con muestra": overlay de PRESENTACIÓN. Rellena el hueco con una foto de muestra y los
  // bindings de texto con copy de ejemplo. NO muta el documento ni afecta al export.
  muestra?: boolean;
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
  // Arrastre de capas con SMART GUIDES y movimiento en grupo: hook extraído (owns el ref multiDrag).
  const { arrastrando, guias, onDragStart, onDragMove, onDragEnd } = useArrastreCapas({
    store,
    stageRef,
    documento,
    escala,
    iman,
    grid,
    paso,
    dentroMarco,
    w,
    h,
    safeTop,
    safeBottom,
    safeLeft,
    safeRight,
  });
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

  // Atajos de teclado (ignora si se está escribiendo en un input/textarea). Hook extraído.
  useAtajosTeclado({ store, setZoom, reencuadreId, onSalirReencuadre, recorteId, onSalirRecorte });

  // Zoom con ctrl/cmd + rueda (centrado en el cursor no es crítico aquí: ajustamos el factor).
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    if (!(e.evt.ctrlKey || e.evt.metaKey)) return;
    e.evt.preventDefault();
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z * (e.evt.deltaY < 0 ? 1.1 : 0.9))));
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

  // Soltar un activo arrastrado desde la Texto: lo inserta como capa DONDE se suelta.
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
  const acciones: AccionLienzo[] =
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
    <div className="flex h-full w-full items-stretch gap-2">
    <div ref={medirRef} className="flex min-w-0 flex-1 items-center justify-center overflow-hidden">
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
                muestra={muestra}
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
      {capaReencuadre && <BannerReencuadre onListo={onSalirReencuadre} />}

      {/* Banner de recorte (crop visual). */}
      {capaRecorte && <BannerRecorte onListo={onSalirRecorte} />}

      {/* Barra de acciones flotante sobre la capa seleccionada. */}
      {rectSel && !arrastrando && !editando && !modoImagen && (
        <BarraAcciones acciones={acciones} rectSel={rectSel} />
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

    </div>
    </div>

    {/* Controles de ENCUADRE + zoom: raíl vertical AL LADO del lienzo (fuera de la foto, no tapa
        el campo visual). Imán, rejilla (+ tamaño de celda) y "dentro del marco" son toggles
        INDEPENDIENTES; sus preferencias se guardan en localStorage. */}
    <ControlesEncuadre
      iman={iman}
      setIman={setIman}
      grid={grid}
      setGrid={setGrid}
      tamCelda={tamCelda}
      setTamCelda={setTamCelda}
      dentroMarco={dentroMarco}
      setDentroMarco={setDentroMarco}
      escala={escala}
      alejar={() => setZoom((z) => Math.max(ZOOM_MIN, z * 0.9))}
      acercar={() => setZoom((z) => Math.min(ZOOM_MAX, z * 1.1))}
      zoomReal={zoomReal}
      ajustarPantalla={ajustarPantalla}
    />
    </div>
  );
}
