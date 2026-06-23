/**
 * Encuadre de una SECCIÓN del dashboard de Métricas con control de visibilidad INLINE.
 *
 * Cada sección se muestra/oculta con su propio toggle (ojo), sin un panel macro aparte:
 *   - Visible: cabecera (título + acciones + toggle) y el contenido.
 *   - Oculta: SOLO una barra fina con el título y un botón "Mostrar". El contenido NO se
 *     monta, así que su consulta NO se dispara: ocultar una sección aligera la carga de la
 *     página (mostrarla la vuelve a encolar). El estado vive en `vistaConfig.secciones`
 *     (persistido) y lo serializan las vistas guardadas.
 *
 * `Bloque` cubre el contenido SIN cabecera propia (KPIs, gráficas, y los pares por marca/red):
 * añade la cabecera con título + toggle. Las secciones basadas en `SeccionColapsable` ya traen
 * su cabecera; ahí el toggle/kebab viven dentro de ella y el gate de montado lo hace el padre
 * (`vis(id) ? <Comp/> : <BarraOculta/>`).
 */
import { Eye, EyeOff, type LucideIcon } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";

import { etiquetaSeccion } from "./seccionesMeta";
import { useVistaConfig } from "./vistaConfig";

/** Botón "ocultar" (ojo tachado) para la cabecera de una sección visible. */
export function BotonOcultar({ id }: { id: string }) {
  const setSeccionVisible = useVistaConfig((s) => s.setSeccionVisible);
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-7 w-7 text-muted-foreground hover:text-foreground"
      aria-label="Ocultar sección"
      title="Ocultar"
      onClick={() => setSeccionVisible(id, false)}
    >
      <EyeOff className="h-4 w-4" />
    </Button>
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
        className="h-7 shrink-0 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setSeccionVisible(id, true)}
        aria-label={`Mostrar ${etiqueta}`}
      >
        <Eye className="h-4 w-4" />
        Mostrar
      </Button>
    </div>
  );
}

/** Cabecera de un `Bloque` con cabecera propia: título + (kebab de columnas) + toggle ocultar. */
function CabeceraBloque({
  id,
  titulo,
  icono: Icono,
  acciones,
}: {
  id: string;
  titulo: string;
  icono?: LucideIcon;
  acciones?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="flex min-w-0 items-center gap-2 text-lg font-semibold tracking-tight">
        {Icono ? <Icono className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
        <span className="truncate">{titulo}</span>
      </h2>
      <div className="flex items-center gap-1">
        {acciones}
        <BotonOcultar id={id} />
      </div>
    </div>
  );
}

/**
 * Encuadre de una sección. Si `secciones[id]` está oculta → barra fina (sin montar el
 * contenido, sin fetch). Si visible → el contenido, envuelto en `data-slide` para el PDF.
 * Con `conCabecera`, añade la cabecera con título + toggle (para contenido sin cabecera propia).
 */
export function Bloque({
  id,
  titulo,
  icono,
  dataSlide,
  acciones,
  conCabecera = false,
  children,
}: {
  id: string;
  /** Título visible (por defecto, la etiqueta de la sección). */
  titulo?: string;
  icono?: LucideIcon;
  /** Valor de `data-slide` (título de la diapositiva del PDF). Sin él, no entra al deck. */
  dataSlide?: string;
  /** Controles a la derecha de la cabecera (p. ej. el kebab de columnas). Requiere `conCabecera`. */
  acciones?: React.ReactNode;
  /** Añade una cabecera (título + acciones + toggle) sobre el contenido. */
  conCabecera?: boolean;
  children: React.ReactNode;
}) {
  const visible = useVistaConfig((s) => s.secciones[id] !== false);
  const etiqueta = titulo ?? etiquetaSeccion(id);

  if (!visible) return <BarraOculta id={id} titulo={etiqueta} icono={icono} />;

  const cuerpo = conCabecera ? (
    <section className="flex flex-col gap-4">
      <CabeceraBloque id={id} titulo={etiqueta} icono={icono} acciones={acciones} />
      {children}
    </section>
  ) : (
    children
  );

  return dataSlide ? <div data-slide={dataSlide}>{cuerpo}</div> : <>{cuerpo}</>;
}
