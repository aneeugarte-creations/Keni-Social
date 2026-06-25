/**
 * Página «Galería» — la BIBLIOTECA de medios unificada del equipo + las galerías locales en vivo.
 *
 * La biblioteca cataloga las fotos disponibles para postear en tres carpetas (portal · originales ·
 * fotografías) sobre `catalogo_media`. Esta página ofrece:
 *  - Un BUSCADOR GLOBAL (sobre `GET /api/biblioteca`, por título + etiquetas) cruzando las tres
 *    carpetas, en posición estable y DESACOPLADO de cualquier sondeo.
 *  - CARPETAS navegables (de `GET /api/biblioteca/carpetas`): Portal · Originales · Fotografías;
 *    dentro de Fotografías, por grupo (partido). Cada foto: thumb, título, etiquetas, descargar y
 *    —en fotografías— navegar la ráfaga del burst.
 *  - El explorador de galerías LOCALES en vivo (apps keni-fotos conectadas por túnel, por SSE): se
 *    busca por túnel y desde una foto remota se puede «Guardar en Fotografías» (catalogarla).
 *
 * La consola en la nube no lee el disco del equipo: las galerías se procesan EN LOCAL con la app de
 * escritorio keni-fotos, que abre un túnel hacia keni-social. La página se acota a la MARCA activa
 * del selector del encabezado.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Download, FolderOpen, ImageOff, Save, Search } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { TarjetaBiblioteca } from "@/components/media/biblioteca/TarjetaBiblioteca";
import { VisorRafaga, type RafagaRef } from "@/components/media/biblioteca/VisorRafaga";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, BASE_API, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CandidataStock,
  DispositivoPropio,
  FuenteBiblioteca,
  ItemBiblioteca,
  RespuestaDispositivosPropio,
} from "@/types";

const ETIQUETA_FUENTE: Record<FuenteBiblioteca, string> = {
  portal: "Portal",
  originales: "Originales",
  fotografias: "Fotografías",
};
const FUENTES: FuenteBiblioteca[] = ["portal", "originales", "fotografias"];

/** ¿Este item de fotografías trae las coordenadas del túnel para navegar su ráfaga? */
function refRafaga(item: ItemBiblioteca, marca?: string): RafagaRef | null {
  if (item.fuente !== "fotografias" || !item.galeria_id || !item.archivo) return null;
  return {
    galeria_id: item.galeria_id,
    archivo: item.archivo,
    marca: item.marca || marca,
    dispositivo: item.dispositivo,
    titulo: item.titulo,
  };
}

/** Buscador GLOBAL de la biblioteca: busca por título + etiquetas cruzando las tres carpetas. */
function BuscadorGlobalBiblioteca({
  marca,
  onRafaga,
}: {
  marca?: string;
  onRafaga: (ref: RafagaRef) => void;
}) {
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ["biblioteca", "global", marca ?? "", qDebounced],
    queryFn: ({ signal }) =>
      api.buscarBiblioteca({ q: qDebounced || undefined, marca }, signal),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar en toda la biblioteca… (título o etiqueta)"
          className="h-9 rounded-lg border-transparent bg-muted/60 pl-8 placeholder:text-muted-foreground focus-visible:border-border"
          aria-label="Buscar en la biblioteca de medios"
        />
      </div>

      <div className="min-h-[6rem]">
        {isLoading || (isFetching && items.length === 0) ? (
          <div className="flex h-24 items-center justify-center text-muted-foreground">
            <Spinner className="h-5 w-5" />
          </div>
        ) : isError ? (
          <p className="flex h-24 items-center justify-center text-sm text-destructive">
            No se pudo buscar en la biblioteca.
          </p>
        ) : !qDebounced ? (
          <div className="flex h-24 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <Search className="h-6 w-6" />
            <p className="text-sm">Escribe para buscar fotos en toda la biblioteca.</p>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-24 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <ImageOff className="h-6 w-6" />
            <p className="text-sm">Sin resultados. Prueba otra búsqueda.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {items.map((item) => {
              const ref = refRafaga(item, marca);
              return (
                <TarjetaBiblioteca
                  key={item.id}
                  item={item}
                  onRafaga={ref ? () => onRafaga(ref) : undefined}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Carpetas navegables: Portal · Originales · Fotografías (esta por grupo/partido). */
function CarpetasBiblioteca({
  marca,
  onRafaga,
}: {
  marca?: string;
  onRafaga: (ref: RafagaRef) => void;
}) {
  const [fuenteActiva, setFuenteActiva] = React.useState<FuenteBiblioteca>("portal");
  const [grupoActivo, setGrupoActivo] = React.useState("");

  const { data: carpetasData } = useQuery({
    queryKey: ["biblioteca", "carpetas", marca ?? ""],
    queryFn: ({ signal }) => api.carpetasBiblioteca(marca, signal),
  });
  const carpetas = carpetasData?.carpetas ?? [];
  const totalDe = (f: FuenteBiblioteca): number =>
    carpetas.find((c) => c.fuente === f)?.total ?? 0;
  const gruposDe = (f: FuenteBiblioteca) =>
    carpetas.find((c) => c.fuente === f)?.grupos ?? [];

  const { data: itemsData, isLoading, isError } = useQuery({
    queryKey: ["biblioteca", "carpeta", marca ?? "", fuenteActiva, grupoActivo],
    queryFn: ({ signal }) =>
      api.buscarBiblioteca(
        { fuente: fuenteActiva, marca, grupo: grupoActivo || undefined },
        signal,
      ),
  });
  const items = itemsData?.items ?? [];

  return (
    <Tabs
      value={fuenteActiva}
      onValueChange={(v) => {
        setFuenteActiva(v as FuenteBiblioteca);
        setGrupoActivo("");
      }}
    >
      <TabsList>
        {FUENTES.map((f) => (
          <TabsTrigger key={f} value={f}>
            {ETIQUETA_FUENTE[f]}
            <Badge variant="secondary">{totalDe(f)}</Badge>
          </TabsTrigger>
        ))}
      </TabsList>

      {FUENTES.map((f) => (
        <TabsContent key={f} value={f} className="space-y-3">
          {/* Fotografías se navega además por grupo (partido): chips de filtro. */}
          {f === "fotografias" && gruposDe(f).length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <ChipGrupo
                etiqueta="Todos"
                activo={grupoActivo === ""}
                onClick={() => setGrupoActivo("")}
              />
              {gruposDe(f).map((g) => (
                <ChipGrupo
                  key={g.grupo}
                  etiqueta={`${g.grupo} · ${g.total}`}
                  activo={grupoActivo === g.grupo}
                  onClick={() => setGrupoActivo(g.grupo)}
                />
              ))}
            </div>
          )}

          {isLoading ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              <Spinner className="h-5 w-5" />
            </div>
          ) : isError ? (
            <p className="flex h-32 items-center justify-center text-sm text-destructive">
              No se pudo cargar la carpeta.
            </p>
          ) : items.length === 0 ? (
            <div className="flex h-32 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
              <p className="text-sm">Esta carpeta aún no tiene fotos.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {items.map((item) => {
                const ref = refRafaga(item, marca);
                return (
                  <TarjetaBiblioteca
                    key={item.id}
                    item={item}
                    onRafaga={ref ? () => onRafaga(ref) : undefined}
                  />
                );
              })}
            </div>
          )}
        </TabsContent>
      ))}
    </Tabs>
  );
}

/** Chip de filtro de grupo (partido) dentro de Fotografías. */
function ChipGrupo({
  etiqueta,
  activo,
  onClick,
}: {
  etiqueta: string;
  activo: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={activo}
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors",
        activo
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {etiqueta}
    </button>
  );
}

/** Buscador de EXPLORACIÓN de las galerías LOCALES (túnel): candidatas en grid, con opción de
 *  guardarlas en la carpeta Fotografías de la biblioteca (conservando sus etiquetas). */
function BuscadorPropio({ marca }: { marca: string }) {
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");
  const clienteQuery = useQueryClient();

  // Debounce de 350ms: el túnel hace fan-out a las apps; no lo golpeamos en cada tecla.
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ["propio", "explorar", marca, qDebounced],
    queryFn: ({ signal }) => api.buscarPropio({ q: qDebounced || undefined, marca }, signal),
    placeholderData: keepPreviousData,
  });

  const candidatos = data?.candidatos ?? [];

  // Guardar en Fotografías: pide el original por el túnel, lo cataloga (conserva etiquetas) y aparece
  // en la carpeta Fotografías. Identificamos el guardado en curso por galería+archivo.
  const [guardandoClave, setGuardandoClave] = React.useState<string | null>(null);
  const guardar = useMutation({
    mutationFn: (c: CandidataStock) =>
      api.guardarRemoto({
        galeria_id: c.galeria_id!,
        archivo: c.archivo!,
        dispositivo: c.dispositivo,
        marca,
      }),
    onSuccess: () => {
      toast.success("Foto guardada en Fotografías.");
      void clienteQuery.invalidateQueries({ queryKey: ["biblioteca"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
    onSettled: () => setGuardandoClave(null),
  });

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar en las galerías… (ej. portero atajada)"
          className="h-9 rounded-lg border-transparent bg-muted/60 pl-8 placeholder:text-muted-foreground focus-visible:border-border"
          aria-label="Buscar fotos en la galería local"
        />
      </div>

      <div className="min-h-[10rem]">
        {isLoading || (isFetching && candidatos.length === 0) ? (
          <div className="flex h-40 items-center justify-center text-muted-foreground">
            <Spinner className="h-5 w-5" />
          </div>
        ) : isError ? (
          <p className="flex h-40 items-center justify-center text-sm text-destructive">
            No se pudo buscar en la galería local.
          </p>
        ) : !qDebounced ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <Search className="h-6 w-6" />
            <p className="text-sm">Escribe qué foto buscas en las galerías.</p>
          </div>
        ) : candidatos.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
            <ImageOff className="h-6 w-6" />
            <p className="text-sm">Sin resultados. Prueba otra búsqueda.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {candidatos.map((c, i) => {
              const clave = `${c.galeria_id ?? ""}-${c.archivo ?? c.url}`;
              const puedeGuardar = !!c.galeria_id && !!c.archivo;
              return (
                <figure
                  key={`${clave}-${i}`}
                  className="flex flex-col overflow-hidden rounded-lg border border-border bg-muted/20"
                >
                  <img
                    src={c.thumb || c.url}
                    alt={c.titulo || "Foto de la galería local"}
                    loading="lazy"
                    className="aspect-square w-full object-cover"
                  />
                  <figcaption className="flex flex-1 flex-col gap-1 px-2 py-1">
                    <span className="block truncate text-[11px] text-foreground">
                      {c.titulo || c.archivo || "Foto"}
                    </span>
                    {c.dispositivo && (
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {c.dispositivo}
                      </span>
                    )}
                    {puedeGuardar && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-auto h-7 justify-start gap-1 px-1 text-[11px]"
                        disabled={guardar.isPending}
                        onClick={() => {
                          setGuardandoClave(clave);
                          guardar.mutate(c);
                        }}
                      >
                        {guardar.isPending && guardandoClave === clave ? (
                          <Spinner className="h-3.5 w-3.5" />
                        ) : (
                          <Save className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        Guardar en Fotografías
                      </Button>
                    )}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Fotos() {
  // La Galería se acota a la marca del selector global del encabezado. Sin marca concreta ("Todas")
  // no hay filtro: se listan todos los dispositivos conectados.
  const { marcaActiva } = useMarcaActiva();
  const marca = marcaActiva ?? undefined;

  // Visor de ráfaga (burst del keeper): compartido por el buscador global y las carpetas.
  const [rafagaRef, setRafagaRef] = React.useState<RafagaRef | null>(null);

  // Dispositivos conectados: PUSH en vivo por SSE (sin sondeo ni parpadeo). El back manda un
  // snapshot inicial y reenvía la lista cada vez que alguien conecta/desconecta o cambia las
  // marcas que comparte. EventSource reconecta solo si el canal se corta. Sin `EventSource`
  // (SSR/test) la lista queda vacía y no se rompe nada.
  const [dispositivos, setDispositivos] = React.useState<DispositivoPropio[]>([]);
  const [cargandoDispositivos, setCargandoDispositivos] = React.useState(true);

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      setCargandoDispositivos(false);
      return;
    }
    setCargandoDispositivos(true);
    const params = marca ? `?marca=${encodeURIComponent(marca)}` : "";
    const fuente = new EventSource(`${BASE_API}/artes/propio/eventos${params}`);
    fuente.onmessage = (ev) => {
      try {
        const datos = JSON.parse(ev.data as string) as RespuestaDispositivosPropio;
        setDispositivos(datos.dispositivos ?? []);
      } catch {
        // Snapshot ilegible: lo ignoramos y esperamos el siguiente.
      }
      setCargandoDispositivos(false);
    };
    return () => fuente.close();
  }, [marca]);

  // Catálogo de marcas (id → nombre) para rotular a qué marcas comparte cada dispositivo.
  const { data: opciones } = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const nombreMarca = (id: string): string =>
    opciones?.marcas.find((m) => m.id === id)?.nombre ?? id;

  const hayDispositivos = dispositivos.length > 0;

  return (
    <>
      <TituloPagina titulo="Galería" icono={Camera} />
      {/* Descarga de la app: discreta arriba, ya que el cuerpo es la galería conectada. */}
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

      <div className="mx-auto w-full max-w-3xl space-y-6 py-6 pb-12">
        {/* Buscador GLOBAL de la biblioteca: en posición estable arriba y DESACOPLADO del SSE de
            dispositivos (su parpadeo no lo desmonta ni le borra el texto/foco). */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-4 w-4 text-keni" aria-hidden="true" />
              Buscar en la biblioteca
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BuscadorGlobalBiblioteca marca={marca} onRafaga={setRafagaRef} />
          </CardContent>
        </Card>

        {/* Carpetas navegables: Portal · Originales · Fotografías. */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="h-4 w-4 text-keni" aria-hidden="true" />
              Carpetas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CarpetasBiblioteca marca={marca} onRafaga={setRafagaRef} />
          </CardContent>
        </Card>

        {/* Explorador de galerías locales en vivo (túnel). DESACOPLADO del SSE de dispositivos. */}
        {marca && (
          <Card>
            <CardHeader>
              <CardTitle>Explorar galerías conectadas</CardTitle>
            </CardHeader>
            <CardContent>
              <BuscadorPropio marca={marca} />
            </CardContent>
          </Card>
        )}

        {/* Dispositivos conectados: su parpadeo (conectar/desconectar) NO afecta a lo de arriba. */}
        {cargandoDispositivos && !hayDispositivos ? (
          <div className="flex h-32 items-center justify-center text-muted-foreground">
            <Spinner className="h-5 w-5" />
          </div>
        ) : !hayDispositivos ? (
          // Vacío: nadie comparte a esta marca. Sobrio: la acción + una línea, centrado.
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
            <Button variant="outline" className="gap-2" onClick={() => api.descargarFotosApp()}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Descargar para macOS
            </Button>
            <p className="text-xs text-muted-foreground">
              Descarga la app en tu Mac y conéctala para ver aquí las galerías del equipo
            </p>
          </div>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Dispositivos conectados
                <Badge variant="secondary">{dispositivos.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {dispositivos.map((d) => (
                <div key={`${d.usuario}-${d.dispositivo}`} className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Camera className="h-4 w-4 text-keni" aria-hidden="true" />
                    <span className="text-sm font-medium">{d.dispositivo}</span>
                    {d.version && <Badge variant="secondary">v{d.version}</Badge>}
                    {d.usuario && (
                      <span className="text-xs text-muted-foreground">de {d.usuario}</span>
                    )}
                  </div>
                  {/* Marcas a las que este dispositivo comparte su galería (las eligió su dueño). */}
                  <div className="flex flex-wrap items-center gap-1.5 pl-6">
                    <span className="text-xs text-muted-foreground">Comparte con:</span>
                    {d.marcas.length === 0 ? (
                      <span className="text-xs text-muted-foreground">ninguna marca</span>
                    ) : (
                      d.marcas.map((m) => (
                        <Badge key={m} variant="outline">
                          {nombreMarca(m)}
                        </Badge>
                      ))
                    )}
                  </div>
                  {d.galerias.length === 0 ? (
                    <p className="pl-6 text-xs text-muted-foreground">Sin galerías procesadas.</p>
                  ) : (
                    <ul className="space-y-1 pl-6">
                      {d.galerias.map((g) => (
                        <li key={g.id} className="flex items-center justify-between gap-3 text-sm">
                          <span className="min-w-0 truncate">{g.nombre}</span>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {g.dia} · {g.fotos} fotos
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      <VisorRafaga ref_={rafagaRef} onCerrar={() => setRafagaRef(null)} />
    </>
  );
}
