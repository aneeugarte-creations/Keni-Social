/**
 * Visor a pantalla completa de la Galería (réplica del lightbox de keni-fotos): la foto grande con
 * navegación (flechas / teclado) + una ficha lateral con título, etiquetas y las acciones de control.
 *
 * Trabaja sobre fotos NORMALIZADAS (`FotoVista`), así que sirve igual para una foto GUARDADA de la
 * biblioteca y para un candidato EN VIVO del túnel. Dos modos de navegación con las MISMAS flechas:
 *  - GALERÍA (por defecto): recorre las fotos de la rejilla.
 *  - RÁFAGA: cuando la foto tiene coordenadas de túnel, «Ráfaga» entra en el burst del keeper y las
 *    flechas recorren los frames del mismo disparo, sin abrir otra ventana (como keni-fotos).
 * Las acciones se deciden por el `origen`: túnel → Guardar; biblioteca → Descargar + Borrar.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, Images, Save, Trash2, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { api } from "@/lib/api";
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
  /** Marca activa (para pedir la ráfaga del túnel). */
  marca?: string;
  /** Guardar en Fotografías (solo túnel). */
  onGuardar?: (foto: FotoVista) => void;
  /** Descargar el binario (solo biblioteca). */
  onDescargar?: (foto: FotoVista) => void;
  /** Quitar de la biblioteca (solo biblioteca). */
  onBorrar?: (foto: FotoVista) => void;
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
  marca,
  onGuardar,
  onDescargar,
  onBorrar,
  guardandoClave,
  borrandoClave,
}: VisorFotoProps) {
  const abierto = indice !== null && indice >= 0 && indice < fotos.length;
  const foto: FotoVista | null = abierto ? fotos[indice] : null;
  const tieneRafaga = !!foto?.galeria_id && !!foto?.archivo;

  // Modo RÁFAGA: navegar el burst del keeper DENTRO del visor (sin segundo modal).
  const [modoRafaga, setModoRafaga] = React.useState(false);
  const [indiceRafaga, setIndiceRafaga] = React.useState(0);
  // Cambiar de foto (o cerrar) sale del modo ráfaga.
  React.useEffect(() => {
    setModoRafaga(false);
  }, [foto?.clave]);

  const rafaga = useQuery({
    queryKey: ["rafaga", foto?.galeria_id ?? "", foto?.archivo ?? "", marca ?? ""],
    queryFn: ({ signal }) =>
      api.rafagaPropio(
        {
          galeria_id: foto!.galeria_id!,
          archivo: foto!.archivo!,
          marca,
          dispositivo: foto!.dispositivo,
        },
        signal,
      ),
    enabled: abierto && modoRafaga && tieneRafaga,
  });
  const frames = rafaga.data?.fotos ?? [];
  // Al cargar el burst, arranca en el keeper (la foto desde la que se entró).
  React.useEffect(() => {
    if (frames.length === 0) return;
    const k = frames.findIndex((f) => f.archivo === foto?.archivo);
    setIndiceRafaga(k >= 0 ? k : 0);
  }, [rafaga.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const enRafaga = modoRafaga && frames.length > 0;

  const ir = React.useCallback(
    (delta: number) => {
      if (enRafaga) {
        setIndiceRafaga((i) => (i + delta + frames.length) % frames.length);
      } else if (indice !== null && fotos.length > 0) {
        onIndice((indice + delta + fotos.length) % fotos.length);
      }
    },
    [enRafaga, frames.length, indice, fotos.length, onIndice],
  );

  React.useEffect(() => {
    if (!abierto) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (modoRafaga) setModoRafaga(false);
        else onCerrar();
      } else if (e.key === "ArrowLeft") ir(-1);
      else if (e.key === "ArrowRight") ir(1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [abierto, modoRafaga, ir, onCerrar]);

  if (!abierto || foto === null) return null;
  const esTunel = foto.origen === "tunel";
  const guardando = guardandoClave === foto.clave;
  const borrando = borrandoClave === foto.clave;
  const fuenteLabel = foto.fuente ? ETIQUETA_FUENTE[foto.fuente] : "";

  const frameActual = enRafaga ? frames[indiceRafaga] : null;
  const src = frameActual ? frameActual.thumb : foto.url || foto.thumb;
  const nombreArchivo = frameActual ? frameActual.archivo : foto.archivo;
  const navegables = enRafaga ? frames.length > 1 : fotos.length > 1;

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
            src={src}
            alt={foto.titulo || nombreArchivo || "Foto"}
            className="max-h-[calc(100dvh-2rem)] w-full object-contain md:w-auto md:max-w-full"
          />

          {navegables && (
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
            </>
          )}

          <div className="absolute left-3 top-3 flex items-center gap-2">
            {enRafaga ? (
              <>
                <span className="rounded-md bg-black/70 px-2 py-1 font-mono text-xs font-medium text-white">
                  {indiceRafaga + 1} / {frames.length}
                </span>
                {frameActual?.archivo === foto.archivo && <Badge variant="aviso">keeper</Badge>}
              </>
            ) : (
              fotos.length > 1 && (
                <span className="rounded-md bg-black/70 px-2 py-1 font-mono text-xs font-medium text-white">
                  {indice + 1} / {fotos.length}
                </span>
              )
            )}
          </div>

          {modoRafaga && rafaga.isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/40">
              <Spinner className="h-6 w-6 text-white" />
            </div>
          )}

          {nombreArchivo && (
            <div className="absolute bottom-3 left-3 max-w-[80%] truncate rounded-md bg-black/70 px-2 py-1 font-mono text-xs text-white">
              {nombreArchivo}
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
            {tieneRafaga && (
              <Button
                variant={modoRafaga ? "secondary" : "outline"}
                size="sm"
                className="flex-1 gap-1"
                aria-pressed={modoRafaga}
                onClick={() => setModoRafaga((v) => !v)}
              >
                <Images className="h-4 w-4" />
                {modoRafaga ? "Salir de ráfaga" : "Ráfaga"}
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

          {/* En modo ráfaga sin más frames: el disparo fue único. */}
          {modoRafaga && !rafaga.isLoading && frames.length <= 1 && (
            <p className="text-xs text-muted-foreground">
              Disparo único: no hay más fotos en esta ráfaga.
            </p>
          )}

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
