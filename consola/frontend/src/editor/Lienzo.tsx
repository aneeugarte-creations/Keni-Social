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
  LayoutGrid,
  SendToBack,
  Trash2,
} from "lucide-react";
import {
  type DragEvent as DragEventReact,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Group, Layer, Line, Rect, Stage, Transformer } from "react-konva";
import { toast } from "sonner";

import { api, urlMedia } from "@/lib/api";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, CapaImagen, CapaOverlay, CapaTexto, Crop } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo, zTope } from "./documento";
import { type GestoLateral, type LadoCaja, docALocal, localADoc, recorteLateral } from "./recorte";
import { useEditor, useStoreEditor } from "./usarEditor";
import { leerDimensionesUrl } from "./useImagen";

import { BannerRecorte, BannerReencuadre } from "./lienzo/BannersModo";
import { type AccionLienzo, BarraAcciones } from "./lienzo/BarraAcciones";
import { ControlesEncuadre } from "./lienzo/ControlesEncuadre";
import { CropOverlay } from "./lienzo/CropOverlay";
import { FondoNodo } from "./lienzo/FondoNodo";
import {
  RATIO_FIJO,
  clampMarco,
  clampZoom,
  etiquetaGrados,
  etiquetaTamano,
  guardarPref,
  prefBool,
  prefNum,
} from "./lienzo/lib";
import { ReframeOverlay } from "./lienzo/ReframeOverlay";
import { useArrastreCapas } from "./lienzo/useArrastreCapas";
import { type LienzoApi, type ZoomApi, useAtajosTeclado } from "./lienzo/useAtajosTeclado";

// Anclas LATERALES del Transformer -> lado de la caja que mueven (gesto de recorte de imagen).
const ANCLA_LADO: Record<string, LadoCaja> = {
  "middle-left": "izq",
  "middle-right": "der",
  "top-center": "arriba",
  "bottom-center": "abajo",
};

// Tiradores estilo Canva: laterales como PÍLDORA, esquinas como CÍRCULO (el rotador conserva su
// forma). Konva aplica la función a cada ancla en cada update (API oficial, no por-hack).
function estiloAncla(ancla: Konva.Rect) {
  const nombre = ancla.name();
  if (nombre.includes("middle-left") || nombre.includes("middle-right")) {
    ancla.setAttrs({ width: 6, height: 16, offsetX: 3, offsetY: 8, cornerRadius: 3 });
  } else if (nombre.includes("top-center") || nombre.includes("bottom-center")) {
    ancla.setAttrs({ width: 16, height: 6, offsetX: 8, offsetY: 3, cornerRadius: 3 });
  } else if (!nombre.includes("rotater")) {
    ancla.setAttrs({ cornerRadius: ancla.width() / 2 });
  }
}

// Lee las dimensiones naturales (px) de un fichero de imagen sin subirlo, para respetar su
// aspect-ratio al insertarlo. Tolerante: devuelve `null` si el navegador no puede decodificarlo.
async function leerDimensiones(archivo: File): Promise<{ w: number; h: number } | null> {
  const url = URL.createObjectURL(archivo);
  try {
    return await leerDimensionesUrl(url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function Lienzo({
  maxAncho = 620,
  maxAlto = 760,
  reencuadreId = null,
  onSalirReencuadre,
  recorteId = null,
  onSalirRecorte,
  muestraFoto = false,
  muestraCopy = false,
  onStage,
  barraSeleccion,
}: {
  maxAncho?: number;
  maxAlto?: number;
  reencuadreId?: string | null;
  onSalirReencuadre?: () => void;
  // Capa imagen en MODO RECORTE visual (crop con tiradores). Mutuamente excluyente con reencuadre.
  recorteId?: string | null;
  onSalirRecorte?: () => void;
  // "Vista con muestra" (PRESENTACIÓN, INDEPENDIENTES): `muestraFoto` rellena el hueco con la foto de
  // muestra; `muestraCopy` rellena los bindings de texto con copy de ejemplo. NO mutan el documento
  // ni afectan al export.
  muestraFoto?: boolean;
  muestraCopy?: boolean;
  // Expone el Stage de Konva + la escala actual al padre (para muestrear píxeles, p.ej. legibilidad).
  onStage?: (stage: Konva.Stage | null, escala: number) => void;
  // Barra CONTEXTUAL de la capa seleccionada (la aporta EditorDocumento): se aloja en la franja
  // reservada de arriba, junto a la píldora de alinear/orden, y solo se ve con selección (y fuera
  // de arrastre/edición/modos de imagen, igual que aquella).
  barraSeleccion?: ReactNode;
}) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const { w, h } = documento.formato;
  // Capa en modo reencuadre (solo imágenes): arrastrar mueve el FOCO, la rueda hace ZOOM.
  const capaReencuadre = reencuadreId ? documento.capas.find((c) => c.id === reencuadreId && c.tipo === "imagen") ?? null : null;
  // MODO RECORTE estilo Canva (solo imágenes): además del modo controlado por el padre (prop
  // `recorteId`, p. ej. desde el inspector), el Lienzo entra POR SÍ MISMO con DOBLE CLIC sobre una
  // capa de imagen (estado interno). Excluyente con reencuadre (el reencuadre manda si coinciden).
  const [recorteInternoId, setRecorteInternoId] = useState<string | null>(null);
  const recorteActivoId = recorteId ?? recorteInternoId;
  const capaRecorte =
    !capaReencuadre && recorteActivoId
      ? documento.capas.find((c) => c.id === recorteActivoId && c.tipo === "imagen") ?? null
      : null;
  // Cualquier modo de edición de imagen oculta los tiradores normales del Transformer.
  const modoImagen = capaReencuadre ?? capaRecorte;

  // SESIÓN de recorte: instantánea al ENTRAR en el modo, para que "Cancelar"/Esc restaure el crop
  // de entrada y para que "Hecho"/Enter colapse todos los gestos del modo en UN paso de deshacer
  // (como Canva). `pasadoLen` ancla el historial al estado de entrada.
  const sesionRecorte = useRef<{ id: string; crop?: Crop; pasadoLen: number } | null>(null);
  useEffect(() => {
    if (!capaRecorte) {
      sesionRecorte.current = null;
      return;
    }
    if (sesionRecorte.current?.id === capaRecorte.id) return;
    const st = store.getState();
    const c = st.documento.capas.find((x) => x.id === capaRecorte.id) as CapaImagen | undefined;
    sesionRecorte.current = {
      id: capaRecorte.id,
      crop: c?.crop ? { ...c.crop } : undefined,
      pasadoLen: st.pasado.length,
    };
  }, [capaRecorte, store]);
  // Si la capa en recorte interno desaparece (deshacer/borrado), el modo se cierra solo.
  useEffect(() => {
    if (recorteInternoId && !documento.capas.some((c) => c.id === recorteInternoId && c.tipo === "imagen")) {
      setRecorteInternoId(null);
    }
  }, [recorteInternoId, documento]);

  const salirRecorte = () => {
    if (recorteInternoId) setRecorteInternoId(null);
    if (recorteId) onSalirRecorte?.();
  };
  // "Hecho"/Enter: confirma el recorte. Colapsa los gestos del modo en UN paso de deshacer
  // (deshacer tras confirmar devuelve el crop de ENTRADA, no los estados intermedios).
  const confirmarRecorte = () => {
    const ses = sesionRecorte.current;
    if (ses) {
      store.setState((s) =>
        s.pasado.length > ses.pasadoLen + 1 ? { pasado: s.pasado.slice(0, ses.pasadoLen + 1) } : {},
      );
    }
    salirRecorte();
  };
  // "Cancelar"/Esc: restaura el crop de entrada y DESCARTA los pasos de historial del modo.
  const cancelarRecorte = () => {
    const ses = sesionRecorte.current;
    if (ses) {
      store.setState((s) => ({
        documento: {
          ...s.documento,
          capas: s.documento.capas.map((c) => {
            if (c.id !== ses.id || c.tipo !== "imagen") return c;
            if (ses.crop) return { ...c, crop: { ...ses.crop } } as Capa;
            const { crop: _omit, ...resto } = c as CapaImagen;
            return resto as Capa;
          }),
        },
        pasado: s.pasado.slice(0, ses.pasadoLen),
      }));
    }
    salirRecorte();
  };

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
  // Etiquetas de DISTANCIA del imán/espaciado igual (px del documento) junto a las guías: overlay
  // HTML que el hook de arrastre muta directamente por frame (sin setState), como la etiqueta viva.
  const etiquetasImanRef = useRef<HTMLDivElement | null>(null);
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
    etiquetasRef: etiquetasImanRef,
  });
  const [editando, setEditando] = useState<{ id: string; x: number; y: number; w: number; fontPx: number } | null>(null);
  const [textoEdit, setTextoEdit] = useState("");

  // ── Interacciones de lienzo (estilo Canva) ───────────────────────────────
  // Pan con barra espaciadora / botón central: `espacio` controla el cursor y desactiva la
  // interacción con las capas (Stage `listening` off) para que el arrastre haga PAN, no mueva capas.
  const [espacio, setEspacio] = useState(false);
  const espacioRef = useRef(false);
  const [paneando, setPaneando] = useState(false);
  // Selección por rectángulo (marquee): caja en coordenadas del DOCUMENTO (mismo sistema que el Stage
  // escalado). `null` = inactiva. Se dibuja en su propia Layer no interactiva.
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  // Ancla de zoom-al-cursor: tras re-renderizar con la nueva escala, ajusta el scroll para que el
  // punto del documento bajo el cursor permanezca bajo el cursor.
  const anclaZoom = useRef<{ docX: number; docY: number; sx: number; sy: number } | null>(null);
  // El aviso de "texto con binding" se muestra una sola vez por vida del componente.
  const avisoBinding = useRef(false);
  // HOVER affordance (estilo Canva): capa bajo el cursor, para dibujarle un contorno fino de
  // acento ANTES de seleccionar. Solo cambia al entrar/salir de un nodo (mouseover/mouseout de
  // Konva burbujean), no en cada movimiento => coste despreciable.
  const [hoverId, setHoverId] = useState<string | null>(null);
  // Etiqueta VIVA del gesto ("W × H px" al redimensionar, grados al rotar): overlay HTML ligero
  // actualizado por mutación directa del DOM (textContent/transform), sin setState por frame.
  const etiquetaGestoRef = useRef<HTMLDivElement | null>(null);

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const capaSel = documento.capas.find((c) => c.id === seleccion) ?? null;
  const ratioFijo = capaSel ? RATIO_FIJO.has(capaSel.tipo) : false;
  // El grupo solo se mueve (resize/rotación se hacen desagrupando).
  const esGrupo = capaSel?.tipo === "grupo";
  // Una IMAGEN sola y no bloqueada gana además los 4 tiradores LATERALES (recorte desde ese borde,
  // estilo Canva; ver `iniciarGestoLateral`). Las esquinas siguen escalando proporcional.
  const lateralesImagen = seleccionMulti.length === 1 && capaSel?.tipo === "imagen" && !capaSel.bloqueada;

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

  // ── Zoom (estilo Canva) ──────────────────────────────────────────────────
  // Todos los cambios de zoom SIN gesto de puntero (botones, menú de %, atajos) se anclan al
  // CENTRO del viewport: el punto del documento que estaba en el centro sigue en el centro tras
  // el cambio de escala. (El zoom con rueda se ancla al cursor en `onWheel`.)
  const anclarCentro = () => {
    const cont = scrollRef.current;
    if (!cont) return;
    const sx = cont.clientWidth / 2;
    const sy = cont.clientHeight / 2;
    anclaZoom.current = { docX: (cont.scrollLeft + sx) / escala, docY: (cont.scrollTop + sy) / escala, sx, sy };
  };
  const acercar = () => { anclarCentro(); setZoom((z) => clampZoom(z * 1.1, baseFit)); };
  const alejar = () => { anclarCentro(); setZoom((z) => clampZoom(z * 0.9, baseFit)); };
  // "Ajustar a pantalla" = el lienzo entero cabe en el espacio disponible. Como `escala = baseFit *
  // zoom` y `baseFit` ya encaja el documento, ajustar a pantalla equivale a zoom=1.
  const ajustarPantalla = () => setZoom(1);
  // "100%" = un píxel del documento ocupa un píxel de pantalla, i.e. escala efectiva 1 => zoom =
  // 1/baseFit (acotado al rango permitido).
  const zoomReal = () => { anclarCentro(); setZoom(clampZoom(1 / baseFit, baseFit)); };
  // Nivel ABSOLUTO del menú de zoom (0.1 => escala efectiva 10 %).
  const fijarEscala = (esc: number) => { anclarCentro(); setZoom(clampZoom(esc / baseFit, baseFit)); };
  // API de zoom para los atajos de teclado, en un ref: el hook no se re-registra en cada render
  // pero siempre ejecuta los handlers frescos (con `baseFit`/`escala` actuales).
  const zoomApi = useRef<ZoomApi>({ acercar, alejar, ajustar: ajustarPantalla, real: zoomReal });
  zoomApi.current = { acercar, alejar, ajustar: ajustarPantalla, real: zoomReal };
  // Servicios del lienzo para los atajos de CREACIÓN (T/R/C/L), en un ref como `zoomApi`. Se
  // rellena más abajo, cuando ya existen `abrirEdicionTexto` y el contenedor de scroll.
  const lienzoApi = useRef<LienzoApi>({ centroViewport: () => ({ x: w / 2, y: h / 2 }), editarTexto: () => {} });

  // Atajos de teclado (ignora si se está escribiendo en un input/textarea). Hook extraído.
  // El modo recorte (prop O interno) cancela con Esc y confirma con Enter.
  useAtajosTeclado({
    store,
    zoom: zoomApi,
    lienzo: lienzoApi,
    reencuadreId,
    onSalirReencuadre,
    recorteId: capaRecorte ? recorteActivoId : null,
    onCancelarRecorte: cancelarRecorte,
    onConfirmarRecorte: confirmarRecorte,
  });

  // Zoom con ctrl/cmd + rueda, CENTRADO EN EL CURSOR: calcula el punto del documento bajo el puntero
  // y deja anotada un ancla; tras re-renderizar con la nueva escala, el efecto de abajo ajusta el
  // scroll para que ese mismo punto quede bajo el cursor (como Figma/Canva).
  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    if (!(e.evt.ctrlKey || e.evt.metaKey)) return;
    e.evt.preventDefault();
    const cont = scrollRef.current;
    const factor = e.evt.deltaY < 0 ? 1.1 : 0.9;
    if (cont) {
      const rect = cont.getBoundingClientRect();
      const sx = e.evt.clientX - rect.left; // offset del cursor dentro del contenedor (px pantalla)
      const sy = e.evt.clientY - rect.top;
      anclaZoom.current = {
        docX: (sx + cont.scrollLeft) / escala,
        docY: (sy + cont.scrollTop) / escala,
        sx,
        sy,
      };
    }
    setZoom((z) => clampZoom(z * factor, baseFit));
  };

  // Aplica el ancla de zoom-al-cursor tras commit (la nueva escala ya está en el DOM, así el scroll
  // no se recorta contra el tamaño viejo del contenido).
  useLayoutEffect(() => {
    const a = anclaZoom.current;
    if (!a) return;
    anclaZoom.current = null;
    const cont = scrollRef.current;
    if (!cont) return;
    cont.scrollLeft = a.docX * escala - a.sx;
    cont.scrollTop = a.docY * escala - a.sy;
  }, [escala]);

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
    // Si el texto tiene binding, lo que se edita es solo la MUESTRA de la plantilla (el render usa el
    // copy real de la pieza). Avisamos una vez para que no confunda. No bloquea la edición.
    if ((capa as CapaTexto).binding != null && !avisoBinding.current) {
      avisoBinding.current = true;
      toast.info(
        "Este texto se rellena con el copy real de la pieza; lo que escribas es el texto de muestra de la plantilla.",
      );
    }
  };

  const cerrarEdicion = (guardar: boolean) => {
    if (editando && guardar) store.getState().actualizar(editando.id, { texto: textoEdit } as Partial<Capa>);
    setEditando(null);
  };

  // Centro del VIEWPORT visible en coords del documento (los elementos nuevos —atajos T/R/C/L,
  // pegado de imágenes— nacen ahí, no en 0,0). Sin medida aún => centro del lienzo.
  const centroViewport = () => {
    const cont = scrollRef.current;
    return cont && cont.clientWidth > 0
      ? { x: (cont.scrollLeft + cont.clientWidth / 2) / escala, y: (cont.scrollTop + cont.clientHeight / 2) / escala }
      : { x: w / 2, y: h / 2 };
  };
  lienzoApi.current = { centroViewport, editarTexto: abrirEdicionTexto };

  // DOBLE CLIC sobre una capa (estilo Canva): en TEXTO abre la edición en línea; en IMAGEN entra en
  // MODO RECORTE. Sube hasta el hijo directo de la Layer (las capas de primer nivel llevan ahí su
  // id; el target del doble clic puede ser un nodo interior, p. ej. el Rect de hit de la imagen).
  const onDobleClic = (e: Konva.KonvaEventObject<MouseEvent | Event>) => {
    const stage = stageRef.current;
    if (!stage || espacioRef.current || modoImagen) return;
    let n: Konva.Node | null = e.target === stage ? null : e.target;
    while (n && !(n.getParent() instanceof Konva.Layer)) n = n.getParent();
    const id = n?.id() || null;
    if (!id) return;
    const capa = documento.capas.find((c) => c.id === id);
    if (!capa) return;
    if (capa.tipo === "texto") return abrirEdicionTexto(id);
    if (capa.tipo === "imagen") {
      const c = capa as CapaImagen;
      // Solo si hay imagen EFECTIVA que recortar: foto real, o la muestra activa sobre el hueco.
      if (!c.objeto && !(muestraFoto && c.es_foto)) return;
      store.getState().seleccionar(id);
      setRecorteInternoId(id);
    }
  };

  // El textarea de edición inline se posiciona en píxeles de pantalla al ABRIR; si cambia la escala
  // (zoom) o se hace scroll del contenedor mientras se edita, quedaría flotando descolocado. Fix
  // mínimo: cerrar guardando ante un cambio de escala. (El scroll se ataja en `onScroll` del
  // contenedor.) Dep SOLO `escala` para no disparar al abrir (cuando cambia `editando`).
  useEffect(() => {
    if (editando) cerrarEdicion(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escala]);

  // Sube un fichero de imagen (portapapeles del SO o arrastre del escritorio) reutilizando el mismo
  // cliente de media del editor y lo inserta como capa imagen centrada en `centro` (coords del
  // documento). Toast de progreso/éxito/error. Respeta el aspect-ratio real de la imagen.
  const subirEInsertarImagen = async (archivo: File, centro: { x: number; y: number }) => {
    const tid = toast.loading("Subiendo imagen…");
    try {
      const [media, dims] = await Promise.all([
        api.subirMedia(archivo, "plantillas"),
        leerDimensiones(archivo),
      ]);
      const cw = Math.round(documento.formato.w * 0.4);
      const ch = dims && dims.w > 0 ? Math.round((cw * dims.h) / dims.w) : cw;
      const st = store.getState();
      const z = zTope(st.documento);
      st.agregar(
        nuevaCapaImagen(media.id, {
          x: Math.round(centro.x - cw / 2),
          y: Math.round(centro.y - ch / 2),
          w: cw,
          h: ch,
          z,
        }),
      );
      const nuevas = st.documento.capas;
      st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
      toast.success("Imagen añadida al lienzo.", { id: tid });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo subir la imagen.", { id: tid });
    }
  };

  // Inserta un activo de la galería (ya subido) como capa imagen centrada en `centro` (coords del
  // documento), adoptando el ASPECT-RATIO natural de la foto (estilo Canva): caja == foto, sin
  // letterbox ni recorte sorpresa, y el marco de selección la abraza exacto. Las dimensiones se
  // leen del propio media (normalmente ya cacheado por la miniatura de la galería); si el
  // navegador no puede decodificarlo, cae al cuadrado de antes.
  const insertarActivoImagen = async (objeto: string, centro: { x: number; y: number }) => {
    const dims = await leerDimensionesUrl(urlMedia(objeto));
    const st = store.getState();
    const cw = Math.round(documento.formato.w * 0.4);
    const ch = dims && dims.w > 0 ? Math.round((cw * dims.h) / dims.w) : cw;
    st.agregar(
      nuevaCapaImagen(objeto, {
        x: Math.round(centro.x - cw / 2),
        y: Math.round(centro.y - ch / 2),
        w: cw,
        h: ch,
        z: zTope(st.documento),
      }),
    );
    const nuevas = st.documento.capas;
    st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
  };

  // Pan con barra ESPACIADORA: mientras está pulsada, cursor grab/grabbing y `listening` del Stage
  // off (los arrastres mueven el lienzo, no las capas). Ignora el espacio si el foco está en un campo
  // editable (evita romper la escritura). `blur` de ventana lo resetea (no quedarse "pegado").
  useEffect(() => {
    const esEditable = (t: EventTarget | null) => {
      const el = t as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || esEditable(e.target)) return;
      e.preventDefault(); // evita el scroll de página al mantener espacio
      if (!espacioRef.current) {
        espacioRef.current = true;
        setEspacio(true);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      espacioRef.current = false;
      setEspacio(false);
    };
    const reset = () => {
      espacioRef.current = false;
      setEspacio(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", reset);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", reset);
    };
  }, []);

  // Pegar imagen del portapapeles del SO: si el foco no está en un input y el clipboard trae un
  // fichero de imagen, se sube e inserta centrada en el VIEWPORT visible del lienzo.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const archivo = Array.from(e.clipboardData?.files ?? []).find((f) => f.type.startsWith("image/"));
      if (!archivo) return;
      e.preventDefault();
      void subirEInsertarImagen(archivo, lienzoApi.current.centroViewport());
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escala, w, h, documento]);

  // PAN del contenedor de scroll: con espacio pulsado (botón izq) o con el botón CENTRAL del ratón.
  // Arrastra cambiando scrollLeft/scrollTop. Funciona aunque el puntero salga del lienzo (listeners
  // en window).
  const onMouseDownContenedor = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (!(espacioRef.current || e.button === 1)) return;
    const cont = scrollRef.current;
    if (!cont) return;
    e.preventDefault();
    setPaneando(true);
    const sx = e.clientX;
    const sy = e.clientY;
    const sl = cont.scrollLeft;
    const stp = cont.scrollTop;
    const onMove = (ev: MouseEvent) => {
      cont.scrollLeft = sl - (ev.clientX - sx);
      cont.scrollTop = stp - (ev.clientY - sy);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setPaneando(false);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  // SELECCIÓN POR RECTÁNGULO (marquee). Arrancar SOLO desde el fondo vacío del Stage (target ===
  // stage), con botón izquierdo, sin espacio (eso es pan) y fuera de los modos de imagen
  // (reencuadre/recorte). Si no hay arrastre real => clic seco => deselección. Con shift, añade.
  const onMouseDownStage = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage || espacioRef.current || modoImagen) return;
    if (e.evt.button !== 0 || e.target !== stage) return;
    const rect = stage.container().getBoundingClientRect();
    const aDoc = (cx: number, cy: number) => ({ x: (cx - rect.left) / escala, y: (cy - rect.top) / escala });
    const inicio = aDoc(e.evt.clientX, e.evt.clientY);
    const shift = e.evt.shiftKey;
    const base = shift ? store.getState().seleccionMulti.slice() : [];
    let fin = inicio;
    let movido = false;
    setMarquee({ x0: inicio.x, y0: inicio.y, x1: inicio.x, y1: inicio.y });
    const onMove = (ev: MouseEvent) => {
      fin = aDoc(ev.clientX, ev.clientY);
      if (Math.abs(fin.x - inicio.x) * escala > 3 || Math.abs(fin.y - inicio.y) * escala > 3) movido = true;
      setMarquee({ x0: inicio.x, y0: inicio.y, x1: fin.x, y1: fin.y });
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setMarquee(null);
      const st = store.getState();
      if (!movido) {
        // Clic seco en el vacío: deselecciona (salvo shift, que conserva la selección).
        if (!shift) st.seleccionar(null);
        return;
      }
      const x0 = Math.min(inicio.x, fin.x);
      const y0 = Math.min(inicio.y, fin.y);
      const x1 = Math.max(inicio.x, fin.x);
      const y1 = Math.max(inicio.y, fin.y);
      const hits = st.documento.capas
        .filter(
          (c) =>
            c.visible &&
            !c.bloqueada &&
            !(c.x > x1 || c.x + c.w < x0 || c.y > y1 || c.y + c.h < y0),
        )
        .map((c) => c.id);
      const ids = shift ? Array.from(new Set([...base, ...hits])) : hits;
      st.seleccionarMuchas(ids);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  // Soltar en el lienzo. Dos orígenes:
  //   1) Activo interno arrastrado desde la galería (mimetype `application/x-keni-activo`): se inserta
  //      como capa DONDE se suelta (flujo intacto).
  //   2) Ficheros del ESCRITORIO (`dataTransfer.files`): si son imágenes, se suben e insertan en el
  //      punto de soltado (igual que el pegado del portapapeles).
  const onDrop = (e: DragEventReact<HTMLDivElement>) => {
    const cont = scrollRef.current;
    if (!cont) return;
    const rect = cont.getBoundingClientRect();
    const dx = (e.clientX - rect.left + cont.scrollLeft) / escala;
    const dy = (e.clientY - rect.top + cont.scrollTop) / escala;

    const raw = e.dataTransfer.getData("application/x-keni-activo");
    if (raw) {
      e.preventDefault();
      let asset: { objeto: string; tipo: string };
      try {
        asset = JSON.parse(raw);
      } catch {
        return;
      }
      if (!asset.objeto) return;
      if (asset.tipo === "logo") {
        const st = store.getState();
        const z = zTope(st.documento);
        const cw = 320, ch = 120;
        st.agregar(nuevaCapaLogo(asset.objeto, { x: Math.round(dx - cw / 2), y: Math.round(dy - ch / 2), w: cw, h: ch, z }));
        const nuevas = st.documento.capas;
        st.seleccionar(nuevas[nuevas.length - 1]?.id ?? null);
      } else {
        // Imagen suelta: la capa adopta el aspect-ratio real de la foto (antes: cuadrado fijo).
        void insertarActivoImagen(asset.objeto, { x: dx, y: dy });
      }
      return;
    }

    // Ficheros del escritorio: sube e inserta cada imagen (ligero offset en cascada si son varias).
    const imagenes = Array.from(e.dataTransfer.files ?? []).filter((f) => f.type.startsWith("image/"));
    if (imagenes.length === 0) return;
    e.preventDefault();
    imagenes.forEach((f, i) => void subirEInsertarImagen(f, { x: dx + i * 24, y: dy + i * 24 }));
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

  // ── Etiqueta viva del gesto (Transformer) ────────────────────────────────
  // Durante el gesto el Transformer muta scaleX/Y y rotation del nodo (w/h se hornean al soltar
  // en onTransformEnd), así que las dimensiones vivas del DOCUMENTO son tamaño base × escala viva.
  const moverEtiquetaGesto = () => {
    const div = etiquetaGestoRef.current;
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!div || !tr || !stage) return;
    const pos = stage.getPointerPosition();
    const nodos = tr.nodes();
    if (!pos || nodos.length === 0) return;
    let texto: string;
    if (tr.getActiveAnchor() === "rotater") {
      texto = etiquetaGrados(nodos[0].rotation());
    } else if (nodos.length === 1) {
      const capa = documento.capas.find((c) => c.id === nodos[0].id());
      if (!capa) return;
      // Texto sin caja (h<=0): alto visual de una línea, igual que hornea onTransformEnd.
      const hBase = capa.tipo === "texto" && capa.h <= 0
        ? (capa as CapaTexto).tamano * (capa as CapaTexto).interlineado
        : capa.h;
      texto = etiquetaTamano(Math.abs(capa.w * nodos[0].scaleX()), Math.abs(hBase * nodos[0].scaleY()));
    } else {
      // Multi-selección: caja envolvente del conjunto en coords del documento.
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of nodos) {
        const r = n.getClientRect({ relativeTo: stage, skipShadow: true, skipStroke: true });
        x0 = Math.min(x0, r.x);
        y0 = Math.min(y0, r.y);
        x1 = Math.max(x1, r.x + r.width);
        y1 = Math.max(y1, r.y + r.height);
      }
      texto = etiquetaTamano(x1 - x0, y1 - y0);
    }
    // Mutación directa del DOM (sin setState): 60 fps durante el gesto.
    div.textContent = texto;
    div.style.display = "block";
    div.style.transform = `translate(${Math.round(pos.x + 14)}px, ${Math.round(pos.y + 18)}px)`;
  };
  const ocultarEtiquetaGesto = () => {
    const div = etiquetaGestoRef.current;
    if (div) div.style.display = "none";
  };

  // ── Recorte LATERAL estilo Canva (tiradores laterales del Transformer en imágenes) ───────────
  // En una capa de IMAGEN, los 4 tiradores laterales no estiran: RECORTAN desde ese borde (la foto
  // mantiene su escala y encuadre; hacia fuera des-recortan hasta el material original). El gesto
  // se deriva de una instantánea al inicio + el puntero en coords LOCALES de la capa (robusto ante
  // rotación, flip y zoom del lienzo), se vuelca al store por frame SIN historial y cuenta como UN
  // paso de deshacer (`comenzarGesto` en el primer movimiento; el `onTransformEnd` de la capa no
  // hornea nada porque el nodo queda con escala 1 y attrs == capa). Las esquinas conservan el
  // escalado proporcional de siempre (keepRatio); la geometría pura vive en `recorteLateral`.
  const gestoLateral = useRef<{
    id: string;
    lado: LadoCaja;
    x0: number;
    y0: number;
    rot: number;
    // El borde se mueve RELATIVO a donde se agarró el tirador (borde inicial - puntero inicial),
    // como el arrastre nativo de las anclas: sin salto al primer movimiento.
    desfase: number;
    params: GestoLateral;
    registrado: boolean;
  } | null>(null);

  const iniciarGestoLateral = () => {
    gestoLateral.current = null;
    const tr = trRef.current;
    const stage = stageRef.current;
    const ancla = tr?.getActiveAnchor();
    const lado = ancla ? ANCLA_LADO[ancla] : undefined;
    if (!tr || !stage || !lado) return;
    const nodos = tr.nodes();
    if (nodos.length !== 1) return;
    const nodo = nodos[0];
    const capa = store.getState().documento.capas.find((c) => c.id === nodo.id());
    if (!capa || capa.tipo !== "imagen" || capa.bloqueada) return;
    const c = capa as CapaImagen;
    // Bitmap EFECTIVO realmente pintado (la foto real o la de muestra del hueco): sin él no hay
    // píxeles que recortar y el tirador cae al estiramiento por defecto (el placeholder vacío es
    // un Rect, no un Group con imagen). El cast es seguro: el lienzo solo pinta
    // HTMLImageElement/canvas (width/height numéricos), los mismos px que usa
    // `geometriaImagenEnCaja` en CapaNodo.
    const img =
      nodo instanceof Konva.Group
        ? (nodo.findOne<Konva.Image>("Image")?.image() as { width: number; height: number } | undefined)
        : undefined;
    if (!img || !(img.width > 0) || !(img.height > 0)) return;
    // Rect que abrazan los tiradores, en coords locales de la capa: la misma base que usa el
    // Transformer para su caja (clientRect local del nodo, sin sombra/trazo).
    const r = nodo.getClientRect({ skipTransform: true, skipShadow: true, skipStroke: true });
    const params: GestoLateral = {
      w: c.w,
      h: c.h,
      iw: img.width,
      ih: img.height,
      ajuste: c.ajuste,
      foco: c.foco,
      zoom: c.zoom,
      crop: c.crop,
      flipH: c.flip_h,
      flipV: c.flip_v,
      caja: { x: r.x, y: r.y, w: r.width, h: r.height },
    };
    // Valida con un gesto nulo (el borde en su posición actual): si la geometría no es recortable
    // (p. ej. contain con letterbox + forma: la foto no cubre la caja), no se arma y el tirador
    // estira como hasta ahora.
    const bordeActual =
      lado === "izq" ? r.x : lado === "der" ? r.x + r.width : lado === "arriba" ? r.y : r.y + r.height;
    if (!recorteLateral(params, lado, bordeActual)) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    const rot = c.rotacion || 0;
    const local = docALocal(c.x, c.y, rot, pos.x / escala, pos.y / escala);
    const desfase = bordeActual - (lado === "izq" || lado === "der" ? local.x : local.y);
    gestoLateral.current = { id: c.id, lado, x0: c.x, y0: c.y, rot, desfase, params, registrado: false };
  };

  const moverGestoLateral = () => {
    const g = gestoLateral.current;
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!g || !tr || !stage) return;
    const nodo = tr.nodes()[0];
    if (!nodo || nodo.id() !== g.id) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    // Puntero -> documento -> coords LOCALES de la capa al inicio del gesto (rotación incluida);
    // el eje del lado da la posición deseada del borde (con el desfase del agarre inicial).
    const local = docALocal(g.x0, g.y0, g.rot, pos.x / escala, pos.y / escala);
    const borde = (g.lado === "izq" || g.lado === "der" ? local.x : local.y) + g.desfase;
    const r = recorteLateral(g.params, g.lado, borde);
    if (!r) return;
    const origen = localADoc(g.x0, g.y0, g.rot, r.x, r.y);
    // Deshace SIEMPRE la escala que el Transformer aplicó este frame: la caja/foto nuevas las
    // pinta React desde el store (mismo patrón de escritura viva que el CropOverlay).
    nodo.setAttrs({ x: origen.x, y: origen.y, rotation: g.rot, scaleX: 1, scaleY: 1 });
    // Gesto totalmente CLAVADO (p. ej. hacia fuera sin material): ni historial ni escritura.
    const actual = store.getState().documento.capas.find((x) => x.id === g.id);
    if (!actual || actual.tipo !== "imagen") return;
    const cropActual = (actual as CapaImagen).crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 };
    const sinCambio =
      actual.x === origen.x &&
      actual.y === origen.y &&
      actual.w === r.w &&
      actual.h === r.h &&
      cropActual.cx === r.crop.cx &&
      cropActual.cy === r.crop.cy &&
      cropActual.cw === r.crop.cw &&
      cropActual.ch === r.crop.ch;
    if (sinCambio) return;
    if (!g.registrado) {
      store.getState().comenzarGesto();
      g.registrado = true;
    }
    store.getState().actualizar(
      g.id,
      { x: origen.x, y: origen.y, w: r.w, h: r.h, crop: r.crop, zoom: r.zoom, foco: r.foco } as Partial<Capa>,
      false,
    );
  };

  // ── Hover affordance ─────────────────────────────────────────────────────
  // Sube hasta el hijo directo de la Layer: las capas de primer nivel llevan ahí su id (las hijas
  // de un grupo resuelven al grupo). Fondo/Transformer no tienen id => null (sin hover).
  const onMouseOverStage = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage || espacioRef.current || modoImagen) return;
    let n: Konva.Node | null = e.target === stage ? null : e.target;
    while (n && !(n.getParent() instanceof Konva.Layer)) n = n.getParent();
    const id = n?.id() || null;
    setHoverId(id && documento.capas.some((c) => c.id === id) ? id : null);
  };
  // Contorno de hover: caja de la capa bajo el cursor (si no está ya seleccionada ni hay gesto en
  // curso). Sin rotación usamos la caja REAL renderizada (clientRect del nodo: con imágenes
  // "contain" abraza la foto exacta, igual que el marco de selección); con rotación, la caja del
  // modelo rotada (overlay/texto sin caja ajustan su alto visual).
  const hoverBox = (() => {
    if (!hoverId || arrastrando || marquee || modoImagen || espacio) return null;
    if (seleccionMulti.includes(hoverId)) return null;
    const c = documento.capas.find((x) => x.id === hoverId);
    if (!c || c.visible === false) return null;
    if (!c.rotacion) {
      const stage = stageRef.current;
      const nodo = stage?.findOne<Konva.Node>(`#${c.id}`);
      if (stage && nodo) {
        const r = nodo.getClientRect({ relativeTo: stage, skipShadow: true, skipStroke: true });
        return { x: r.x, y: r.y, w: r.width, h: r.height, rot: 0 };
      }
    }
    const alto =
      c.tipo === "overlay"
        ? Math.max(1, c.h * (c as CapaOverlay).alto_frac)
        : c.tipo === "texto" && c.h <= 0
          ? (c as CapaTexto).tamano * (c as CapaTexto).interlineado
          : c.h;
    const y = c.tipo === "overlay" ? c.y + c.h - alto : c.y;
    return { x: c.x, y, w: c.w, h: alto, rot: c.rotacion };
  })();

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
                // «Ordenar» (tidy up): espaciado uniforme en el eje dominante + centros alineados.
                { icono: LayoutGrid, titulo: "Ordenar", atajo: "⌥⇧T", onClick: () => store.getState().ordenarMulti() },
              ]
            : []),
          ...(!multi && seleccion
            ? [
                { icono: BringToFront, titulo: "Traer al frente", atajo: "⌘]", onClick: () => store.getState().traerAlFrente(seleccion) },
                { icono: SendToBack, titulo: "Enviar al fondo", atajo: "⌘[", onClick: () => store.getState().enviarAlFondo(seleccion) },
              ]
            : []),
          { icono: Copy, titulo: "Duplicar", atajo: "⌘D", onClick: () => store.getState().duplicarMulti() },
          { icono: Trash2, titulo: "Borrar", atajo: "Supr", onClick: () => store.getState().quitarMulti() },
        ]
      : [];

  return (
    <div className="flex h-full w-full items-stretch gap-2">
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
    {/* Franja superior fija: aloja la barra CONTEXTUAL de la capa + la píldora de acciones ARRIBA
        de la imagen (fuera del lienzo), en un sitio estable que NO sigue a la selección —igual que
        el raíl de zoom va a la derecha—. La altura va reservada siempre para que el lienzo no se
        recoloque al aparecer/desaparecer la selección. */}
    <div className="flex h-11 shrink-0 items-center justify-center px-1">
      {acciones.length > 0 && !arrastrando && !editando && !modoImagen && (
        <div className="flex min-w-0 max-w-full items-center gap-1.5">
          {barraSeleccion}
          <BarraAcciones acciones={acciones} />
        </div>
      )}
    </div>
    <div ref={medirRef} className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
    <div className="relative" style={{ width: baseFit * w, height: baseFit * h }}>
      <div
        ref={scrollRef}
        className="h-full w-full overflow-auto rounded-md border border-border shadow-sm"
        style={{ cursor: paneando ? "grabbing" : espacio ? "grab" : undefined }}
        onMouseDown={onMouseDownContenedor}
        onScroll={() => { if (editando) cerrarEdicion(true); }}
        onDragOver={(e) => {
          // Permite el drop tanto del activo interno como de ficheros del escritorio.
          if (e.dataTransfer.types.includes("application/x-keni-activo") || e.dataTransfer.types.includes("Files")) e.preventDefault();
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
          // Con espacio pulsado, el Stage no escucha: el arrastre lo captura el contenedor (PAN) en
          // vez de mover capas. Sin espacio, interacción normal de capas.
          listening={!espacio}
          onMouseDown={onMouseDownStage}
          onMouseOver={onMouseOverStage}
          onMouseLeave={() => setHoverId(null)}
          onWheel={onWheel}
          onDblClick={onDobleClic}
          onDblTap={onDobleClic}
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
                muestraFoto={muestraFoto}
                muestraCopy={muestraCopy}
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
            {/* Rejilla FINA con el `paso` configurable. Gris medio (no blanco): visible sobre fondos
                claros Y oscuros (el blanco a 0.1 desaparecía sobre el tablero/claros). */}
            {grid &&
              Array.from({ length: Math.max(0, Math.ceil(w / paso) - 1) }, (_, i) => (
                <Line key={`gx${i}`} points={[(i + 1) * paso, 0, (i + 1) * paso, h]} stroke="#888888" strokeWidth={1 / escala} opacity={0.35} />
              ))}
            {grid &&
              Array.from({ length: Math.max(0, Math.ceil(h / paso) - 1) }, (_, i) => (
                <Line key={`gy${i}`} points={[0, (i + 1) * paso, w, (i + 1) * paso]} stroke="#888888" strokeWidth={1 / escala} opacity={0.35} />
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
            {/* ESPACIADO IGUAL (estilo Canva): un segmento con topes en cada hueco equidistante
                (la etiqueta px va en el overlay HTML de etiquetas, mutado por el hook). */}
            {guias.espX?.segmentos.map((s, i) => (
              <Group key={`espx${i}`}>
                <Line points={[s.desde, s.perp, s.hasta, s.perp]} stroke="#ec4899" strokeWidth={1.5 / escala} />
                <Line points={[s.desde, s.perp - 6 / escala, s.desde, s.perp + 6 / escala]} stroke="#ec4899" strokeWidth={1.5 / escala} />
                <Line points={[s.hasta, s.perp - 6 / escala, s.hasta, s.perp + 6 / escala]} stroke="#ec4899" strokeWidth={1.5 / escala} />
              </Group>
            ))}
            {guias.espY?.segmentos.map((s, i) => (
              <Group key={`espy${i}`}>
                <Line points={[s.perp, s.desde, s.perp, s.hasta]} stroke="#ec4899" strokeWidth={1.5 / escala} />
                <Line points={[s.perp - 6 / escala, s.desde, s.perp + 6 / escala, s.desde]} stroke="#ec4899" strokeWidth={1.5 / escala} />
                <Line points={[s.perp - 6 / escala, s.hasta, s.perp + 6 / escala, s.hasta]} stroke="#ec4899" strokeWidth={1.5 / escala} />
              </Group>
            ))}
            {/* HOVER (estilo Canva): contorno fino de acento sobre la capa bajo el cursor ANTES de
                seleccionarla. Solo visual (Layer sin listening). */}
            {hoverBox && (
              <Rect
                x={hoverBox.x}
                y={hoverBox.y}
                width={hoverBox.w}
                height={hoverBox.h}
                rotation={hoverBox.rot}
                stroke="#3b82f6"
                strokeWidth={1.5 / escala}
                listening={false}
              />
            )}
            {/* Rectángulo de selección (marquee): caja punteada en coords del documento. */}
            {marquee && (
              <Rect
                x={Math.min(marquee.x0, marquee.x1)}
                y={Math.min(marquee.y0, marquee.y1)}
                width={Math.abs(marquee.x1 - marquee.x0)}
                height={Math.abs(marquee.y1 - marquee.y0)}
                stroke="#3b82f6"
                strokeWidth={1 / escala}
                dash={[5 / escala, 4 / escala]}
                fill="#3b82f6"
                opacity={0.12}
              />
            )}
          </Layer>
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled={!esGrupo}
              resizeEnabled={!esGrupo}
              keepRatio={ratioFijo}
              // Imágenes y logos: esquinas con proporción fija. Una imagen sola (no bloqueada)
              // gana además los LATERALES, que recortan en vez de estirar (gesto lateral arriba).
              enabledAnchors={
                esGrupo
                  ? []
                  : lateralesImagen
                    ? ["top-left", "top-right", "bottom-left", "bottom-right", "middle-left", "middle-right", "top-center", "bottom-center"]
                    : ratioFijo
                      ? ["top-left", "top-right", "bottom-left", "bottom-right"]
                      : undefined
              }
              anchorStyleFunc={estiloAncla}
              ignoreStroke
              // Snap SUAVE de la rotación a 0/45/90… (estilo Canva); fuera del umbral gira libre.
              rotationSnaps={[0, 45, 90, 135, 180, 225, 270, 315]}
              rotationSnapTolerance={5}
              // Etiqueta viva junto al cursor: "W × H px" al redimensionar, grados al rotar. El
              // gesto LATERAL de imagen intercepta el transform ANTES de la etiqueta (recorta en
              // vez de estirar) y se desarma al soltar.
              onTransformStart={() => {
                iniciarGestoLateral();
                moverEtiquetaGesto();
              }}
              onTransform={() => {
                moverGestoLateral();
                moverEtiquetaGesto();
              }}
              onTransformEnd={() => {
                gestoLateral.current = null;
                ocultarEtiquetaGesto();
              }}
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
            muestraFoto={muestraFoto}
          />
        )}
        {/* Etiqueta VIVA del gesto: rótulo junto al cursor durante resize/rotación. Movido por
            mutación directa del DOM (solo transform durante el gesto => 60 fps). */}
        <div
          ref={etiquetaGestoRef}
          aria-hidden
          className="pointer-events-none absolute left-0 top-0 z-30 rounded border border-border bg-popover px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-popover-foreground shadow-md will-change-transform"
          style={{ display: "none" }}
        />
        {/* Etiquetas de DISTANCIA del imán/espaciado igual: contenedor que `useArrastreCapas` puebla
            por mutación directa del DOM durante el arrastre (sin setState por frame). */}
        <div ref={etiquetasImanRef} aria-hidden className="pointer-events-none absolute inset-0 z-30" />
       </div>
      </div>

      {/* Banner de reencuadre. */}
      {capaReencuadre && <BannerReencuadre onListo={onSalirReencuadre} />}

      {/* Banner de recorte (estilo Canva): Hecho confirma (Enter), Cancelar restaura (Esc). */}
      {capaRecorte && <BannerRecorte onListo={confirmarRecorte} onCancelar={cancelarRecorte} />}

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
      alejar={alejar}
      acercar={acercar}
      zoomReal={zoomReal}
      ajustarPantalla={ajustarPantalla}
      fijarEscala={fijarEscala}
    />
    </div>
  );
}
