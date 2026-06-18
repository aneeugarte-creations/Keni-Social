import { fortalezaPassword, type NivelFortaleza } from "@/lib/password";
import { cn } from "@/lib/utils";

/** Color del segmento lleno por nivel de fortaleza. */
const COLOR_BARRA: Record<NivelFortaleza, string> = {
  0: "bg-destructive",
  1: "bg-amber-500",
  2: "bg-lime-500",
  3: "bg-emerald-500",
};

/** Color del texto de la etiqueta por nivel. */
const COLOR_TEXTO: Record<NivelFortaleza, string> = {
  0: "text-destructive",
  1: "text-amber-600 dark:text-amber-500",
  2: "text-lime-600 dark:text-lime-500",
  3: "text-emerald-600 dark:text-emerald-500",
};

const ETIQUETA: Record<NivelFortaleza, string> = {
  0: "Débil",
  1: "Aceptable",
  2: "Fuerte",
  3: "Muy fuerte",
};

/**
 * Barra de fortaleza de contraseña: cuatro segmentos que se llenan según la longitud y la
 * variedad de caracteres, con una etiqueta (Débil / Aceptable / Fuerte / Muy fuerte). Es una
 * GUÍA visual: no bloquea el envío (el mínimo de longitud lo controla el formulario y la
 * blocklist el backend). No pinta nada con la contraseña vacía.
 */
export function MedidorPassword({
  password,
  className,
}: {
  password: string;
  className?: string;
}) {
  if (!password) return null;
  const nivel = fortalezaPassword(password);
  return (
    <div className={cn("space-y-1", className)} aria-live="polite">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              i <= nivel ? COLOR_BARRA[nivel] : "bg-muted",
            )}
          />
        ))}
      </div>
      <p className={cn("text-xs", COLOR_TEXTO[nivel])}>Seguridad: {ETIQUETA[nivel]}</p>
    </div>
  );
}
