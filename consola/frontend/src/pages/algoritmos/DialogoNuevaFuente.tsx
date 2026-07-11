import * as React from "react";

import { Campo } from "@/components/comunes/Campo";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CuerpoFuenteAlgoritmo, OpcionAlgoritmo } from "@/types";

/** Diálogo: alta de fuente. */
export function DialogoNuevaFuente({
  abierto,
  onCerrar,
  onGuardar,
  guardando,
  plataformas,
  tipos,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onGuardar: (cuerpo: CuerpoFuenteAlgoritmo) => void;
  guardando: boolean;
  plataformas: OpcionAlgoritmo[];
  tipos: OpcionAlgoritmo[];
}) {
  const [nombre, setNombre] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [plataforma, setPlataforma] = React.useState("general");
  const [tipo, setTipo] = React.useState("agregador");
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  React.useEffect(() => {
    if (abierto) {
      setNombre("");
      setUrl("");
      setPlataforma("general");
      setTipo("agregador");
      setIntentado(false);
    }
  }, [abierto]);

  const errNombre = !nombre.trim() ? "El nombre es obligatorio." : null;
  const errUrl = !url.trim() ? "La URL del feed es obligatoria." : null;
  const hayErrores = Boolean(errNombre || errUrl);

  const enviar = () => {
    setIntentado(true);
    if (hayErrores) return;
    onGuardar({ nombre, url, plataforma, tipo });
  };

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva fuente de algoritmo</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Campo etiqueta="Nombre" htmlFor="alg-nombre" error={intentado ? errNombre : null}>
            <Input
              id="alg-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Meta Newsroom"
              aria-invalid={(intentado && Boolean(errNombre)) || undefined}
            />
          </Campo>
          <Campo etiqueta="URL del feed" htmlFor="alg-url" error={intentado ? errUrl : null}>
            <Input
              id="alg-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://about.fb.com/news/feed/"
              aria-invalid={(intentado && Boolean(errUrl)) || undefined}
            />
          </Campo>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Campo etiqueta="Plataforma">
              <Select value={plataforma} onValueChange={setPlataforma}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {plataformas.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Campo>
            <Campo etiqueta="Tipo">
              <Select value={tipo} onValueChange={setTipo}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {tipos.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Campo>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Button>
          <Button variant="default" onClick={enviar} disabled={guardando}>
            Añadir fuente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
