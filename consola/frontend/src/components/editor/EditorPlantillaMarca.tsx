/**
 * Editor de la "plantilla de marca": la identidad visual con la que el Estudio
 * estampa una imagen (logo/pleca/titular + colores). Vive en un `Dialog` que se
 * abre desde el Estudio.
 *
 * Flujo: al elegir/cambiar la marca se carga su plantilla (`plantillaMarca`) y se
 * rellena el formulario; "Guardar" hace el PUT (`guardarPlantillaMarca`). El logo
 * se sube con el método existente `subirMedia` (devuelve `{id, url}`) y se guarda
 * su `id` en `logo` (la URL para la preview viene en `logo_url`).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Upload, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { EditorPlantillaSpec } from "@/components/editor/EditorPlantillaSpec";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { api, ApiError, urlMedia } from "@/lib/api";
import type { MarcaDisponible, PlantillaMarca, PosicionLogo } from "@/types";

/** Posiciones del logo dentro del lienzo, con etiqueta legible. */
const POSICIONES: { id: PosicionLogo; etiqueta: string }[] = [
  { id: "superior-izquierda", etiqueta: "Superior izquierda" },
  { id: "superior-derecha", etiqueta: "Superior derecha" },
  { id: "inferior-izquierda", etiqueta: "Inferior izquierda" },
  { id: "inferior-derecha", etiqueta: "Inferior derecha" },
];

/** Plantilla vacía de base mientras carga (o si la marca aún no tiene una guardada). */
function plantillaVacia(marca: string): PlantillaMarca {
  return {
    marca,
    rojo: "#E10600",
    tinta: "#111111",
    blanco: "#FFFFFF",
    etiqueta_default: "",
    titular_mayusculas: true,
    titular_condensada: true,
    logo: "",
    logo_url: "",
    logo_posicion: "inferior-derecha",
    wordmark: "",
  };
}

/** Un input de color (color picker + hex en texto, sincronizados). */
function CampoColor({
  id,
  etiqueta,
  valor,
  onCambio,
  disabled,
}: {
  id: string;
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs">
        {etiqueta}
      </Label>
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="color"
          value={valor || "#000000"}
          onChange={(e) => onCambio(e.target.value)}
          disabled={disabled}
          className="h-9 w-12 shrink-0 cursor-pointer rounded border border-border bg-transparent disabled:cursor-not-allowed disabled:opacity-50"
          aria-label={etiqueta}
        />
        <Input
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          placeholder="#000000"
          disabled={disabled}
          className="font-mono"
        />
      </div>
    </div>
  );
}

export function EditorPlantillaMarca({
  abierto,
  onOpenChange,
  marcas,
  marcaInicial,
}: {
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
  marcas: MarcaDisponible[];
  /** Marca a preseleccionar al abrir (la del contexto de la pieza, si la hay). */
  marcaInicial?: string;
}) {
  // Marca seleccionada en el editor (al cambiar recargamos su plantilla).
  const [marca, setMarca] = React.useState(marcaInicial || marcas[0]?.id || "");
  const [datos, setDatos] = React.useState<PlantillaMarca>(() => plantillaVacia(marca));
  const logoInputRef = React.useRef<HTMLInputElement>(null);

  // Al abrir, sincroniza la marca con la del contexto si aún no hay una elegida.
  React.useEffect(() => {
    if (abierto && !marca) setMarca(marcaInicial || marcas[0]?.id || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto]);

  // Carga la plantilla de la marca activa (solo con el diálogo abierto y marca elegida).
  const plantillaQuery = useQuery({
    queryKey: ["plantilla-marca", marca],
    queryFn: ({ signal }) => api.plantillaMarca(marca, signal),
    enabled: abierto && marca.length > 0,
  });

  // Rehidrata el formulario cuando llega la plantilla (o cambia la marca).
  React.useEffect(() => {
    if (plantillaQuery.data?.plantilla) {
      setDatos(plantillaQuery.data.plantilla);
    }
  }, [plantillaQuery.data]);

  // Subida del logo: usa el método existente y guarda el id (+ url para la preview).
  const subirLogo = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (data) => {
      setDatos((d) => ({ ...d, logo: data.id, logo_url: data.url }));
      toast.success("Logo subido");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo subir el logo."),
  });

  function onArchivoLogo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subirLogo.mutate(archivo);
    if (logoInputRef.current) logoInputRef.current.value = "";
  }

  const guardar = useMutation({
    mutationFn: () => api.guardarPlantillaMarca(marca, datos),
    onSuccess: (data) => {
      setDatos(data.plantilla);
      toast.success("Plantilla guardada");
      onOpenChange(false);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo guardar la plantilla.");
    },
  });

  const cargando = plantillaQuery.isLoading;
  const bloqueado = cargando || subirLogo.isPending || guardar.isPending;
  const previewLogo = datos.logo ? urlMedia(datos.logo_url || datos.logo) : "";

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Editar plantilla de marca</DialogTitle>
          <DialogDescription>
            Diseña la plantilla por formato (fondo, logo, textos, hueco de foto). Lo que diseñas es
            lo que se genera. Abajo quedan los ajustes básicos rápidos.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Marca */}
          <div className="space-y-1.5">
            <Label htmlFor="plantilla-marca" className="text-xs">
              Marca
            </Label>
            <SelectorMarca
              id="plantilla-marca"
              marcas={marcas}
              valor={marca}
              onCambio={setMarca}
              incluirTodas={false}
              placeholder="Elige una marca"
              ariaLabel="Marca de la plantilla"
              disabled={guardar.isPending}
              className="w-full"
            />
          </div>

          {/* Diseño de capas (control total): editor visual + vista real del servidor. */}
          {marca && !cargando && (
            <div className="rounded-md border border-border p-3">
              <Label className="text-sm font-medium">Diseño de capas (control total)</Label>
              <div className="mt-2">
                <EditorPlantillaSpec marca={marca} />
              </div>
            </div>
          )}

          {cargando ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Cargando plantilla…
            </div>
          ) : (
            <>
              {/* Logo */}
              <div className="space-y-2 rounded-md border border-border p-3">
                <Label className="text-sm font-medium">Logo</Label>
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/png"
                  onChange={onArchivoLogo}
                  className="hidden"
                  aria-label="Subir logo de la marca"
                />
                <div className="flex items-center gap-3">
                  {previewLogo ? (
                    <img
                      src={previewLogo}
                      alt="Logo de la marca"
                      className="h-16 w-16 rounded border border-border bg-muted/30 object-contain p-1"
                    />
                  ) : (
                    <div className="flex h-16 w-16 items-center justify-center rounded border border-dashed border-border text-center text-[10px] text-muted-foreground">
                      Sin logo
                    </div>
                  )}
                  <div className="flex flex-col gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => logoInputRef.current?.click()}
                      disabled={bloqueado}
                    >
                      {subirLogo.isPending ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : (
                        <Upload className="mr-1 h-4 w-4" />
                      )}
                      Subir logo
                    </Button>
                    {datos.logo && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground"
                        onClick={() => setDatos((d) => ({ ...d, logo: "", logo_url: "" }))}
                        disabled={bloqueado}
                      >
                        <X className="mr-1 h-4 w-4" />
                        Quitar logo
                      </Button>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  El logo debe ser PNG con transparencia. Si no hay logo, se usa el texto de
                  respaldo (wordmark).
                </p>
              </div>

              {/* Posición del logo */}
              <div className="space-y-1.5">
                <Label htmlFor="plantilla-posicion" className="text-xs">
                  Posición del logo
                </Label>
                <Select
                  value={datos.logo_posicion}
                  onValueChange={(v) =>
                    setDatos((d) => ({ ...d, logo_posicion: v as PosicionLogo }))
                  }
                >
                  <SelectTrigger id="plantilla-posicion" aria-label="Posición del logo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {POSICIONES.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.etiqueta}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Colores */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <CampoColor
                  id="plantilla-rojo"
                  etiqueta="Rojo"
                  valor={datos.rojo}
                  onCambio={(v) => setDatos((d) => ({ ...d, rojo: v }))}
                  disabled={bloqueado}
                />
                <CampoColor
                  id="plantilla-tinta"
                  etiqueta="Tinta"
                  valor={datos.tinta}
                  onCambio={(v) => setDatos((d) => ({ ...d, tinta: v }))}
                  disabled={bloqueado}
                />
                <CampoColor
                  id="plantilla-blanco"
                  etiqueta="Blanco"
                  valor={datos.blanco}
                  onCambio={(v) => setDatos((d) => ({ ...d, blanco: v }))}
                  disabled={bloqueado}
                />
              </div>

              {/* Etiqueta por defecto */}
              <div className="space-y-1.5">
                <Label htmlFor="plantilla-etiqueta" className="text-xs">
                  Etiqueta/pleca por defecto
                </Label>
                <Input
                  id="plantilla-etiqueta"
                  value={datos.etiqueta_default}
                  onChange={(e) => setDatos((d) => ({ ...d, etiqueta_default: e.target.value }))}
                  placeholder="p. ej. ÚLTIMA HORA"
                  disabled={bloqueado}
                />
              </div>

              {/* Wordmark de respaldo */}
              <div className="space-y-1.5">
                <Label htmlFor="plantilla-wordmark" className="text-xs">
                  Wordmark (texto de respaldo)
                </Label>
                <Input
                  id="plantilla-wordmark"
                  value={datos.wordmark}
                  onChange={(e) => setDatos((d) => ({ ...d, wordmark: e.target.value }))}
                  placeholder="Texto si no hay logo"
                  disabled={bloqueado}
                />
              </div>

              {/* Toggles del titular */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="plantilla-mayusculas"
                    checked={datos.titular_mayusculas}
                    onCheckedChange={(v) => setDatos((d) => ({ ...d, titular_mayusculas: v }))}
                    disabled={bloqueado}
                  />
                  <Label htmlFor="plantilla-mayusculas" className="text-sm font-normal">
                    Titular en mayúsculas
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="plantilla-condensada"
                    checked={datos.titular_condensada}
                    onCheckedChange={(v) => setDatos((d) => ({ ...d, titular_condensada: v }))}
                    disabled={bloqueado}
                  />
                  <Label htmlFor="plantilla-condensada" className="text-sm font-normal">
                    Tipografía condensada
                  </Label>
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={guardar.isPending}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() => guardar.mutate()}
            disabled={bloqueado || marca.length === 0}
          >
            {guardar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
