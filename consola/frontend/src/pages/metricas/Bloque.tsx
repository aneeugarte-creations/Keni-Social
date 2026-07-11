/**
 * GATE de visibilidad de una sección del dashboard de Métricas.
 *
 * `<Bloque id>` decide si su sección se monta: visible ⇒ pinta el contenido (la sección
 * trae su propia cabecera con título + toggle vía `<Seccion>`); oculta ⇒ pinta solo una
 * barra fina con el título y un botón "Mostrar", y NO monta el contenido (su consulta no se
 * dispara: aligera la carga). El estado vive en `vistaConfig.secciones` (persistido) y lo
 * serializan las vistas guardadas. El toggle de ocultar (`BotonOcultar`) vive en la cabecera
 * de la sección; el de mostrar, en la barra fina.
 */
import { Eye, EyeOff, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";

import { etiquetaSeccion } from "./seccionesMeta";
import { useVistaConfig } from "./vistaConfig";

/** Botón "ocultar" (ojo tachado) para la cabecera de una sección visible. */
export function BotonOcultar({ id }: { id: string }) {
  const setSeccionVisible = useVistaConfig((s) => s.setSeccionVisible);
  return (
    <Tooltip label="Ocultar">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-muted-foreground hover:text-foreground"
        aria-label="Ocultar sección"
        onClick={() => setSeccionVisible(id, false)}
      >
        <EyeOff className="h-4 w-4" />
      </Button>
    </Tooltip>
  );
}

/** Barra fina que ocupa el sitio de una sección oculta: título + botón "Mostrar". */
export function BarraOculta({
  id,
  titulo,
  icono: Icono,
}: {
  id: string;
  titulo?: string;
  icono?: LucideIcon;
}) {
  const setSeccionVisible = useVistaConfig((s) => s.setSeccionVisible);
  const etiqueta = titulo ?? etiquetaSeccion(id);
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border/70 bg-muted/30 px-4 py-2">
      <span className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
        {Icono ? <Icono className="h-4 w-4 shrink-0" aria-hidden="true" /> : null}
        <span className="truncate">{etiqueta}</span>
        <span className="shrink-0 text-xs text-muted-foreground/70">· oculta</span>
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="shrink-0 gap-1.5 text-muted-foreground hover:text-foreground"
        onClick={() => setSeccionVisible(id, true)}
        aria-label={`Mostrar ${etiqueta}`}
      >
        <Eye className="h-4 w-4" />
        Mostrar
      </Button>
    </div>
  );
}

/**
 * Gate de una sección: oculta → barra fina (sin montar el contenido, sin fetch); visible →
 * el contenido tal cual (su `<Seccion>` ya trae la cabecera con título + toggle).
 */
export function Bloque({
  id,
  titulo,
  icono,
  children,
}: {
  id: string;
  /** Título de la barra fina cuando está oculta (por defecto, la etiqueta de la sección). */
  titulo?: string;
  icono?: LucideIcon;
  children: React.ReactNode;
}) {
  const visible = useVistaConfig((s) => s.secciones[id] !== false);
  if (!visible) return <BarraOculta id={id} titulo={titulo} icono={icono} />;
  return <>{children}</>;
}
