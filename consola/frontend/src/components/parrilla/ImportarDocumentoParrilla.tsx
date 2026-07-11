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
  FileText,
  Inbox,
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
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { usePropuestaParrilla } from "@/hooks/use-propuesta-parrilla";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  ConflictoAplicarParrilla,
  EstadoPropuestaParrilla,
  PropuestaParrilla,
} from "@/types";

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
 * Línea-resumen de una propuesta multi-semana: "N cambios · M semanas · del DD/MM/AAAA al
 * DD/MM/AAAA". Usa `propuesta.rango` cuando viene; si no (propuesta legada de una sola
 * semana), cae a `nOperaciones` y a `propuesta.semana`.
 */
function ResumenRango({
  propuesta,
  nOperaciones,
}: {
  propuesta: PropuestaParrilla;
  nOperaciones: number;
}) {
  const rango = propuesta.rango;
  const total = rango?.total ?? nOperaciones;
  const nSemanas = rango?.semanas?.length ?? (propuesta.semana ? 1 : 0);
  const fmt = (iso: string) => {
    const d = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("es-MX", { day: "2-digit", month: "2-digit", year: "numeric" });
  };
  const partes: string[] = [`${total} cambio${total === 1 ? "" : "s"}`];
  if (nSemanas > 0) partes.push(`${nSemanas} semana${nSemanas === 1 ? "" : "s"}`);
  if (rango?.desde && rango?.hasta) partes.push(`del ${fmt(rango.desde)} al ${fmt(rango.hasta)}`);
  return (
    <p className="text-xs font-medium text-muted-foreground" data-testid="rota-importar-resumen-rango">
      {partes.join(" · ")}
    </p>
  );
}

/**
 * Punto de entrada: botón "Importar documento" + badge de pendientes. La apertura del
 * Dialog y la propuesta en curso se gestionan aquí; el calendario padre solo nos pasa un
 * `onAplicado` para refrescar tras el merge. No se elige semana destino: una propuesta
 * puede abarcar muchas semanas (hasta un año) y cada operación lleva su propia fecha.
 */
export function ImportarDocumentoParrilla({
  onAplicado,
  marca,
  renderTrigger,
}: {
  /** Se invoca tras aplicar una propuesta (para refrescar el calendario real). */
  onAplicado: () => void;
  /** Marca activa: dice de qué equipo son las franjas a las que se mapean las personas. */
  marca: string;
  /** Disparador a medida: recibe la función que abre el asistente. Sin él se pinta el botón
   *  outline «Importar documento» por defecto; con él se puede incrustar como fila de una franja. */
  renderTrigger?: (abrir: () => void) => React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(false);
  // Propuesta activa que estamos siguiendo en el Dialog (recién subida o reabierta).
  const [propuestaId, setPropuestaId] = React.useState<string | null>(null);
  const abrir = () => {
    setPropuestaId(null);
    setAbierto(true);
  };

  return (
    <>
      <div className="flex items-center gap-2">
        {renderTrigger ? (
          renderTrigger(abrir)
        ) : (
          <Button variant="outline" onClick={abrir} data-testid="rota-importar-documento">
            <Upload className="h-4 w-4" />
            Importar documento
          </Button>
        )}
        <BadgePropuestasPendientes
          onAbrir={(id) => {
            setPropuestaId(id);
            setAbierto(true);
          }}
        />
      </div>

      {abierto && (
        <DialogImportarParrilla
          propuestaId={propuestaId}
          setPropuestaId={setPropuestaId}
          marca={marca}
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
    etiqueta: `Documento${p.doc_tipo ? ` ${p.doc_tipo.toUpperCase()}` : ""}${p.creado ? ` · ${p.creado.slice(0, 10)}` : ""}`,
    icono: FileText,
    onClick: () => onAbrir(p.id),
  }));

  return (
    <MenuContextual items={items} disparador="click">
      <Tooltip label="Propuestas pendientes">
        <Button variant="ghost" size="sm" className="gap-1.5">
          <Inbox className="h-4 w-4" />
          <Badge variant="aviso" className="h-5 px-1.5 font-normal">
            {propuestas.length}
          </Badge>
        </Button>
      </Tooltip>
    </MenuContextual>
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
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-8 text-center transition",
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
            PDF, imagen, Word, Excel o texto.
          </p>
        </>
      )}
    </div>
  );
}

function DialogImportarParrilla({
  propuestaId,
  setPropuestaId,
  marca,
  onCerrar,
  onAplicado,
}: {
  propuestaId: string | null;
  setPropuestaId: (id: string | null) => void;
  marca: string;
  onCerrar: () => void;
  onAplicado: () => void;
}) {
  const queryClient = useQueryClient();
  const [archivo, setArchivo] = React.useState<File | null>(null);
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
    mutationFn: () => api.importarParrilla(archivo!, { marca, modo: "turnos" }),
    onSuccess: (r) => {
      setPropuestaId(r.propuesta_id);
      queryClient.invalidateQueries({ queryKey: ["parrilla", "propuestas"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aplicar = useMutation({
    mutationFn: () => api.aplicarPropuestaParrilla(propuestaId!),
    onSuccess: (r) => {
      const creados = (r?.turnos_creados ?? 0) + (r?.eventos_creados ?? 0);
      const yaEstaban = r?.ya_existe ?? 0;
      const enConflicto = r?.omitidas_conflicto ?? 0;
      const extra = [
        yaEstaban > 0 ? `${yaEstaban} ya ${yaEstaban === 1 ? "estaba" : "estaban"}` : "",
        enConflicto > 0 ? `${enConflicto} omitid${enConflicto === 1 ? "o" : "os"} por conflicto` : "",
      ]
        .filter(Boolean)
        .join(", ");
      toast.success(
        `Aplicada. ${creados} ${creados === 1 ? "nuevo" : "nuevos"}${extra ? `, ${extra}` : ""}.`,
      );
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
  // Operaciones que YA están en el calendario (idénticas): se omiten al aplicar, sin alarmar.
  const nYaExisten = operaciones.filter((o) => o.ya_existe).length;
  const nCambios = operaciones.length - nYaExisten;

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
            Revisa los cambios propuestos antes de aplicar.
          </DialogDescription>
        </DialogHeader>

        {enSubida ? (
          <div className="space-y-4">
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
                <Spinner className="h-7 w-7 text-primary" />
                <p className="text-sm font-medium">Analizando el documento…</p>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              El análisis sigue en segundo plano.
            </p>
            {generacion?.prompt && <VerPrompt prompt={generacion.prompt} />}
          </div>
        ) : estado === "error" ? (
          <div className="space-y-3">
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <AlertTriangle className="h-7 w-7 text-destructive" />
              <p className="text-sm font-medium">No se pudo analizar el documento</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {propuesta.error || "El análisis falló. Reintenta con otro documento."}
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
            <ResumenRango propuesta={propuesta} nOperaciones={nCambios} />
            {nYaExisten > 0 && (
              <p className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                {nYaExisten === 1
                  ? "1 coincidencia ya está en el calendario; se omitirá al aplicar (no se duplica)."
                  : `${nYaExisten} coincidencias ya están en el calendario; se omitirán al aplicar (no se duplican).`}
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
            <CalendarioPreview operaciones={operaciones} />
            {operaciones.length === 0 && (
              <p className="text-sm text-muted-foreground">
                La propuesta no contiene cambios aplicables.
              </p>
            )}
            {generacion?.prompt && <VerPrompt prompt={generacion.prompt} />}
            {conflictoAplicar && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
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
                variant="default"
                onClick={() => subir.mutate()}
                disabled={!archivo || subir.isPending}
                data-testid="rota-importar-subir"
              >
                {subir.isPending && <Spinner className="h-4 w-4" />}
                <Upload className="h-4 w-4" />
                Subir y analizar
              </Button>
            </>
          ) : estado === "pendiente" ? (
            <>
              <Button
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => descartar.mutate()}
                disabled={descartar.isPending || aplicar.isPending}
              >
                {descartar.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <X className="h-4 w-4" />
                )}
                Descartar
              </Button>
              <Button
                variant="default"
                onClick={() => aplicar.mutate()}
                disabled={aplicar.isPending || descartar.isPending || operaciones.length === 0}
                data-testid="rota-importar-aceptar"
              >
                {aplicar.isPending ? (
                  <Spinner className="h-4 w-4" />
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
