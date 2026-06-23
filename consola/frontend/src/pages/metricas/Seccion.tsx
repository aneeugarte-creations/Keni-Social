/**
 * Encuadre UNIFORME de una sección del dashboard de Métricas.
 *
 * Toda sección (tabla, gráfica, tarjetas) se pinta igual: una cabecera SIEMPRE FUERA del
 * contenido — título a la izquierda; a la derecha sus controles propios, el editor de
 * campos (kebab, si la sección tiene columnas configurables) y el toggle de ocultar —, y
 * debajo el contenido. Sin colapsables: mostrar/ocultar lo hace el toggle (el gate de
 * montado lo aplica `<Bloque>` en el padre; oculta ⇒ ni se monta ni consulta).
 *
 * No envuelve el contenido en una `Card`: el título queda fuera de la tabla/gráfica. Cada
 * sección decide si su contenido va en una tarjeta propia.
 */
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { BotonOcultar } from "./Bloque";
import type { ColumnaMeta } from "./columnasMeta";
import { MenuColumnas } from "./MenuColumnas";

export function Seccion({
  id,
  titulo,
  descripcion,
  icono: Icono,
  acciones,
  tablaId,
  columnas,
  etiquetaCampos,
  contentClassName,
  children,
}: {
  /** Id de sección: clave de visibilidad (`vistaConfig.secciones`) y del toggle ocultar. */
  id: string;
  titulo: React.ReactNode;
  descripcion?: React.ReactNode;
  /** Icono opcional junto al título (lucide). */
  icono?: LucideIcon;
  /** Controles propios de la sección (selectores, filtros, modos…), a la izquierda del kebab. */
  acciones?: React.ReactNode;
  /** Si la sección tiene campos configurables: id de tabla (`vistaConfig.columnas`). */
  tablaId?: string;
  /** Catálogo de campos de la sección (junto con `tablaId` activa el editor "⋮"). */
  columnas?: ColumnaMeta[];
  /** Texto del editor de campos (por defecto "Campos"; p. ej. "Tarjetas" en KPIs). */
  etiquetaCampos?: string;
  /** Clase del envoltorio del contenido. */
  contentClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {Icono ? (
            <Icono className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          ) : null}
          <h2 className="truncate text-lg font-semibold tracking-tight">{titulo}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {acciones}
          {tablaId && columnas ? (
            <MenuColumnas tablaId={tablaId} columnas={columnas} etiqueta={etiquetaCampos} />
          ) : null}
          <BotonOcultar id={id} />
        </div>
      </div>
      {descripcion ? <p className="text-sm text-muted-foreground">{descripcion}</p> : null}
      <div className={contentClassName}>{children}</div>
    </section>
  );
}
