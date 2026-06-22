/**
 * Tratamiento visual de una imagen de STOCK SIN LICENCIA (ayuda visual no publicable).
 *
 * Envuelve la imagen y, cuando la pieza está en STOCK_NO_AUTORIZADO, la pinta ATENUADA
 * (opacidad + desaturación) con una banda diagonal repetida "SIN LICENCIA" encima, para que se lea
 * de un vistazo que esa foto NO puede salir a redes hasta autorizarla. Si la imagen de stock ya
 * está autorizada, no atenúa nada: solo deja pasar a sus hijos (un badge sutil lo señala aparte).
 *
 * Se usa en la preview del editor y en las miniaturas del feed/lista. El propio overlay es
 * `pointer-events-none`: no roba clics a la imagen ni a sus controles.
 */
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface OverlaySinLicenciaProps {
  /** `true` cuando la imagen es stock NO autorizado (atenúa + watermark). */
  activo: boolean;
  /** Imagen (o cualquier contenido) a tratar. */
  children: React.ReactNode;
  /** Tamaño del rótulo: "sm" para miniaturas, "md" para la preview del editor. */
  tamano?: "sm" | "md";
  className?: string;
}

export function OverlaySinLicencia({
  activo,
  children,
  tamano = "md",
  className,
}: OverlaySinLicenciaProps) {
  if (!activo) {
    return <div className={cn("relative", className)}>{children}</div>;
  }
  // Banda diagonal repetida con el rótulo: deja claro que es una referencia, no un arte final.
  const banda = tamano === "sm" ? "SIN LICENCIA · " : "SIN LICENCIA · SIN LICENCIA · ";
  return (
    <div className={cn("relative overflow-hidden", className)}>
      {/* Atenuación: opacidad + desaturación. La imagen se ve, pero apagada. */}
      <div className="opacity-60 grayscale-[0.4] contrast-95">{children}</div>
      {/* Watermark diagonal a todo el área. No intercepta clics. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
      >
        <div
          className={cn(
            "w-[200%] -rotate-12 select-none whitespace-nowrap text-center font-bold uppercase tracking-widest text-red-600/70 dark:text-red-400/70",
            tamano === "sm" ? "text-[10px] leading-5" : "text-sm leading-7",
          )}
        >
          {Array.from({ length: tamano === "sm" ? 4 : 6 }).map((_, i) => (
            <span key={i} className="block">
              {banda.repeat(tamano === "sm" ? 3 : 4)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Badge compacto del estado de la imagen de stock:
 *  - sin autorizar → rojo "{proveedor} · SIN LICENCIA".
 *  - autorizada    → verde sutil "Autorizada · {proveedor}".
 * Devuelve `null` si la imagen no es de stock.
 */
export function BadgeStock({
  proveedor,
  autorizada,
  className,
}: {
  proveedor: string;
  autorizada: boolean;
  className?: string;
}) {
  return (
    <Badge
      variant={autorizada ? "ok" : "error"}
      className={cn("text-[10px] font-semibold uppercase tracking-wide", className)}
    >
      {autorizada ? `Autorizada · ${proveedor}` : `${proveedor} · Sin licencia`}
    </Badge>
  );
}
