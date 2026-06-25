import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/**
 * Panel unificado "Estamos actualizando la consola": el mismo lenguaje calmado para CUALQUIER
 * indisponibilidad temporal —el front recreándose (página de mantenimiento) o el back desplegando
 * (puerta de sesión + velo en la app)—. Nunca un error rojo alarmante: una actualización es algo
 * esperado y reversible, no un fallo.
 *
 * Lenguaje minimalista (sin caja ni sombra, como los estados vacíos de la app): un eyebrow KENI
 * apagado, el título en la tipografía de la app, el progreso reducido a un HILO de 1px que cruza
 * el panel (curva que frena cerca del 94%, nunca llega sola al 100%) y, opcional, un "Reintentar"
 * discreto. El 100% solo lo pone una señal REAL de disponibilidad (`sondearListo`); si no se
 * provee, la barra avanza y el padre desmonta el panel cuando el servicio vuelve (reaparece sola).
 */

// Tiempo medio aproximado de vuelta del servicio tras un deploy. La curva escala con esto.
const DURACION_ESTIMADA_MS = 22000;
const INTERVALO_SONDEO_MS = 2000;

/**
 * `deploy`: actualización transitoria, vuelve sola -> barra de progreso (lenguaje calmado).
 * `incidente`: avería real, NO vuelve sin intervención -> SIN barra (una barra prometería un
 * retorno automático que no va a pasar) + aviso honesto de que el equipo ya lo sabe.
 */
export type VariantePanel = "deploy" | "incidente";

export function PanelActualizando({
  // Por defecto `deploy`: preserva el comportamiento previo (todo uso existente es un deploy).
  variante = "deploy",
  // Si no se pasa, el título lo decide la variante (actualizando vs no disponible).
  titulo,
  // Sondeo de disponibilidad real (p. ej. la página de mantenimiento sondea `/version.json`): si
  // resuelve `true`, la barra salta al 100% y se llama a `onListo` (recargar / refrescar).
  sondearListo,
  onListo,
  // Botón de reintento manual (la puerta de sesión lo ofrece; su test lo pulsa).
  onReintentar,
  reintentando = false,
  className,
}: {
  variante?: VariantePanel;
  titulo?: string;
  sondearListo?: () => Promise<boolean>;
  onListo?: () => void;
  onReintentar?: () => void;
  reintentando?: boolean;
  className?: string;
}) {
  const esIncidente = variante === "incidente";
  const tituloEfectivo =
    titulo ?? (esIncidente ? "La consola no está disponible" : "Estamos actualizando la consola");
  const [pct, setPct] = useState(0);
  const [completo, setCompleto] = useState(false);

  // Arranca la animación al siguiente frame: la transición CSS larga lleva la barra de 0 -> 94%.
  useEffect(() => {
    const id = requestAnimationFrame(() => setPct(94));
    return () => cancelAnimationFrame(id);
  }, []);

  // Sondeo de disponibilidad real (opcional): al estar listo -> 100% y `onListo`.
  useEffect(() => {
    if (!sondearListo) return;
    let vivo = true;
    let pendiente: number | undefined;
    const sondear = async () => {
      let listo = false;
      try {
        listo = await sondearListo();
      } catch {
        // Sin respuesta todavía: se reintenta abajo.
      }
      if (!vivo) return;
      if (listo) {
        setCompleto(true);
        setPct(100);
        window.setTimeout(() => onListo?.(), 500);
        return;
      }
      pendiente = window.setTimeout(sondear, INTERVALO_SONDEO_MS);
    };
    pendiente = window.setTimeout(sondear, INTERVALO_SONDEO_MS);
    return () => {
      vivo = false;
      window.clearTimeout(pendiente);
    };
  }, [sondearListo, onListo]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex w-full max-w-sm flex-col items-center gap-6 text-center",
        className,
      )}
    >
      <div className="flex flex-col items-center gap-2.5">
        <span className="text-[0.7rem] font-light uppercase tracking-[0.35em] text-muted-foreground">
          KENI
        </span>
        <h1 className="text-sm font-medium text-foreground">{tituloEfectivo}</h1>
      </div>

      {esIncidente ? (
        // Avería: ni hilo ni promesa de retorno automático. Decimos la verdad y que ya se sabe.
        <p className="text-xs text-muted-foreground">
          El equipo ya ha sido avisado y está trabajando en ello.
        </p>
      ) : (
        <div
          className="h-px w-full overflow-hidden bg-border"
          role="progressbar"
          aria-label="Progreso de la actualización"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
        >
          <div
            className="h-full bg-foreground"
            style={{
              width: `${pct}%`,
              // Avance lento por curva; el salto al 100% (señal real) es rápido.
              transition: `width ${completo ? 500 : DURACION_ESTIMADA_MS}ms ${completo ? "ease-out" : "cubic-bezier(0,0.6,0.2,1)"}`,
            }}
          />
        </div>
      )}

      {onReintentar && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto px-2 py-1 font-normal text-muted-foreground hover:text-foreground"
          onClick={onReintentar}
          disabled={reintentando}
        >
          {reintentando ? <Spinner aria-hidden /> : null}
          Reintentar
        </Button>
      )}
    </div>
  );
}
