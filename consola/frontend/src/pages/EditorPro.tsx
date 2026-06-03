// Página del Editor profesional — WORKSPACE multi-marca.
//
// Cada PESTAÑA es un documento independiente (marca + RED) con su PROPIO store Zustand e historial,
// así editar la plantilla de UnoTV/Instagram no toca la de Claro Sports/X y no hay que cerrar una
// para abrir otra. Los stores persisten en un ref por id de pestaña.
//
// Las plantillas se guardan POR MARCA Y POR RED (la `categoria` de la plantilla es la red). Sin
// pestañas se muestra la GALERÍA de plantillas de la marca; si no hay ninguna, se abre un lienzo en
// blanco automáticamente. El tamaño/formato del lienzo se ajusta DENTRO del editor (Ajustes).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Plus, Save, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { documentoVacio, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, urlMedia, type PlantillaDiseno } from "@/lib/api";

// Dimensiones por defecto del lienzo (4:5, el post de noticias/deportes más común). El tamaño real
// se ajusta luego en «Ajustes del lienzo»; la red NO fija una dimensión rígida.
const DIMS_DEFECTO: Documento["formato"] = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

interface Pestana {
  id: string;
  marca: string;
  red: string;
  // Si la pestaña está anclada a una publicación (historial/versionado).
  contenido?: string;
  plataforma?: string;
}

let _seq = 0;

// Clave de autoguardado por pestaña: estable entre recargas (por pieza, o por marca+red).
function claveAuto(p: { marca: string; red: string; contenido?: string; plataforma?: string }): string {
  return p.contenido && p.plataforma
    ? `keni:editor:pieza:${p.contenido}:${p.plataforma}`
    : `keni:editor:doc:${p.marca}:${p.red}`;
}

function leerAuto(clave: string): Documento | null {
  try {
    const s = sessionStorage.getItem(clave);
    return s ? (JSON.parse(s) as Documento) : null;
  } catch {
    return null;
  }
}

export default function EditorPro() {
  const opciones = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];
  const redes = opciones.data?.redes ?? [];
  const redNombre = (id: string) => redes.find((r) => r.id === id)?.nombre ?? id;

  const { marcaActiva } = useMarcaActiva();
  const marcaInicial = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : marcas[0]?.id;

  const [searchParams] = useSearchParams();

  // Marca y red elegidas en la barra (para abrir pestaña nueva / ver su galería).
  const [marcaNueva, setMarcaNueva] = useState("");
  const [redNueva, setRedNueva] = useState("");

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [galeria, setGaleria] = useState(false);
  // Diálogo de nombre al guardar plantilla — in-app, no window.prompt.
  const [dialogo, setDialogo] = useState<{ nombre: string } | null>(null);

  const marcaEfectiva = marcaNueva || marcaInicial || "";
  const redEfectiva = redNueva || redes[0]?.id || "";

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;
  const marcaPanel = pestanaActiva?.marca || marcaEfectiva;

  const nuevaPestana = (marca: string, red: string, doc?: Documento, ancla?: { contenido: string; plataforma: string }): StoreEditor => {
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(doc ?? documentoVacio(DIMS_DEFECTO, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, red, ...ancla }]);
    setActiva(id);
    return store;
  };

  // Lienzo EN BLANCO de verdad: documento vacío (sin las capas de la plantilla de marca, que el
  // usuario tenía que borrar). Solo restaura un autoguardado previo de ese marca+red si existe.
  const abrirPestana = (marcaArg?: string, redArg?: string) => {
    const marca = marcaArg || marcaEfectiva;
    const red = redArg || redEfectiva;
    if (!marca) return;
    const store = nuevaPestana(marca, red);
    const guardado = leerAuto(claveAuto({ marca, red }));
    if (guardado) store.getState().cargar(guardado);
  };

  // Abre una plantilla guardada EN UNA PESTAÑA NUEVA (su red = categoria de la plantilla).
  const abrirPlantilla = (p: PlantillaDiseno) => {
    nuevaPestana(p.marca, p.categoria || redEfectiva, p.documento as Documento);
    setGaleria(false);
    toast.success(`Plantilla «${p.nombre}» abierta.`);
  };

  // Abre una pestaña ANCLADA a una publicación (su red = la plataforma de la pieza).
  const abrirPiezaTab = async (cid: string, pid: string, marca: string) => {
    const store = nuevaPestana(marca, pid, undefined, { contenido: cid, plataforma: pid });
    const guardado = leerAuto(claveAuto({ marca, red: pid, contenido: cid, plataforma: pid }));
    if (guardado) {
      store.getState().cargar(guardado);
      return;
    }
    try {
      const pieza = await api.editorPieza(cid, pid);
      if (pieza.documento) {
        store.getState().cargar(pieza.documento as Documento);
      } else {
        const res = await api.editorPlantilla(marca, "feed");
        store.getState().cargar(res.documento as Documento);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo abrir la pieza.");
    }
  };

  const qc = useQueryClient();

  // Plantillas de la marca de referencia (funciona SIN pestaña activa: la galería del estado vacío
  // las muestra y no se "pierden" al cerrar todas las pestañas).
  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", marcaPanel],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: marcaPanel || undefined }, signal),
    enabled: !!marcaPanel,
  });

  // Apertura inicial (una vez): pieza por URL → ancla; si no, con plantillas deja la GALERÍA; sin
  // ninguna abre un lienzo en blanco.
  const abiertoInicial = useRef(false);
  useEffect(() => {
    if (abiertoInicial.current) return;
    const cid = searchParams.get("contenido");
    const pid = searchParams.get("plataforma");
    if (cid && pid) {
      abiertoInicial.current = true;
      void abrirPiezaTab(cid, pid, searchParams.get("marca") || marcaInicial || "");
      return;
    }
    if (marcas.length === 0 || !plantillasQ.isSuccess) return;
    abiertoInicial.current = true;
    if ((plantillasQ.data?.plantillas.length ?? 0) === 0) {
      void abrirPestana(marcaInicial ?? marcas[0].id, redEfectiva);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, marcas, plantillasQ.isSuccess, plantillasQ.data]);

  const cerrarPestana = (id: string) => {
    stores.current.delete(id);
    setPestanas((p) => {
      const resto = p.filter((t) => t.id !== id);
      if (activa === id) setActiva(resto.length ? resto[resto.length - 1].id : null);
      return resto;
    });
  };

  const exportar = useMutation({
    mutationFn: () => {
      const store = activa ? stores.current.get(activa) : null;
      if (!store) throw new Error("No hay pestaña activa.");
      return api.editorRender(store.getState().documento);
    },
    onSuccess: (res) => {
      setExportUrl(`/api/media/${res.id}`);
      toast.success("PNG generado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo exportar."),
  });

  // AUTOGUARDADO: persiste el documento de la pestaña activa en sessionStorage (debounce 800 ms).
  const [guardado, setGuardado] = useState(true);
  useEffect(() => {
    if (!activa) return;
    const store = stores.current.get(activa);
    const p = pestanas.find((t) => t.id === activa);
    if (!store || !p) return;
    const clave = claveAuto(p);
    let timer: number | undefined;
    const unsub = store.subscribe((estado, previo) => {
      if (estado.documento === previo.documento) return;
      setGuardado(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        try {
          sessionStorage.setItem(clave, JSON.stringify(estado.documento));
          setGuardado(true);
        } catch {
          /* cuota llena: el trabajo sigue en memoria */
        }
      }, 800);
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, [activa, pestanas]);

  const guardarPlantilla = useMutation({
    mutationFn: async (nombre: string) => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const documento = storeActivo.getState().documento;
      let miniatura = "";
      try {
        miniatura = (await api.editorRender(documento)).id;
      } catch {
        /* sin miniatura: la galería muestra un marcador */
      }
      // La plantilla queda etiquetada por marca + RED (categoria = red).
      return api.crearPlantillaDiseno({ marca: pestanaActiva.marca, nombre, categoria: pestanaActiva.red, documento, miniatura });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla guardada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar."),
  });

  const cargarPlantillaEnActiva = (p: PlantillaDiseno) => {
    if (storeActivo) {
      storeActivo.getState().cargar(p.documento as Documento);
      toast.success(`Plantilla «${p.nombre}» cargada.`);
    }
  };

  const borrarPlantilla = useMutation({
    mutationFn: (id: string) => api.borrarPlantillaDiseno(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla borrada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo borrar."),
  });

  const confirmarNombre = () => {
    const nombre = dialogo?.nombre.trim();
    if (!nombre) return;
    guardarPlantilla.mutate(nombre);
    setDialogo(null);
  };

  // Guarda el documento en la PUBLICACIÓN anclada (render + versión + fija su imagen).
  const guardarEnPieza = useMutation({
    mutationFn: () => {
      if (!storeActivo || !pestanaActiva?.contenido || !pestanaActiva?.plataforma) {
        throw new Error("Esta pestaña no está anclada a una publicación.");
      }
      return api.editorPiezaGuardar(pestanaActiva.contenido, pestanaActiva.plataforma, storeActivo.getState().documento);
    },
    onSuccess: (res) => {
      setExportUrl(`/api/media/${res.id}`);
      toast.success(`Guardado en la pieza (v${res.version}).`);
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar en la pieza."),
  });

  const plantillas = plantillasQ.data?.plantillas ?? [];

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Barra superior: marca + red (a qué red diseñar) + acciones de pieza/plantilla + export. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <h1 className="mr-1 text-base font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marcaEfectiva} onCambio={setMarcaNueva} incluirTodas={false} />
        {redes.length > 0 && (
          <select
            value={redEfectiva}
            onChange={(e) => setRedNueva(e.target.value)}
            className="rounded border border-input bg-background px-2 py-1.5 text-sm"
            aria-label="Red"
            title="Red para la que diseñar la plantilla"
          >
            {redes.map((r) => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        )}
        {pestanaActiva && (
          <>
            <div className="mx-1 h-5 w-px bg-border" />
            {pestanaActiva.contenido && (
              <Button size="icon" disabled={guardarEnPieza.isPending} onClick={() => guardarEnPieza.mutate()} title="Guardar en la publicación">
                <FileUp className="h-4 w-4" />
              </Button>
            )}
            <Button size="icon" variant="outline" disabled={guardarPlantilla.isPending} onClick={() => setDialogo({ nombre: "" })} title="Guardar como plantilla">
              <Save className="h-4 w-4" />
            </Button>
          </>
        )}
        {pestanaActiva && (
          <span className="ml-auto text-xs text-muted-foreground" title="Autoguardado local">
            {guardado ? "Guardado ✓" : "Guardando…"}
          </span>
        )}
        {exportUrl && (
          <a href={exportUrl} target="_blank" rel="noreferrer" className="text-sm text-primary underline">
            Ver PNG exportado
          </a>
        )}
      </div>

      {/* Pestañas abiertas. El «+» (lienzo nuevo) solo aparece cuando ya hay alguna pestaña. */}
      {pestanas.length > 0 && (
        <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-muted/30 px-2">
          {pestanas.map((t) => {
            const marca = marcas.find((m) => m.id === t.marca)?.nombre ?? t.marca;
            return (
              <div
                key={t.id}
                className={`flex items-center gap-1 border-b-2 px-3 py-1.5 text-sm ${
                  t.id === activa ? "border-primary font-medium" : "border-transparent text-muted-foreground"
                }`}
              >
                <button onClick={() => setActiva(t.id)}>{marca} · {redNombre(t.red)}</button>
                <button onClick={() => cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
          <button
            onClick={() => abrirPestana()}
            disabled={!marcaEfectiva}
            title="Nuevo lienzo en blanco"
            className="ml-1 rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {pestanaActiva && storeActivo ? (
          <EditorDocumento
            key={pestanaActiva.id}
            store={storeActivo}
            marca={pestanaActiva.marca}
            onExportar={() => exportar.mutate()}
            onPlantillas={() => setGaleria(true)}
          />
        ) : (
          <GaleriaInline
            marca={marcas.find((m) => m.id === marcaPanel)?.nombre ?? marcaPanel}
            plantillas={plantillas}
            cargando={plantillasQ.isLoading}
            redNombre={redNombre}
            onAbrir={abrirPlantilla}
            onBorrar={(p) => borrarPlantilla.mutate(p.id)}
            onBlanco={() => abrirPestana()}
          />
        )}
      </div>

      {/* Galería modal: cambiar la plantilla de la pestaña ACTIVA (desde el rail). */}
      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillas}
          onCargar={(p) => { cargarPlantillaEnActiva(p); setGaleria(false); }}
          onBorrar={(p) => borrarPlantilla.mutate(p.id)}
          onCerrar={() => setGaleria(false)}
        />
      )}

      {/* Diálogo de nombre (in-app) para guardar plantilla. */}
      <Dialog open={!!dialogo} onOpenChange={(o) => !o && setDialogo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Guardar plantilla</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="Nombre de la plantilla"
            value={dialogo?.nombre ?? ""}
            onChange={(e) => setDialogo((d) => (d ? { nombre: e.target.value } : d))}
            onKeyDown={(e) => { if (e.key === "Enter") confirmarNombre(); }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(null)}>Cancelar</Button>
            <Button onClick={confirmarNombre} disabled={!dialogo?.nombre.trim()}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Galería del estado vacío: rejilla de plantillas (por marca, etiquetadas por red) + tarjeta de
// «lienzo en blanco» (único acceso a empezar de cero aquí).
function GaleriaInline({
  marca,
  plantillas,
  cargando,
  redNombre,
  onAbrir,
  onBorrar,
  onBlanco,
}: {
  marca: string;
  plantillas: PlantillaDiseno[];
  cargando: boolean;
  redNombre: (id: string) => string;
  onAbrir: (p: PlantillaDiseno) => void;
  onBorrar: (p: PlantillaDiseno) => void;
  onBlanco: () => void;
}) {
  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <h2 className="mb-3 text-sm font-semibold">Plantillas{marca ? ` · ${marca}` : ""}</h2>
      {cargando ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Cargando plantillas…</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          <button
            onClick={onBlanco}
            className="flex aspect-[4/5] flex-col items-center justify-center gap-1 rounded border border-dashed border-border text-xs text-muted-foreground hover:border-primary hover:text-foreground"
          >
            <Plus className="h-6 w-6" />
            Lienzo en blanco
          </button>
          {plantillas.map((p) => (
            <div key={p.id} className="group relative">
              <button
                onClick={() => onAbrir(p)}
                title={`Abrir «${p.nombre}»`}
                className="block w-full overflow-hidden rounded border border-border bg-muted/40 hover:ring-2 hover:ring-primary"
              >
                <div className="aspect-[4/5] w-full">
                  {p.miniatura ? (
                    <img src={urlMedia(p.miniatura)} alt={p.nombre} draggable={false} className="pointer-events-none h-full w-full object-contain" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">{redNombre(p.categoria)}</div>
                  )}
                </div>
                <div className="flex items-center justify-between gap-1 px-1.5 py-1 text-left">
                  <span className="truncate text-xs">{p.nombre || "(sin nombre)"}</span>
                  {p.categoria && <span className="shrink-0 rounded bg-muted px-1 text-[9px] uppercase text-muted-foreground">{redNombre(p.categoria)}</span>}
                </div>
              </button>
              <button
                onClick={() => onBorrar(p)}
                title="Borrar plantilla"
                className="absolute right-1 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
