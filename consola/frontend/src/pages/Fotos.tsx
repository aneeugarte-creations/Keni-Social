/**
 * Página «Galería» — la BIBLIOTECA de medios unificada + las galerías locales en vivo, con dos vistas:
 *
 *  - BUSCAR: un único buscador que cruza A LA VEZ la biblioteca catalogada (portal · subidas ·
 *    fotografías) y las galerías EN VIVO de las apps keni-fotos conectadas (túnel). Resultados en una
 *    sola rejilla; al hacer clic se abre el visor a pantalla completa.
 *  - CARPETAS: un explorador estilo gestor de archivos. Raíz: Portal · Subidas · Fotografías. Dentro
 *    de Fotografías, las carpetas de los PARTIDOS —fusionando las guardadas con las galerías vivas de
 *    los keni-fotos conectados, por nombre—. Navegación con migas de pan, como un explorador normal.
 *
 * El visor replica el de keni-fotos (foto grande + ficha con etiquetas) y concentra las acciones:
 * Guardar (túnel→Fotografías), Descargar y Borrar (biblioteca). La consola NO lee el disco del
 * equipo: las galerías vivas llegan por el túnel. La página se acota a la MARCA activa del encabezado.
 */
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Camera,
  ChevronRight,
  Download,
  Folder,
  Home,
  ImageOff,
  Radio,
  Search,
} from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { VisorFoto } from "@/components/media/biblioteca/VisorFoto";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, BASE_API, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CandidataStock,
  DispositivoPropio,
  FotoVista,
  FuenteBiblioteca,
  ItemBiblioteca,
  RespuestaDispositivosPropio,
} from "@/types";

const ETIQUETA_FUENTE: Record<FuenteBiblioteca, string> = {
  portal: "Portal",
  subidas: "Subidas",
  fotografias: "Fotografías",
};
const FUENTES: FuenteBiblioteca[] = ["portal", "subidas", "fotografias"];

// --------------------------------------------------------------------------- //
// Normalización: biblioteca + túnel → una sola forma de foto (`FotoVista`)      //
// --------------------------------------------------------------------------- //

function deBiblioteca(item: ItemBiblioteca): FotoVista {
  return {
    clave: `bib-${item.id}`,
    origen: "biblioteca",
    titulo: item.titulo,
    thumb: item.thumb || item.url,
    url: item.url,
    etiquetas: item.etiquetas,
    id: item.id,
    fuente: item.fuente,
    grupo: item.grupo,
    marca: item.marca,
    galeria_id: item.galeria_id,
    archivo: item.archivo,
    dispositivo: item.dispositivo,
  };
}

function deCandidata(c: CandidataStock): FotoVista {
  return {
    clave: `tun-${c.galeria_id ?? ""}-${c.archivo ?? c.url}`,
    origen: "tunel",
    titulo: c.titulo || c.archivo || "Foto",
    thumb: c.thumb || c.url,
    url: c.url || c.thumb,
    etiquetas: c.etiquetas ?? [],
    galeria_id: c.galeria_id,
    archivo: c.archivo,
    dispositivo: c.dispositivo,
  };
}

// --------------------------------------------------------------------------- //
// Celda de foto (rejilla): miniatura clicable que abre el visor                 //
// --------------------------------------------------------------------------- //

function CeldaFoto({ foto, onAbrir }: { foto: FotoVista; onAbrir: () => void }) {
  return (
    <button
      type="button"
      onClick={onAbrir}
      className="group relative overflow-hidden rounded-lg border border-border bg-muted/20 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <img
        src={foto.thumb || foto.url}
        alt={foto.titulo || "Foto"}
        loading="lazy"
        className="aspect-square w-full object-cover transition-transform group-hover:scale-[1.03]"
      />
      {foto.origen === "tunel" && (
        <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
          en vivo
        </span>
      )}
      <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 pb-1 pt-4 text-[11px] text-white">
        {foto.titulo || foto.archivo || "Foto"}
      </span>
    </button>
  );
}

function RejillaFotos({
  fotos,
  onAbrir,
}: {
  fotos: FotoVista[];
  onAbrir: (indice: number) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {fotos.map((foto, i) => (
        <CeldaFoto key={foto.clave} foto={foto} onAbrir={() => onAbrir(i)} />
      ))}
    </div>
  );
}

function EstadoVacio({ icono: Icono, texto }: { icono: typeof ImageOff; texto: string }) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
      <Icono className="h-6 w-6" />
      <p className="text-sm">{texto}</p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Pestaña BUSCAR: un buscador que cruza biblioteca + túnel a la vez             //
// --------------------------------------------------------------------------- //

function BuscadorUnificado({
  marca,
  onVisor,
}: {
  marca?: string;
  onVisor: (fotos: FotoVista[], indice: number) => void;
}) {
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const biblioteca = useQuery({
    queryKey: ["biblioteca", "buscar", marca ?? "", qDebounced],
    queryFn: ({ signal }) => api.buscarBiblioteca({ q: qDebounced || undefined, marca }, signal),
    placeholderData: keepPreviousData,
    enabled: qDebounced.length > 0,
  });

  // El túnel exige marca (sin ella no hay galerías a las que preguntar).
  const tunel = useQuery({
    queryKey: ["propio", "buscar", marca ?? "", qDebounced],
    queryFn: ({ signal }) => api.buscarPropio({ q: qDebounced || undefined, marca }, signal),
    placeholderData: keepPreviousData,
    enabled: qDebounced.length > 0 && !!marca,
  });

  const fotos: FotoVista[] = React.useMemo(() => {
    const deBib = (biblioteca.data?.items ?? []).map(deBiblioteca);
    const deTun = (tunel.data?.candidatos ?? []).map(deCandidata);
    return [...deBib, ...deTun];
  }, [biblioteca.data, tunel.data]);

  const cargando = biblioteca.isLoading || tunel.isLoading;

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar fotos en todo: biblioteca + galerías conectadas…"
          className="h-10 rounded-lg border-transparent bg-muted/60 pl-9 placeholder:text-muted-foreground focus-visible:border-border"
          aria-label="Buscar en toda la galería"
        />
      </div>

      <div className="min-h-[10rem]">
        {!qDebounced ? (
          <EstadoVacio icono={Search} texto="Escribe para buscar en toda la galería a la vez." />
        ) : cargando && fotos.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-muted-foreground">
            <Spinner className="h-5 w-5" />
          </div>
        ) : fotos.length === 0 ? (
          <EstadoVacio icono={ImageOff} texto="Sin resultados. Prueba otra búsqueda." />
        ) : (
          <RejillaFotos fotos={fotos} onAbrir={(i) => onVisor(fotos, i)} />
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Pestaña CARPETAS: explorador estilo gestor de archivos                        //
// --------------------------------------------------------------------------- //

/** Una carpeta de partido dentro de Fotografías: lo guardado + las galerías vivas con ese nombre. */
interface CarpetaPartido {
  nombre: string;
  guardadas: number;
  galerias: { galeria_id: string; dispositivo: string; fotos: number }[];
}

/** Migas de pan. */
function Migas({
  ruta,
  onRaiz,
  onFuente,
}: {
  ruta: { fuente: FuenteBiblioteca; grupo?: string } | null;
  onRaiz: () => void;
  onFuente: (f: FuenteBiblioteca) => void;
}) {
  return (
    <nav className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
      <button
        type="button"
        onClick={onRaiz}
        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground"
      >
        <Home className="h-3.5 w-3.5" /> Galería
      </button>
      {ruta && (
        <>
          <ChevronRight className="h-3.5 w-3.5" />
          <button
            type="button"
            onClick={() => onFuente(ruta.fuente)}
            className={cn(
              "rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground",
              !ruta.grupo && "font-medium text-foreground",
            )}
          >
            {ETIQUETA_FUENTE[ruta.fuente]}
          </button>
        </>
      )}
      {ruta?.grupo && (
        <>
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="px-1.5 py-0.5 font-medium text-foreground">{ruta.grupo}</span>
        </>
      )}
    </nav>
  );
}

/** Una baldosa de carpeta (raíz o partido). */
function Baldosa({
  nombre,
  detalle,
  enVivo,
  onClick,
}: {
  nombre: string;
  detalle: string;
  enVivo?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-3 py-3 text-left transition-colors hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Folder className="h-8 w-8 shrink-0 text-muted-foreground" strokeWidth={0.75} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium text-foreground">{nombre}</span>
          {enVivo && <Radio className="h-3 w-3 shrink-0 text-emerald-500" aria-label="en vivo" />}
        </div>
        <div className="truncate text-xs text-muted-foreground">{detalle}</div>
      </div>
    </button>
  );
}

function NavegadorCarpetas({
  marca,
  dispositivos,
  onVisor,
}: {
  marca?: string;
  dispositivos: DispositivoPropio[];
  onVisor: (fotos: FotoVista[], indice: number) => void;
}) {
  const [ruta, setRuta] = React.useState<{ fuente: FuenteBiblioteca; grupo?: string } | null>(null);

  const { data: carpetasData } = useQuery({
    queryKey: ["biblioteca", "carpetas", marca ?? ""],
    queryFn: ({ signal }) => api.carpetasBiblioteca(marca, signal),
  });
  const carpetas = carpetasData?.carpetas ?? [];
  const totalDe = (f: FuenteBiblioteca) => carpetas.find((c) => c.fuente === f)?.total ?? 0;

  // Galerías VIVAS de los dispositivos conectados que comparten la marca (o todas si no hay marca).
  const galeriasVivas = React.useMemo(() => {
    const out: { nombre: string; galeria_id: string; dispositivo: string; fotos: number }[] = [];
    for (const d of dispositivos) {
      if (d.online === false) continue;
      if (marca && d.marcas && !d.marcas.includes(marca)) continue;
      for (const g of d.galerias ?? []) {
        out.push({
          nombre: g.nombre || g.id,
          galeria_id: g.id,
          dispositivo: d.dispositivo ?? "",
          fotos: g.fotos,
        });
      }
    }
    return out;
  }, [dispositivos, marca]);

  // Carpetas de partido = fusión de los grupos GUARDADOS y las galerías vivas, por nombre.
  const partidos: CarpetaPartido[] = React.useMemo(() => {
    const mapa = new Map<string, CarpetaPartido>();
    const gruposGuardados = carpetas.find((c) => c.fuente === "fotografias")?.grupos ?? [];
    for (const g of gruposGuardados) {
      mapa.set(g.grupo, { nombre: g.grupo, guardadas: g.total, galerias: [] });
    }
    for (const v of galeriasVivas) {
      const prev = mapa.get(v.nombre) ?? { nombre: v.nombre, guardadas: 0, galerias: [] };
      prev.galerias.push({ galeria_id: v.galeria_id, dispositivo: v.dispositivo, fotos: v.fotos });
      mapa.set(v.nombre, prev);
    }
    return [...mapa.values()].sort((a, b) => a.nombre.localeCompare(b.nombre));
  }, [carpetas, galeriasVivas]);

  return (
    <div className="space-y-4">
      <Migas ruta={ruta} onRaiz={() => setRuta(null)} onFuente={(f) => setRuta({ fuente: f })} />

      {ruta === null ? (
        // Raíz: las tres carpetas de la biblioteca.
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {FUENTES.map((f) => (
            <Baldosa
              key={f}
              nombre={ETIQUETA_FUENTE[f]}
              detalle={
                f === "fotografias"
                  ? `${partidos.length} ${partidos.length === 1 ? "partido" : "partidos"}`
                  : `${totalDe(f)} ${totalDe(f) === 1 ? "foto" : "fotos"}`
              }
              onClick={() => setRuta({ fuente: f })}
            />
          ))}
        </div>
      ) : ruta.fuente === "fotografias" && !ruta.grupo ? (
        // Fotografías: las carpetas de los partidos (guardados + en vivo).
        partidos.length === 0 ? (
          <EstadoVacio
            icono={Folder}
            texto="Aún no hay partidos. Conecta un keni-fotos o guarda fotos."
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            {partidos.map((p) => (
              <Baldosa
                key={p.nombre}
                nombre={p.nombre}
                enVivo={p.galerias.length > 0}
                detalle={[
                  p.guardadas > 0 ? `${p.guardadas} guardadas` : "",
                  p.galerias.length > 0
                    ? `${p.galerias.reduce((n, g) => n + g.fotos, 0)} en vivo`
                    : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
                onClick={() => setRuta({ fuente: "fotografias", grupo: p.nombre })}
              />
            ))}
          </div>
        )
      ) : (
        <ContenidoCarpeta
          marca={marca}
          fuente={ruta.fuente}
          grupo={ruta.grupo}
          partido={partidos.find((p) => p.nombre === ruta.grupo)}
          onVisor={onVisor}
        />
      )}
    </div>
  );
}

/** El contenido de una carpeta hoja: fotos guardadas + (en un partido) las fotos vivas del túnel. */
function ContenidoCarpeta({
  marca,
  fuente,
  grupo,
  partido,
  onVisor,
}: {
  marca?: string;
  fuente: FuenteBiblioteca;
  grupo?: string;
  partido?: CarpetaPartido;
  onVisor: (fotos: FotoVista[], indice: number) => void;
}) {
  const guardadas = useQuery({
    queryKey: ["biblioteca", "carpeta", marca ?? "", fuente, grupo ?? ""],
    queryFn: ({ signal }) =>
      api.buscarBiblioteca({ fuente, marca, grupo: grupo || undefined }, signal),
  });

  // Fotos VIVAS del túnel: una consulta por galería conectada con ese nombre de partido.
  const galerias = partido?.galerias ?? [];
  const vivasQueries = useQueries({
    queries: galerias.map((g) => ({
      queryKey: ["propio", "galeria", marca ?? "", g.galeria_id, g.dispositivo],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.galeriaPropio({ galeria_id: g.galeria_id, marca, dispositivo: g.dispositivo }, signal),
      enabled: !!marca,
    })),
  });

  // Fusión guardadas + vivas (cálculo barato en cada render). Dedup: una viva ya guardada (mismo
  // galeria_id+archivo) no se repite.
  const guard = (guardadas.data?.items ?? []).map(deBiblioteca);
  const vivas = vivasQueries.flatMap((q) => (q.data?.candidatos ?? []).map(deCandidata));
  const clavesGuardadas = new Set(
    guard.map((f) => `${f.galeria_id ?? ""}-${f.archivo ?? ""}`).filter((k) => k !== "-"),
  );
  const fotos: FotoVista[] = [
    ...guard,
    ...vivas.filter((f) => !clavesGuardadas.has(`${f.galeria_id ?? ""}-${f.archivo ?? ""}`)),
  ];

  const cargando = guardadas.isLoading || vivasQueries.some((q) => q.isLoading);

  if (cargando && fotos.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }
  if (fotos.length === 0) {
    return <EstadoVacio icono={ImageOff} texto="Esta carpeta no tiene fotos." />;
  }
  return <RejillaFotos fotos={fotos} onAbrir={(i) => onVisor(fotos, i)} />;
}

// --------------------------------------------------------------------------- //
// Página                                                                        //
// --------------------------------------------------------------------------- //

export default function Fotos() {
  const { marcaActiva } = useMarcaActiva();
  const marca = marcaActiva ?? undefined;
  const clienteQuery = useQueryClient();

  // Visor a pantalla completa: una lista de fotos + el índice mostrado.
  const [visor, setVisor] = React.useState<{ fotos: FotoVista[]; indice: number } | null>(null);
  const abrirVisor = (fotos: FotoVista[], indice: number) => setVisor({ fotos, indice });

  // Dispositivos conectados (SSE): alimentan las carpetas de partidos vivos + el indicador.
  const [dispositivos, setDispositivos] = React.useState<DispositivoPropio[]>([]);
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const params = marca ? `?marca=${encodeURIComponent(marca)}` : "";
    const fuente = new EventSource(`${BASE_API}/artes/propio/eventos${params}`);
    fuente.onmessage = (ev) => {
      try {
        const datos = JSON.parse(ev.data as string) as RespuestaDispositivosPropio;
        setDispositivos(datos.dispositivos ?? []);
      } catch {
        // Snapshot ilegible: lo ignoramos.
      }
    };
    return () => fuente.close();
  }, [marca]);

  const guardar = useMutation({
    mutationFn: (foto: FotoVista) =>
      api.guardarRemoto({
        galeria_id: foto.galeria_id!,
        archivo: foto.archivo!,
        dispositivo: foto.dispositivo,
        marca,
        // Conserva el título y las etiquetas IA que ya trae keni-fotos.
        titulo: foto.titulo,
        etiquetas: foto.etiquetas,
      }),
    onSuccess: () => {
      toast.success("Foto guardada en Fotografías.");
      void clienteQuery.invalidateQueries({ queryKey: ["biblioteca"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: (foto: FotoVista) => api.borrarArte(foto.id!, true),
    onSuccess: () => {
      toast.success("Foto quitada de la biblioteca.");
      void clienteQuery.invalidateQueries({ queryKey: ["biblioteca"] });
      setVisor(null);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const dispositivosOnline = dispositivos.filter((d) => d.online !== false).length;

  return (
    <>
      <TituloPagina titulo="Galería" icono={Camera} />
      <AccionesPagina>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="gap-2"
          onClick={() => api.descargarFotosApp()}
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          Descargar app
        </Button>
      </AccionesPagina>

      <div className="w-full space-y-4 py-6 pb-12">
        <Tabs defaultValue="buscar">
          <div className="flex items-center justify-between gap-3">
            <TabsList>
              <TabsTrigger value="buscar">
                <Search className="h-4 w-4" /> Buscar
              </TabsTrigger>
              <TabsTrigger value="carpetas">
                <Folder className="h-4 w-4" /> Carpetas
              </TabsTrigger>
            </TabsList>
            {dispositivosOnline > 0 && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Radio className="h-3.5 w-3.5 text-emerald-500" />
                {dispositivosOnline} {dispositivosOnline === 1 ? "conectado" : "conectados"}
              </span>
            )}
          </div>

          <TabsContent value="buscar" className="mt-4">
            <BuscadorUnificado marca={marca} onVisor={abrirVisor} />
          </TabsContent>

          <TabsContent value="carpetas" className="mt-4">
            <NavegadorCarpetas marca={marca} dispositivos={dispositivos} onVisor={abrirVisor} />
          </TabsContent>
        </Tabs>

        {dispositivosOnline === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 border-t border-border py-8 text-center">
            <Button variant="outline" className="gap-2" onClick={() => api.descargarFotosApp()}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Descargar para macOS
            </Button>
            <p className="text-xs text-muted-foreground">
              Conecta la app keni-fotos en tu Mac para ver aquí las galerías en vivo del equipo.
            </p>
          </div>
        )}
      </div>

      <VisorFoto
        fotos={visor?.fotos ?? []}
        indice={visor?.indice ?? null}
        onIndice={(indice) => setVisor((v) => (v ? { ...v, indice } : v))}
        onCerrar={() => setVisor(null)}
        marca={marca}
        onGuardar={(foto) => guardar.mutate(foto)}
        onDescargar={(foto) => foto.id && api.descargarBiblioteca(foto.id)}
        onBorrar={(foto) => {
          if (window.confirm("¿Quitar esta foto de la biblioteca?")) borrar.mutate(foto);
        }}
        guardandoClave={guardar.isPending ? (guardar.variables as FotoVista)?.clave : null}
        borrandoClave={borrar.isPending ? (borrar.variables as FotoVista)?.clave : null}
      />
    </>
  );
}
