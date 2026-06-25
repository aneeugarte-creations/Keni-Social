/**
 * Página «Galería» — el panel de la galería LOCAL del equipo (apps keni-fotos conectadas).
 *
 * La consola en la nube no lee el disco del equipo: la galería se procesa EN LOCAL con la app de
 * escritorio keni-fotos, que abre un túnel hacia keni-social. Esta página lista TODOS los
 * dispositivos conectados (`GET /api/artes/propio/dispositivos`) con su DUEÑO, las MARCAS a las que
 * comparte cada uno y sus galerías. Aquí solo se MIRA; el adjuntar a una pieza vive en el editor del
 * feed (donde la fuente «Propio» tira de los dispositivos que comparten a la marca de la pieza).
 * Arriba, un botón discreto para descargar la app (`/api/fotos/app`).
 *
 * Si no hay dispositivos conectados, la página explica cómo empezar y destaca la descarga.
 */
import { useQuery } from "@tanstack/react-query";
import { Camera, Download } from "lucide-react";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";

export default function Fotos() {
  const { data, isLoading } = useQuery({
    queryKey: ["propio", "dispositivos"],
    queryFn: ({ signal }) => api.dispositivosPropio(undefined, signal),
    // Sondeo corto: cuando alguien abre la app y conecta el túnel, su equipo aparece casi al
    // instante sin recargar. Refresca también al volver a la pestaña.
    refetchInterval: 5_000,
    refetchOnWindowFocus: true,
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
          // Vacío: nadie ha conectado su app. Sobrio como Audio: la acción + una línea, centrado.
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
          <div className="py-6">
            {/* Dispositivos conectados: dueño, marcas a las que comparte y galerías. */}
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
          </div>
        )}
      </div>
    </>
  );
}
