/**
 * Página «Galería» — el panel de la galería LOCAL del equipo (apps keni-fotos conectadas).
 *
 * La consola en la nube no lee el disco del equipo: la galería se procesa EN LOCAL con la app de
 * escritorio keni-fotos, que abre un túnel hacia keni-social. Esta página se acota a la MARCA
 * activa del selector del encabezado: lista los dispositivos que comparten a esa marca
 * (`GET /api/artes/propio/dispositivos?marca=`) con su DUEÑO y galerías, y ofrece un buscador de
 * EXPLORACIÓN (`GET /api/artes/propio/buscar?marca=`) — aquí solo se MIRA; el adjuntar a una pieza
 * vive en el editor del feed. Arriba, un botón discreto para descargar la app (`/api/fotos/app`).
 *
 * Si no hay dispositivos para la marca, la página explica cómo empezar y destaca la descarga.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Camera, Download, ImageOff, Search } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

/** Buscador de EXPLORACIÓN de la galería local de una marca: candidatas en grid, sin adjuntar. */
function BuscadorPropio({ marca }: { marca: string }) {
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");

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
            {candidatos.map((c, i) => (
              <figure
                key={`${c.galeria_id ?? ""}-${c.archivo ?? c.url}-${i}`}
                className="overflow-hidden rounded-lg border border-border bg-muted/20"
              >
                <img
                  src={c.thumb || c.url}
                  alt={c.titulo || "Foto de la galería local"}
                  loading="lazy"
                  className="aspect-square w-full object-cover"
                />
                <figcaption className="space-y-0.5 px-2 py-1">
                  <span className="block truncate text-[11px] text-foreground">
                    {c.titulo || c.archivo || "Foto"}
                  </span>
                  {c.dispositivo && (
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {c.dispositivo}
                    </span>
                  )}
                </figcaption>
              </figure>
            ))}
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

  const { data, isLoading } = useQuery({
    queryKey: ["propio", "dispositivos", marca ?? ""],
    queryFn: ({ signal }) => api.dispositivosPropio(marca, signal),
    // Sondeo corto: cuando alguien abre la app y conecta el túnel, su equipo aparece casi al
    // instante sin recargar. `keepPreviousData` evita que el contador parpadee a vacío en el
    // refetch. Refresca también al volver a la pestaña.
    refetchInterval: 5_000,
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
  });

  // Catálogo de marcas (id → nombre) para rotular a qué marcas comparte cada dispositivo.
  const { data: opciones } = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const nombreMarca = (id: string): string =>
    opciones?.marcas.find((m) => m.id === id)?.nombre ?? id;

  const dispositivos = data?.dispositivos ?? [];
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

      <div className="mx-auto w-full max-w-3xl pb-12">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center text-muted-foreground">
            <Spinner className="h-5 w-5" />
          </div>
        ) : !hayDispositivos ? (
          // Vacío: nadie comparte a esta marca. Sobrio como Audio: la acción + una línea, centrado.
          <div className="flex min-h-[calc(100dvh-8rem)] flex-col items-center justify-center gap-3 text-center">
            <Button variant="outline" className="gap-2" onClick={() => api.descargarFotosApp()}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Descargar para macOS
            </Button>
            <p className="text-xs text-muted-foreground">
              Descarga la app en tu Mac y conéctala para ver aquí las galerías del equipo
            </p>
          </div>
        ) : (
          <div className="space-y-6 py-6">
            {/* Dispositivos que comparten a la marca: dueño, marcas compartidas y galerías. */}
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
                          <li
                            key={g.id}
                            className="flex items-center justify-between gap-3 text-sm"
                          >
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

            {/* Explorar las galerías de la marca (solo mirar; adjuntar se hace desde el editor).
                Sin marca concreta ("Todas") no hay una galería única que explorar. */}
            {marca && (
              <Card>
                <CardHeader>
                  <CardTitle>Explorar fotos</CardTitle>
                </CardHeader>
                <CardContent>
                  <BuscadorPropio marca={marca} />
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </>
  );
}
