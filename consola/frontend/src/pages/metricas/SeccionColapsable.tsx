/**
 * Sección colapsable compartida del dashboard de Métricas.
 *
 * Envuelve cualquier tabla/gráfica en una `Card` con cabecera clicable (chevron) que
 * pliega/despliega el contenido. Unifica TODAS las secciones de Analíticas: mismo
 * patrón de título, controles (filtros) a la derecha y colapso. Sin dependencias nuevas
 * (estado local); por defecto abierta.
 *
 * Uso:
 *   <SeccionColapsable titulo="Detalle por red" acciones={<SelectRed .../>} contentClassName="p-0">
 *     <Table>…</Table>
 *   </SeccionColapsable>
 *
 * `acciones` (filtros/controles) NO togglea el colapso (clic aislado del trigger).
 */
import { ChevronDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { BotonOcultar } from "./Bloque";
import { MenuColumnas } from "./MenuColumnas";

export function SeccionColapsable({
  titulo,
  descripcion,
  icono: Icono,
  acciones,
  id,
  tablaColumnas,
  defaultAbierto = true,
  contentClassName,
  sinCaja = false,
  children,
}: {
  titulo: React.ReactNode;
  descripcion?: React.ReactNode;
  /** Icono opcional junto al título (lucide). */
  icono?: LucideIcon;
  /** Controles a la derecha de la cabecera (filtros, toggles, descargas…). */
  acciones?: React.ReactNode;
  /** Id de sección: si se pasa, la cabecera muestra el toggle "ocultar" (`vistaConfig`). */
  id?: string;
  /** Id de tabla configurable: si se pasa, la cabecera muestra el kebab de columnas. */
  tablaColumnas?: string;
  defaultAbierto?: boolean;
  /** Clase para el `CardContent` (p. ej. "p-0" para tablas a sangre). */
  contentClassName?: string;
  /**
   * Sin la `Card` envolvente (sin recuadro blanco ni borde): solo el título
   * colapsable + el contenido. Útil cuando el contenido ya son tarjetas propias
   * y no se quiere anidar tarjeta-dentro-de-tarjeta; el título sigue agrupándolas.
   */
  sinCaja?: boolean;
  children: React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(defaultAbierto);

  // Disparador (chevron + icono + título) compartido por ambas variantes.
  const cabecera = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="group flex min-w-0 items-center gap-2 text-left rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:text-foreground",
            !abierto && "-rotate-90",
          )}
          aria-hidden="true"
        />
        {Icono ? (
          <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : null}
        <h3 className="truncate text-base font-semibold leading-none tracking-tight group-hover:underline">{titulo}</h3>
      </button>
      <div className="flex flex-wrap items-center gap-2">
        {acciones}
        {tablaColumnas ? <MenuColumnas tablaId={tablaColumnas} /> : null}
        {id ? <BotonOcultar id={id} /> : null}
      </div>
    </div>
  );

  // Variante sin caja: mismo título colapsable, pero sin la Card envolvente.
  if (sinCaja) {
    return (
      <section className="space-y-4">
        {cabecera}
        {descripcion && abierto ? (
          <p className="text-sm text-muted-foreground">{descripcion}</p>
        ) : null}
        {abierto ? <div className={contentClassName}>{children}</div> : null}
      </section>
    );
  }

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        {cabecera}
        {descripcion && abierto ? (
          <p className="text-sm text-muted-foreground">{descripcion}</p>
        ) : null}
      </CardHeader>
      {abierto ? (
        <CardContent className={cn("pt-0", contentClassName)}>{children}</CardContent>
      ) : null}
    </Card>
  );
}
