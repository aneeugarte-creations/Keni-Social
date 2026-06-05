/**
 * Diálogo "Importar calendario": sube un archivo de CUALQUIER formato (Excel, CSV,
 * PDF, Word, una imagen/captura…) y vuelca su contenido al tablero.
 *
 * DOS CAMINOS (los decide el backend):
 *   - TABULAR (.xlsx/.csv bien formados): el back lo parsea de forma SÍNCRONA (sin IA);
 *     se PREVISUALIZA (sin escribir) y luego se confirma. UX clásica con vista previa.
 *   - IA (PDF/Word/imagen/captura/Excel raro): el back NO ejecuta `claude`; ENCOLA un job
 *     de IA al worker y responde `{pendiente, generacion}`. Aquí mostramos "Procesando con
 *     IA…" y SONDEAMOS la generación (`useGeneracion`); al completarse mostramos el nº de
 *     contenidos creados. Los ítems aterrizan como borradores en el tablero (la revisión).
 *
 * Las filas marcadas como obligatorias entran etiquetadas "compromiso" (lo hace el back).
 */
import { useMutation } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";
import * as React from "react";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { NINGUNA, ningunaParam } from "@/components/comunes/selectores";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { useGeneracion } from "@/hooks/use-generacion";
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
  RespuestaImportCalendarioPendiente,
  RespuestaImportPreview,
} from "@/types";

type RespuestaImportar =
  | RespuestaImportPreview
  | RespuestaImportCalendario
  | RespuestaImportCalendarioPendiente;

function esPreview(r: RespuestaImportar): r is RespuestaImportPreview {
  return (r as RespuestaImportPreview).previsualizacion === true;
}

function esPendiente(r: RespuestaImportar): r is RespuestaImportCalendarioPendiente {
  return (r as RespuestaImportCalendarioPendiente).pendiente === true;
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

  // Camino IA (PDF/Word/imagen): el back encola un job al worker; sondeamos la generación.
  const { generacion, ejecutando, iniciar, limpiar: limpiarGen, cancelar, cancelando } =
    useGeneracion();

  function limpiar() {
    setArchivo(null);
    setMarca(marcaPorDefecto);
    setPreview(null);
    setError("");
    limpiarGen();
  }

  function cerrar() {
    limpiar();
    onCerrar();
  }

  const previsualizar = useMutation({
    mutationFn: () => api.importarCalendario(archivo as File, { marca: marcaParam, previsualizar: true }),
    onSuccess: (r) => {
      setError("");
      if (esPreview(r)) {
        setPreview(r);
      } else if (esPendiente(r)) {
        // Formato no tabular: no hay preview síncrona. Arranca el sondeo de la importación IA.
        setPreview(null);
        iniciar(r.generacion);
      }
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "No se pudo leer el archivo."),
  });

  const importar = useMutation({
    mutationFn: () => api.importarCalendario(archivo as File, { marca: marcaParam }),
    onSuccess: (r) => {
      if (esPreview(r)) return;
      if (esPendiente(r)) {
        // Camino IA: el worker lo procesa; sondeamos la generación hasta su estado terminal.
        setError("");
        iniciar(r.generacion);
        return;
      }
      onImportado(r.creados);
      cerrar();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "No se pudo importar el archivo."),
  });

  // Cierre del camino IA: al completarse la generación, lee el nº de creados de su `resultado`
  // y avisa al padre; si falló, muestra el error. Los ítems aterrizan como borradores.
  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      onImportado(generacion.resultado?.creados ?? 0);
      cerrar();
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      setError(generacion.error || "No se pudo importar el calendario con IA.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generacion]);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    setArchivo(e.target.files?.[0] ?? null);
    setPreview(null);
    setError("");
    limpiarGen();
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

          {/* Camino IA (formato no tabular): el worker procesa el archivo; sondeamos. */}
          {generacion && (ejecutando || generacion.estado === "error") && (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <p className="flex items-center gap-2 font-medium">
                <Loader2 className="h-4 w-4 animate-spin" />
                Procesando con IA…
              </p>
              <p className="text-xs text-muted-foreground">
                La IA está leyendo el archivo y extrayendo el calendario. Los temas
                aparecerán como borradores en el tablero al terminar.
              </p>
              <ProgresoGeneracion
                generacion={generacion}
                onCancelar={cancelar}
                cancelando={cancelando}
              />
            </div>
          )}

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
            disabled={!archivo || previsualizar.isPending || ejecutando}
          >
            Previsualizar
          </Button>
          <Button
            onClick={() => importar.mutate()}
            disabled={!archivo || importar.isPending || ejecutando}
          >
            <Upload className="h-4 w-4" />
            Importar{preview ? ` ${preview.filas.length}` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
