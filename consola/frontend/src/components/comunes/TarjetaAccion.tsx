import * as React from "react";

import { cn } from "@/lib/utils";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";

interface TarjetaAccionProps {
  /**
   * Acción primaria: se dispara con click izquierdo sobre el cuerpo de la tarjeta (o
   * Enter/Espacio). Es la acción intuitiva principal; todo lo demás vive en el menú.
   */
  onPrimaria?: () => void;
  /**
   * Acciones secundarias y destructivas. Alimentan el menú contextual (click derecho),
   * el long-press táctil y la apertura por teclado (Shift+F10 / tecla Menú). Sin botones
   * sueltos en la tarjeta: el descubrimiento es el realce naranja del borde al hover.
   */
  acciones?: EntradaMenuContextual[];
  /** Etiqueta accesible del menú (aria-label). */
  etiquetaAcciones?: string;
  /** Clases extra del contenedor (layout interno, padding, etc.). */
  className?: string;
  children: React.ReactNode;
}

/**
 * Tarjeta accionable con el modelo "item-first" de toda la consola: la acción principal
 * se dispara con click izquierdo sobre la tarjeta y las secundarias/destructivas viven en
 * un único menú (click derecho · long-press táctil · teclado). NO pinta botones ni iconos:
 * la pista de que es accionable es el realce naranja del borde al pasar el ratón o enfocar.
 *
 * Reemplaza a las tarjetas saturadas de 3-4 botones. Para acciones que requieren entrada
 * (elegir, escribir), `onPrimaria` debe abrir un diálogo/popup; las acciones directas
 * (ir a, generar) van en `onPrimaria` o en `acciones` según sean primaria o secundaria.
 */
export function TarjetaAccion({
  onPrimaria,
  acciones = [],
  etiquetaAcciones,
  className,
  children,
}: TarjetaAccionProps) {
  return (
    <FilaConAcciones
      como="div"
      onPrimaria={onPrimaria}
      acciones={acciones}
      etiquetaAcciones={etiquetaAcciones}
      kebab="nunca"
      realce
      className={cn(
        "rounded-xl border border-border bg-card text-card-foreground",
        className,
      )}
    >
      {children}
    </FilaConAcciones>
  );
}
