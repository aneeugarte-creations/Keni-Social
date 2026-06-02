/**
 * Flujo "Importar documento" de la parrilla (turnos + eventos).
 *
 * 1. Un botón abre un Dialog con una zona drag-and-drop (acepta cualquier archivo:
 *    PDF, imagen, docx, xlsx, txt) + un selector de SEMANA destino (por defecto la
 *    semana en vista). Al enviar, sube el archivo (`POST /api/parrilla/importar`).
 * 2. Un `claude -p` analiza el documento en 2º plano y produce una PROPUESTA (diff de
 *    operaciones). Sondeamos su estado (`usePropuestaParrilla`) hasta `pendiente`/`error`.
 * 3. Cuando está lista, mostramos una PREVISUALIZACIÓN: el MISMO calendario de la página,
 *    en solo lectura, con las operaciones propuestas superpuestas y codificadas por color
 *    (verde nuevo · ámbar cambio · rojo conflicto), vía `CalendarioPreview`.
 * 4. Botones Aceptar (mergea) y Descartar. Al aceptar refrescamos el calendario real.
 *    Además exponemos un badge con las propuestas pendientes.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  Inbox,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  CalendarioPreview,
  LeyendaPreview,
} from "@/components/parrilla/CalendarioPreview";
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
import { Label } from "@/components/ui/label";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { usePropuestaParrilla } from "@/hooks/use-propuesta-parrilla";
import { api, ApiError } from "@/lib/api";
import {
  formatearRango,
  lunesDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import type { ConflictoAplicarParrilla, EstadoPropuestaParrilla } from "@/types";

function mensajeError(e: unknown): string {
  if (e instanceof ApiError || e instanceof Error) return e.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Colapsable con el prompt EXACTO enviado a `claude -p` (visibilidad/control). */
function VerPrompt({ prompt }: { prompt: string }) {
  return (
    <details className="rounded-md border bg-muted/30 text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-medium">
        Ver prompt enviado a Keni
      </summary>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words border-t px-3 py-2 text-xs text-muted-foreground">
        {prompt}
      </pre>
    </details>
  );
}

/**
 * Punto de entrada: botón "Importar documento" + badge de pendientes. La apertura del
 * Dialog y la propuesta en curso se gestionan aquí; el calendario padre solo nos pasa la
 * semana en vista (default del selector) y un `onAplicado` para refrescar tras el merge.
 */
export function ImportarDocumentoParrilla({
  semanaEnVista,
  onAplicado,
}: {
  /** Lunes ISO de la semana visible (default del selector de semana). */
  semanaEnVista: string;
  /** Se invoca tras aplicar una propuesta (para refrescar el calendario real). */
  onAplicado: () => void;
}) {
  const [abierto, setAbierto] = React.useState(false);
  // Propuesta activa que estamos siguiendo en el Dialog (recién subida o reabierta).
  const [propuestaId, setPropuestaId] = React.useState<string | null>(null);

  return (
    <>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          onClick={() => {
            setPropuestaId(null);
            setAbierto(true);
          }}
          data-testid="rota-importar-documento"
        >
          <Upload className="h-4 w-4" />
          Importar documento
        </Button>
        <BadgePropuestasPendientes
          onAbrir={(id) => {
            setPropuestaId(id);
            setAbierto(true);
          }}
        />
      </div>

      {abierto && (
        <DialogImportarParrilla
          semanaEnVista={semanaEnVista}
          propuestaId={propuestaId}
          setPropuestaId={setPropuestaId}
          onCerrar={() => setAbierto(false)}
          onAplicado={() => {
            onAplicado();
            setAbierto(false);
          }}
        />
      )}
    </>
  );
}

/** Badge/lista de propuestas pendientes (las más recientes primero). */
function BadgePropuestasPendientes({ onAbrir }: { onAbrir: (id: string) => void }) {
  const pendientesQ = useQuery({
    queryKey: ["parrilla", "propuestas", "pendiente"],
    queryFn: ({ signal }) => api.propuestasParrilla({ estado: "pendiente" }, signal),
    // Refresco moderado para que aparezcan propuestas terminadas sin recargar.
    refetchInterval: 8000,
  });
  const propuestas = pendientesQ.data?.propuestas ?? [];
  if (propuestas.length === 0) return null;

  const items: EntradaMenuContextual[] = propuestas.map((p) => ({
    etiqueta: `Documento${p.doc_tipo ? ` ${p.doc_tipo.toUpperCase()}` : ""} · semana ${p.semana}`,
    icono: FileText,
    onClick: () => onAbrir(p.id),
  }));

  return (
    <MenuContextual items={items} disparador="click">
      <Button variant="ghost" size="sm" className="gap-1.5" title="Propuestas pendientes">
        <Inbox className="h-4 w-4" />
        <Badge variant="aviso" className="h-5 px-1.5 font-normal">
          {propuestas.length}
        </Badge>
      </Button>
    </MenuContextual>
  );
}

/** Selector de semana compacto (chevrons + rango legible). */
function SelectorSemana({
  lunes,
  setLunes,
}: {
  lunes: string;
  setLunes: (l: string) => void;
}) {
  const fin = lunesSiguiente(lunes, 1);
  const finInclusivo = new Date(`${fin}T00:00:00`);
  finInclusivo.setDate(finInclusivo.getDate() - 1);
  const finIso = `${finInclusivo.getFullYear()}-${String(finInclusivo.getMonth() + 1).padStart(2, "0")}-${String(finInclusivo.getDate()).padStart(2, "0")}`;
  return (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label="Semana anterior"
        onClick={() => setLunes(lunesSiguiente(lunes, -1))}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <div className="min-w-[11rem] text-center text-sm font-medium">
        {formatearRango(lunes, finIso) || "Semana"}
      </div>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label="Semana siguiente"
        onClick={() => setLunes(lunesSiguiente(lunes, 1))}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

/** Zona drag-and-drop que acepta cualquier archivo. */
function Dropzone({
  archivo,
  setArchivo,
}: {
  archivo: File | null;
  setArchivo: (f: File | null) => void;
}) {
  const [arrastrando, setArrastrando] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setArrastrando(true);
      }}
      onDragLeave={() => setArrastrando(false)}
      onDrop={(e) => {
        e.preventDefault();
        setArrastrando(false);
        const f = e.dataTransfer.files?.[0];
        if (f) setArchivo(f);
      }}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      role="button"
      tabIndex={0}
      aria-label="Soltar o elegir un archivo"
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition",
        arrastrando
          ? "border-primary bg-primary/5"
          : "border-border hover:border-primary/60 hover:bg-muted/40",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        // Aceptamos cualquier archivo: PDF, imagen, docx, xlsx, txt…
        onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
      />
      {archivo ? (
        <>
          <FileText className="h-6 w-6 text-primary" />
          <div className="flex items-center gap-2 text-sm font-medium">
            <span className="max-w-[16rem] truncate">{archivo.name}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setArchivo(null);
              }}
              className="text-muted-foreground hover:text-destructive"
              aria-label="Quitar archivo"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <span className="text-xs text-muted-foreground">
            {(archivo.size / 1024).toFixed(0)} KB
          </span>
        </>
      ) : (
        <>
          <Upload className="h-6 w-6 text-muted-foreground" />
          <p className="text-sm font-medium">Arrastra un documento o haz clic para elegir</p>
          <p className="text-xs text-muted-foreground">
            PDF, imagen, Word, Excel o texto. Keni lo analizará y propondrá los cambios.
          </p>
        </>
      )}
    </div>
  );
}

function DialogImportarParrilla({
  semanaEnVista,
  propuestaId,
  setPropuestaId,
  onCerrar,
  onAplicado,
}: {
  semanaEnVista: string;
  propuestaId: string | null;
  setPropuestaId: (id: string | null) => void;
  onCerrar: () => void;
  onAplicado: () => void;
}) {
  const queryClient = useQueryClient();
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [semana, setSemana] = React.useState(() => lunesDeSemana(new Date(`${semanaEnVista}T00:00:00`)));
  // Payload de un 409 al aplicar (el calendario cambió): lo mostramos para reabrir/refrescar.
  const [conflictoAplicar, setConflictoAplicar] = React.useState<ConflictoAplicarParrilla | null>(null);

  const { propuesta, generando } = usePropuestaParrilla(propuestaId);

  // Stream EN VIVO del `claude -p` + prompt exacto: sondeamos la generación por su id.
  // Refresca token a token SOLO mientras genera; al terminar se queda quieto (pero seguimos
  // teniendo el objeto, con su prompt, para "Ver prompt" en las fases error/pendiente).
  const genId = propuesta?.gen_id || "";
  const genQuery = useQuery({
    queryKey: ["generacion", genId],
    queryFn: ({ signal }) => api.generacion(genId, signal).then((r) => r.generacion),
    enabled: !!genId,
    refetchInterval: () => (propuesta?.estado === "generando" ? 1200 : false),
  });
  const generacion = genQuery.data;

  const subir = useMutation({
    mutationFn: () => api.importarParrilla(archivo!, semana),
    onSuccess: (r) => {
      setPropuestaId(r.propuesta_id);
      queryClient.invalidateQueries({ queryKey: ["parrilla", "propuestas"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aplicar = useMutation({
    mutationFn: () => api.aplicarPropuestaParrilla(propuestaId!),
    onSuccess: (r) => {
      toast.success(r?.mensaje ?? "Propuesta aplicada al calendario.");
      // Refresca el calendario real y la lista de pendientes.
      queryClient.invalidateQueries({ queryKey: ["rota"] });
      queryClient.invalidateQueries({ queryKey: ["parrilla"] });
      onAplicado();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        setConflictoAplicar((e.cuerpo as ConflictoAplicarParrilla | null) ?? { mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const descartar = useMutation({
    mutationFn: () => api.descartarPropuestaParrilla(propuestaId!),
    onSuccess: () => {
      toast.success("Propuesta descartada.");
      queryClient.invalidateQueries({ queryKey: ["parrilla", "propuestas"] });
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // ----- Fase: subida (aún no hay propuesta) -----
  const enSubida = !propuestaId;
  // ----- Fase: generando / error / pendiente -----
  const estado: EstadoPropuestaParrilla | undefined = propuesta?.estado;
  const operaciones = propuesta?.operaciones ?? [];
  const nConflictos = operaciones.filter((o) => o.conflicto).length;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent
        className={cn(
          // En modo previsualización el Dialog se hace ancho para que quepa el calendario.
          estado === "pendiente" ? "max-w-5xl" : "max-w-lg",
        )}
      >
        <DialogHeader>
          <DialogTitle>Importar documento a la parrilla</DialogTitle>
          <DialogDescription>
            Sube una nota, parrilla o calendario; Keni lo analiza y propone los cambios
            (eventos y turnos). Revisa la previsualización antes de aplicar.
          </DialogDescription>
        </DialogHeader>

        {enSubida ? (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Semana destino</Label>
              <SelectorSemana lunes={semana} setLunes={setSemana} />
            </div>
            <Dropzone archivo={archivo} setArchivo={setArchivo} />
          </div>
        ) : generando || !propuesta ? (
          <div className="space-y-3">
            {generacion ? (
              // Stream en vivo del `claude -p` (fase + tokens + métricas), mismo
              // componente que la generación de copy.
              <ProgresoGeneracion generacion={generacion} />
            ) : (
              <div className="flex flex-col items-center gap-3 py-10 text-center">
                <Loader2 className="h-7 w-7 animate-spin text-primary" />
                <p className="text-sm font-medium">Analizando el documento…</p>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              Keni está leyendo el documento y preparando la propuesta. Puedes cerrar y volver
              desde el badge de pendientes; el análisis sigue en segundo plano.
            </p>
            {generacion?.prompt && <VerPrompt prompt={generacion.prompt} />}
          </div>
        ) : estado === "error" ? (
          <div className="space-y-3">
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <AlertTriangle className="h-7 w-7 text-destructive" />
              <p className="text-sm font-medium">No se pudo analizar el documento</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {propuesta.error || "El análisis falló. Vuelve a intentarlo con otro documento."}
              </p>
            </div>
            {generacion?.prompt && <VerPrompt prompt={generacion.prompt} />}
          </div>
        ) : (
          // estado === "pendiente" (o aplicada/descartada que tratamos como vista final)
          <div className="space-y-3">
            {propuesta.resumen && (
              <p className="rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                {propuesta.resumen}
              </p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <LeyendaPreview />
              {nConflictos > 0 && (
                <Badge variant="error" className="gap-1 font-normal">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {nConflictos} conflicto{nConflictos === 1 ? "" : "s"}
                </Badge>
              )}
            </div>
            <CalendarioPreview semana={propuesta.semana} operaciones={operaciones} />
            {operaciones.length === 0 && (
              <p className="text-sm text-muted-foreground">
                La propuesta no contiene cambios aplicables.
              </p>
            )}
            {generacion?.prompt && <VerPrompt prompt={generacion.prompt} />}
            {conflictoAplicar && (
              <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
                <p className="font-medium">El calendario cambió desde que se generó esta propuesta.</p>
                <p>
                  {conflictoAplicar.mensaje ??
                    conflictoAplicar.error ??
                    "Refresca y vuelve a revisar la previsualización antes de aplicar."}
                </p>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {enSubida ? (
            <>
              <Button variant="ghost" onClick={onCerrar}>
                Cancelar
              </Button>
              <Button
                onClick={() => subir.mutate()}
                disabled={!archivo || subir.isPending}
                data-testid="rota-importar-subir"
              >
                {subir.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                <Upload className="h-4 w-4" />
                Subir y analizar
              </Button>
            </>
          ) : estado === "pendiente" ? (
            <>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => descartar.mutate()}
                disabled={descartar.isPending || aplicar.isPending}
              >
                {descartar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <X className="h-4 w-4" />
                )}
                Descartar
              </Button>
              <Button
                onClick={() => aplicar.mutate()}
                disabled={aplicar.isPending || descartar.isPending || operaciones.length === 0}
                data-testid="rota-importar-aceptar"
              >
                {aplicar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Aceptar y aplicar
              </Button>
            </>
          ) : (
            <Button variant="ghost" onClick={onCerrar}>
              Cerrar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
