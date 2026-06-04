/**
 * Visor de resultado de una generación de salida "documento" (un único texto
 * Markdown: brief, calendario semanal, metadatos de YouTube, termómetro, etc.).
 *
 * Renderiza el documento con `Markdown`, ofrece copiar al portapapeles y permite
 * guardarlo como publicación eligiendo UNA O VARIAS redes vía el historial NEUTRO
 * `POST /api/skills/historial/{id}/guardar` (común a todas las generaciones). El
 * termómetro genera el caption del posteo por red; al guardar se crea UN borrador por
 * red elegida (selector multi-red). Componente compartido (lo usa Termómetro).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, ExternalLink, FileText, ImageIcon, Loader2, Save } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/ui/Markdown";
import { api, ApiError, urlMedia } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import type { ImagenGenerada } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Enlace de éxito al tablero (modo Publicaciones) que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/operacion/feed/lista" className="inline-flex items-center gap-1 underline">
      Ver en el tablero
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

/**
 * Galería de imágenes producidas por una skill de imagen (estudio-imagen). Cada
 * imagen ya está en el almacén de media; aquí se PREVISUALIZA con un enlace para
 * abrirla/descargarla a tamaño completo. No renderiza nada si no hay imágenes.
 */
function PreviewImagenes({ imagenes }: { imagenes: ImagenGenerada[] }) {
  if (imagenes.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ImageIcon className="h-4 w-4 text-muted-foreground" />
        {imagenes.length === 1 ? "Imagen generada" : `Imágenes generadas (${imagenes.length})`}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {imagenes.map((img) => {
          const src = urlMedia(img.url || img.nombre);
          return (
            <a
              key={img.nombre}
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              className="group relative block overflow-hidden rounded-md border border-border bg-muted/20"
              title="Abrir a tamaño completo"
            >
              <img
                src={src}
                alt="Imagen generada por el Estudio de imagen"
                loading="lazy"
                className="aspect-square w-full object-contain"
              />
              <span className="absolute right-1.5 top-1.5 rounded bg-background/80 p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                <Download className="h-3.5 w-3.5" />
              </span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

export function ResultadoDocumento({
  documento,
  historialId,
  imagenes = [],
}: {
  documento: string;
  historialId: string;
  /** Imágenes producidas (skills de imagen); vacío para documentos de solo texto. */
  imagenes?: ImagenGenerada[];
}) {
  const queryClient = useQueryClient();
  const [redes, setRedes] = React.useState<Set<string>>(() => new Set());
  const [copiado, setCopiado] = React.useState(false);
  // A-4: timer de reset de 'copiado' con cleanup al desmontar.
  const timerRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const opcionesRedes = opcionesQuery.data?.redes.map((r) => ({ id: r.id, nombre: r.nombre })) ?? [];

  function alternarRed(red: string, marcada: boolean) {
    setRedes((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const guardar = useMutation({
    mutationFn: () => api.guardarHistorial(historialId, { redes: [...redes] }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const n = data?.publicaciones?.length ?? 1;
      toast.success(
        `Se ${n === 1 ? "guardó" : "guardaron"} ${n} ${n === 1 ? "publicación" : "publicaciones"}`,
        { description: <EnlacePublicaciones /> },
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(documento);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  const puedeGuardar = !guardar.isPending && historialId !== "" && redes.size > 0;

  return (
    <Card>
      <CardHeader className="space-y-2 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4 text-muted-foreground" />
          Documento generado
        </CardTitle>
        <Badge variant="aviso">Borrador · no guardado</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <PreviewImagenes imagenes={imagenes} />

        <div className="max-h-[32rem] overflow-auto rounded-md border border-border bg-muted/20 p-4 leading-relaxed">
          {documento.trim() ? (
            <Markdown>{documento}</Markdown>
          ) : (
            <p className="text-sm italic text-muted-foreground">El documento llegó vacío.</p>
          )}
        </div>

        <SelectorRedMultiple
          opciones={opcionesRedes}
          seleccionadas={redes}
          onCambio={alternarRed}
          disabled={guardar.isPending}
        />

        <div className="flex flex-wrap items-end gap-2">
          <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Guardar como publicación
          </Button>
          <Button variant="outline" size="sm" onClick={() => void copiar()}>
            {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiado ? "Copiado" : "Copiar"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
