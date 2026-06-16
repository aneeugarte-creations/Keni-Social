import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Leaf, Loader2, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";

import { CLASE_LABEL, CLAVE_ETIQUETAS, GLOBAL } from "./lib";
import type { ClaseLinea } from "./tipos";

/** Formulario de alta (inline). */
export function FormularioLinea({
  clase,
  marcas,
  onListo,
}: {
  clase: ClaseLinea;
  marcas: { id: string; nombre: string }[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState("");
  const [marca, setMarca] = React.useState(
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : GLOBAL,
  );
  const [keywords, setKeywords] = React.useState("");
  const [hashtags, setHashtags] = React.useState("");
  const [ttlDias, setTtlDias] = React.useState(0);
  const [esEvergreen, setEsEvergreen] = React.useState(false);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({
        nombre: nombre.trim(),
        clase,
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
        hashtags: hashtags.trim(),
        ttl_dias: ttlDias,
        es_evergreen: esEvergreen,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });
      toast.success(`${CLASE_LABEL[clase]} creada.`);
      onListo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = nombre.trim().length > 0 && !crear.isPending;

  return (
    <div className="space-y-3 rounded-md border border-dashed border-border p-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <Label htmlFor={`linea-nombre-${clase}`}>Nombre</Label>
          <Input
            id={`linea-nombre-${clase}`}
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder={clase === "vertical" ? "Ej. Futbol" : "Ej. Externo"}
            maxLength={60}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`linea-marca-${clase}`}>Marca</Label>
          <Select value={marca} onValueChange={setMarca}>
            <SelectTrigger id={`linea-marca-${clase}`} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GLOBAL}>Global</SelectItem>
              {marcas.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {clase === "vertical" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`linea-ttl-${clase}`}>
              TTL (días)
            </Label>
            <Input
              id={`linea-ttl-${clase}`}
              type="number"
              min={0}
              value={ttlDias}
              onChange={(e) => setTtlDias(Math.max(0, parseInt(e.target.value) || 0))}
              className="w-24"
            />
            <p className="text-xs text-muted-foreground">0 días = sin caducidad / evergreen</p>
          </div>
          <div className="flex items-center gap-3 pt-5">
            <Switch
              id={`linea-evergreen-${clase}`}
              checked={esEvergreen}
              onCheckedChange={setEsEvergreen}
            />
            <Label htmlFor={`linea-evergreen-${clase}`} className="flex items-center gap-1 cursor-pointer">
              <Leaf className="h-3.5 w-3.5 text-evergreen-600" />
              Evergreen
            </Label>
          </div>
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor={`linea-keywords-${clase}`}>
          Palabras clave
        </Label>
        <Textarea
          id={`linea-keywords-${clase}`}
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="liga, gol, partido, jornada"
          rows={2}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`linea-hashtags-${clase}`}>
          Hashtags
        </Label>
        <Textarea
          id={`linea-hashtags-${clase}`}
          value={hashtags}
          onChange={(e) => setHashtags(e.target.value)}
          placeholder="Nacional, Mundial2026"
          rows={2}
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={crear.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Añadir
        </Button>
      </div>
    </div>
  );
}
