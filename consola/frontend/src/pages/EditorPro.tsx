// Página del Editor profesional — WORKSPACE multi-marca.
//
// Cada PESTAÑA es un documento independiente (marca + formato) con su PROPIO store Zustand e
// historial, así editar la plantilla de UnoTV no toca la de Claro Sports y no hay que cerrar una
// para abrir otra. Los stores persisten en un ref por id de pestaña: cambiar de pestaña conserva
// las ediciones (no recarga la plantilla).
//
// SIN pestañas se muestra la GALERÍA de plantillas de la marca (o, si no hay ninguna, se abre una
// pestaña en blanco automáticamente). El tamaño/formato se elige DENTRO del editor (Ajustes del
// lienzo), no aquí: la barra superior queda mínima.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Package, Plus, Save, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { documentoVacio, type Capa, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, urlMedia, type PlantillaDiseno } from "@/lib/api";

const DIMS: Record<string, Documento["formato"]> = {
  vertical: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 },
  feed: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 },
  cuadrado: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 },
  horizontal: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 },
};
const FORMATO_DEFECTO = "feed";

interface Pestana {
  id: string;
  marca: string;
  formato: string;
  // Si la pestaña está anclada a una publicación (historial/versionado).
  contenido?: string;
  plataforma?: string;
}

let _seq = 0;

// Clave de autoguardado por pestaña: estable entre recargas (por pieza, o por marca+formato).
function claveAuto(p: { marca: string; formato: string; contenido?: string; plataforma?: string }): string {
  return p.contenido && p.plataforma
    ? `keni:editor:pieza:${p.contenido}:${p.plataforma}`
    : `keni:editor:doc:${p.marca}:${p.formato}`;
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
  // Marca activa del workspace: default al abrir una pieza/pestaña nueva.
  const { marcaActiva } = useMarcaActiva();
  const marcaInicial = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : marcas[0]?.id;

  const [searchParams] = useSearchParams();

  // Marca elegida en la barra (para abrir pestaña nueva / ver su galería).
  const [marcaNueva, setMarcaNueva] = useState("");

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  // Stores por pestaña (persisten entre cambios de pestaña).
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [galeria, setGaleria] = useState(false);
  // Diálogo de nombre (guardar plantilla / bloque) — in-app, no window.prompt.
  const [dialogo, setDialogo] = useState<{ tipo: "plantilla" | "bloque"; nombre: string } | null>(null);

  const marcaEfectiva = marcaNueva || marcaInicial || "";

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;
  // Marca de referencia para galería/bloques: la de la pestaña, o la elegida en la barra.
  const marcaPanel = pestanaActiva?.marca || marcaEfectiva;

  const nuevaPestana = (marca: string, formato: string, doc?: Documento, ancla?: { contenido: string; plataforma: string }): StoreEditor => {
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(doc ?? documentoVacio(DIMS[formato] ?? DIMS.feed, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, formato, ...ancla }]);
    setActiva(id);
    return store;
  };

  const abrirPestana = async (marcaArg?: string, formatoArg?: string) => {
    const marca = marcaArg || marcaEfectiva;
    const formato = formatoArg || FORMATO_DEFECTO;
    if (!marca) return;
    const store = nuevaPestana(marca, formato);
    const guardado = leerAuto(claveAuto({ marca, formato }));
    if (guardado) {
      store.getState().cargar(guardado);
      return;
    }
    try {
      const res = await api.editorPlantilla(marca, formato);
      store.getState().cargar(res.documento as Documento);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo cargar la plantilla.");
    }
  };

  // Abre una plantilla de diseño guardada EN UNA PESTAÑA NUEVA.
  const abrirPlantilla = (p: PlantillaDiseno) => {
    nuevaPestana(p.marca, p.categoria || FORMATO_DEFECTO, p.documento as Documento);
    setGaleria(false);
    toast.success(`Plantilla «${p.nombre}» abierta.`);
  };

  // Abre una pestaña ANCLADA a una publicación.
  const abrirPiezaTab = async (cid: string, pid: string, marca: string, formato: string) => {
    const store = nuevaPestana(marca, formato, undefined, { contenido: cid, plataforma: pid });
    const guardado = leerAuto(claveAuto({ marca, formato, contenido: cid, plataforma: pid }));
    if (guardado) {
      store.getState().cargar(guardado);
      return;
    }
    try {
      const pieza = await api.editorPieza(cid, pid);
      if (pieza.documento) {
        store.getState().cargar(pieza.documento as Documento);
      } else {
        const res = await api.editorPlantilla(marca, formato);
        store.getState().cargar(res.documento as Documento);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo abrir la pieza.");
    }
  };

  const qc = useQueryClient();

  // Plantillas de diseño de la marca de referencia (funciona SIN pestaña activa: así la galería del
  // estado vacío las muestra y no se "pierden" al cerrar todas las pestañas).
  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", marcaPanel],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: marcaPanel || undefined }, signal),
    enabled: !!marcaPanel,
  });

  // Apertura inicial (una vez): pieza por URL → ancla; si no, espera a saber si la marca tiene
  // plantillas: con plantillas deja la GALERÍA (estado vacío); sin ninguna abre lienzo en blanco.
  const abiertoInicial = useRef(false);
  useEffect(() => {
    if (abiertoInicial.current) return;
    const cid = searchParams.get("contenido");
    const pid = searchParams.get("plataforma");
    if (cid && pid) {
      abiertoInicial.current = true;
      const marca = searchParams.get("marca") || marcaInicial || "";
      void abrirPiezaTab(cid, pid, marca, searchParams.get("formato") || FORMATO_DEFECTO);
      return;
    }
    if (marcas.length === 0 || !plantillasQ.isSuccess) return;
    abiertoInicial.current = true;
    if ((plantillasQ.data?.plantillas.length ?? 0) === 0) {
      void abrirPestana(marcaInicial ?? marcas[0].id);
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
      return api.crearPlantillaDiseno({ marca: pestanaActiva.marca, nombre, categoria: pestanaActiva.formato, documento, miniatura });
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

  // Almacén de bloques (capas reutilizables) de la marca de referencia.
  const bloquesQ = useQuery({
    queryKey: ["bloques", marcaPanel],
    queryFn: ({ signal }) => api.bloques({ marca: marcaPanel || undefined }, signal),
    enabled: !!marcaPanel,
  });

  const guardarBloque = useMutation({
    mutationFn: (nombre: string) => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const st = storeActivo.getState();
      const capa = st.documento.capas.find((c) => c.id === st.seleccion);
      if (!capa) throw new Error("Selecciona una capa para guardarla como bloque.");
      return api.crearBloque({ marca: pestanaActiva.marca, nombre, capas: [capa] });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bloques"] });
      toast.success("Bloque guardado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar el bloque."),
  });

  const insertarBloque = (id: string) => {
    const b = bloquesQ.data?.bloques.find((x) => x.id === id);
    if (b && storeActivo) {
      storeActivo.getState().insertarBloque(b.capas as Capa[]);
      toast.success(`Bloque «${b.nombre}» insertado.`);
    }
  };

  // Abre el diálogo de nombre para guardar plantilla/bloque (valida selección para bloque).
  const pedirNombre = (tipo: "plantilla" | "bloque") => {
    if (tipo === "bloque") {
      const st = storeActivo?.getState();
      if (!st || !st.documento.capas.find((c) => c.id === st.seleccion)) {
        toast.error("Selecciona una capa para guardarla como bloque.");
        return;
      }
    }
    setDialogo({ tipo, nombre: "" });
  };

  const confirmarNombre = () => {
    if (!dialogo) return;
    const nombre = dialogo.nombre.trim();
    if (!nombre) return;
    if (dialogo.tipo === "plantilla") guardarPlantilla.mutate(nombre);
    else guardarBloque.mutate(nombre);
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

  const bloques = bloquesQ.data?.bloques ?? [];
  const plantillas = plantillasQ.data?.plantillas ?? [];

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Barra superior MÍNIMA: marca + (acciones de pieza/plantilla como iconos) + export. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <h1 className="mr-1 text-base font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marcaEfectiva} onCambio={setMarcaNueva} incluirTodas={false} />
        {pestanaActiva && (
          <>
            <div className="mx-1 h-5 w-px bg-border" />
            {pestanaActiva.contenido && (
              <Button size="icon" variant="default" disabled={guardarEnPieza.isPending} onClick={() => guardarEnPieza.mutate()} title="Guardar en la publicación">
                <FileUp className="h-4 w-4" />
              </Button>
            )}
            <Button size="icon" variant="outline" disabled={guardarPlantilla.isPending} onClick={() => pedirNombre("plantilla")} title="Guardar como plantilla">
              <Save className="h-4 w-4" />
            </Button>
            <Button size="icon" variant="outline" disabled={guardarBloque.isPending} onClick={() => pedirNombre("bloque")} title="Guardar la capa seleccionada como bloque">
              <Package className="h-4 w-4" />
            </Button>
            {bloques.length > 0 && (
              <select
                value=""
                onChange={(e) => { if (e.target.value) insertarBloque(e.target.value); }}
                className="rounded border border-input bg-background px-2 py-1.5 text-sm"
                aria-label="Insertar bloque"
              >
                <option value="">Insertar bloque…</option>
                {bloques.map((b) => (
                  <option key={b.id} value={b.id}>{b.nombre || "(sin nombre)"}</option>
                ))}
              </select>
            )}
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

      {/* Pestañas abiertas + botón «nueva pestaña» (icono). */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-muted/30 px-2">
        {pestanas.map((t) => {
          const nombre = marcas.find((m) => m.id === t.marca)?.nombre ?? t.marca;
          return (
            <div
              key={t.id}
              className={`flex items-center gap-1 border-b-2 px-3 py-1.5 text-sm ${
                t.id === activa ? "border-primary font-medium" : "border-transparent text-muted-foreground"
              }`}
            >
              <button onClick={() => setActiva(t.id)}>{nombre} · {t.formato}</button>
              <button onClick={() => cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
        <button
          onClick={() => abrirPestana()}
          disabled={!marcaEfectiva}
          title="Nueva pestaña en blanco"
          className="ml-1 rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {pestanaActiva && storeActivo ? (
          <EditorDocumento
            key={pestanaActiva.id}
            store={storeActivo}
            marca={pestanaActiva.marca}
            formato={pestanaActiva.formato}
            onExportar={() => exportar.mutate()}
            onPlantillas={() => setGaleria(true)}
          />
        ) : (
          // ESTADO VACÍO: galería de plantillas de la marca + lienzo en blanco.
          <GaleriaInline
            marca={marcas.find((m) => m.id === marcaPanel)?.nombre ?? marcaPanel}
            plantillas={plantillas}
            cargando={plantillasQ.isLoading}
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

      {/* Diálogo de nombre (in-app) para guardar plantilla / bloque. */}
      <Dialog open={!!dialogo} onOpenChange={(o) => !o && setDialogo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{dialogo?.tipo === "bloque" ? "Guardar bloque" : "Guardar plantilla"}</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder={dialogo?.tipo === "bloque" ? "Nombre del bloque" : "Nombre de la plantilla"}
            value={dialogo?.nombre ?? ""}
            onChange={(e) => setDialogo((d) => (d ? { ...d, nombre: e.target.value } : d))}
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

// Galería del estado vacío: una rejilla de plantillas + tarjeta de «lienzo en blanco».
function GaleriaInline({
  marca,
  plantillas,
  cargando,
  onAbrir,
  onBorrar,
  onBlanco,
}: {
  marca: string;
  plantillas: PlantillaDiseno[];
  cargando: boolean;
  onAbrir: (p: PlantillaDiseno) => void;
  onBorrar: (p: PlantillaDiseno) => void;
  onBlanco: () => void;
}) {
  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Plantillas{marca ? ` · ${marca}` : ""}</h2>
        <Button size="sm" onClick={onBlanco}>
          <Plus className="mr-1 h-4 w-4" /> Lienzo en blanco
        </Button>
      </div>
      {cargando ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Cargando plantillas…</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {/* Tarjeta de lienzo en blanco siempre primera. */}
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
                    <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">{p.categoria}</div>
                  )}
                </div>
                <div className="truncate px-1.5 py-1 text-left text-xs">{p.nombre || "(sin nombre)"}</div>
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
