// Shell del editor (patrón Canva/Polotno, mobile-first):
//
//   [rail] [flyout?] [ barra contextual + acciones ]   [inspector?]
//                    [          LIENZO            ]
//
// - RAIL de herramientas: tira vertical de iconos (izquierda en escritorio, barra inferior en
//   móvil). Cada icono abre/cierra un FLYOUT con su panel (Elementos, Texto, IA, Capas).
// - BARRA CONTEXTUAL: controles rápidos de la capa seleccionada; a su derecha, deshacer/rehacer y
//   exportar (siempre visibles).
// - INSPECTOR: panel de ajustes profundos, se abre desde «Ajustes» (columna derecha en escritorio,
//   hoja inferior en móvil).
// - Flyout e inspector son UN solo elemento responsive: columna acoplada en `md+`, hoja inferior
//   en móvil (clases `max-md:`), con backdrop solo en móvil.

import type Konva from "konva";
import {
  DollarSign,
  Eye,
  ImageOff,
  LayoutTemplate,
  Layers,
  Image as ImageIcon,
  Maximize2,
  MoreHorizontal,
  Redo2,
  Shapes,
  Undo2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { BarraContextual } from "./BarraContextual";
import { ExportarDialogo } from "./ExportarDialogo";
import { BotonesMuestra } from "./BotonesMuestra";
import { Lienzo } from "./Lienzo";
import { PanelGaleria } from "./PanelGaleria";
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

// El generador de IA NO va en el editor: era solo para las imágenes del feed (sobra aquí).
type Herramienta = "elementos" | "texto" | "capas";

// Preferencias de "Vista con muestra" (toggles de PRESENTACIÓN del editor) en localStorage. Foto y
// copy son INDEPENDIENTES. Por defecto ENCENDIDOS: al abrir una plantilla se ve de inmediato cómo
// cae la foto y un titular real.
const CLAVE_MUESTRA_FOTO = "keni.editor.muestra.foto.on";
const CLAVE_MUESTRA_COPY = "keni.editor.muestra.copy.on";
function leerToggle(clave: string): boolean {
  try {
    const v = localStorage.getItem(clave);
    // Migración: si no hay valor propio, hereda la antigua clave única `keni.editor.muestra`.
    if (v === null) {
      const legado = localStorage.getItem("keni.editor.muestra");
      return legado === null ? true : legado === "1";
    }
    return v === "1";
  } catch {
    return true;
  }
}

const HERRAMIENTAS: { clave: Herramienta; etiqueta: string; Icono: typeof Shapes; costo?: boolean }[] = [
  { clave: "elementos", etiqueta: "Elementos", Icono: Shapes },
  // `clave: "texto"` es el id INTERNO histórico del panel (antes «Biblioteca»); la etiqueta visible
  // es «Galería» (galería de imágenes/activos de la marca), que es lo que de verdad es este panel.
  { clave: "texto", etiqueta: "Galería", Icono: ImageIcon },
  { clave: "capas", etiqueta: "Capas", Icono: Layers },
];

export function EditorDocumento({
  store,
  marca,
  exportar,
  onPlantillas,
  avisaHueco,
  onAbrirAdaptado,
}: {
  store: StoreEditor;
  marca: string;
  // Config de EXPORTACIÓN: presente => muestra el botón «Exportar» (diálogo de descarga con
  // formato/calidad/escala). Ausente (p. ej. overlay de vídeo) => sin botón de export.
  exportar?: { bindings?: Record<string, string>; nombre?: string };
  onPlantillas?: () => void;
  // Si la pestaña está atada a plantilla, avisa cuando NO hay capa marcada como hueco de foto.
  avisaHueco?: boolean;
  // «Adaptar a…»: abre el documento reencuadrado en una pestaña nueva (lo cablea Imagen).
  onAbrirAdaptado?: (doc: Documento, nombre: string) => void;
}) {
  const fuentesExtra = useFuentesMarca(marca);
  // Stage de Konva + escala actual (publicados por el Lienzo) para muestrear píxeles (legibilidad).
  const stageInfo = useRef<{ stage: Konva.Stage | null; escala: number }>({ stage: null, escala: 1 });
  // Menú «Más…» (acciones secundarias plegadas: adaptar + legibilidad) abierto.
  const [menuMas, setMenuMas] = useState(false);
  // Sin panel abierto al entrar: el lienzo se ve completo (en móvil un panel tapaba la mitad).
  const [tool, setTool] = useState<Herramienta | null>(null);
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

  const abrirTool = (t: Herramienta) => setTool((prev) => (prev === t ? null : t));

  // ESCAPE cierra el overlay ABIERTO más "alto" (menú > flyout > inspector), esté donde
  // esté el foco. Los backdrops (`Telon`) cubren además teclado con foco en ellos.
  useCerrarConEscape(menuMas || tool !== null || ajustes, () => {
    if (menuMas) setMenuMas(false);
    else if (tool !== null) setTool(null);
    else setAjustes(false);
  });

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
    }
  };

  // ADAPTAR a otro formato/red: genera el documento reencuadrado y lo abre en pestaña nueva.
  const adaptarA = (preset: (typeof PRESETS_FORMATO)[number]) => {
    setMenuMas(false);
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
  const revisarLegibilidad = () => {
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
    const arreglar = window.confirm(
      `${malos.length} ${malos.length === 1 ? "titular es poco legible" : "titulares son poco legibles"} sobre la foto. ¿Arreglar automáticamente (overlay/contorno/sombra)?`,
    );
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
      case "elementos": return <PanelElementos />;
      case "texto": return <PanelGaleria marca={marca} reemplazarId={reemplazarId} onReemplazado={() => setReemplazarId(null)} />;
      case "capas": return <PanelCapas />;
      default: return null;
    }
  })();
  const tituloTool = HERRAMIENTAS.find((h) => h.clave === tool)?.etiqueta ?? "";

  return (
    <ProveedorEditor store={store}>
      <div className="flex h-full min-h-0 w-full bg-background">
        {/* RAIL (escritorio: vertical izquierda). */}
        <nav className="hidden w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-muted/30 py-2 md:flex">
          {onPlantillas && (
            <RailBtn etiqueta="Plantillas" Icono={LayoutTemplate} onClick={onPlantillas} />
          )}
          {HERRAMIENTAS.map((h) => (
            <RailBtn key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => abrirTool(h.clave)} />
          ))}
        </nav>

        {/* FLYOUT del rail (columna en md+, hoja inferior en móvil). */}
        {tool && (
          <>
            <Telon
              onCerrar={() => setTool(null)}
              etiqueta="Cerrar panel de herramienta"
              className="fixed inset-0 z-20 bg-black/30 md:hidden"
            />
            <aside className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-[calc(4rem_+_env(safe-area-inset-bottom))] max-md:top-auto max-md:h-[55vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-72 md:border-r">
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

        {/* COLUMNA CENTRAL: barra contextual + acciones + lienzo. En móvil deja hueco inferior
            para que el rail fijo (h-16) no tape el lienzo. */}
        <div className="flex min-w-0 flex-1 flex-col max-md:pb-[calc(4rem_+_env(safe-area-inset-bottom))]">
          <div className="flex items-stretch border-b border-border">
            <div className="min-w-0 flex-1">
              <BarraContextual
                fuentesExtra={fuentesExtra}
                onAbrirAjustes={() => setAjustes(true)}
                onReencuadrar={abrirReencuadre}
                onReemplazar={abrirReemplazo}
              />
            </div>
            <div className="flex shrink-0 items-center gap-1 border-l border-border bg-background px-2">
              {faltaHueco && (
                <span
                  title="Marca una imagen como «hueco de foto» para que el equipo coloque la foto real."
                  className="mr-1 hidden items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 sm:inline-flex dark:bg-amber-950 dark:text-amber-400"
                >
                  <ImageOff className="h-3 w-3" />
                  Falta hueco de foto
                </span>
              )}
              {/* VISTA CON MUESTRA — dos botones INDEPENDIENTES (foto/copy), editables. Solo
                  presentación: no tocan el documento ni el export. */}
              <BotonesMuestra
                verFoto={muestraFoto}
                setVerFoto={setMuestraFoto}
                verCopy={muestraCopy}
                setVerCopy={setMuestraCopy}
              />
              {/* MÁS — acciones secundarias plegadas (adaptar a otra red + revisar legibilidad). */}
              <div className="relative">
                <button
                  title="Más acciones"
                  aria-label="Más acciones"
                  aria-expanded={menuMas}
                  onClick={() => setMenuMas((v) => !v)}
                  className={`flex items-center rounded-md p-1.5 hover:bg-accent ${
                    menuMas ? "bg-accent text-foreground" : "text-muted-foreground"
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
                      {/* Revisar legibilidad. */}
                      <button
                        onClick={() => { setMenuMas(false); revisarLegibilidad(); }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                      >
                        <Eye className="h-4 w-4 text-muted-foreground" /> Revisar legibilidad
                      </button>
                      <div className="my-1 border-t border-border" />
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
              <button
                title="Deshacer (⌘Z)"
                disabled={!puedeDeshacer}
                onClick={() => store.getState().deshacer()}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                title="Rehacer (⇧⌘Z)"
                disabled={store.getState().futuro.length === 0}
                onClick={() => store.getState().rehacer()}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
              >
                <Redo2 className="h-4 w-4" />
              </button>
              {exportar && (
                <ExportarDialogo store={store} bindings={exportar.bindings} nombre={exportar.nombre} />
              )}
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-2 md:p-4">
            <Lienzo
              reencuadreId={reencuadreId}
              onSalirReencuadre={() => setReencuadreId(null)}
              recorteId={recorteId}
              onSalirRecorte={() => setRecorteId(null)}
              muestraFoto={muestraFoto}
              muestraCopy={muestraCopy}
              onStage={(stage, escala) => { stageInfo.current = { stage, escala }; }}
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
            <aside className="z-30 flex flex-col overflow-hidden border-border bg-background max-md:fixed max-md:inset-x-0 max-md:bottom-[calc(4rem_+_env(safe-area-inset-bottom))] max-md:top-auto max-md:h-[55vh] max-md:rounded-t-xl max-md:border-t max-md:shadow-2xl md:relative md:w-72 md:border-l">
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
        <nav className="fixed inset-x-0 bottom-0 z-30 grid h-[calc(4rem_+_env(safe-area-inset-bottom))] grid-cols-5 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] md:hidden">
          {onPlantillas && <RailBtnMovil etiqueta="Plantillas" Icono={LayoutTemplate} onClick={onPlantillas} />}
          {HERRAMIENTAS.map((h) => (
            <RailBtnMovil key={h.clave} etiqueta={h.etiqueta} Icono={h.Icono} costo={h.costo} activo={tool === h.clave} onClick={() => abrirTool(h.clave)} />
          ))}
        </nav>
      </div>
    </ProveedorEditor>
  );
}

function RailBtn({ etiqueta, Icono, activo, costo, onClick }: { etiqueta: string; Icono: typeof Shapes; activo?: boolean; costo?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
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
