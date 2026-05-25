/**
 * Visor de resultado para skills de salida "documento" (un único texto Markdown:
 * brief, calendario semanal, metadatos de YouTube, auditoría de imagen, etc.).
 *
 * Renderiza el documento con `Markdown`, ofrece copiar al portapapeles y, como
 * en `ResultadoRedes`, permite guardarlo como publicación eligiendo una red vía
 * `POST /api/skills/historial/{id}/guardar`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, FileText, Loader2, Save } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";

import { CLAVE_PUBLICACIONES } from "../publicaciones/claves";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Enlace de éxito a Publicaciones que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/publicaciones" className="inline-flex items-center gap-1 underline">
      Ver en Publicaciones
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

export function ResultadoDocumento({
  documento,
  historialId,
}: {
  documento: string;
  historialId: string;
}) {
  const queryClient = useQueryClient();
  const [red, setRed] = React.useState("");
  const [copiado, setCopiado] = React.useState(false);

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const redes = opcionesQuery.data?.redes.map((r) => ({ id: r.id, nombre: r.nombre })) ?? [];

  const guardar = useMutation({
    mutationFn: () => api.guardarHistorial(historialId, { red }),
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
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  const puedeGuardar = !guardar.isPending && historialId !== "" && red !== "";

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
        <div className="max-h-[32rem] overflow-auto rounded-md border border-border bg-muted/20 p-4 leading-relaxed">
          {documento.trim() ? (
            <Markdown>{documento}</Markdown>
          ) : (
            <p className="text-sm italic text-muted-foreground">El documento llegó vacío.</p>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor="doc-red">Red</Label>
            <Select value={red} onValueChange={setRed}>
              <SelectTrigger id="doc-red" className="w-44">
                <SelectValue placeholder="Elige una red" />
              </SelectTrigger>
              <SelectContent>
                {redes.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
