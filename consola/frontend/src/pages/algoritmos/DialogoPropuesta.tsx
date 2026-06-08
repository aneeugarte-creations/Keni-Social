import { Clipboard } from "lucide-react";
import { Link } from "react-router-dom";
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
import { Markdown } from "@/components/ui/Markdown";

/** Diálogo: propuesta para la texto. */
export function DialogoPropuesta({
  propuesta,
  onCerrar,
}: {
  propuesta: string | null;
  onCerrar: () => void;
}) {
  return (
    <Dialog open={propuesta !== null} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Propuesta para la texto</DialogTitle>
          <DialogDescription>
            Borrador listo para pegar en la ficha editorial de la plataforma. La línea
            editorial la decide el equipo: cópialo y confírmalo en la Texto.
          </DialogDescription>
        </DialogHeader>
        {propuesta && (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <Markdown>{propuesta}</Markdown>
          </div>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              if (propuesta) {
                void navigator.clipboard?.writeText(propuesta);
                toast.success("Copiado al portapapeles.");
              }
            }}
          >
            <Clipboard className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Copiar
          </Button>
          <Button asChild>
            <Link to="/contenido/texto">Abrir Texto</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
