/**
 * Página «Galería» — el panel de la galería LOCAL del equipo (apps keni-fotos conectadas).
 *
 * La consola en la nube no lee el disco del equipo: la galería se procesa EN LOCAL con la app de
 * escritorio keni-fotos, que abre un túnel hacia keni-social. Esta página muestra los dispositivos
 * conectados con sus galerías (`GET /api/artes/propio/dispositivos`) y un buscador de exploración
 * (`GET /api/artes/propio/buscar`, marca fija Claro Sports) — aquí solo se MIRA; el adjuntar a una
 * pieza vive en el editor del feed. Arriba, un botón discreto para descargar la app (`/api/fotos/app`).
 *
 * Si no hay dispositivos conectados, la página explica cómo empezar y destaca la descarga.
 */
import { useQuery } from "@tanstack/react-query";
import { Camera, Download, ImageOff, Search, Terminal } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";

/** Marca cuya galería local sirve la página (la del piloto de fotos propias). */
const MARCA = "claro-sports";

/** Buscador de EXPLORACIÓN de la galería local: muestra candidatas en grid, sin adjuntar. */
function BuscadorPropio() {
  const [q, setQ] = React.useState("");
  const [qDebounced, setQDebounced] = React.useState("");

  // Debounce de 350ms: el túnel hace fan-out a las apps; no lo golpeamos en cada tecla.
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ["propio", "explorar", qDebounced],
    queryFn: ({ signal }) => api.buscarPropio({ q: qDebounced || undefined, marca: MARCA }, signal),
  });

  const candidatos = data?.candidatos ?? [];

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar en tus galerías… (ej. portero atajada)"
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
            <p className="text-sm">Escribe qué foto buscas en tus galerías.</p>
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
  const { data, isLoading } = useQuery({
    queryKey: ["propio", "dispositivos"],
    queryFn: ({ signal }) => api.dispositivosPropio(signal),
    refetchInterval: 15_000,
  });

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
          // Vacío explicativo: nadie ha conectado su app; se destaca la descarga.
          <section className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-keni/10 text-keni">
              <Camera className="h-8 w-8" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">Sin dispositivos conectados</h2>
              <p className="max-w-md text-sm text-muted-foreground">
                Descarga la app keni-fotos en el equipo que tiene las fotos del partido. Al abrirla
                e iniciar sesión, sus galerías aparecen aquí y podrás usarlas en tus piezas.
              </p>
            </div>
            <Button className="gap-2" onClick={() => api.descargarFotosApp()}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Descargar para macOS
            </Button>
            <p className="max-w-md text-xs text-muted-foreground">
              Abre el .dmg y arrastra keni-fotos a Aplicaciones. La primera vez macOS la bloquea
              (app sin firmar): ábrela con clic derecho → Abrir. Procesa la carpeta del partido y
              deja la app abierta con tu sesión iniciada.
            </p>
          </section>
        ) : (
          <div className="space-y-6 py-6">
            {/* Dispositivos conectados con sus galerías. */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  Dispositivos conectados
                  <Badge variant="secondary">{dispositivos.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {dispositivos.map((d) => (
                  <div key={`${d.dispositivo}-${d.version}`} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Camera className="h-4 w-4 text-keni" aria-hidden="true" />
                      <span className="text-sm font-medium">{d.dispositivo}</span>
                      {d.version && <Badge variant="secondary">v{d.version}</Badge>}
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

            {/* Explorar la galería local (solo mirar; adjuntar se hace desde el editor). */}
            <Card>
              <CardHeader>
                <CardTitle>Explorar fotos</CardTitle>
              </CardHeader>
              <CardContent>
                <BuscadorPropio />
              </CardContent>
            </Card>
          </div>
        )}

        {/* Modo avanzado: descargar el código y montar la app con Claude. */}
        <Card className="mt-6">
          <CardContent className="pt-6">
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                Modo avanzado · montar con Claude
              </summary>
              <div className="mt-4 space-y-3">
                <p className="text-sm text-muted-foreground">
                  ¿No puedes abrir la app? Descarga el código y deja que un Claude local la compile y
                  lance.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => api.descargarFotosBundle()}
                >
                  <Terminal className="h-4 w-4" aria-hidden="true" />
                  Descargar código
                </Button>
              </div>
            </details>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
