// Lienzo Konva del editor: fondo + capas (por z), con selección, arrastre con SMART GUIDES,
// Transformer con aspect-ratio (imágenes/logos), zoom (+/−/ajustar, ctrl+rueda, pinch), barra de
// acciones FLOTANTE sobre la capa seleccionada (alinear/orden/duplicar/borrar), edición de texto
// EN LÍNEA (doble clic) y atajos de teclado. Táctil de serie (Konva). El estado vive en el store.
//
// Este fichero es el componente PRINCIPAL: mantiene los refs del Stage/Transformer y la GLUE de
// composición (modo imagen, doble clic, acotar al marco), y COMPONE los hooks y sub-componentes
// extraídos a `editor/lienzo/`: zoom/pan, encuadre, recorte, edición en línea, inserción de
// imágenes, marquee, hover, etiqueta de gesto, recorte lateral, arrastre, atajos, las capas
// visuales (`CapaGuias`), el overlay de edición y la barra de acciones/controles de encuadre.

import Konva from "konva";
import { type ReactNode, useEffect, useRef } from "react";
import { Layer, Stage, Transformer } from "react-konva";
import { toast } from "sonner";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, CapaImagen } from "./documento";
import { decidirSeleccionClic } from "./store";
import { useEditor, useStoreEditor } from "./usarEditor";

import { useAccionesLienzo } from "./lienzo/accionesLienzo";
import { estiloAncla } from "./lienzo/anclas";
import { BannerRecorte, BannerReencuadre } from "./lienzo/BannersModo";
import { BarraAcciones } from "./lienzo/BarraAcciones";
import { CapaGuias } from "./lienzo/CapaGuias";
import { ControlesEncuadre } from "./lienzo/ControlesEncuadre";
import { CropOverlay } from "./lienzo/CropOverlay";
import { FondoNodo } from "./lienzo/FondoNodo";
import { RATIO_FIJO, acotarCajaTransformer, clampMarco, franjasZonaSegura } from "./lienzo/lib";
import { OverlayEdicionTexto } from "./lienzo/OverlayEdicionTexto";
import { RecorteCajaOverlay } from "./lienzo/RecorteCajaOverlay";
import { ReframeOverlay } from "./lienzo/ReframeOverlay";
import { useArrastreCapas } from "./lienzo/useArrastreCapas";
import { type LienzoApi, type ZoomApi, useAtajosTeclado } from "./lienzo/useAtajosTeclado";
import { useEdicionTexto } from "./lienzo/useEdicionTexto";
import { useEncuadre } from "./lienzo/useEncuadre";
import { useEtiquetaGesto } from "./lienzo/useEtiquetaGesto";
import { useGestoLateral } from "./lienzo/useGestoLateral";
import { useHover } from "./lienzo/useHover";
import { useModificadoresTransform } from "./lienzo/useModificadoresTransform";
import { useInsercionImagen } from "./lienzo/useInsercionImagen";
import { useMarquee } from "./lienzo/useMarquee";
import { useRecorte } from "./lienzo/useRecorte";
import { useZoomPan } from "./lienzo/useZoomPan";

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
  fondo,
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
  // Fondo OPCIONAL detrás del Stage: sustituye el tablero de transparencia (p. ej. el `<video>`
  // base en el Estudio de video, para editar las capas overlay DIRECTAMENTE sobre el vídeo). Se
  // pinta a tamaño del lienzo escalado; el Stage transparente lo deja ver. No afecta al export.
  fondo?: ReactNode;
}) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const { w, h } = documento.formato;
  // Los overlays HTML de recorte/reencuadre se posicionan SIN rotar y sus gestos van en ejes de
  // pantalla: con una imagen rotada el marco saldría descolocado y el arrastre movería en
  // diagonal cruzada. Hasta que resuelvan la rotación, esos modos solo se abren con rotación 0
  // (el gesto LATERAL del Transformer sí la resuelve, vía docALocal, y sigue disponible).
  const sinRotacion = (c: Capa) => ((c.rotacion % 360) + 360) % 360 === 0;
  // Capa en modo reencuadre (solo imágenes): arrastrar mueve el FOCO, la rueda hace ZOOM.
  const capaReencuadre = reencuadreId
    ? documento.capas.find((c) => c.id === reencuadreId && c.tipo === "imagen" && sinRotacion(c)) ?? null
    : null;
  // MODO RECORTE estilo Canva (prop O interno por doble clic) — hook con su sesión de historial.
  const { setRecorteInternoId, recorteActivoId, capaRecorte, confirmarRecorte, cancelarRecorte } = useRecorte({
    store,
    documento,
    recorteId,
    onSalirRecorte,
    capaReencuadre,
    sinRotacion,
  });
  // Cualquier modo de edición de imagen oculta los tiradores normales del Transformer.
  const modoImagen = capaReencuadre ?? capaRecorte;

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Selección DIFERIDA a clic-vs-arrastre: la selección de una capa se resuelve en `mousedown`, pero
  // los cambios que ROMPERÍAN un arrastre inmediato (quitar del grupo una capa ya seleccionada con
  // Shift, o colapsar una multi-selección a la capa clicada) se aplazan a `mouseup` SIN arrastre.
  // `null` = nada pendiente; `arrastroRef` marca que el gesto derivó en arrastre (cancela el clic).
  const clicSelRef = useRef<{ id: string; tipo: "quitar" | "colapsar" } | null>(null);
  const arrastroRef = useRef(false);
  // Etiquetas de DISTANCIA del imán/espaciado igual (px del documento) junto a las guías: overlay
  // HTML que el hook de arrastre muta directamente por frame (sin setState), como la etiqueta viva.
  const etiquetasImanRef = useRef<HTMLDivElement | null>(null);

  // Zoom + PAN (medida responsive, escala efectiva, ancla al cursor/centro, espacio/botón central).
  const {
    medirRef,
    baseFit,
    escala,
    zoom,
    acercar,
    alejar,
    ajustarPantalla,
    zoomReal,
    fijarEscala,
    onWheel,
    espacio,
    espacioRef,
    paneando,
    onMouseDownContenedor,
  } = useZoomPan({ w, h, maxAncho, maxAlto, scrollRef });

  // ENCUADRE: imán / rejilla (+ tamaño de celda) / dentro del marco / zonas seguras (prefs en LS).
  const { iman, setIman, grid, setGrid, tamCelda, setTamCelda, dentroMarco, setDentroMarco, zonas, setZonas, paso } =
    useEncuadre();
  // Márgenes (encuadre) del formato: lados con default 0 (retrocompat con formatos sin laterales).
  const safeTop = documento.formato.safe_top || 0;
  const safeBottom = documento.formato.safe_bottom || 0;
  const safeLeft = documento.formato.safe_left || 0;
  const safeRight = documento.formato.safe_right || 0;
  const hayMargenes = safeTop > 0 || safeBottom > 0 || safeLeft > 0 || safeRight > 0;
  // Franjas del overlay de zonas seguras (`null` si el formato no define ningún safe_* > 0: con
  // toggle activo pero formato sin zonas, no se pinta nada).
  const franjasZonas = zonas ? franjasZonaSegura(w, h, documento.formato) : null;

  // Publica el Stage + la escala al padre cuando cambian (para muestreo de píxeles externo).
  useEffect(() => {
    onStage?.(stageRef.current, escala);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escala, documento, onStage]);

  // Arrastre de capas con SMART GUIDES y movimiento en grupo: hook extraído (owns el ref multiDrag).
  // En multi-selección el imán actúa sobre la CAJA ENVOLVENTE del grupo (mismas guías y etiquetas).
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

  // Edición de texto EN LÍNEA WYSIWYG (doble clic): estado + manejadores (overlay en subcomponente).
  const { editando, textoEdit, setTextoEdit, abrirEdicionTexto, cerrarEdicion, ajustarAltoEdicion } = useEdicionTexto({
    store,
    documento,
    muestraCopy,
  });

  // API de zoom para los atajos de teclado, en un ref: el hook no se re-registra en cada render
  // pero siempre ejecuta los handlers frescos (con `baseFit`/`escala` actuales).
  const zoomApi = useRef<ZoomApi>({ acercar, alejar, ajustar: ajustarPantalla, real: zoomReal });
  zoomApi.current = { acercar, alejar, ajustar: ajustarPantalla, real: zoomReal };
  // Servicios del lienzo para los atajos de CREACIÓN (T/R/C/L), en un ref como `zoomApi`. Se
  // rellena más abajo, cuando ya existen `abrirEdicionTexto` y el contenedor de scroll.
  const lienzoApi = useRef<LienzoApi>({ centroViewport: () => ({ x: w / 2, y: h / 2 }), editarTexto: () => {} });

  // Centro del VIEWPORT visible en coords del documento (los elementos nuevos —atajos T/R/C/L,
  // pegado de imágenes— nacen ahí, no en 0,0). Sin medida aún => centro del lienzo.
  const centroViewport = () => {
    const cont = scrollRef.current;
    return cont && cont.clientWidth > 0
      ? { x: (cont.scrollLeft + cont.clientWidth / 2) / escala, y: (cont.scrollTop + cont.clientHeight / 2) / escala }
      : { x: w / 2, y: h / 2 };
  };
  lienzoApi.current = { centroViewport, editarTexto: abrirEdicionTexto };

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

  // Inserción de imágenes (portapapeles, arrastre del escritorio, activos de la galería): hook.
  const { onDrop } = useInsercionImagen({ store, documento, escala, w, h, scrollRef, lienzoApi });

  // Sale del modo de imagen activo: el recorte se CONFIRMA (como su botón "Hecho"); el reencuadre se
  // aplica en vivo, así que solo se cierra. Lo usa el marquee para "clicar fuera de la foto" y salir.
  const salirDeModoImagen = () => {
    if (capaRecorte) confirmarRecorte();
    else if (capaReencuadre) onSalirReencuadre?.();
  };

  // Selección por rectángulo (marquee) sobre el fondo vacío del Stage: hook.
  const { marquee, onMouseDownStage } = useMarquee({ stageRef, espacioRef, modoImagen, escala, store, salirDeModoImagen });

  // HOVER affordance (contorno fino de acento sobre la capa bajo el cursor antes de seleccionar).
  const { setHoverId, onMouseOverStage, hoverBox } = useHover({
    stageRef,
    espacioRef,
    modoImagen,
    documento,
    seleccionMulti,
    arrastrando,
    marquee,
    reencuadreId,
    recorteActivoId,
    espacio,
  });

  // Etiqueta VIVA del gesto del Transformer ("W × H px" / grados): hook (ref + mutación del DOM).
  const { etiquetaGestoRef, moverEtiquetaGesto, ocultarEtiquetaGesto } = useEtiquetaGesto({ trRef, stageRef, documento });

  // Recorte LATERAL estilo Canva (tiradores laterales del Transformer en imágenes): hook.
  const { iniciarGestoLateral, moverGestoLateral, finalizarGestoLateral } = useGestoLateral({
    trRef,
    stageRef,
    store,
    escala,
  });

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const capaSel = documento.capas.find((c) => c.id === seleccion) ?? null;
  // Ratio fijo si CUALQUIER seleccionada lo exige (imagen/logo), no solo la primaria: una
  // multi-selección con foto debe escalar proporcional aunque la última clicada sea un texto.
  const ratioFijo = seleccionMulti.some((id) => {
    const c = documento.capas.find((x) => x.id === id);
    return !!c && RATIO_FIJO.has(c.tipo);
  });
  // El grupo solo se mueve (resize/rotación se hacen desagrupando). Se mira TODA la selección
  // (no solo la primaria): un grupo colado en una multi-selección recibiría escala/rotación del
  // Transformer que su nodo (sin onTransformEnd) jamás hornearía en el documento — transform
  // fantasma que el export ignora y la recarga revierte.
  const hayGrupo = seleccionMulti.some((id) => documento.capas.find((c) => c.id === id)?.tipo === "grupo");
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

  // Shift = bloquear/liberar proporción; Alt = escalar desde el centro (mientras el Transformer
  // está activo). Vuelca los flags al nodo Konva por eventos de teclado (efímero, no toca el store).
  useModificadoresTransform({
    trRef,
    ratioBase: ratioFijo,
    activo: !modoImagen && seleccionMulti.length > 0,
  });

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
      // El overlay de recorte no resuelve rotación (ver `sinRotacion`): avisar en vez de abrir
      // un marco descolocado con gestos en ejes equivocados.
      if (!sinRotacion(c)) {
        toast.info("Para recortar, pon la rotación de la imagen a 0 (el recorte aún no rota).");
        return;
      }
      store.getState().seleccionar(id);
      setRecorteInternoId(id);
    }
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

  // SELECCIÓN al presionar una capa (`mousedown`/`tap`). Resuelve YA la selección necesaria para
  // arrastrar de inmediato, pero DIFIERE a un clic seco (mouseup sin arrastre) los cambios que
  // romperían un arrastre en grupo:
  //   · Shift/⌘-clic sobre una capa YA en la multi-selección: no la quita ahora (arrancar un
  //     shift-arrastre del grupo la sacaba antes de moverse); un clic seco sí la quita.
  //   · Clic seco sobre una capa que ya forma parte de una multi-selección: no colapsa el grupo a
  //     ella ahora (para poder arrastrar todo el grupo); un clic seco sí colapsa.
  const onSeleccionarCapa = (id: string, e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
    const add = "shiftKey" in e.evt && (e.evt.shiftKey || e.evt.metaKey || e.evt.ctrlKey);
    const st = store.getState();
    arrastroRef.current = false;
    const { inmediato, diferido } = decidirSeleccionClic(st.seleccionMulti, id, add);
    if (inmediato === "alternar") st.alternar(id);
    else if (inmediato === "seleccionar") st.seleccionar(id);
    clicSelRef.current = diferido;
  };

  // Aplica la selección diferida en un clic seco (mouseup/touchend sin que el gesto derivara en
  // arrastre). Tras un arrastre, `arrastroRef` está en true y aquí no se toca la selección.
  const resolverClicSeleccion = () => {
    const pend = clicSelRef.current;
    clicSelRef.current = null;
    if (!pend || arrastroRef.current) return;
    const st = store.getState();
    if (pend.tipo === "quitar") st.alternar(pend.id);
    else st.seleccionar(pend.id);
  };

  // Marca el gesto como ARRASTRE (cancela la selección diferida) y delega en el hook de arrastre.
  const onInicioArrastre = (e: Konva.KonvaEventObject<DragEvent>) => {
    arrastroRef.current = true;
    onDragStart(e);
  };

  const acciones = useAccionesLienzo({ store, seleccion, seleccionMulti });

  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-hidden">
    {/* Franja superior fija: aloja la barra CONTEXTUAL de la capa + la píldora de acciones ARRIBA
        de la imagen (fuera del lienzo), en un sitio estable que NO sigue a la selección —igual que
        la barra de zoom/encuadre va abajo—. La altura va reservada siempre para que el lienzo no
        se recoloque al aparecer/desaparecer la selección. */}
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
           // Con `fondo` (vídeo) detrás del Stage no se pinta el tablero: el vídeo es el fondo y el
           // Stage transparente lo deja ver. Sin `fondo`, tablero de ajedrez (GIMP/Adobe) donde el
           // documento es transparente. Solo editor; el PNG exportado es transparente.
           ...(fondo
             ? { backgroundColor: "#000" }
             : {
                 backgroundImage:
                   "linear-gradient(45deg,#c8c8c8 25%,transparent 25%),linear-gradient(-45deg,#c8c8c8 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#c8c8c8 75%),linear-gradient(-45deg,transparent 75%,#c8c8c8 75%)",
                 backgroundSize: "16px 16px",
                 backgroundPosition: "0 0,0 8px,8px -8px,-8px 0",
                 backgroundColor: "#fff",
               }),
         }}
       >
        {/* Fondo opcional (vídeo base): detrás del Stage, a tamaño del lienzo escalado. */}
        {fondo && (
          <div className="pointer-events-none absolute inset-0 overflow-hidden">{fondo}</div>
        )}
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
          onMouseUp={resolverClicSeleccion}
          onTouchEnd={resolverClicSeleccion}
          onMouseOver={onMouseOverStage}
          onMouseLeave={() => setHoverId(null)}
          onWheel={onWheel}
          onDblClick={onDobleClic}
          onDblTap={onDobleClic}
          onDragStart={onInicioArrastre}
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
                oculta={editando?.id === capa.id}
                onSelect={(e) => onSeleccionarCapa(capa.id, e)}
                onChange={(cambios) => store.getState().actualizar(capa.id, acotarCambios(capa, cambios))}
                onGesto={() => store.getState().comenzarGesto()}
              />
            ))}
          </Layer>
          <CapaGuias
            grid={grid}
            paso={paso}
            w={w}
            h={h}
            escala={escala}
            iman={iman}
            hayMargenes={hayMargenes}
            safeTop={safeTop}
            safeBottom={safeBottom}
            safeLeft={safeLeft}
            safeRight={safeRight}
            franjasZonas={franjasZonas}
            guias={guias}
            hoverBox={hoverBox}
            marquee={marquee}
          />
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled={!hayGrupo}
              resizeEnabled={!hayGrupo}
              // `keepRatio`/`centeredScaling` y los snaps de rotación los gobierna
              // `useModificadoresTransform` en vivo (Shift/Alt); aquí solo va el resto de la config.
              // Imágenes y logos: esquinas con proporción fija. Una imagen sola (no bloqueada)
              // gana además los LATERALES, que recortan en vez de estirar (gesto lateral arriba).
              enabledAnchors={
                hayGrupo
                  ? []
                  : lateralesImagen
                    ? ["top-left", "top-right", "bottom-left", "bottom-right", "middle-left", "middle-right", "top-center", "bottom-center"]
                    : ratioFijo
                      ? ["top-left", "top-right", "bottom-left", "bottom-right"]
                      : undefined
              }
              anchorStyleFunc={estiloAncla}
              ignoreStroke
              // Base sin Shift: snap SUAVE de la rotación a 0/45/90… (fuera del umbral gira libre).
              // Con Shift, `useModificadoresTransform` la restringe a incrementos de 15°.
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
                finalizarGestoLateral();
                ocultarEtiquetaGesto();
              }}
              // El clamp de tamaño mínimo solo aplica al REDIMENSIONAR; la rotación pasa siempre
              // (si no, una capa fina —línea/titular bajo— no podría girar desde el cuadrado).
              boundBoxFunc={(o, n) => acotarCajaTransformer(o, n, trRef.current?.getActiveAnchor() ?? null)}
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
        {capaRecorte && (capaRecorte.tipo === "imagen" ? (
          <CropOverlay
            capa={capaRecorte as CapaImagen}
            escala={escala}
            store={store}
            muestraFoto={muestraFoto}
          />
        ) : (
          // Objeto sin píxeles (forma, línea, logo): recorta el RECUADRO con tiradores.
          <RecorteCajaOverlay capa={capaRecorte} escala={escala} store={store} />
        ))}
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
        {/* Edición de texto en línea WYSIWYG (patrón Canva): subcomponente que vive dentro del
            TABLERO (px del canvas) para que el scroll lo arrastre consigo. */}
        {editando && (
          <OverlayEdicionTexto
            editando={editando}
            documento={documento}
            escala={escala}
            textoEdit={textoEdit}
            setTextoEdit={setTextoEdit}
            ajustarAltoEdicion={ajustarAltoEdicion}
            cerrarEdicion={cerrarEdicion}
          />
        )}
       </div>
      </div>

      {/* Banner de reencuadre. */}
      {capaReencuadre && <BannerReencuadre onListo={onSalirReencuadre} />}

      {/* Banner de recorte (estilo Canva): Hecho confirma (Enter), Cancelar restaura (Esc). */}
      {capaRecorte && <BannerRecorte onListo={confirmarRecorte} onCancelar={cancelarRecorte} />}

    </div>
    </div>

    {/* Controles de ENCUADRE + zoom: BARRA INFERIOR estilo Canva, a lo ancho del área del lienzo
        (debajo de la foto, no tapa el campo visual). Imán, rejilla (+ tamaño de celda), "dentro
        del marco" y "zonas seguras" son toggles INDEPENDIENTES; sus preferencias se guardan en
        localStorage. */}
    <ControlesEncuadre
      iman={iman}
      setIman={setIman}
      grid={grid}
      setGrid={setGrid}
      tamCelda={tamCelda}
      setTamCelda={setTamCelda}
      dentroMarco={dentroMarco}
      setDentroMarco={setDentroMarco}
      zonas={zonas}
      setZonas={setZonas}
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
