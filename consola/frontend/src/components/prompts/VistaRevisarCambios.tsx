/**
 * Vista de REVISIÓN de cambios a pantalla completa, estilo Pull Request: el diff de prosa
 * (`DiffProsa`) es el protagonista, centrado a un ancho de lectura cómodo, con scroll propio.
 *
 * Dos modos:
 *   - "lectura": solo el diff (revisar una solicitud, comparar versiones…).
 *   - "publicar": añade un pie con la nota de cambio obligatoria y la acción de envío
 *     ("Publicar cambios" si admin, "Solicitar publicación" si no). La validación de la
 *     nota y el estado de "enviando" viven aquí; la mutación concreta la inyecta el padre
 *     vía `onEnviar` (así esta vista no depende de react-query y es reutilizable).
 *
 * El diff se renderiza por defecto desde `antes`/`despues`; si el padre necesita cargar los
 * cuerpos de forma diferida (p. ej. la bandeja de solicitudes, que los pide por SHA al abrir),
 * puede pasar `renderDiff(soloCambios)` y omitir `antes`/`despues`.
 */
import { ArrowLeft, Rocket, Send } from "lucide-react";
import * as React from "react";

import { Aviso } from "@/components/comunes/Aviso";
import { DiffProsa } from "@/components/prompts/DiffProsa";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

export type ModoRevisar = "lectura" | "publicar";

export interface VistaRevisarCambiosProps {
  abierto: boolean;
  onCerrar: () => void;
  /** Título de la cabecera (p. ej. "Revisar y publicar"). */
  titulo: string;
  /** Subtítulo opcional bajo el título (p. ej. "Cambios desde lo publicado hasta tu borrador"). */
  subtitulo?: string;
  /** Cuerpo (markdown) de la versión vieja. Ignorado si se pasa `renderDiff`. */
  antes?: string;
  /** Cuerpo (markdown) de la versión nueva. Ignorado si se pasa `renderDiff`. */
  despues?: string;
  /** Render alternativo del diff (carga diferida); recibe el estado del toggle "Solo cambios". */
  renderDiff?: (soloCambios: boolean) => React.ReactNode;
  /** "lectura" (solo diff) o "publicar" (con pie de nota + acción). Por defecto "lectura". */
  modo?: ModoRevisar;
  /** En modo "publicar": admin → "Publicar cambios"; si no → "Solicitar publicación". */
  esAdmin?: boolean;
  /** En modo "publicar": acción en curso (deshabilita la acción y muestra "…"). */
  enviando?: boolean;
  /** En modo "publicar": envío con la nota de cambio (ya validada y recortada). */
  onEnviar?: (nota: string) => void;
}

/**
 * Overlay a pantalla completa donde el diff manda. Reutiliza el `Dialog` de shadcn (foco
 * atrapado + Escape) con un `DialogContent` que ocupa todo el viewport.
 */
export function VistaRevisarCambios({
  abierto,
  onCerrar,
  titulo,
  subtitulo,
  antes = "",
  despues = "",
  renderDiff,
  modo = "lectura",
  esAdmin = false,
  enviando = false,
  onEnviar,
}: VistaRevisarCambiosProps) {
  const [soloCambios, setSoloCambios] = React.useState(true);
  const [nota, setNota] = React.useState("");

  // Al abrir, arranca limpio: toggle en "solo cambios" y la nota vacía.
  React.useEffect(() => {
    if (abierto) {
      setSoloCambios(true);
      setNota("");
    }
  }, [abierto]);

  const esPublicar = modo === "publicar";
  const notaValida = nota.trim().length > 0;
  const Icono = esAdmin ? Rocket : Send;
  const etiquetaAccion = esAdmin ? "Publicar cambios" : "Solicitar publicación";

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent
        className="flex h-screen w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-0 p-0 left-0 top-0 max-h-screen sm:rounded-none"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {/* ───────── Cabecera ───────── */}
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-background px-4 py-3 pr-14 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={onCerrar}
            aria-label="Cerrar"
            className="shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate text-base font-semibold leading-tight">
              {titulo}
            </DialogTitle>
            {subtitulo ? (
              <p className="mt-0.5 truncate text-xs text-muted-foreground">{subtitulo}</p>
            ) : null}
          </div>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            Solo cambios
            <Switch
              checked={soloCambios}
              onCheckedChange={setSoloCambios}
              aria-label="Solo cambios"
            />
          </label>
        </header>

        {/* ───────── Cuerpo: el diff, centrado a ancho de lectura ───────── */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-muted/20">
          <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
            <div className="rounded-lg border border-border bg-background p-5 shadow-sm sm:p-6">
              {renderDiff ? (
                renderDiff(soloCambios)
              ) : (
                <DiffProsa antes={antes} despues={despues} soloCambios={soloCambios} />
              )}
            </div>
          </div>
        </div>

        {/* ───────── Pie (solo modo publicar): nota obligatoria + acción ───────── */}
        {esPublicar ? (
          <footer className="shrink-0 border-t border-border bg-background px-4 py-4 sm:px-6">
            <div className="mx-auto w-full max-w-3xl space-y-3">
              <Aviso icono={false}>
                {esAdmin
                  ? "Al publicar, esta versión servirá todas las generaciones."
                  : "Si un admin la aprueba, servirá todas las generaciones. Hasta entonces, sin cambios."}
              </Aviso>
              <div className="space-y-1.5">
                <Label htmlFor="nota-revisar">
                  Nota del cambio <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="nota-revisar"
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  rows={2}
                  placeholder="Qué cambia y por qué"
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button variant="ghost" onClick={onCerrar} disabled={enviando}>
                  Cancelar
                </Button>
                <Button
                  variant="brand"
                  disabled={!notaValida || enviando}
                  onClick={() => onEnviar?.(nota.trim())}
                >
                  <Icono className="mr-1 h-3.5 w-3.5" />
                  {enviando
                    ? esAdmin
                      ? "Publicando…"
                      : "Enviando…"
                    : etiquetaAccion}
                </Button>
              </div>
            </div>
          </footer>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
