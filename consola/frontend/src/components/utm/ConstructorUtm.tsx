/**
 * Constructor de enlaces UTM (solo frontend, sin API).
 *
 * Diálogo con una URL base y los cinco parámetros UTM estándar. Genera la URL
 * etiquetada (con los parámetros correctamente encodeados) y ofrece:
 *  - **Copiar** la URL al portapapeles.
 *  - **Insertar** el enlace al final del contenido del post en composición.
 *
 * No toca el backend. React Query no es necesario aquí. Toasts (`sonner`); modo
 * claro/oscuro; texto es-MX.
 */
import { Check, Copy, Link2, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { CAMPOS_UTM_VACIOS, type CamposUtm, construirUrlUtm } from "./utm";

/** Una fila etiqueta + input para un parámetro UTM. */
function CampoUtm({
  id,
  etiqueta,
  valor,
  onCambio,
  placeholder,
  opcional = false,
}: {
  id: string;
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  placeholder: string;
  opcional?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {etiqueta}
        {opcional && <span className="font-normal text-muted-foreground"> (opcional)</span>}
      </Label>
      <Input
        id={id}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

export function ConstructorUtm({
  abierto,
  onCerrar,
  /** Si se pasa, habilita el botón "Insertar" que añade el enlace al contenido. */
  onInsertar,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onInsertar?: (enlace: string) => void;
}) {
  const [base, setBase] = React.useState("");
  const [campos, setCampos] = React.useState<CamposUtm>(CAMPOS_UTM_VACIOS);
  const [copiado, setCopiado] = React.useState(false);

  // Al cerrar, reseteamos el formulario.
  React.useEffect(() => {
    if (!abierto) {
      setBase("");
      setCampos(CAMPOS_UTM_VACIOS);
      setCopiado(false);
    }
  }, [abierto]);

  const resultado = React.useMemo(() => construirUrlUtm(base, campos), [base, campos]);
  const baseInvalida = base.trim().length > 0 && resultado === "";

  function set(clave: keyof CamposUtm, valor: string) {
    setCampos((prev) => ({ ...prev, [clave]: valor }));
  }

  async function copiar() {
    if (!resultado) return;
    try {
      await navigator.clipboard.writeText(resultado);
      setCopiado(true);
      toast.success("Enlace copiado al portapapeles");
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  function insertar() {
    if (!resultado || !onInsertar) return;
    onInsertar(resultado);
    toast.success("Enlace insertado en el contenido");
    onCerrar();
  }

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Constructor de enlaces UTM
          </DialogTitle>
          <DialogDescription>
            Etiqueta una URL con parámetros UTM para medir el origen del tráfico. Los valores se
            codifican automáticamente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="utm-base">URL base</Label>
            <Input
              id="utm-base"
              value={base}
              onChange={(e) => setBase(e.target.value)}
              placeholder="https://ejemplo.com/pagina"
              type="url"
              inputMode="url"
            />
            {baseInvalida && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Escribe una URL válida, incluyendo https://
              </p>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <CampoUtm
              id="utm-source"
              etiqueta="utm_source"
              valor={campos.source}
              onCambio={(v) => set("source", v)}
              placeholder="instagram"
            />
            <CampoUtm
              id="utm-medium"
              etiqueta="utm_medium"
              valor={campos.medium}
              onCambio={(v) => set("medium", v)}
              placeholder="social"
            />
            <CampoUtm
              id="utm-campaign"
              etiqueta="utm_campaign"
              valor={campos.campaign}
              onCambio={(v) => set("campaign", v)}
              placeholder="lanzamiento_verano"
            />
            <CampoUtm
              id="utm-term"
              etiqueta="utm_term"
              valor={campos.term}
              onCambio={(v) => set("term", v)}
              placeholder="fútbol"
              opcional
            />
            <CampoUtm
              id="utm-content"
              etiqueta="utm_content"
              valor={campos.content}
              onCambio={(v) => set("content", v)}
              placeholder="banner_superior"
              opcional
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="utm-resultado">Enlace etiquetado</Label>
            <Input
              id="utm-resultado"
              value={resultado}
              readOnly
              placeholder="El enlace aparecerá aquí…"
              className="font-mono text-xs"
            />
          </div>
        </div>

        <DialogFooter className="sm:justify-between">
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => void copiar()} disabled={!resultado}>
              {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copiado ? "Copiado" : "Copiar"}
            </Button>
            {onInsertar && (
              <Button onClick={insertar} disabled={!resultado}>
                <Plus className="h-4 w-4" />
                Insertar
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
