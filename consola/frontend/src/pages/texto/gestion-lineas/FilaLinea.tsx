import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Leaf, Loader2, Pencil, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { Badge } from "@/components/ui/badge";
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
import { api, mensajeError } from "@/lib/api";
import type { Etiqueta } from "@/types";

import { CLASE_LABEL, CLAVE_ETIQUETAS, GLOBAL } from "./lib";
import type { ClaseLinea } from "./tipos";

/** Una fila con edición en línea (nombre · marca · keywords · ttl · evergreen) y borrado. */
export function FilaLinea({
  etiqueta,
  clase,
  marcas,
}: {
  etiqueta: Etiqueta;
  clase: ClaseLinea;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const [editando, setEditando] = React.useState(false);
  const [nombre, setNombre] = React.useState(etiqueta.nombre);
  const [marca, setMarca] = React.useState(etiqueta.marca || GLOBAL);
  const [keywords, setKeywords] = React.useState(etiqueta.keywords ?? "");
  const [ttlDias, setTtlDias] = React.useState(etiqueta.ttl_dias ?? 0);
  const [esEvergreen, setEsEvergreen] = React.useState(etiqueta.es_evergreen ?? false);

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });

  const empezar = () => {
    setNombre(etiqueta.nombre);
    setMarca(etiqueta.marca || GLOBAL);
    setKeywords(etiqueta.keywords ?? "");
    setTtlDias(etiqueta.ttl_dias ?? 0);
    setEsEvergreen(etiqueta.es_evergreen ?? false);
    setEditando(true);
  };

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarEtiqueta(etiqueta.id, {
        nombre: nombre.trim(),
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
        ttl_dias: ttlDias,
        es_evergreen: esEvergreen,
      }),
    onSuccess: () => {
      invalidar();
      setEditando(false);
      toast.success(`${CLASE_LABEL[clase]} actualizada.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarEtiqueta(etiqueta.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? `${CLASE_LABEL[clase]} borrada.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (editando) {
    return (
      <div className="space-y-3 rounded-md border border-border/60 p-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label htmlFor={`edit-nombre-${etiqueta.id}`} className="sr-only">
              Nombre
            </Label>
            <Input
              id={`edit-nombre-${etiqueta.id}`}
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              maxLength={60}
            />
          </div>
          <Select value={marca} onValueChange={setMarca}>
            <SelectTrigger aria-label="Marca" className="w-40">
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
        {clase === "vertical" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`edit-ttl-${etiqueta.id}`}>TTL (días)</Label>
              <Input
                id={`edit-ttl-${etiqueta.id}`}
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
                id={`edit-evergreen-${etiqueta.id}`}
                checked={esEvergreen}
                onCheckedChange={setEsEvergreen}
              />
              <Label htmlFor={`edit-evergreen-${etiqueta.id}`} className="flex items-center gap-1 cursor-pointer">
                <Leaf className="h-3.5 w-3.5 text-evergreen-600" />
                Everevergreen
              </Label>
            </div>
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor={`edit-keywords-${etiqueta.id}`}>
            Palabras clave{" "}
            <span className="font-normal text-muted-foreground">(separadas por comas)</span>
          </Label>
          <Textarea
            id={`edit-keywords-${etiqueta.id}`}
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="liga, gol, partido, jornada"
            rows={2}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditando(false)}
            disabled={actualizar.isPending}
          >
            <X className="h-4 w-4" />
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={() => actualizar.mutate()}
            disabled={nombre.trim().length === 0 || actualizar.isPending}
          >
            {actualizar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Guardar
          </Button>
        </div>
      </div>
    );
  }

  const palabras = (etiqueta.keywords ?? "")
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={empezar}
      etiquetaAcciones={`Acciones de "${etiqueta.nombre}"`}
      kebab="hover"
      acciones={[
        { etiqueta: "Editar", icono: Pencil, onClick: empezar },
        { separador: true },
        {
          etiqueta: "Borrar",
          icono: Trash2,
          destructivo: true,
          deshabilitado: borrar.isPending,
          onClick: async () => {
            if (
              await confirmar({
                mensaje: `¿Borrar "${etiqueta.nombre}"? Esta acción no se puede deshacer.`,
                destructivo: true,
                textoConfirmar: "Borrar",
              })
            )
              borrar.mutate();
          },
        },
      ]}
      className="space-y-1.5 rounded-md border border-border/60 p-3 pr-10"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{etiqueta.nombre}</span>
        <Badge variant="outline" className="font-normal">
          {etiqueta.marca_nombre || "Global"}
        </Badge>
        {clase === "vertical" && etiqueta.es_evergreen && (
          <Badge variant="secondary" className="gap-1 font-normal text-evergreen-700">
            <Leaf className="h-3 w-3" />
            Everevergreen
          </Badge>
        )}
        {clase === "vertical" && !etiqueta.es_evergreen && etiqueta.ttl_dias > 0 && (
          <Badge variant="outline" className="font-normal text-amber-600">
            {etiqueta.ttl_dias}d TTL
          </Badge>
        )}
      </div>
      {palabras.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {palabras.map((p) => (
            <Badge key={p} variant="secondary" className="font-normal">
              {p}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Sin palabras clave.</p>
      )}
    </FilaConAcciones>
  );
}
