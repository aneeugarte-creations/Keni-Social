import * as React from "react";

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

  React.useEffect(() => {
    if (abierto) {
      setNombre("");
      setUrl("");
      setPlataforma("general");
      setTipo("agregador");
    }
  }, [abierto]);

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva fuente de algoritmo</DialogTitle>
          <DialogDescription>
            Un feed RSS de un blog oficial o agregador.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="alg-nombre">Nombre</Label>
            <Input
              id="alg-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Meta Newsroom"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="alg-url">URL del feed</Label>
            <Input
              id="alg-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://about.fb.com/news/feed/"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Plataforma</Label>
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
            </div>
            <div className="space-y-1">
              <Label>Tipo</Label>
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
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Button>
          <Button
            onClick={() => onGuardar({ nombre, url, plataforma, tipo })}
            disabled={guardando || !nombre.trim() || !url.trim()}
          >
            Añadir fuente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
