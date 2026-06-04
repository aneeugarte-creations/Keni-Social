/**
 * Diálogo "Importar calendario": sube un archivo de CUALQUIER formato (Excel, CSV,
 * PDF, Word, una imagen/captura…) y vuelca su contenido al tablero. El backend usa el
 * parser tabular para .xlsx/.csv bien formados y, para todo lo demás, deja que Claude
 * LEA el archivo y extraiga el calendario. Previsualiza (sin escribir) y luego confirma.
 * Las filas marcadas como obligatorias entran etiquetadas "compromiso" (lo hace el back).
 */
import { useMutation } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import * as React from "react";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { NINGUNA, ningunaParam } from "@/components/comunes/selectores";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import type {
  MarcaDisponible,
  RespuestaImportCalendario,
  RespuestaImportPreview,
} from "@/types";

function esPreview(
  r: RespuestaImportPreview | RespuestaImportCalendario,
): r is RespuestaImportPreview {
  return (r as RespuestaImportPreview).previsualizacion === true;
}

export function DialogoImportarCalendario({
  abierto,
  onCerrar,
  marcas,
  onImportado,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: MarcaDisponible[];
  /** Se llama tras importar con éxito (con el nº de contenidos creados). */
  onImportado: (creados: number) => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const marcaPorDefecto =
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : NINGUNA;
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [marca, setMarca] = React.useState<string>(marcaPorDefecto);
  const [preview, setPreview] = React.useState<RespuestaImportPreview | null>(null);
  const [error, setError] = React.useState<string>("");

  const marcaParam = ningunaParam(marca) || undefined;

  function limpiar() {
    setArchivo(null);
    setMarca(marcaPorDefecto);
    setPreview(null);
    setError("");
  }

  function cerrar() {
    limpiar();
    onCerrar();
  }

  const previsualizar = useMutation({
    mutationFn: () => api.importarCalendario(archivo as File, { marca: marcaParam, previsualizar: true }),
    onSuccess: (r) => {
      setError("");
      if (esPreview(r)) setPreview(r);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "No se pudo leer el archivo."),
  });

  const importar = useMutation({
    mutationFn: () => api.importarCalendario(archivo as File, { marca: marcaParam }),
    onSuccess: (r) => {
      if (!esPreview(r)) {
        onImportado(r.creados);
        cerrar();
      }
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "No se pudo importar el archivo."),
  });

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    setArchivo(e.target.files?.[0] ?? null);
    setPreview(null);
    setError("");
  }

  return (
    <Dialog open={abierto} onOpenChange={(o) => { if (!o) cerrar(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Importar calendario</DialogTitle>
          <DialogDescription>
            Sube un archivo en cualquier formato (Excel, CSV, PDF, Word, una imagen o
            captura…). La IA lo interpreta y extrae título, fecha, marca, redes, prioridad y
            compromiso. Las filas marcadas como obligatorias se etiquetan “compromiso”.
            Previsualiza antes de volcar al tablero.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Input type="file" onChange={onArchivo} aria-label="Archivo a importar" />
          <div>
            <p className="mb-1 text-xs text-muted-foreground">
              Marca por defecto (para las filas sin marca propia):
            </p>
            <SelectorMarca
              marcas={marcas}
              valor={marca}
              onCambio={setMarca}
              incluirTodas={false}
              incluirNinguna
              etiquetaNinguna="Ninguna"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {preview && (
            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">
                {preview.filas.length} fila(s) a importar
                {preview.errores.length > 0 && `, ${preview.errores.length} con aviso`}.
              </p>
              <ul className="mt-2 max-h-48 overflow-auto">
                {preview.filas.slice(0, 20).map((f, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between gap-2 border-b border-border/50 py-1 last:border-0"
                  >
                    <span className="truncate">{f.titulo}</span>
                    <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                      {f.fecha && <span className="tabular-nums">{f.fecha}</span>}
                      {f.compromiso && <Badge variant="outline">compromiso</Badge>}
                    </span>
                  </li>
                ))}
              </ul>
              {preview.errores.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-amber-700 dark:text-amber-300">
                  {preview.errores.slice(0, 5).map((er, i) => (
                    <li key={i}>Fila {er.fila ?? "?"}: {er.motivo}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => previsualizar.mutate()}
            disabled={!archivo || previsualizar.isPending}
          >
            Previsualizar
          </Button>
          <Button
            onClick={() => importar.mutate()}
            disabled={!archivo || importar.isPending}
          >
            <Upload className="h-4 w-4" />
            Importar{preview ? ` ${preview.filas.length}` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
