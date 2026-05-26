import { Check, Copy, Download, FileText } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** Descarga un texto como archivo local (.txt o .md). */
function descargarTexto(texto: string, extension: "txt" | "md") {
  const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const sello = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = `copy-keni-${sello}.${extension}`;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

/**
 * Panel del borrador generado: muestra el texto con acciones para copiarlo al
 * portapapeles o descargarlo. Deja claro que nada se publica.
 */
export function Resultado({ resultado }: { resultado: string }) {
  const [copiado, setCopiado] = React.useState(false);
  // A-4: guardamos el id del timer para cancelarlo si el componente se desmonta.
  const timerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  React.useEffect(() => {
    // Si llega un resultado nuevo, reseteamos el estado "copiado".
    setCopiado(false);
  }, [resultado]);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(resultado);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle className="text-base">Borrador generado</CardTitle>
          <Badge variant="aviso">Borrador · no se publica</Badge>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void copiar()}>
            {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiado ? "Copiado" : "Copiar"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => descargarTexto(resultado, "txt")}>
            <Download className="h-4 w-4" />
            .txt
          </Button>
          <Button variant="outline" size="sm" onClick={() => descargarTexto(resultado, "md")}>
            <FileText className="h-4 w-4" />
            .md
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-4 text-sm leading-relaxed">
          {resultado}
        </pre>
      </CardContent>
    </Card>
  );
}
