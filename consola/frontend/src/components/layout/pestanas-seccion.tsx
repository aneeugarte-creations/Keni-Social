import type { LucideIcon } from "lucide-react";
import * as React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** Una pestaña de NAVEGACIÓN DE SECCIÓN conmutada por ESTADO (no por ruta). */
export interface PestanaSeccion {
  /** Valor que identifica la pestaña: lo que la página guarda en su estado/`?param=`. */
  valor: string;
  etiqueta: string;
  icono: LucideIcon;
  /** Insignia opcional a la derecha de la etiqueta (p. ej. un contador de pendientes). */
  insignia?: React.ReactNode;
}

/**
 * Clases de una pestaña de la cabecera de sección. ÚNICA fuente de los estados activo/hover/foco,
 * para que la subnav por RUTA (`EncabezadoSeccion`, NavLink) y la subnav por ESTADO
 * (`PestanasSeccion`, botón) se vean y se comporten idénticas: misma altura, mismo subrayado de la
 * activa que muerde el borde del header, mismo hover.
 */
// Helper co-localizado con el componente cuyo formato define (fuente única de las clases).
// eslint-disable-next-line react-refresh/only-export-components
export function clasesPestanaSeccion(activo: boolean): string {
  return cn(
    "-mb-px flex items-center gap-2 border-b-2 px-3 text-sm transition-colors",
    activo
      ? "border-foreground font-medium text-foreground"
      : "border-transparent font-normal text-muted-foreground hover:border-border hover:text-foreground",
  );
}

/**
 * Tira de pestañas de SECCIÓN conmutada por estado, con el MISMO formato que la subnav por ruta del
 * topbar (`EncabezadoSeccion`):
 *   - ESCRITORIO (`md+`): una fila a altura completa cuya pestaña activa muerde el borde inferior
 *     del header.
 *   - MÓVIL (`<md`): un dropdown compacto (no ocupa una fila entera).
 * No portaliza: de eso se encarga `PestanasSeccion` (en `encabezado`). Presentacional y reutilizable.
 */
export function TiraPestanasSeccion({
  pestanas,
  activo,
  onSelect,
}: {
  pestanas: PestanaSeccion[];
  activo: string;
  onSelect: (valor: string) => void;
}) {
  return (
    <nav aria-label="Secciones" className="flex h-full min-w-0 items-stretch self-stretch">
      {/* ESCRITORIO: fila a altura completa; la activa muerde el borde del header. */}
      <div className="hidden h-full items-stretch md:flex">
        {pestanas.map((p) => {
          const Icono = p.icono;
          return (
            <button
              key={p.valor}
              type="button"
              aria-current={p.valor === activo ? "page" : undefined}
              onClick={() => onSelect(p.valor)}
              className={clasesPestanaSeccion(p.valor === activo)}
            >
              <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{p.etiqueta}</span>
              {p.insignia}
            </button>
          );
        })}
      </div>

      {/* MÓVIL: el mismo conjunto de pestañas, como dropdown compacto. */}
      <div className="flex items-center md:hidden">
        <Select value={activo} onValueChange={onSelect}>
          <SelectTrigger
            aria-label="Sección"
            className="h-8 w-auto gap-2 border-none bg-transparent px-2 font-medium shadow-none focus:ring-0 focus:ring-offset-0"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pestanas.map((p) => {
              const Icono = p.icono;
              return (
                <SelectItem key={p.valor} value={p.valor}>
                  <span className="flex items-center gap-2">
                    <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {p.etiqueta}
                  </span>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>
    </nav>
  );
}
