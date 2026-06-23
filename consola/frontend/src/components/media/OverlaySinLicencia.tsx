/**
 * Tratamiento visual de una imagen de STOCK SIN LICENCIA (ayuda visual no publicable).
 *
 * Envuelve la imagen y, cuando la pieza está en STOCK_NO_AUTORIZADO, pinta UNA sola marca discreta
 * "SIN LICENCIA" centrada encima, para avisar de que esa foto NO puede salir a redes hasta
 * autorizarla. La foto se ve NÍTIDA (sin atenuar ni desaturar): solo la marca central avisa. Si la
 * imagen de stock ya está autorizada, no pinta nada: deja pasar a sus hijos (un badge sutil lo
 * señala aparte).
 *
 * Se usa en la preview del editor y en las miniaturas del feed/lista. El propio overlay es
 * `pointer-events-none`: no roba clics a la imagen ni a sus controles.
 */
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { etiquetaOverlayStock } from "@/lib/stock";
import { cn } from "@/lib/utils";

export interface OverlaySinLicenciaProps {
  /** `true` cuando la imagen es stock NO autorizado (marca "SIN LICENCIA"). */
  activo: boolean;
  /** Imagen (o cualquier contenido) a tratar. */
  children: React.ReactNode;
  /** Tamaño del rótulo: "sm" para miniaturas, "md" para la preview del editor. */
  tamano?: "sm" | "md";
  /** Proveedor del stock: junto a la licencia, decide el nivel ("Autorizar" vs "Sin licencia"). */
  proveedor?: string;
  /** Licencia real de la foto: clasifica el nivel (las usables rotulan "Autorizar"). */
  licencia?: string;
  className?: string;
}

export function OverlaySinLicencia({
  activo,
  children,
  tamano = "md",
  proveedor,
  licencia,
  className,
}: OverlaySinLicenciaProps) {
  if (!activo) {
    return <div className={cn("relative", className)}>{children}</div>;
  }
  return (
    <div className={cn("relative overflow-hidden", className)}>
      {/* La foto se ve nítida: solo una marca central tenue avisa de que es una referencia. */}
      {children}
      {/* Marca única "SIN LICENCIA" centrada, discreta. No intercepta clics. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 flex items-center justify-center"
      >
        <span
          className={cn(
            "select-none rounded-sm bg-black/35 font-semibold uppercase tracking-widest text-white/90 backdrop-blur-[1px]",
            tamano === "sm" ? "px-1.5 py-0.5 text-[9px]" : "px-2.5 py-1 text-xs",
          )}
        >
          {etiquetaOverlayStock({ licencia, proveedor })}
        </span>
      </div>
    </div>
  );
}

/**
 * Badge sutil de la FUENTE de una imagen de stock (esquina inferior derecha de la imagen):
 *  - sin autorizar → solo el nombre de la fuente (p. ej. "Openverse"). El aviso "sin licencia"
 *    lo da el overlay central, no el badge.
 *  - autorizada    → "Autorizada · {fuente}".
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
      variant="secondary"
      className={cn(
        "border-transparent bg-black/55 text-[10px] font-medium tracking-wide text-white/90 backdrop-blur-[1px]",
        className,
      )}
    >
      {autorizada ? `Autorizada · ${proveedor}` : proveedor}
    </Badge>
  );
}
