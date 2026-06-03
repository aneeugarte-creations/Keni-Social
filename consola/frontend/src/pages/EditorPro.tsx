// Página del Editor profesional — WORKSPACE multi-marca (Frente A + B).
//
// Cada PESTAÑA es un documento independiente (marca + formato) con su PROPIO store Zustand e
// historial, así editar la plantilla de UnoTV no toca la de Claro Sports y no hay que cerrar una
// para abrir otra. Los stores persisten en un ref por id de pestaña: cambiar de pestaña conserva
// las ediciones (no recarga la plantilla).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Plus, Save, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { Button } from "@/components/ui/button";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { documentoVacio, type Capa, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

const DIMS: Record<string, Documento["formato"]> = {
  vertical: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 },
  feed: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 },
  cuadrado: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 },
  horizontal: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 },
};
const FORMATOS = Object.keys(DIMS);

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
  const marcaInicial = marcaActiva && marcas.some((m) => m.id === marcaActiva)
    ? marcaActiva
    : marcas[0]?.id;

  const [searchParams] = useSearchParams();

  // Selectores para abrir una pestaña nueva.
  const [marcaNueva, setMarcaNueva] = useState("");
  const [formatoNuevo, setFormatoNuevo] = useState("feed");

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  // Stores por pestaña (persisten entre cambios de pestaña).
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [galeria, setGaleria] = useState(false);

  const marcaEfectiva = marcaNueva || marcaInicial || "";

  const abrirPestana = async (marcaArg?: string, formatoArg?: string) => {
    const marca = marcaArg || marcaEfectiva;
    const formato = formatoArg || formatoNuevo;
    if (!marca) return;
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(documentoVacio(DIMS[formato] ?? DIMS.feed, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, formato }]);
    setActiva(id);
    // Restaura el autoguardado si existe; si no, carga la plantilla de la marca.
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

  // Abre una pestaña ANCLADA a una publicación: carga el documento guardado de la pieza, o la
  // plantilla de su marca si aún no se editó. La invoca el efecto de apertura por URL.
  const abrirPiezaTab = async (cid: string, pid: string, marca: string, formato: string) => {
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(documentoVacio(DIMS[formato] ?? DIMS.feed, marca));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca, formato, contenido: cid, plataforma: pid }]);
    setActiva(id);
    // Prioridad: autoguardado local (ediciones sin guardar) > documento guardado de la pieza >
    // plantilla de la marca.
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

  // Apertura inicial AUTOMÁTICA (una vez): si la URL trae una pieza, la abre anclada; si no,
  // abre una pestaña por defecto (primera marca, formato feed) en cuanto llega el catálogo, para
  // aterrizar directo en un lienzo sin tener que pulsar nada.
  const abiertoInicial = useRef(false);
  useEffect(() => {
    if (abiertoInicial.current) return;
    const cid = searchParams.get("contenido");
    const pid = searchParams.get("plataforma");
    if (cid && pid) {
      abiertoInicial.current = true;
      const marca = searchParams.get("marca") || marcaInicial || "";
      void abrirPiezaTab(cid, pid, marca, searchParams.get("formato") || "feed");
      return;
    }
    if (marcas.length > 0) {
      abiertoInicial.current = true;
      void abrirPestana(marcaInicial ?? marcas[0].id, "feed");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, marcas]);

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

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;

  // AUTOGUARDADO: persiste el documento de la pestaña activa en sessionStorage (debounce 800 ms)
  // para no perder trabajo al recargar o cambiar de pestaña. La restauración ocurre al abrir.
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

  const qc = useQueryClient();

  // Plantillas de diseño guardadas para la marca de la pestaña activa.
  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", pestanaActiva?.marca ?? ""],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: pestanaActiva?.marca || undefined }, signal),
    enabled: !!pestanaActiva,
  });

  const guardarPlantilla = useMutation({
    mutationFn: async () => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const nombre = window.prompt("Nombre de la plantilla")?.trim();
      if (!nombre) throw new Error("__cancelado__");
      const documento = storeActivo.getState().documento;
      // Miniatura: renderiza el documento (best-effort) para la galería visual.
      let miniatura = "";
      try {
        miniatura = (await api.editorRender(documento)).id;
      } catch {
        /* sin miniatura: la galería muestra un marcador */
      }
      return api.crearPlantillaDiseno({
        marca: pestanaActiva.marca,
        nombre,
        categoria: pestanaActiva.formato,
        documento,
        miniatura,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno", pestanaActiva?.marca ?? ""] });
      toast.success("Plantilla guardada.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__cancelado__") return;
      toast.error(e instanceof Error ? e.message : "No se pudo guardar.");
    },
  });

  const cargarPlantilla = (id: string) => {
    const p = plantillasQ.data?.plantillas.find((x) => x.id === id);
    if (p && storeActivo) {
      storeActivo.getState().cargar(p.documento as Documento);
      toast.success(`Plantilla «${p.nombre}» cargada.`);
    }
  };

  const borrarPlantilla = useMutation({
    mutationFn: (id: string) => api.borrarPlantillaDiseno(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno", pestanaActiva?.marca ?? ""] });
      toast.success("Plantilla borrada.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo borrar."),
  });

  // Almacén de bloques (capas reutilizables) de la marca activa.
  const bloquesQ = useQuery({
    queryKey: ["bloques", pestanaActiva?.marca ?? ""],
    queryFn: ({ signal }) => api.bloques({ marca: pestanaActiva?.marca || undefined }, signal),
    enabled: !!pestanaActiva,
  });

  const guardarBloque = useMutation({
    mutationFn: () => {
      if (!storeActivo || !pestanaActiva) throw new Error("No hay pestaña activa.");
      const st = storeActivo.getState();
      const capa = st.documento.capas.find((c) => c.id === st.seleccion);
      if (!capa) throw new Error("Selecciona una capa para guardarla como bloque.");
      const nombre = window.prompt("Nombre del bloque")?.trim();
      if (!nombre) throw new Error("__cancelado__");
      return api.crearBloque({ marca: pestanaActiva.marca, nombre, capas: [capa] });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bloques", pestanaActiva?.marca ?? ""] });
      toast.success("Bloque guardado.");
    },
    onError: (e: unknown) => {
      if (e instanceof Error && e.message === "__cancelado__") return;
      toast.error(e instanceof Error ? e.message : "No se pudo guardar el bloque.");
    },
  });

  const insertarBloque = (id: string) => {
    const b = bloquesQ.data?.bloques.find((x) => x.id === id);
    if (b && storeActivo) {
      storeActivo.getState().insertarBloque(b.capas as Capa[]);
      toast.success(`Bloque «${b.nombre}» insertado.`);
    }
  };

  // Guarda el documento en la PUBLICACIÓN anclada (render + versión + fija su imagen).
  const guardarEnPieza = useMutation({
    mutationFn: () => {
      if (!storeActivo || !pestanaActiva?.contenido || !pestanaActiva?.plataforma) {
        throw new Error("Esta pestaña no está anclada a una publicación.");
      }
      return api.editorPiezaGuardar(
        pestanaActiva.contenido,
        pestanaActiva.plataforma,
        storeActivo.getState().documento,
      );
    },
    onSuccess: (res) => {
      setExportUrl(`/api/media/${res.id}`);
      toast.success(`Guardado en la pieza (v${res.version}).`);
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar en la pieza."),
  });

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Barra superior: abrir pestaña (marca + formato) + export. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <h1 className="mr-1 text-base font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marcaEfectiva} onCambio={setMarcaNueva} incluirTodas={false} />
        <select
          value={formatoNuevo}
          onChange={(e) => setFormatoNuevo(e.target.value)}
          className="rounded border border-input bg-background px-2 py-1.5 text-sm"
          aria-label="Formato"
        >
          {FORMATOS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <Button variant="outline" size="sm" onClick={() => abrirPestana()} disabled={!marcaEfectiva}>
          <Plus className="mr-1 h-4 w-4" /> Nueva pestaña
        </Button>
        {pestanaActiva && (
          <>
            <div className="mx-1 h-5 w-px bg-border" />
            {pestanaActiva.contenido && (
              <Button size="sm" disabled={guardarEnPieza.isPending} onClick={() => guardarEnPieza.mutate()}>
                <FileUp className="mr-1 h-4 w-4" /> Guardar en la pieza
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={guardarPlantilla.isPending}
              onClick={() => guardarPlantilla.mutate()}
            >
              <Save className="mr-1 h-4 w-4" /> Guardar plantilla
            </Button>
            <Button variant="outline" size="sm" onClick={() => setGaleria(true)}>
              Plantillas
            </Button>
            <Button variant="outline" size="sm" disabled={guardarBloque.isPending} onClick={() => guardarBloque.mutate()}>
              Guardar bloque
            </Button>
            {(bloquesQ.data?.bloques.length ?? 0) > 0 && (
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) insertarBloque(e.target.value);
                }}
                className="rounded border border-input bg-background px-2 py-1.5 text-sm"
                aria-label="Insertar bloque"
              >
                <option value="">Insertar bloque…</option>
                {bloquesQ.data!.bloques.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.nombre || "(sin nombre)"}
                  </option>
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

      {/* Pestañas abiertas. */}
      {pestanas.length > 0 && (
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
                <button onClick={() => setActiva(t.id)}>
                  {nombre} · {t.formato}
                </button>
                <button onClick={() => cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

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
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Elige una marca y un formato, y pulsa «Nueva pestaña» para empezar a editar.
          </div>
        )}
      </div>

      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillasQ.data?.plantillas ?? []}
          onCargar={(p) => {
            cargarPlantilla(p.id);
            setGaleria(false);
          }}
          onBorrar={(p) => borrarPlantilla.mutate(p.id)}
          onCerrar={() => setGaleria(false)}
        />
      )}
    </div>
  );
}
