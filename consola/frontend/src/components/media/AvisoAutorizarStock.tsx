/**
 * Cuerpo del diálogo de AUTORIZAR una foto de stock. Se pasa como `mensaje` (ReactNode) a
 * `confirmar(...)`. El texto depende del NIVEL de licencia real de la foto (`nivelLicencia`):
 *
 *  - "libre": licencia de uso libre (CC0/dominio público/Pexels/Pixabay). Explica que permite uso
 *    comercial sin atribución y enumera los 2 riesgos editoriales a descartar antes de publicar.
 *  - "atribucion": uso comercial permitido PERO con crédito obligatorio (CC BY / CC BY-SA). Muestra
 *    el crédito a mantener y, si es share-alike, avisa de que editar obliga a licenciar igual.
 *  - "restringida": el aviso de responsabilidad de siempre (derechos bajo su criterio).
 */
import {
  atribucionStock,
  esShareAlike,
  nivelLicencia,
  nombreProveedor,
  RIESGOS_STOCK_LIBRE,
} from "@/lib/stock";

export interface AvisoAutorizarStockProps {
  proveedor?: string;
  licencia?: string;
  autor?: string;
}

/** Lista de los 2 riesgos editoriales a descartar antes de publicar una foto de stock usable. */
function RiesgosEditoriales() {
  return (
    <div className="space-y-1 text-sm text-muted-foreground">
      <p>Antes de publicar, comprueba solo dos cosas:</p>
      <ul className="list-disc space-y-1 pl-4">
        {RIESGOS_STOCK_LIBRE.map((riesgo) => (
          <li key={riesgo}>{riesgo}</li>
        ))}
      </ul>
    </div>
  );
}

export function AvisoAutorizarStock({ proveedor, licencia, autor }: AvisoAutorizarStockProps) {
  const nivel = nivelLicencia({ licencia, proveedor });

  if (nivel === "libre") {
    return (
      <div className="space-y-2">
        <p className="text-sm">
          Licencia {licencia?.trim() || nombreProveedor(proveedor)}: uso libre, incluso comercial,
          sin atribución obligatoria.
        </p>
        <RiesgosEditoriales />
      </div>
    );
  }

  if (nivel === "atribucion") {
    const credito = atribucionStock({ autor, licencia, proveedor });
    return (
      <div className="space-y-2">
        <p className="text-sm">
          Licencia {licencia?.trim() || nombreProveedor(proveedor)}: uso comercial permitido, PERO
          debes mantener el crédito visible al publicar:
        </p>
        <p className="text-sm font-medium">{credito}</p>
        {esShareAlike(licencia) && (
          <p className="text-sm text-muted-foreground">
            Si editas la foto, tu publicación debe llevar la misma licencia (CC BY-SA).
          </p>
        )}
        <RiesgosEditoriales />
      </div>
    );
  }

  return (
    <span className="text-sm text-muted-foreground">
      Confirmas que tienes derechos para publicar esta imagen. Bajo tu responsabilidad.
    </span>
  );
}
