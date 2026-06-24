/**
 * Página «Galería» — la FICHA (estilo marketplace) de la herramienta local keni-fotos.
 *
 * La consola en la nube no puede leer el disco del equipo, así que la galería se procesa EN LOCAL:
 * esta página explica qué es la herramienta y ofrece un botón simple para descargarla. Un Claude
 * local (con el CLAUDE.md del bundle) termina el trabajo sobre la carpeta de fotos del partido.
 *
 * El texto (prompt, comandos y pasos) lo sirve `GET /api/fotos/info`; si la carga falla, la página
 * cae a unas constantes embebidas (espejo del backend) para seguir siendo útil sin red.
 */
import { useQuery } from "@tanstack/react-query";
import { Camera, Check, Copy, Download, Terminal } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { RespuestaFotosInfo } from "@/lib/api";

/** Texto de respaldo (espejo de `api/fotos.py`) si `GET /api/fotos/info` no carga. */
const RESPALDO: RespuestaFotosInfo = {
  version: "",
  prompt_claude:
    "Eres el agente local de keni-fotos. Lee el CLAUDE.md de esta carpeta y monta y " +
    "ejecuta la app sobre mi carpeta de fotos del partido. Pregúntame la ruta de la " +
    "carpeta y el nombre del partido si no te los doy.",
  comandos: ["unzip keni-fotos.zip && cd keni-fotos", "claude"],
  instrucciones: [
    "Descarga keni-fotos.zip y descomprímelo en tu equipo.",
    "Abre Claude Code en la carpeta keni-fotos y pega el prompt de arriba.",
    "Indícale la ruta de tu carpeta de fotos del partido y su nombre.",
  ],
};

/** Lo que hace la herramienta (la «descripción de producto» de la ficha). */
const QUE_HACE = [
  "Agrupa automáticamente las ráfagas de cada cámara.",
  "Etiqueta cada ráfaga con IA: jugadores, momento y tipo de plano.",
  "Separa pre-partido, in-game y post-partido en orden cronológico.",
  "Abre una galería local buscable. Nunca toca tus fotos originales.",
];

/** Botón que copia un texto al portapapeles y confirma con un check efímero + toast. */
function BotonCopiar({ texto, etiqueta }: { texto: string; etiqueta: string }) {
  const [copiado, setCopiado] = React.useState(false);

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      toast.success("Copiado al portapapeles.");
      window.setTimeout(() => setCopiado(false), 1500);
    } catch {
      toast.error("No se pudo copiar al portapapeles.");
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="shrink-0"
      onClick={() => void copiar()}
      aria-label={`Copiar ${etiqueta}`}
    >
      {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      Copiar
    </Button>
  );
}

/** Bloque de texto monoespaciado para copiar (prompt o comando), con su botón de copia. */
function BloqueCopiable({ texto, etiqueta }: { texto: string; etiqueta: string }) {
  return (
    <div className="flex items-start gap-2">
      <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap break-words rounded-md border bg-muted px-3 py-2 font-mono text-xs text-foreground">
        {texto}
      </pre>
      <BotonCopiar texto={texto} etiqueta={etiqueta} />
    </div>
  );
}

export default function Fotos() {
  const { data } = useQuery({
    queryKey: ["fotos", "info"],
    queryFn: ({ signal }) => api.fotosInfo(signal),
  });

  // Mientras carga (o si falla) usamos el respaldo embebido: la página siempre muestra el texto.
  const info = data ?? RESPALDO;

  return (
    <>
      <TituloPagina titulo="Galería" icono={Camera} />

      <div className="mx-auto w-full max-w-2xl pb-12">
        {/* Ficha de producto: icono, nombre, qué es y el botón simple de descarga. */}
        <section className="flex flex-col items-center gap-4 py-10 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-keni/10 text-keni">
            <Camera className="h-8 w-8" aria-hidden="true" />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">keni-fotos</h2>
              {info.version && <Badge variant="secondary">v{info.version}</Badge>}
            </div>
            <p className="text-xs text-muted-foreground">Herramienta local · macOS</p>
          </div>

          <p className="max-w-md text-sm text-muted-foreground">
            Ordena las fotos de un partido en tu propio equipo. La web no puede leer tu disco, así
            que la descargas y un Claude local termina el trabajo sobre tu carpeta de fotos. Nada de
            lo que elijas sale de tu equipo.
          </p>

          <Button variant="outline" className="gap-2" onClick={() => api.descargarFotosBundle()}>
            <Download className="h-4 w-4" aria-hidden="true" />
            Descargar keni-fotos
          </Button>
          <p className="text-xs text-muted-foreground">
            Se monta y ejecuta con Claude Code; pega el prompt tras descomprimir.
          </p>
        </section>

        {/* Qué hace — la «descripción» del producto. */}
        <Card>
          <CardHeader>
            <CardTitle>Qué hace</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2.5">
              {QUE_HACE.map((linea) => (
                <li key={linea} className="flex items-start gap-2.5 text-sm">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-keni" aria-hidden="true" />
                  <span>{linea}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Cómo usarla: pasos + el prompt y los comandos para copiar. */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Cómo usarla</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <ol className="space-y-3">
              {info.instrucciones.map((paso, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                    {i + 1}
                  </span>
                  <span className="pt-0.5 text-sm">{paso}</span>
                </li>
              ))}
            </ol>

            <div className="space-y-2">
              <p className="text-label">Prompt para Claude</p>
              <BloqueCopiable texto={info.prompt_claude} etiqueta="el prompt" />
            </div>

            <div className="space-y-2">
              <p className="text-label flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
                Comandos
              </p>
              {info.comandos.map((comando) => (
                <BloqueCopiable key={comando} texto={comando} etiqueta="el comando" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
