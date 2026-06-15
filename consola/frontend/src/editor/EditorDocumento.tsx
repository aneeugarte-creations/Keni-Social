// Shell del editor (patrón Canva: lienzo protagonista, cromo a los lados):
//
//   cabecera del shell ←(portales)— centro: [deshacer/rehacer · muestra · Más] · derecha: [estado/guardar · Exportar]
//   [rail] [flyout?] [        LIENZO centrado         ] [inspector?]
//                    [barra contextual flotante (solo con selección)]
//
// - RAIL de herramientas: tira vertical de iconos (izquierda en escritorio, barra inferior en
//   móvil), orden estilo Canva: Diseño (plantillas) SIEMPRE primero, luego Elementos, Galería,
//   Marca (kit de identidad), Subidas (tus propias fotos) y Capas. Cada icono abre/cierra un
//   FLYOUT (~350px) con su panel y «Ajustes» abre el inspector.
//   Con puntero real (hover:hover) y sin `prefers-reduced-motion: reduce`, reposar ~200 ms
//   sobre un icono abre su panel SIN FIJAR (overlay); el clic lo fija; salir del rail+panel
//   sin fijar lo cierra a los ~300 ms.
//   «Diseño» pinta el panel que aporta la página (`panelDiseno`); si la página solo da
//   `onPlantillas` (overlay de vídeo), el botón cae al modal clásico.
// - ACCIONES: con `accionesEnCabecera` se PORTALIZAN a la barra de cabecera unificada del shell en
//   DOS portales (patrón Canva): las herramientas (deshacer/rehacer, vista con muestra, menú
//   «Más») al carril CENTRADO (`AccionesPagina`) y guardado/exportar al flanco DERECHO
//   (`AccionesPaginaFin`); sin ella (p. ej. overlay de vídeo) todo se pinta como una fila fina
//   propia. La página puede aportar `accionesInicio` (estado de guardado + guardar),
//   `accionesFin` (acción primaria contextual) y `menuExtra` (entradas para el menú «Más»).
// - BARRA CONTEXTUAL: controles de la capa seleccionada; FLOTA sobre el lienzo (franja reservada
//   del Lienzo, junto a alinear/orden/duplicar/borrar) y SOLO aparece con selección.
// - INSPECTOR: panel de ajustes profundos, desde «Ajustes» del rail o de la barra contextual
//   (columna derecha en escritorio, hoja inferior en móvil).
// - Flyout e inspector son UN solo elemento responsive: columna acoplada en `md+`, hoja inferior
//   en móvil (clases `max-md:`), con backdrop solo en móvil.

import type Konva from "konva";
import {
  ChevronDown,
  DollarSign,
  Eye,
  ImageOff,
  ImagePlay,
  LayoutTemplate,
  Layers,
  Image as ImageIcon,
  Maximize2,
  MoreHorizontal,
  Palette,
  Redo2,
  Settings2,
  Shapes,
  Type,
  Undo2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { AccionesPagina, AccionesPaginaFin } from "@/components/layout/encabezado";
import { confirmar } from "@/components/comunes/confirmar";

import { BarraContextual } from "./BarraContextual";
import { ExportarDialogo } from "./ExportarDialogo";
import { BotonesMuestra } from "./BotonesMuestra";
import { Lienzo } from "./Lienzo";
import { PanelGaleria } from "./PanelGaleria";
import { PanelMarca } from "./PanelMarca";
import { PanelSubidas } from "./PanelSubidas";
import { PanelElementos } from "./PanelElementos";
import { Inspector, PanelCapas } from "./Paneles";
import { adaptarDocumento } from "./adaptar";
import { ProveedorEditor } from "./contexto";
import type { Documento } from "./documento";
import { PRESETS_FORMATO, mismoFormato } from "./formatos";
import {
  analizarLegibilidad,
  correccionPara,
  muestreadorDeStage,
  type Correccion,
} from "./legibilidad";
import { suscribirMuestra } from "./muestra";
import type { StoreEditor } from "./store";
import { Telon, useCerrarConEscape } from "./Telon";
import { useFuentesMarca } from "./useFuentesMarca";

type Herramienta = "diseno" | "elementos" | "texto" | "marca" | "subidas" | "capas";

// Preferencias de "Vista con muestra" (toggles de PRESENTACIÓN del editor) en localStorage. Foto y
// copy son INDEPENDIENTES. Por defecto ENCENDIDOS: al abrir una plantilla se ve de inmediato cómo
// cae la foto y un titular real.
const CLAVE_MUESTRA_FOTO = "keni.editor.muestra.foto.on";
const CLAVE_MUESTRA_COPY = "keni.editor.muestra.copy.on";
function leerToggle(clave: string): boolean {
  try {
    const v = localStorage.getItem(clave);
    if (v === null) {
      const legado = localStorage.getItem("keni.editor.muestra");
      return legado === null ? true : legado === "1";
    }
    return v === "1";
  } catch {
    return true;
  }
}

// Hover del rail (patrón Canva): reposo que abre el panel sin fijar y gracia antes de cerrarlo.
const HOVER_ABRIR_MS = 200;
const HOVER_CERRAR_MS = 300;
/** ¿Hay puntero con hover real? (en táctil `hover: none` y el hover-para-abrir no aplica). */
function conHoverReal(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(hover: hover)").matches;
}
/** ¿El usuario pide movimiento reducido? Con `prefers-reduced-motion: reduce`, que un panel
 *  aparezca SOLO por reposar el puntero es movimiento no solicitado: el hover no abre nada
 *  (los paneles se abren únicamente por clic). */
function prefiereMenosMovimiento(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

const HERRAMIENTAS: { clave: Herramienta; etiqueta: string; Icono: typeof Shapes; costo?: boolean }[] = [
  // Orden Canva: «Diseño» (plantillas) SIEMPRE primero. Solo aparece si la página aporta
  // `panelDiseno` u `onPlantillas` (se filtra en el componente).
  { clave: "diseno", etiqueta: "Diseño", Icono: LayoutTemplate },
  { clave: "elementos", etiqueta: "Elementos", Icono: Shapes },
  // `clave: "texto"` es el id INTERNO del panel; la etiqueta visible es «Galería» (galería de
  // imágenes/activos de la marca), que es lo que de verdad es este panel.
  { clave: "texto", etiqueta: "Galería", Icono: ImageIcon },
  // «Marca» (Brand Kit estilo Canva): kit de identidad de la marca del documento a un clic
  // (logos + colores + tipografías). Tras Galería (orden Canva: …Texto, Marca…), antes de Capas.
  { clave: "marca", etiqueta: "Marca", Icono: Palette },
  // «Subidas» (patrón Canva): sube tus propias fotos y reutilízalas. Tras Marca, antes de Capas.
  { clave: "subidas", etiqueta: "Subidas", Icono: Upload },
  { clave: "capas", etiqueta: "Capas", Icono: Layers },
];

export function EditorDocumento({
  store,
  marca,
  exportar,
  onPlantillas,
  panelDiseno,
  avisaHueco,
  onAbrirAdaptado,
  accionesEnCabecera,
  accionesInicio,
  accionesFin,
  menuExtra,
}: {
  store: StoreEditor;
  marca: string;
  // Config de EXPORTACIÓN: presente => muestra el botón «Exportar» (diálogo de descarga con
  // formato/calidad/escala). Ausente (p. ej. overlay de vídeo) => sin botón de export.
  // `primario: false` lo degrada a botón secundario (cuando la acción primaria es otra, p. ej.
  // «Guardar en pieza»).
  exportar?: { bindings?: Record<string, string>; nombre?: string; primario?: boolean };
  onPlantillas?: () => void;
  // Panel «Diseño» del rail (galería de plantillas como COLUMNA, estilo Canva). Si está, el botón
  // «Diseño» abre este panel; si solo hay `onPlantillas`, cae al modal clásico (overlay de vídeo).
  panelDiseno?: ReactNode;
  // Si la pestaña está atada a plantilla, avisa cuando NO hay capa marcada como hueco de foto.
  avisaHueco?: boolean;
  // «Adaptar a…»: abre el documento reencuadrado en una pestaña nueva (lo cablea Imagen).
  onAbrirAdaptado?: (doc: Documento, nombre: string) => void;
  // PORTALIZA el clúster de acciones a la barra de cabecera del shell (`AccionesPagina`). Sin
  // esta prop el clúster se pinta como fila propia (overlay de vídeo, tests sueltos).
  accionesEnCabecera?: boolean;
  // Acciones de la PÁGINA al inicio del clúster (estado de guardado + guardar).
  accionesInicio?: ReactNode;
  // Acción primaria contextual de la página al FINAL del clúster (p. ej. «Guardar en pieza»).
  accionesFin?: ReactNode;
  // Entradas extra para el menú «Más» (terciarias de la página, p. ej. «Guardar como…»).
  menuExtra?: ReactNode;
}) {
  const fuentesExtra = useFuentesMarca(marca);
  // Stage de Konva + escala actual (publicados por el Lienzo) para muestrear píxeles (legibilidad).
  const stageInfo = useRef<{ stage: Konva.Stage | null; escala: number }>({ stage: null, escala: 1 });
  // Menú «Más…» (acciones secundarias plegadas: legibilidad + extras) abierto.
  const [menuMas, setMenuMas] = useState(false);
  // «Adaptar a otro formato» (el «Redimensionar» de Canva): control propio y visible en la barra,
  // ya no escondido en «Más». Abre un desplegable con los presets de formato.
  const [menuFormato, setMenuFormato] = useState(false);
  // Sin panel abierto al entrar: el lienzo se ve completo (en móvil un panel tapaba la mitad).
  const [tool, setTool] = useState<Herramienta | null>(null);
  // ¿El panel abierto está FIJADO (clic) o es un overlay de hover sin fijar? El clic siempre fija.
  const [fijado, setFijado] = useState(true);
  const [ajustes, setAjustes] = useState(false);
  // Capa de imagen a REENCUADRAR (B5), a RECORTAR (crop visual) y a REEMPLAZAR (clic en activo).
  const [reencuadreId, setReencuadreId] = useState<string | null>(null);
  const [recorteId, setRecorteId] = useState<string | null>(null);
  const [reemplazarId, setReemplazarId] = useState<string | null>(null);
  // "Vista con muestra": dos toggles INDEPENDIENTES de PRESENTACIÓN (foto y copy). NO mutan el
  // documento ni el export; solo el render del lienzo. Preferencias persistidas en localStorage.
  const [muestraFoto, setMuestraFoto] = useState(() => leerToggle(CLAVE_MUESTRA_FOTO));
  const [muestraCopy, setMuestraCopy] = useState(() => leerToggle(CLAVE_MUESTRA_COPY));
  useEffect(() => {
    try {
      localStorage.setItem(CLAVE_MUESTRA_FOTO, muestraFoto ? "1" : "0");
    } catch {
      /* almacenamiento no disponible: la preferencia no se persiste, sin romper. */
    }
  }, [muestraFoto]);
  useEffect(() => {
    try {
      localStorage.setItem(CLAVE_MUESTRA_COPY, muestraCopy ? "1" : "0");
    } catch {
      /* almacenamiento no disponible */
    }
  }, [muestraCopy]);

  const puedeDeshacer = store.getState().pasado.length > 0; // se refresca abajo con suscripción
  const [, force] = useState(0);
  useEffect(() => store.subscribe(() => force((n) => n + 1)), [store]);
  // Redibuja el lienzo cuando el equipo edita la foto/copy de muestra (estado fuera del store).
  useEffect(() => suscribirMuestra(() => force((n) => n + 1)), []);

  const seleccion = store.getState().seleccion;
  // Hueco de foto ausente: el componente se re-renderiza con cada cambio del store (suscripción
  // arriba), así el aviso aparece/desaparece al marcar una imagen como hueco.
  const faltaHueco =
    !!avisaHueco && !store.getState().documento.capas.some((c) => c.tipo === "imagen" && c.es_foto);

  // Herramientas visibles del rail: «Diseño» solo si la página aporta su panel o el modal clásico.
  const herramientas = HERRAMIENTAS.filter(
    (h) => h.clave !== "diseno" || panelDiseno !== undefined || onPlantillas !== undefined,
  );

  // ── HOVER DEL RAIL (patrón Canva, guía 1.3) ──────────────────────────────────────────────────
  // Reposar el puntero ~200 ms sobre un botón del rail con el panel cerrado ABRE su panel como
  // overlay SIN FIJAR; el clic lo fija (el toggle clásico queda intacto); salir del rail+panel sin
  // fijar lo cierra a los ~300 ms. Solo con puntero real (`hover: hover`): en táctil no hay hover.
  // Con `prefers-reduced-motion: reduce` el hover tampoco abre (solo clic): la aparición
  // espontánea de un panel es movimiento que el usuario pidió evitar. El flujo de teclado no
  // pasa por aquí (solo eventos de ratón).
  const timerAbrir = useRef<number | null>(null);
  const timerCerrar = useRef<number | null>(null);
  const cancelarAbrir = () => {
    if (timerAbrir.current !== null) {
      window.clearTimeout(timerAbrir.current);
      timerAbrir.current = null;
    }
  };
  const cancelarCierre = () => {
    if (timerCerrar.current !== null) {
      window.clearTimeout(timerCerrar.current);
      timerCerrar.current = null;
    }
  };
  useEffect(() => () => {
    cancelarAbrir();
    cancelarCierre();
  }, []);

  /** mouseenter en un botón del rail: arma la apertura sin fijar (si procede). */
  const hoverBoton = (t: Herramienta) => {
    cancelarCierre();
    cancelarAbrir();
    if (!conHoverReal()) return; // táctil/sin puntero: el hover no existe
    if (prefiereMenosMovimiento()) return; // movimiento reducido: los paneles solo se abren por clic
    if (t === "diseno" && panelDiseno === undefined) return; // el modal clásico NO se abre por hover
    if (tool === t) return; // ya abierto (fijado o no)
    if (tool !== null && fijado) return; // un panel fijado por clic no se cambia por hover
    timerAbrir.current = window.setTimeout(() => {
      timerAbrir.current = null;
      setTool(t);
      setFijado(false);
    }, HOVER_ABRIR_MS);
  };

  /** mouseleave del rail o del flyout: con panel sin fijar, arma el cierre diferido. */
  const hoverSalir = () => {
    cancelarAbrir();
    if (tool === null || fijado) return;
    cancelarCierre();
    timerCerrar.current = window.setTimeout(() => {
      timerCerrar.current = null;
      setTool(null);
    }, HOVER_CERRAR_MS);
  };

  // «Diseño» abre su PANEL si la página lo aporta; si solo hay `onPlantillas`, cae al modal.
  // El clic sobre el panel hover-abierto lo FIJA en vez de cerrarlo (toggle solo si está fijado).
  const pulsarTool = (t: Herramienta) => {
    cancelarAbrir();
    cancelarCierre();
    if (t === "diseno" && panelDiseno === undefined) return onPlantillas?.();
    if (tool === t && fijado) {
      setTool(null);
      return;
    }
    setTool(t);
    setFijado(true);
  };

  // ESCAPE cierra el overlay ABIERTO más "alto" (menú > flyout > inspector), esté donde
  // esté el foco. Los backdrops (`Telon`) cubren además teclado con foco en ellos.
  // CASCADA estilo Canva: con un modo de imagen activo o una capa seleccionada, ese Escape lo
  // consume el Lienzo (salir del modo → deseleccionar); los paneles solo se cierran en el
  // siguiente Escape. El menú «Más» sí se cierra siempre (es el overlay más alto).
  const seleccionActiva = !!seleccion || store.getState().seleccionMulti.length > 0;
  useCerrarConEscape(
    menuMas ||
      menuFormato ||
      ((tool !== null || ajustes) && !seleccionActiva && !reencuadreId && !recorteId),
    () => {
      if (menuMas) setMenuMas(false);
      else if (menuFormato) setMenuFormato(false);
      else if (tool !== null) setTool(null);
      else setAjustes(false);
    },
  );

  const abrirReencuadre = () => {
    const sel = store.getState().seleccion;
    if (sel) {
      setReencuadreId(sel);
      setRecorteId(null);
      setAjustes(false);
      setTool(null);
    }
  };
  // RECORTAR (crop visual con tiradores): entra al modo recorte sobre la capa imagen seleccionada.
  // Cierra los paneles (en móvil la hoja inferior tapaba el lienzo y el recorte no se veía).
  const abrirRecorte = () => {
    const sel = store.getState().seleccion;
    if (sel) {
      setRecorteId(sel);
      setReencuadreId(null);
      setAjustes(false);
      setTool(null);
    }
  };
  const abrirReemplazo = () => {
    const sel = store.getState().seleccion;
    if (sel) {
      setReemplazarId(sel);
      setTool("texto");
      setFijado(true); // apertura programática: cuenta como fijada (no la cierra el mouse-leave)
    }
  };

  // ADAPTAR a otro formato/red: genera el documento reencuadrado y lo abre en pestaña nueva.
  const adaptarA = (preset: (typeof PRESETS_FORMATO)[number]) => {
    setMenuFormato(false);
    const doc = store.getState().documento;
    const adaptado = adaptarDocumento(doc, preset.f);
    if (!onAbrirAdaptado) {
      // Sin callback (caso raro): al menos reformatea el documento actual.
      store.getState().cargar(adaptado);
      return;
    }
    const base = store.getState().documento.marca || marca || "Diseño";
    onAbrirAdaptado(adaptado, `${base} · ${preset.etiqueta}`);
    toast.success(`Adaptado a ${preset.nombre}. Revísalo en la pestaña nueva.`);
  };

  // REVISAR LEGIBILIDAD: muestrea el canvas bajo cada titular y arregla los que no llegan a AA.
  const revisarLegibilidad = async () => {
    const { stage, escala } = stageInfo.current;
    const doc = store.getState().documento;
    if (!stage) {
      toast.error("El lienzo aún no está listo. Inténtalo de nuevo.");
      return;
    }
    const muestrear = muestreadorDeStage(stage, escala);
    const malos = analizarLegibilidad(doc, muestrear);
    if (malos.length === 0) {
      toast.success("Todos los titulares tienen contraste suficiente (AA).");
      return;
    }
    const arreglar = await confirmar({
      titulo: "Legibilidad",
      mensaje: `${malos.length} ${malos.length === 1 ? "titular es poco legible" : "titulares son poco legibles"} sobre la foto. ¿Arreglar automáticamente (overlay/contorno/sombra)?`,
      textoConfirmar: "Arreglar",
    });
    if (!arreglar) return;
    const st = store.getState();
    st.comenzarGesto();
    const correcciones: Correccion[] = malos.map((d) => correccionPara(doc, d));
    for (const c of correcciones) {
      if (c.tipo === "overlay") st.agregar(c.capa);
      else st.actualizar(c.id, c.cambios, false);
    }
    toast.success(`Arreglado${malos.length > 1 ? "s" : ""} ${malos.length}.`);
  };

  const panel = (() => {
    switch (tool) {
      case "diseno": return panelDiseno ?? null;
      case "elementos": return <PanelElementos />;
      case "texto": return <PanelGaleria marca={marca} reemplazarId={reemplazarId} onReemplazado={() => setReemplazarId(null)} />;
      case "marca": return <PanelMarca marca={marca} />;
      case "subidas": return <PanelSubidas marca={marca} />;
      case "capas": return <PanelCapas />;
      default: return null;
    }
  })();
  const tituloTool = HERRAMIENTAS.find((h) => h.clave === tool)?.etiqueta ?? "";

  // ── CLÚSTER DE ACCIONES ─────────────────────────────────────────────────────────────────────
  // Dos piezas: HERRAMIENTAS (deshacer/rehacer · muestra (sm+) · «Más») y GUARDADO/EXPORTAR
  // ([página: estado+guardar] · Exportar · [página: primaria contextual]). Con
  // `accionesEnCabecera` cada pieza va a SU portal de la cabecera del shell (patrón Canva):
  // herramientas al carril CENTRADO (`AccionesPagina`) y guardado/exportar al flanco DERECHO,
  // junto al contexto de marca (`AccionesPaginaFin`). Sin cabecera (overlay de vídeo) se pinta
  // todo como una sola fila fina propia, en el orden de siempre.
  // Formato actual del lienzo (para el control «Adaptar»): su etiqueta corta (p. ej. «4:5») o
  // «Adaptar» si el lienzo no coincide con ningún preset. Se relee en cada render (suscrito al store).
  const presetActual = PRESETS_FORMATO.find((p) => mismoFormato(p.f, store.getState().documento.formato));
  const etiquetaFormato = presetActual?.etiqueta ?? "Adaptar";

  const botonesHerramientas = (
    <>
      <button
        title="Deshacer (⌘Z)"
        disabled={!puedeDeshacer}
        onClick={() => store.getState().deshacer()}
        className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent disabled:opacity-40"
      >
        <Undo2 className="h-4 w-4" />
      </button>
      <button
        title="Rehacer (⇧⌘Z)"
        disabled={store.getState().futuro.length === 0}
        onClick={() => store.getState().rehacer()}
        className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent disabled:opacity-40"
      >
        <Redo2 className="h-4 w-4" />
      </button>
      {/* VISTA CON MUESTRA — dos botones INDEPENDIENTES (foto/copy), editables. Solo presentación:
          no tocan el documento ni el export. En móvil viven dentro del menú «Más». */}
      <div className="hidden items-center sm:flex">
        <BotonesMuestra
          verFoto={muestraFoto}
          setVerFoto={setMuestraFoto}
          verCopy={muestraCopy}
          setVerCopy={setMuestraCopy}
        />
      </div>
      {/* ADAPTAR A OTRO FORMATO — el «Redimensionar» de Canva: control propio y VISIBLE (icono de
          redimensionar + formato actual), ya no escondido en «Más». Abre el desplegable de presets;
          cada uno reencuadra el documento y lo abre en una pestaña nueva.
          ABIERTO = píldora `--control-activo` (albaricoque clara con glifo negro en la barra del
          editor, como un hover sostenido; el accent normal fuera). Mismo lenguaje en «Más». */}
      <div className="relative">
        <button
          title="Adaptar a otro formato (story, feed, horizontal…)"
          aria-label="Adaptar a otro formato"
          aria-expanded={menuFormato}
          onClick={() => { setMenuMas(false); setMenuFormato((v) => !v); }}
          className={`flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm ${
            // Hover accent solo CERRADO: abierto conserva la píldora `--control-activo` (glifo legible).
            menuFormato
              ? "bg-[hsl(var(--control-activo))] text-[hsl(var(--control-activo-foreground))]"
              : "text-muted-foreground hover:bg-accent"
          }`}
        >
          <Maximize2 className="h-4 w-4" />
          <span className="hidden sm:inline">{etiquetaFormato}</span>
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
        {menuFormato && (
          <>
            <Telon
              onCerrar={() => setMenuFormato(false)}
              etiqueta="Cerrar adaptar a otro formato"
              className="fixed inset-0 z-30"
            />
            <div className="absolute right-0 top-full z-40 mt-1 w-56 overflow-hidden rounded-md border border-border bg-popover py-1 shadow-md">
              <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Adaptar a…
              </div>
              {PRESETS_FORMATO.map((p) => {
                const actual = mismoFormato(p.f, store.getState().documento.formato);
                return (
                  <button
                    key={p.etiqueta}
                    onClick={() => adaptarA(p)}
                    disabled={actual}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-40"
                  >
                    <span className="flex items-center gap-2">
                      <Maximize2 className="h-4 w-4 text-muted-foreground" /> {p.nombre}
                    </span>
                    {actual && <span className="text-[10px] text-muted-foreground">actual</span>}
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
      {/* MÁS — acciones secundarias/terciarias plegadas. */}
      <div className="relative">
        <button
          title="Más acciones"
          aria-label="Más acciones"
          aria-expanded={menuMas}
          onClick={() => { setMenuFormato(false); setMenuMas((v) => !v); }}
          className={`flex h-8 w-8 items-center justify-center rounded-md ${
            // Hover accent solo CERRADO: abierto conserva la píldora `--control-activo` (glifo legible).
            menuMas
              ? "bg-[hsl(var(--control-activo))] text-[hsl(var(--control-activo-foreground))]"
              : "text-muted-foreground hover:bg-accent"
          }`}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
        {menuMas && (
          <>
            <Telon
              onCerrar={() => setMenuMas(false)}
              etiqueta="Cerrar menú de más acciones"
              className="fixed inset-0 z-30"
            />
            <div className="absolute right-0 top-full z-40 mt-1 w-56 overflow-hidden rounded-md border border-border bg-popover py-1 shadow-md">
              {/* Entradas de la página (terciarias, p. ej. «Guardar como…»). Cierra el menú al
                  pulsar cualquiera (captura), sin que cada entrada tenga que hacerlo. */}
              {menuExtra && (
                <>
                  <div onClickCapture={() => setMenuMas(false)}>{menuExtra}</div>
                  <div className="my-1 border-t border-border" />
                </>
              )}
              {/* En móvil los toggles de muestra no caben en la cabecera: viven aquí. */}
              <div className="sm:hidden">
                <button
                  onClick={() => setMuestraFoto(!muestraFoto)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  <ImagePlay className="h-4 w-4 text-muted-foreground" />
                  Foto de muestra
                  <span className="ml-auto text-[10px] text-muted-foreground">{muestraFoto ? "Sí" : "No"}</span>
                </button>
                <button
                  onClick={() => setMuestraCopy(!muestraCopy)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  <Type className="h-4 w-4 text-muted-foreground" />
                  Copy de muestra
                  <span className="ml-auto text-[10px] text-muted-foreground">{muestraCopy ? "Sí" : "No"}</span>
                </button>
                <div className="my-1 border-t border-border" />
              </div>
              {/* Revisar legibilidad. */}
              <button
                onClick={() => { setMenuMas(false); void revisarLegibilidad(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <Eye className="h-4 w-4 text-muted-foreground" /> Revisar legibilidad
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );

  const exportarYFin = (
    <>
      {exportar && (
        <ExportarDialogo
          store={store}
          bindings={exportar.bindings}
          nombre={exportar.nombre}
          variante={exportar.primario === false ? "secundario" : "primario"}
        />
      )}
      {accionesFin}
    </>
  );

  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 w-full bg-background">
        {/* RAIL (escritorio: vertical izquierda), orden Canva: Diseño · Elementos · Galería ·
            Marca · Subidas · Capas. «Ajustes» (inspector) al fondo. */}
        <nav
          aria-label="Herramientas del editor"
          onMouseEnter={cancelarCierre}
          onMouseLeave={hoverSalir}
          className="hidden w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-muted/30 py-2 md:flex"
        >
          {herramientas.map((h) => (
            <RailBtn key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => pulsarTool(h.clave)} onHover={() => hoverBoton(h.clave)} />
          ))}
          <div className="mt-auto w-full">
            <RailBtn etiqueta="Ajustes" Icono={Settings2} activo={ajustes} onClick={() => setAjustes((v) => !v)} />
          </div>
        </nav>

        {/* FLYOUT del rail (columna en md+, hoja inferior en móvil). */}
        {tool && (
          <>
            <Telon
              onCerrar={() => setTool(null)}
              etiqueta="Cerrar panel de herramienta"
              className="fixed inset-0 z-20 bg-black/30 md:hidden"
            />
            {/* ~350px (patrón Canva) en escritorio; hoja inferior en móvil (colapso intacto).
                Hover: entrar cancela el cierre diferido; salir sin fijar lo arma; cualquier
                interacción dentro FIJA el panel (que no se esfume mientras se usa). */}
            <aside
              onMouseEnter={cancelarCierre}
              onMouseLeave={hoverSalir}
              onMouseDownCapture={() => setFijado(true)}
              className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-[calc(4rem_+_env(safe-area-inset-bottom))] max-md:top-auto max-md:h-[55vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-[350px] md:border-r">
              <div className="mx-auto mt-1.5 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/30 md:hidden" />
              <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
                <span className="text-sm font-semibold">{tituloTool}</span>
                <button onClick={() => setTool(null)} className="text-muted-foreground hover:text-foreground" title="Cerrar">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">{panel}</div>
            </aside>
          </>
        )}

        {/* COLUMNA CENTRAL: SOLO el lienzo (las acciones van arriba en la cabecera del shell, o en
            una fila fina si no hay cabecera). La barra contextual de la selección flota DENTRO del
            área del lienzo (franja reservada del Lienzo), así el lienzo no se recoloca al
            seleccionar. En móvil deja hueco inferior para el rail fijo (h-16). */}
        <div className="flex min-w-0 flex-1 flex-col max-md:pb-[calc(4rem_+_env(safe-area-inset-bottom))]">
          {accionesEnCabecera ? (
            <>
              <AccionesPagina>
                <div className="flex min-w-0 items-center gap-1">{botonesHerramientas}</div>
              </AccionesPagina>
              <AccionesPaginaFin>
                <div className="flex min-w-0 items-center gap-1">
                  {accionesInicio}
                  {exportarYFin}
                </div>
              </AccionesPaginaFin>
            </>
          ) : (
            <div className="flex items-center justify-end border-b border-border bg-background px-2 py-1">
              <div className="flex min-w-0 items-center gap-1">
                {accionesInicio}
                {botonesHerramientas}
                {exportarYFin}
              </div>
            </div>
          )}

          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-2 md:p-4">
            {/* Aviso de hueco de foto: chip flotante discreto, centrado, por encima de la
                barra inferior de zoom/encuadre (no roba una franja entera de cromo). */}
            {faltaHueco && (
              <div className="pointer-events-none absolute bottom-14 left-1/2 z-10 -translate-x-1/2">
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-700 shadow-sm dark:bg-amber-950 dark:text-amber-400">
                  <ImageOff className="h-3 w-3" />
                  Marca una imagen como «hueco de foto»
                </span>
              </div>
            )}
            <Lienzo
              reencuadreId={reencuadreId}
              onSalirReencuadre={() => setReencuadreId(null)}
              recorteId={recorteId}
              onSalirRecorte={() => setRecorteId(null)}
              muestraFoto={muestraFoto}
              muestraCopy={muestraCopy}
              onStage={(stage, escala) => { stageInfo.current = { stage, escala }; }}
              barraSeleccion={
                <BarraContextual
                  fuentesExtra={fuentesExtra}
                  onAbrirAjustes={() => setAjustes(true)}
                  onReencuadrar={abrirReencuadre}
                  onReemplazar={abrirReemplazo}
                />
              }
            />
          </div>
        </div>

        {/* INSPECTOR (ajustes profundos): columna derecha en md+, hoja inferior en móvil. */}
        {ajustes && (
          <>
            <Telon
              onCerrar={() => setAjustes(false)}
              etiqueta="Cerrar ajustes"
              className="fixed inset-0 z-20 bg-black/30 md:hidden"
            />
            <aside className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-[calc(4rem_+_env(safe-area-inset-bottom))] max-md:top-auto max-md:h-[55vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-[350px] md:border-l">
              <div className="mx-auto mt-1.5 h-1 w-10 shrink-0 rounded-full bg-muted-foreground/30 md:hidden" />
              <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
                <span className="text-sm font-semibold">{seleccion ? "Ajustes de la capa" : "Lienzo y fondo"}</span>
                <button onClick={() => setAjustes(false)} className="text-muted-foreground hover:text-foreground" title="Cerrar">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">
                <Inspector fuentesExtra={fuentesExtra} onRecortar={abrirRecorte} />
              </div>
            </aside>
          </>
        )}

        {/* RAIL móvil (barra inferior fija, respetando el safe-area del notch inferior). */}
        <nav aria-label="Herramientas del editor (móvil)" className={`fixed inset-x-0 bottom-0 z-30 grid h-[calc(4rem_+_env(safe-area-inset-bottom))] ${herramientas.length >= 6 ? "grid-cols-7" : herramientas.length >= 5 ? "grid-cols-6" : "grid-cols-5"} border-t border-border bg-background pb-[env(safe-area-inset-bottom)] md:hidden`}>
          {herramientas.map((h) => (
            <RailBtnMovil key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => pulsarTool(h.clave)} />
          ))}
          <RailBtnMovil etiqueta="Ajustes" Icono={Settings2} activo={ajustes} onClick={() => setAjustes((v) => !v)} />
        </nav>
      </div>
    </ProveedorEditor>
  );
}

function RailBtn({ etiqueta, Icono, activo, costo, onClick, onHover }: { etiqueta: string; Icono: typeof Shapes; activo?: boolean; costo?: boolean; onClick: () => void; onHover?: () => void }) {
  return (
    <button
      onClick={onClick}
      onMouseEnter={onHover}
      title={costo ? `${etiqueta} · usa IA con coste` : etiqueta}
      className={`flex w-full flex-col items-center gap-0.5 rounded-md py-2 text-[10px] transition-colors ${
        activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      <span className="relative">
        <Icono className="h-5 w-5" />
        {costo && <DollarSign className="absolute -right-2 -top-1 h-3 w-3 rounded-full bg-background" />}
      </span>
      {etiqueta}
    </button>
  );
}

function RailBtnMovil({ etiqueta, Icono, activo, costo, onClick }: { etiqueta: string; Icono: typeof Shapes; activo?: boolean; costo?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center justify-center gap-0.5 text-[10px] ${activo ? "text-primary" : "text-muted-foreground"}`}
    >
      <span className="relative">
        <Icono className="h-5 w-5" />
        {costo && <DollarSign className="absolute -right-2 -top-1 h-3 w-3 rounded-full bg-background" />}
      </span>
      {etiqueta}
    </button>
  );
}
