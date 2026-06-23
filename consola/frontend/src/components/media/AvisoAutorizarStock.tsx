/**
 * Cuerpo del diálogo de AUTORIZAR una foto de stock. Se pasa como `mensaje` (ReactNode) a
 * `confirmar(...)`.
 *
 *  - Proveedor con licencia libre clara (Pexels/Pixabay): explica que la licencia permite uso
 *    libre y enumera los 2 riesgos editoriales que el humano debe descartar antes de publicar.
 *  - Resto de proveedores: el aviso de responsabilidad de siempre (derechos bajo su criterio).
 */
import { esProveedorLibre, nombreProveedor, RIESGOS_STOCK_LIBRE } from "@/lib/stock";

export interface AvisoAutorizarStockProps {
  proveedor?: string;
  licencia?: string;
}

export function AvisoAutorizarStock({ proveedor, licencia }: AvisoAutorizarStockProps) {
  if (!esProveedorLibre(proveedor)) {
    return (
      <span className="text-sm text-muted-foreground">
        Confirmas que tienes derechos para publicar esta imagen. Bajo tu responsabilidad.
      </span>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-sm">
        Licencia {licencia?.trim() || nombreProveedor(proveedor)}: uso libre, incluso comercial,
        sin atribución obligatoria.
      </p>
      <div className="space-y-1 text-sm text-muted-foreground">
        <p>Antes de publicar, comprueba solo dos cosas:</p>
        <ul className="list-disc space-y-1 pl-4">
          {RIESGOS_STOCK_LIBRE.map((riesgo) => (
            <li key={riesgo}>{riesgo}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
