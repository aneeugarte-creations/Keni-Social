/**
 * Visor a pantalla completa de la Galería (réplica del lightbox de keni-fotos): la foto grande con
 * navegación (flechas / teclado) + una ficha lateral con título, etiquetas y las acciones de control.
 *
 * Trabaja sobre fotos NORMALIZADAS (`FotoVista`), así que sirve igual para una foto GUARDADA de la
 * biblioteca y para un candidato EN VIVO del túnel. Las acciones se deciden por el `origen`:
 *  - túnel (en vivo): «Guardar en Fotografías» (baja el original por el túnel y lo cataloga).
 *  - biblioteca (guardada): «Descargar» (attachment) y «Borrar» (la quita de la biblioteca).
 *  - cualquiera con coordenadas de túnel: «Ráfaga» (navegar el burst del keeper).
 * El visor solo orquesta: las mutaciones viven en la página, que pasa los callbacks y los estados.
 */
import { ChevronLeft, ChevronRight, Download, Images, Save, Trash2, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { FotoVista } from "@/types";

const ETIQUETA_FUENTE: Record<string, string> = {
  portal: "Portal",
  subidas: "Subidas",
  fotografias: "Fotografías",
};

export interface VisorFotoProps {
  /** Fotos navegables (la rejilla actual); `indice` apunta a la que se muestra. `null` = cerrado. */
  fotos: FotoVista[];
  indice: number | null;
  onIndice: (indice: number) => void;
  onCerrar: () => void;
  /** Guardar en Fotografías (solo túnel). */
  onGuardar?: (foto: FotoVista) => void;
  /** Descargar el binario (solo biblioteca). */
  onDescargar?: (foto: FotoVista) => void;
  /** Quitar de la biblioteca (solo biblioteca). */
  onBorrar?: (foto: FotoVista) => void;
  /** Navegar la ráfaga del burst (cuando hay coordenadas de túnel). */
  onRafaga?: (foto: FotoVista) => void;
  /** Clave de la foto que se está guardando ahora (para el spinner). */
  guardandoClave?: string | null;
  /** Clave de la foto que se está borrando ahora. */
  borrandoClave?: string | null;
}

/** Fila de la ficha: rótulo + contenido (se oculta si no hay contenido). */
function Campo({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  if (children === null || children === undefined || children === "") return null;
  return (
    <div className="space-y-0.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {titulo}
      </div>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  );
}

export function VisorFoto({
  fotos,
  indice,
  onIndice,
  onCerrar,
  onGuardar,
  onDescargar,
  onBorrar,
  onRafaga,
  guardandoClave,
  borrandoClave,
}: VisorFotoProps) {
  const abierto = indice !== null && indice >= 0 && indice < fotos.length;

  const ir = React.useCallback(
    (delta: number) => {
      if (indice === null || fotos.length === 0) return;
      onIndice((indice + delta + fotos.length) % fotos.length);
    },
    [indice, fotos.length, onIndice],
  );

  React.useEffect(() => {
    if (!abierto) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCerrar();
      else if (e.key === "ArrowLeft") ir(-1);
      else if (e.key === "ArrowRight") ir(1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [abierto, ir, onCerrar]);

  if (!abierto || indice === null) return null;
  const foto = fotos[indice];
  const esTunel = foto.origen === "tunel";
  const guardando = guardandoClave === foto.clave;
  const borrando = borrandoClave === foto.clave;
  const fuenteLabel = foto.fuente ? ETIQUETA_FUENTE[foto.fuente] : "";
  const tieneRafaga = !!foto.galeria_id && !!foto.archivo;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onCerrar}
      role="dialog"
      aria-modal="true"
      aria-label={foto.titulo || "Foto"}
    >
      <div
        className="flex max-h-[calc(100dvh-2rem)] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-lg md:flex-row"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Imagen + navegación */}
        <div className="relative flex min-h-[40vh] flex-1 items-center justify-center bg-black md:min-h-0">
          <img
            src={foto.url || foto.thumb}
            alt={foto.titulo || foto.archivo || "Foto"}
            className="max-h-[calc(100dvh-2rem)] w-full object-contain md:w-auto md:max-w-full"
          />

          {fotos.length > 1 && (
            <>
              <Button
                variant="secondary"
                size="icon"
                onClick={() => ir(-1)}
                className="absolute left-3 top-1/2 -translate-y-1/2 opacity-90"
                aria-label="Anterior"
              >
                <ChevronLeft className="h-5 w-5" />
              </Button>
              <Button
                variant="secondary"
                size="icon"
                onClick={() => ir(1)}
                className="absolute right-3 top-1/2 -translate-y-1/2 opacity-90"
                aria-label="Siguiente"
              >
                <ChevronRight className="h-5 w-5" />
              </Button>
              <div className="absolute left-3 top-3 rounded-md bg-black/70 px-2 py-1 font-mono text-xs font-medium text-white">
                {indice + 1} / {fotos.length}
              </div>
            </>
          )}
          {foto.archivo && (
            <div className="absolute bottom-3 left-3 max-w-[80%] truncate rounded-md bg-black/70 px-2 py-1 font-mono text-xs text-white">
              {foto.archivo}
            </div>
          )}
        </div>

        {/* Ficha lateral */}
        <aside className="flex w-full shrink-0 flex-col gap-4 overflow-y-auto border-t border-border p-5 md:w-80 md:border-l md:border-t-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[15px] font-medium tracking-tight">
                {foto.titulo || "Sin título"}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {esTunel ? (
                  <Badge variant="aviso">En vivo</Badge>
                ) : (
                  fuenteLabel && <Badge variant="secondary">{fuenteLabel}</Badge>
                )}
                {foto.grupo && <Badge variant="outline">{foto.grupo}</Badge>}
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onCerrar} aria-label="Cerrar">
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Acciones de control (según origen) */}
          <div className="flex flex-wrap gap-2">
            {esTunel && onGuardar && (
              <Button
                variant="outline"
                size="sm"
                className="flex-1 gap-1"
                disabled={guardando}
                onClick={() => onGuardar(foto)}
              >
                {guardando ? <Spinner className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                Guardar
              </Button>
            )}
            {!esTunel && onDescargar && (
              <Button
                variant="outline"
                size="sm"
                className="flex-1 gap-1"
                onClick={() => onDescargar(foto)}
              >
                <Download className="h-4 w-4" />
                Descargar
              </Button>
            )}
            {tieneRafaga && onRafaga && (
              <Button
                variant="outline"
                size="sm"
                className="flex-1 gap-1"
                onClick={() => onRafaga(foto)}
              >
                <Images className="h-4 w-4" />
                Ráfaga
              </Button>
            )}
            {!esTunel && onBorrar && (
              <Button
                variant="outline"
                size="sm"
                className="flex-1 gap-1 text-destructive hover:text-destructive"
                disabled={borrando}
                onClick={() => onBorrar(foto)}
              >
                {borrando ? <Spinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                Borrar
              </Button>
            )}
          </div>

          {foto.etiquetas.length > 0 && (
            <Campo titulo="Etiquetas">
              <div className="flex flex-wrap gap-1">
                {foto.etiquetas.map((t, i) => (
                  <span
                    key={`${t}-${i}`}
                    className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </Campo>
          )}
        </aside>
      </div>
    </div>
  );
}
