import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Rss } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Campo } from "@/components/comunes/Campo";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
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
import { Spinner } from "@/components/ui/spinner";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { FuenteRss, MarcaDisponible } from "@/types";

import { CLAVE_FUENTES, CLAVE_ITEMS } from "./lib";

// Relevancia editorial de la fuente (pondera la corroboración del ranking). El back la
// expone como tier potente/normal/baja; aquí se habla SIEMPRE de Alta/Media/Baja.
const RELEVANCIAS: { id: string; peso: number; nombre: string }[] = [
  { id: "potente", peso: 2.0, nombre: "Alta" },
  { id: "normal", peso: 1.0, nombre: "Media" },
  { id: "baja", peso: 0.5, nombre: "Baja" },
];

/** Etiqueta de cadencia de una línea (el feed la hereda de su línea). */
const CADENCIA_ETIQUETA: Record<string, string> = {
  rapida: "~3 min",
  normal: "~10 min",
  evergreen: "~30 min",
};

/** Diálogo de alta / edición de un feed. */
export function DialogoFuente({
  abierto,
  fuente,
  marcas,
  onCerrar,
}: {
  abierto: boolean;
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  onCerrar: () => void;
}) {
  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rss className="h-5 w-5" />
            {fuente ? "Editar feed" : "Nuevo feed"}
          </DialogTitle>
        </DialogHeader>
        {abierto && (
          <FormularioFuente fuente={fuente} marcas={marcas} onListo={onCerrar} />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Formulario de alta/edición de un feed (dentro del diálogo). */
function FormularioFuente({
  fuente,
  marcas,
  onListo,
}: {
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  // Feed NUEVO: por defecto la marca activa (así nace tagueado y alimenta su radar).
  // Editando: respeta la marca guardada del feed.
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState(fuente?.nombre ?? "");
  const [url, setUrl] = React.useState(fuente?.url ?? "");
  // Marcas SERVIDAS por el feed (multimarca): ingiere una vez y hace fan-out por marca. Feed NUEVO:
  // por defecto la marca activa (compartido si el switch global está en "Todas"). Editando: las del
  // feed. La PRINCIPAL (display + validación de línea, que es por marca) es la primera de la lista.
  const marcaBase = fuente
    ? fuente.marca
    : marcaActiva && marcas.some((m) => m.id === marcaActiva)
      ? marcaActiva
      : "";
  const [marcasServidas, setMarcasServidas] = React.useState<string[]>(
    fuente
      ? fuente.marcas.length
        ? fuente.marcas
        : fuente.marca
          ? [fuente.marca]
          : []
      : marcaBase
        ? [marcaBase]
        : [],
  );
  const marcaPrincipal = marcasServidas[0] ?? "";
  const alternarMarca = (id: string) =>
    setMarcasServidas((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id],
    );
  const [activo, setActivo] = React.useState(fuente?.activo ?? true);
  const [propia, setPropia] = React.useState(fuente?.propia ?? false);
  // CATEGORÍA de la que cuelga el feed (catch-all "" = General). La cadencia se hereda.
  const [lineaId, setLineaId] = React.useState(fuente?.linea_id ?? "");
  // Líneas de la marca del feed (clase `categoria`, activas): de aquí cuelga el feed.
  const lineasQuery = useQuery({
    queryKey: ["etiquetas", "categoria", marcaPrincipal],
    queryFn: ({ signal }) =>
      api.etiquetas({ marca: marcaPrincipal, clase: "categoria", activas: true }, signal),
  });
  const lineas = lineasQuery.data?.etiquetas ?? [];
  // Relevancia. Alta nueva: "" = el back decide por el medio; al editar, la del feed.
  const [tier, setTier] = React.useState(fuente?.tier ?? "");
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  const guardar = useMutation({
    mutationFn: () => {
      const pesoVal = RELEVANCIAS.find((t) => t.id === tier)?.peso;
      if (fuente) {
        return api.actualizarFuenteRss(fuente.id, {
          nombre: nombre.trim(),
          url: url.trim(),
          marca: marcaPrincipal,
          marcas: marcasServidas,
          activo,
          propia,
          linea_id: lineaId,
          ...(pesoVal != null ? { peso: pesoVal } : {}),
        });
      }
      return api.crearFuenteRss({
        nombre: nombre.trim(),
        url: url.trim(),
        marca: marcaPrincipal || undefined,
        marcas: marcasServidas.length ? marcasServidas : undefined,
        propia: propia || undefined,
        linea_id: lineaId || undefined,
        // Sin relevancia elegida, el back la asigna por el medio.
        ...(pesoVal != null ? { peso: pesoVal } : {}),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      // La SALUD del motor (pestaña Salud de fuentes) lee otra query: sin invalidarla, un
      // alta/edición no se refleja allí hasta el siguiente refetch (45 s) — parecía un bug.
      void queryClient.invalidateQueries({ queryKey: ["noticias", "salud"] });
      toast.success(fuente ? "Feed actualizado" : "Feed añadido");
      onListo();
    },
    // El backend puede devolver 400 si la URL no es válida o por SSRF.
    onError: (e) => toast.error(mensajeError(e)),
  });

  const errNombre = !nombre.trim() ? "El nombre es obligatorio." : null;
  const errUrl = !url.trim() ? "La URL del feed es obligatoria." : null;
  const hayErrores = Boolean(errNombre || errUrl);

  const onGuardar = () => {
    setIntentado(true);
    if (hayErrores) return;
    guardar.mutate();
  };

  return (
    <div className="space-y-4">
      <Campo etiqueta="Nombre" htmlFor="fuente-nombre" error={intentado ? errNombre : null}>
        <Input
          id="fuente-nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Ej. UnoTV Deportes"
          maxLength={120}
          aria-invalid={(intentado && Boolean(errNombre)) || undefined}
        />
      </Campo>
      <Campo etiqueta="URL del feed" htmlFor="fuente-url" error={intentado ? errUrl : null}>
        <Input
          id="fuente-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ejemplo.com/rss.xml"
          type="url"
          inputMode="url"
          aria-invalid={(intentado && Boolean(errUrl)) || undefined}
        />
      </Campo>
      <Campo etiqueta="Marcas">
        <div className="space-y-1.5 pt-1">
          {marcas.map((m) => (
            <label key={m.id} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={marcasServidas.includes(m.id)}
                onCheckedChange={() => alternarMarca(m.id)}
                aria-label={`Servir a ${m.nombre}`}
              />
              {m.nombre}
            </label>
          ))}
          <p className="text-xs text-muted-foreground">
            {marcasServidas.length === 0
              ? "Compartida (todas las marcas)."
              : "El feed ingiere una vez y alimenta a cada marca marcada."}
          </p>
        </div>
      </Campo>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Línea" htmlFor="fuente-linea">
          <Select
            value={lineaId || "__sin__"}
            onValueChange={(v) => setLineaId(v === "__sin__" ? "" : v)}
          >
            <SelectTrigger id="fuente-linea" aria-label="Línea del feed">
              <SelectValue placeholder="General" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__sin__">General (cadencia normal)</SelectItem>
              {lineas.map((l) => (
                <SelectItem key={l.id} value={l.id}>
                  {l.grupo ? `${l.grupo} · ` : ""}
                  {l.nombre}
                  {CADENCIA_ETIQUETA[l.cadencia] ? ` · ${CADENCIA_ETIQUETA[l.cadencia]}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Campo>
      </div>
      <Campo etiqueta="Relevancia" htmlFor="fuente-relevancia">
        <Select value={tier} onValueChange={(v) => setTier(v)}>
          <SelectTrigger
            id="fuente-relevancia"
            aria-label="Relevancia de la fuente"
            data-testid="select-relevancia"
          >
            <SelectValue placeholder="Media" />
          </SelectTrigger>
          <SelectContent>
            {RELEVANCIAS.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Campo>
      <div className="flex items-center gap-2">
        <Checkbox
          id="fuente-activo"
          checked={activo}
          onCheckedChange={(v) => setActivo(v)}
          aria-label="Feed activo"
        />
        <Label htmlFor="fuente-activo" className="cursor-pointer font-normal">
          Feed activo
        </Label>
      </div>
      <div className="flex items-start gap-2">
        <Checkbox
          id="fuente-propia"
          checked={propia}
          onCheckedChange={(v) => setPropia(!!v)}
          aria-label="Fuente de marca propia"
          className="mt-0.5"
        />
        <div className="space-y-0.5">
          <Label htmlFor="fuente-propia" className="cursor-pointer font-normal">
            Fuente de marca propia
          </Label>
          <p className="text-xs text-muted-foreground">
            Reutiliza imágenes originales en las piezas generadas.
          </p>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={onGuardar} disabled={guardar.isPending}>
          {guardar.isPending ? (
            <Spinner className="h-4 w-4" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {fuente ? "Guardar cambios" : "Añadir feed"}
        </Button>
      </div>
    </div>
  );
}
