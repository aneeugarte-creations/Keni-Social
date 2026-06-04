// Página del Editor profesional — WORKSPACE multi-marca.
//
// Cada PESTAÑA es un documento independiente (por MARCA) con su PROPIO store Zustand e historial;
// los stores persisten en un ref por id de pestaña. Todo post es 4:5 y una misma plantilla sirve
// para todas las redes (no hay dimensión ni filtro por red).
//
// PLANTILLAS por marca: «Guardar» actualiza la plantilla a la que está atada la pestaña (sin pedir
// nombre); «Guardar como» crea una nueva. Un indicador estilo Word muestra si hay cambios sin
// guardar. Sin pestañas se ve la GALERÍA de plantillas de la marca (o lienzo en blanco si no hay).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileUp, Loader2, Plus, Save, SaveAll, X } from "lucide-react";
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

// Todo post es 4:5 (1080×1350). El tamaño se puede ajustar en «Ajustes del lienzo».
const DIMS_DEFECTO: Documento["formato"] = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

interface Pestana {
  id: string;
  marca: string;
  nombre?: string; // nombre de la plantilla atada (si la hay)
  plantillaId?: string; // plantilla de diseño a la que «Guardar» sobrescribe
  // Si la pestaña está anclada a una publicación (historial/versionado).
  contenido?: string;
  plataforma?: string;
}

let _seq = 0;

// Clave de autoguardado local (crash-safety): por pieza, por plantilla, o por marca.
function claveAuto(p: Pestana): string {
  if (p.contenido && p.plataforma) return `keni:editor:pieza:${p.contenido}:${p.plataforma}`;
  if (p.plantillaId) return `keni:editor:plantilla:${p.plantillaId}`;
  return `keni:editor:doc:${p.marca}`;
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

  const { marcaActiva } = useMarcaActiva();
  const marcaInicial = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : marcas[0]?.id;

  const [searchParams] = useSearchParams();

  const [marcaNueva, setMarcaNueva] = useState("");

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [galeria, setGaleria] = useState(false);
  // Diálogo de «Guardar como» (nombre de plantilla nueva), in-app.
  const [dialogo, setDialogo] = useState<{ nombre: string } | null>(null);
  // Cambios sin guardar en la plantilla, por pestaña (indicador estilo Word).
  const [dirty, setDirty] = useState<Record<string, boolean>>({});

  const marcaEfectiva = marcaNueva || marcaInicial || "";

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;
  const marcaPanel = pestanaActiva?.marca || marcaEfectiva;
  const sucia = activa ? dirty[activa] : false;

  const marcarLimpia = (id: string) => setDirty((d) => ({ ...d, [id]: false }));
  const bindPlantilla = (id: string, plantillaId: string, nombre: string) =>
    setPestanas((p) => p.map((t) => (t.id === id ? { ...t, plantillaId, nombre } : t)));

  const nuevaPestana = (marca: string, doc?: Documento, extra?: Partial<Pestana>): { id: string; store: StoreEditor } => {
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(doc ?? documentoVacio(DIMS_DEFECTO, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, ...extra }]);
    setActiva(id);
    setDirty((d) => ({ ...d, [id]: false }));
    return { id, store };
  };

  // Lienzo EN BLANCO de verdad (documento vacío). Solo restaura un autoguardado previo si existe.
  const abrirPestana = (marcaArg?: string) => {
    const marca = marcaArg || marcaEfectiva;
    if (!marca) return;
    const { store } = nuevaPestana(marca);
    const guardado = leerAuto(claveAuto({ id: "", marca }));
    if (guardado) store.getState().cargar(guardado);
  };

  // Abre una plantilla guardada EN UNA PESTAÑA NUEVA, atada a esa plantilla.
  const abrirPlantilla = (p: PlantillaDiseno) => {
    nuevaPestana(p.marca, p.documento as Documento, { nombre: p.nombre, plantillaId: p.id });
    setGaleria(false);
    toast.success(`Plantilla «${p.nombre}» abierta.`);
  };

  // Abre una pestaña ANCLADA a una publicación.
  const abrirPiezaTab = async (cid: string, pid: string, marca: string) => {
    const { store } = nuevaPestana(marca, undefined, { contenido: cid, plataforma: pid });
    const guardado = leerAuto(claveAuto({ id: "", marca, contenido: cid, plataforma: pid }));
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

  // Al editar: marca "sin guardar", autoguarda local (crash-safety, ~0.8 s) y, si la pestaña está
  // atada a una plantilla, AUTOGUARDA en la plantilla tras 3 s de inactividad (estilo Word).
  useEffect(() => {
    if (!activa) return;
    const store = stores.current.get(activa);
    const p = pestanas.find((t) => t.id === activa);
    if (!store || !p) return;
    const clave = claveAuto(p);
    let tSession: number | undefined;
    let tAuto: number | undefined;
    const unsub = store.subscribe((estado, previo) => {
      if (estado.documento === previo.documento) return;
      setDirty((d) => ({ ...d, [p.id]: true }));
      // Borrador local.
      window.clearTimeout(tSession);
      tSession = window.setTimeout(() => {
        try {
          sessionStorage.setItem(clave, JSON.stringify(estado.documento));
        } catch {
          /* cuota llena: el trabajo sigue en memoria */
        }
      }, 800);
      // Autoguardado a la plantilla tras 3 s sin tocar nada.
      window.clearTimeout(tAuto);
      tAuto = window.setTimeout(async () => {
        if (!p.plantillaId) return; // sin plantilla atada no hay dónde guardar (usa «Guardar como»)
        const st = stores.current.get(p.id);
        if (!st) return;
        const doc = st.getState().documento;
        try {
          // Solo el documento (sin re-render de miniatura, para no cargar el server cada 3 s; la
          // miniatura se refresca al Guardar manual).
          await api.actualizarPlantillaDiseno(p.plantillaId, { documento: doc });
          // Solo marcar limpio si no se editó MIENTRAS guardaba (igualdad por referencia).
          if (stores.current.get(p.id)?.getState().documento === doc) {
            setDirty((d) => ({ ...d, [p.id]: false }));
          }
          qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
        } catch {
          /* falló el autoguardado: el punto rojo permanece */
        }
      }, 3000);
    });
    return () => {
      window.clearTimeout(tSession);
      window.clearTimeout(tAuto);
      unsub();
    };
  }, [activa, pestanas, qc]);

  // Genera la miniatura (render best-effort) del documento actual.
  const miniaturaDe = async (documento: Documento): Promise<string> => {
    try {
      return (await api.editorRender(documento)).id;
    } catch {
      return "";
    }
  };

  // GUARDAR: si la pestaña ya está atada a una plantilla, la sobrescribe (sin pedir nombre);
  // si no, abre «Guardar como».
  const guardar = useMutation({
    mutationFn: async () => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      if (!pestanaActiva.plantillaId) throw new Error("__sin_plantilla__");
      const documento = storeActivo.getState().documento;
      const miniatura = await miniaturaDe(documento);
      return api.actualizarPlantillaDiseno(pestanaActiva.plantillaId, { documento, miniatura });
    },
    onSuccess: () => {
      if (activa) marcarLimpia(activa);
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Guardado.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__sin_plantilla__") {
        setDialogo({ nombre: pestanaActiva?.nombre ?? "" });
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo guardar.");
    },
  });

  // GUARDAR COMO: crea una plantilla nueva con el nombre dado y ata la pestaña a ella.
  const guardarComo = useMutation({
    mutationFn: async (nombre: string) => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const documento = storeActivo.getState().documento;
      const miniatura = await miniaturaDe(documento);
      return api.crearPlantillaDiseno({ marca: pestanaActiva.marca, nombre, categoria: "post", documento, miniatura });
    },
    onSuccess: (res, nombre) => {
      if (activa) {
        bindPlantilla(activa, res.plantilla.id, nombre);
        marcarLimpia(activa);
      }
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla guardada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar."),
  });

  const confirmarNombre = () => {
    const nombre = dialogo?.nombre.trim();
    if (!nombre) return;
    guardarComo.mutate(nombre);
    setDialogo(null);
  };

  // Carga una plantilla en la pestaña ACTIVA (la ata a ella).
  const cargarPlantillaEnActiva = (p: PlantillaDiseno) => {
    if (storeActivo && activa) {
      storeActivo.getState().cargar(p.documento as Documento);
      bindPlantilla(activa, p.id, p.nombre);
      marcarLimpia(activa);
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

  // Guarda el documento en la PUBLICACIÓN anclada (render + versión + fija su imagen).
  const guardarEnPieza = useMutation({
    mutationFn: () => {
      if (!storeActivo || !pestanaActiva?.contenido || !pestanaActiva?.plataforma) {
        throw new Error("Esta pestaña no está anclada a una publicación.");
      }
      return api.editorPiezaGuardar(pestanaActiva.contenido, pestanaActiva.plataforma, storeActivo.getState().documento);
    },
    onSuccess: (res) => {
      if (activa) marcarLimpia(activa);
      setExportUrl(`/api/media/${res.id}`);
      toast.success(`Guardado en la pieza (v${res.version}).`);
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar en la pieza."),
  });

  const plantillas = plantillasQ.data?.plantillas ?? [];
  const guardando = guardar.isPending || guardarComo.isPending;

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col">
      {/* Barra superior: marca + acciones (guardar / guardar como / pieza) + estado + export. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <h1 className="mr-1 text-base font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marcaEfectiva} onCambio={setMarcaNueva} incluirTodas={false} />
        {pestanaActiva && (
          <>
            <div className="mx-1 h-5 w-px bg-border" />
            {pestanaActiva.contenido && (
              <Button size="icon" disabled={guardarEnPieza.isPending} onClick={() => guardarEnPieza.mutate()} title="Guardar en la publicación">
                <FileUp className="h-4 w-4" />
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              disabled={guardando}
              onClick={() => guardar.mutate()}
              title={sucia ? "Guardar (cambios sin guardar)" : "Guardado — se autoguarda a los 3 s"}
            >
              <span className="relative mr-1 inline-flex">
                <Save className="h-4 w-4" />
                {/* Estado EN el icono: punto rojo si hay cambios; check verde si está guardado. */}
                {guardando ? (
                  <Loader2 className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 animate-spin text-muted-foreground" />
                ) : sucia ? (
                  <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500 ring-1 ring-background" />
                ) : (
                  <Check className="absolute -right-1.5 -top-1.5 h-3 w-3 rounded-full bg-background text-emerald-500" />
                )}
              </span>
              Guardar
            </Button>
            <Button size="icon" variant="ghost" disabled={guardando} onClick={() => setDialogo({ nombre: "" })} title="Guardar como… (plantilla nueva)">
              <SaveAll className="h-4 w-4" />
            </Button>
          </>
        )}
        <span className="ml-auto" />
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
                <button onClick={() => setActiva(t.id)} className="max-w-[200px] truncate">
                  {t.nombre || marca}
                  {dirty[t.id] && <span className="ml-1 text-red-500">•</span>}
                </button>
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
            onAbrir={abrirPlantilla}
            onBorrar={(p) => borrarPlantilla.mutate(p.id)}
            onBlanco={() => abrirPestana()}
          />
        )}
      </div>

      {/* Galería modal: aplicar una plantilla a la pestaña ACTIVA (desde el rail). */}
      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillas}
          onCargar={(p) => { cargarPlantillaEnActiva(p); setGaleria(false); }}
          onBorrar={(p) => borrarPlantilla.mutate(p.id)}
          onCerrar={() => setGaleria(false)}
        />
      )}

      {/* Diálogo «Guardar como» (nombre de plantilla nueva). */}
      <Dialog open={!!dialogo} onOpenChange={(o) => !o && setDialogo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Guardar como plantilla</DialogTitle>
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

// Galería del estado vacío: rejilla de plantillas de la marca + tarjeta de «lienzo en blanco».
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
                    <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">Sin vista previa</div>
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
