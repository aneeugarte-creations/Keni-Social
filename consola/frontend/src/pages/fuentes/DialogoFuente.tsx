import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Rss } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { desdeMarca, marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { FuenteRss, MarcaDisponible, RedPublicacion } from "@/types";

import { CLAVE_FUENTES, CLAVE_ITEMS } from "./lib";

/**
 * Categorías canónicas de feed (espejo del catálogo de presets + breaking). La categoría
 * manda la CADENCIA de sondeo del motor de ingesta — un feed de deportes se sondea cada
 * ~3 min, uno de gaming cada ~30 — y alimenta la cobertura/huecos de Salud.
 */
/**
 * Tiers de PESO editorial de una fuente: ponderan la corroboración del ranking de
 * historias (una nota en dos fuentes potentes a la vez sube al top y sale al feed).
 */
const TIERS_FUENTE: { id: string; peso: number; nombre: string; ayuda: string }[] = [
  { id: "potente", peso: 2.0, nombre: "Potente", ayuda: "agencias y cabeceras de primer nivel (Reuters, AP, BBC…)" },
  { id: "normal", peso: 1.0, nombre: "Normal", ayuda: "la mayoría de los medios" },
  { id: "baja", peso: 0.5, nombre: "Baja confiabilidad", ayuda: "agregadores, foros, fuentes sin verificar" },
];

const CATEGORIAS_FEED: { id: string; nombre: string; cadencia: string }[] = [
  { id: "mx", nombre: "México (nacional)", cadencia: "~10 min" },
  { id: "regional", nombre: "Regional (estados)", cadencia: "~10 min" },
  { id: "internacional", nombre: "Internacional", cadencia: "~10 min" },
  { id: "deportes", nombre: "Deportes", cadencia: "~3 min" },
  { id: "ciencia-tech", nombre: "Ciencia y tecnología", cadencia: "~30 min" },
  { id: "gaming", nombre: "Gaming", cadencia: "~30 min" },
  { id: "negocios", nombre: "Negocios", cadencia: "~10 min" },
  { id: "tendencias", nombre: "Tendencias", cadencia: "~10 min" },
  { id: "breaking", nombre: "Breaking (máxima cadencia)", cadencia: "~3 min" },
];

/** Diálogo de alta / edición de un feed. */
export function DialogoFuente({
  abierto,
  fuente,
  marcas,
  redes,
  onCerrar,
}: {
  abierto: boolean;
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
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
          <DialogDescription>
            Configura el feed RSS: filtros por palabra clave, redes por defecto al generar y si
            está activo.
          </DialogDescription>
        </DialogHeader>
        {abierto && (
          <FormularioFuente
            fuente={fuente}
            marcas={marcas}
            redes={redes}
            onListo={onCerrar}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Formulario de alta/edición de un feed (dentro del diálogo). */
function FormularioFuente({
  fuente,
  marcas,
  redes,
  onListo,
}: {
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  // Feed NUEVO: por defecto la marca activa (así nace tagueado y alimenta su radar).
  // Editando: respeta la marca guardada del feed.
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState(fuente?.nombre ?? "");
  const [url, setUrl] = React.useState(fuente?.url ?? "");
  // La marca la fija el switch global (ya no hay selector propio): un feed NUEVO es de la marca
  // activa (o compartido cuando el global está en "Todas"); al EDITAR se conserva la del feed.
  const marca = fuente
    ? desdeMarca(fuente.marca)
    : desdeMarca(marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : undefined);
  const nombreMarcaFuente =
    marcas.find((m) => m.id === marcaParam(marca))?.nombre ?? "Compartida (todas las marcas)";
  const [incluir, setIncluir] = React.useState(fuente?.incluir ?? "");
  const [excluir, setExcluir] = React.useState(fuente?.excluir ?? "");
  const [activo, setActivo] = React.useState(fuente?.activo ?? true);
  const [propia, setPropia] = React.useState(fuente?.propia ?? false);
  const [categoria, setCategoria] = React.useState(fuente?.categoria ?? "");
  // Tier de PESO editorial. Alta nueva: "" = que el back decida por el host (Reuters/BBC
  // nacen potentes solas); al editar se muestra el tier real del feed.
  const [tier, setTier] = React.useState(fuente?.tier ?? "");
  const [redesDef, setRedesDef] = React.useState<Set<string>>(
    () => new Set(fuente?.redes_def ?? []),
  );

  const guardar = useMutation({
    mutationFn: () => {
      const marcaVal = marcaParam(marca) ?? "";
      const redesArr = [...redesDef];
      const pesoVal = TIERS_FUENTE.find((t) => t.id === tier)?.peso;
      if (fuente) {
        return api.actualizarFuenteRss(fuente.id, {
          nombre: nombre.trim(),
          url: url.trim(),
          marca: marcaVal,
          activo,
          incluir: incluir.trim(),
          excluir: excluir.trim(),
          redes_def: redesArr,
          propia,
          categoria,
          ...(pesoVal != null ? { peso: pesoVal } : {}),
        });
      }
      return api.crearFuenteRss({
        nombre: nombre.trim(),
        url: url.trim(),
        marca: marcaVal || undefined,
        incluir: incluir.trim() || undefined,
        excluir: excluir.trim() || undefined,
        redes_def: redesArr.length > 0 ? redesArr : undefined,
        propia: propia || undefined,
        categoria: categoria || undefined,
        // Sin tier elegido, el back asigna el peso por el host (seed automático).
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

  function alternarRed(red: string, marcada: boolean) {
    setRedesDef((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const opcionesRedes = React.useMemo(
    () => redes.map((r) => ({ id: r.id, nombre: r.nombre })),
    [redes],
  );

  const puedeGuardar =
    nombre.trim().length > 0 && url.trim().length > 0 && !guardar.isPending;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="fuente-nombre">Nombre</Label>
        <Input
          id="fuente-nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Ej. UnoTV Deportes"
          maxLength={120}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-url">URL del feed</Label>
        <Input
          id="fuente-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ejemplo.com/rss.xml"
          type="url"
          inputMode="url"
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Marca</Label>
          <p className="text-sm text-muted-foreground pt-1.5">{nombreMarcaFuente}</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fuente-categoria">Categoría</Label>
          <Select
            value={categoria || "__sin__"}
            onValueChange={(v) => setCategoria(v === "__sin__" ? "" : v)}
          >
            <SelectTrigger id="fuente-categoria" aria-label="Categoría del feed">
              <SelectValue placeholder="Sin categoría" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__sin__">Sin categoría (cadencia normal)</SelectItem>
              {CATEGORIAS_FEED.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.nombre} · {c.cadencia}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Marca la frecuencia con la que el motor sondea este feed.
          </p>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-tier">Potencia de la fuente</Label>
        <Select
          value={tier || "__auto__"}
          onValueChange={(v) => setTier(v === "__auto__" ? "" : v)}
        >
          <SelectTrigger id="fuente-tier" aria-label="Potencia de la fuente" data-testid="select-tier">
            <SelectValue placeholder="Automática" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__auto__">Automática (según el medio)</SelectItem>
            {TIERS_FUENTE.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.nombre} — {t.ayuda}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Pondera la corroboración del ranking: una nota confirmada por dos fuentes potentes
          casi a la vez sube al top y sale sola al feed.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="fuente-incluir">
            Incluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-incluir"
            value={incluir}
            onChange={(e) => setIncluir(e.target.value)}
            placeholder="fútbol, liga"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fuente-excluir">
            Excluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-excluir"
            value={excluir}
            onChange={(e) => setExcluir(e.target.value)}
            placeholder="opinión, podcast"
          />
        </div>
      </div>
      <SelectorRedMultiple
        opciones={opcionesRedes}
        seleccionadas={redesDef}
        onCambio={alternarRed}
      />
      <p className="-mt-1 text-xs text-muted-foreground">
        Redes por defecto al generar copy desde una noticia de este feed.
      </p>
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
            Sitio propio: su imagen original es reutilizable, así que las piezas generadas
            desde sus noticias nacen con la imagen del artículo lista para usarse.
          </p>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {fuente ? "Guardar cambios" : "Añadir feed"}
        </Button>
      </div>
    </div>
  );
}
