import { Check, ClipboardCopy, Download } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  construirMarkdownLista,
  nombreArchivoLista,
  type ItemExportable,
} from "@/components/comunes/exportarLista";

/**
 * Par de botones "Copiar / Descargar" para exportar una lista (tendencias o plan del
 * día) en formato copiar-pegar (Markdown listo para Word/WhatsApp/email).
 *
 * - "Copiar": construye el Markdown y lo escribe en el portapapeles (con feedback).
 * - "Descargar": ofrece el mismo Markdown como fichero .txt.
 *
 * El armado del texto vive en `construirMarkdownLista` (pura, testeada aparte); aquí
 * solo está el wiring con el portapapeles y la descarga (efectos del DOM).
 */
export function BotonExportarLista({
  titulo,
  items,
  disabled,
}: {
  titulo: string;
  items: ItemExportable[];
  disabled?: boolean;
}) {
  const [copiado, setCopiado] = React.useState(false);
  const timerRef = React.useRef<number | null>(null);

  React.useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const vacio = disabled || items.length === 0;

  async function copiar() {
    const texto = construirMarkdownLista(titulo, items);
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      toast.success("Lista copiada al portapapeles");
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Usa “Descargar .txt”.");
    }
  }

  function descargar() {
    const texto = construirMarkdownLista(titulo, items);
    const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombreArchivoLista(titulo);
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex shrink-0 items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => void copiar()} disabled={vacio}>
        {copiado ? <Check className="h-4 w-4" /> : <ClipboardCopy className="h-4 w-4" />}
        {copiado ? "Copiado" : "Copiar lista"}
      </Button>
      <Button variant="outline" size="sm" onClick={descargar} disabled={vacio}>
        <Download className="h-4 w-4" />
        Descargar .txt
      </Button>
    </div>
  );
}
