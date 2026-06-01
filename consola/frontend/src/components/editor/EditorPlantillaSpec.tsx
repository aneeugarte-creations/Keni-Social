/**
 * Editor visual de la PLANTILLA por marca y por formato (control total del diseño).
 *
 * El usuario ajusta cada capa (fondo, hueco de foto, logo, textos) por formato; la "vista real"
 * la renderiza el SERVIDOR con el mismo motor que produce las placas (paridad pixel: lo que se
 * diseña = lo que sale). Guardar persiste el SPEC; a partir de ahí toda composición de esa marca
 * (auto-generación al crear copy + integrar foto) usa este diseño.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Loader2, RefreshCw, Save } from "lucide-react";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, urlMedia } from "@/lib/api";
import {
  type CapaTexto,
  type FormatoId,
  FORMATOS,
  type PlantillaSpec,
} from "@/lib/specPlantilla";

function msg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Ocurrió un problema inesperado.";
}

/** Campo numérico compacto (px). */
function Num({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Input
        type="number"
        value={Math.round(value)}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="h-8"
      />
    </label>
  );
}

/** Campo de color (picker + hex). */
function Color({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-9 shrink-0 cursor-pointer rounded border border-border bg-transparent"
          aria-label={label}
        />
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="h-8" />
      </span>
    </label>
  );
}

export function EditorPlantillaSpec({ marca }: { marca: string }) {
  const queryClient = useQueryClient();
  const [spec, setSpec] = React.useState<PlantillaSpec | null>(null);
  const [formato, setFormato] = React.useState<FormatoId>("feed");
  const [previewUrl, setPreviewUrl] = React.useState("");
  const logoInputRef = React.useRef<HTMLInputElement>(null);
  const fondoInputRef = React.useRef<HTMLInputElement>(null);

  const specQuery = useQuery({
    queryKey: ["plantilla-spec", marca],
    queryFn: ({ signal }) => api.specPlantilla(marca, signal),
    enabled: marca.length > 0,
  });
  React.useEffect(() => {
    if (specQuery.data?.spec) setSpec(specQuery.data.spec);
  }, [specQuery.data]);

  const fmt = spec?.formatos[formato];

  // Vista real: el servidor renderiza el spec en edición (placeholder + titular de muestra).
  const preview = useMutation({
    mutationFn: () => {
      if (!spec) throw new Error("Sin spec");
      return api.previewPlantilla(marca, spec, formato, "Titular de ejemplo");
    },
    onSuccess: (d) => setPreviewUrl(urlMedia(d.url)),
    onError: (e) => toast.error(msg(e)),
  });
  // Refresca la vista al cargar y al cambiar de formato.
  React.useEffect(() => {
    if (spec) preview.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec !== null, formato]);

  const guardar = useMutation({
    mutationFn: () => {
      if (!spec) throw new Error("Sin spec");
      return api.guardarSpecPlantilla(marca, spec);
    },
    onSuccess: (d) => {
      setSpec(d.spec);
      void queryClient.invalidateQueries({ queryKey: ["plantilla-spec", marca] });
      toast.success("Diseño de plantilla guardado");
    },
    onError: (e) => toast.error(msg(e)),
  });

  const subirLogo = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) =>
      mutarFmt((f) => {
        f.logo = { ...f.logo, tipo: "imagen", media_id: d.id };
      }),
    onError: (e) => toast.error(msg(e)),
  });
  const subirFondo = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) =>
      mutarFmt((f) => {
        f.fondo = { tipo: "imagen", imagen: { media_id: d.id, ajuste: "cover" } };
      }),
    onError: (e) => toast.error(msg(e)),
  });

  // Helpers de mutación inmutable del formato activo.
  function mutarSpec(fn: (s: PlantillaSpec) => void) {
    setSpec((prev) => {
      if (!prev) return prev;
      const copia: PlantillaSpec = JSON.parse(JSON.stringify(prev));
      fn(copia);
      return copia;
    });
  }
  function mutarFmt(fn: (f: PlantillaSpec["formatos"][FormatoId]) => void) {
    mutarSpec((s) => fn(s.formatos[formato]));
  }
  function mutarTexto(i: number, fn: (t: CapaTexto) => void) {
    mutarFmt((f) => fn(f.textos[i]));
  }

  if (specQuery.isLoading || !spec || !fmt) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando diseño…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Tabs value={formato} onValueChange={(v) => setFormato(v as FormatoId)}>
          <TabsList>
            {FORMATOS.map((f) => (
              <TabsTrigger key={f.id} value={f.id}>
                {f.etiqueta}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => preview.mutate()}
            disabled={preview.isPending}
          >
            {preview.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Vista real
          </Button>
          <Button type="button" size="sm" onClick={() => guardar.mutate()} disabled={guardar.isPending}>
            {guardar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Guardar diseño
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[minmax(0,260px)_1fr]">
        {/* Vista real (servidor) */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Vista real (servidor)</Label>
          <div className="overflow-hidden rounded-md border border-border bg-muted/30">
            {previewUrl ? (
              <img src={previewUrl} alt="Vista de la plantilla" className="w-full" />
            ) : (
              <div className="flex aspect-[4/5] items-center justify-center text-xs text-muted-foreground">
                Pulsa «Vista real»
              </div>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Render del servidor: idéntico a la placa final. La foto va vacía (placeholder).
          </p>
        </div>

        {/* Paneles de propiedades */}
        <div className="space-y-4">
          {/* FONDO */}
          <fieldset className="space-y-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium">Fondo</legend>
            <Select value={fmt.fondo.tipo} onValueChange={(v) =>
              mutarFmt((f) => {
                if (v === "color") f.fondo = { tipo: "color", color: f.fondo.color || "#111315" };
                else if (v === "degradado")
                  f.fondo = { tipo: "degradado", degradado: f.fondo.degradado || { desde: "#000000", hasta: "#111315", angulo: 180 } };
                else f.fondo = { tipo: "imagen", imagen: f.fondo.imagen || { media_id: "", ajuste: "cover" } };
              })
            }>
              <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="color">Color</SelectItem>
                <SelectItem value="degradado">Degradado</SelectItem>
                <SelectItem value="imagen">Imagen</SelectItem>
              </SelectContent>
            </Select>
            {fmt.fondo.tipo === "color" && (
              <Color label="Color" value={fmt.fondo.color || "#111315"} onChange={(v) => mutarFmt((f) => { f.fondo.color = v; })} />
            )}
            {fmt.fondo.tipo === "degradado" && fmt.fondo.degradado && (
              <div className="grid grid-cols-2 gap-2">
                <Color label="Desde" value={fmt.fondo.degradado.desde} onChange={(v) => mutarFmt((f) => { f.fondo.degradado!.desde = v; })} />
                <Color label="Hasta" value={fmt.fondo.degradado.hasta} onChange={(v) => mutarFmt((f) => { f.fondo.degradado!.hasta = v; })} />
              </div>
            )}
            {fmt.fondo.tipo === "imagen" && (
              <div className="flex items-center gap-2">
                <input ref={fondoInputRef} type="file" accept="image/*" className="hidden"
                  onChange={(e) => { const a = e.target.files?.[0]; if (a) subirFondo.mutate(a); e.target.value = ""; }} />
                <Button type="button" variant="outline" size="sm" onClick={() => fondoInputRef.current?.click()}>
                  <ImageUp className="h-4 w-4" /> Subir fondo
                </Button>
                <span className="text-xs text-muted-foreground">
                  {fmt.fondo.imagen?.media_id ? "imagen cargada" : "sin imagen"}
                </span>
              </div>
            )}
          </fieldset>

          {/* HUECO DE FOTO */}
          <fieldset className="space-y-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium">Hueco de foto</legend>
            <div className="grid grid-cols-4 gap-2">
              <Num label="X" value={fmt.foto_slot.x} onChange={(v) => mutarFmt((f) => { f.foto_slot.x = v; })} />
              <Num label="Y" value={fmt.foto_slot.y} onChange={(v) => mutarFmt((f) => { f.foto_slot.y = v; })} />
              <Num label="Ancho" value={fmt.foto_slot.w} onChange={(v) => mutarFmt((f) => { f.foto_slot.w = v; })} />
              <Num label="Alto" value={fmt.foto_slot.h} onChange={(v) => mutarFmt((f) => { f.foto_slot.h = v; })} />
            </div>
            <Select value={fmt.foto_slot.ajuste} onValueChange={(v) => mutarFmt((f) => { f.foto_slot.ajuste = v as "cover" | "contain"; })}>
              <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cover">Cubrir (cover)</SelectItem>
                <SelectItem value="contain">Contener (contain)</SelectItem>
              </SelectContent>
            </Select>
          </fieldset>

          {/* LOGO */}
          <fieldset className="space-y-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium">Logo</legend>
            <div className="flex items-center gap-2">
              <Select value={fmt.logo.tipo} onValueChange={(v) => mutarFmt((f) => { f.logo.tipo = v as "imagen" | "wordmark"; })}>
                <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="imagen">Imagen (logo)</SelectItem>
                  <SelectItem value="wordmark">Wordmark (texto)</SelectItem>
                </SelectContent>
              </Select>
              <input ref={logoInputRef} type="file" accept="image/*" className="hidden"
                onChange={(e) => { const a = e.target.files?.[0]; if (a) subirLogo.mutate(a); e.target.value = ""; }} />
              <Button type="button" variant="outline" size="sm" onClick={() => logoInputRef.current?.click()}>
                <ImageUp className="h-4 w-4" /> Subir logo
              </Button>
            </div>
            <div className="grid grid-cols-4 gap-2">
              <Num label="X" value={fmt.logo.x} onChange={(v) => mutarFmt((f) => { f.logo.x = v; })} />
              <Num label="Y" value={fmt.logo.y} onChange={(v) => mutarFmt((f) => { f.logo.y = v; })} />
              <Num label="Ancho" value={fmt.logo.w} onChange={(v) => mutarFmt((f) => { f.logo.w = v; })} />
              <Num label="Alto" value={fmt.logo.h} onChange={(v) => mutarFmt((f) => { f.logo.h = v; })} />
            </div>
            {fmt.logo.tipo === "wordmark" && (
              <div className="grid grid-cols-2 gap-2">
                <label className="col-span-2 flex flex-col gap-0.5 text-xs">
                  <span className="text-muted-foreground">Texto</span>
                  <Input value={fmt.logo.wordmark.texto} onChange={(e) => mutarFmt((f) => { f.logo.wordmark.texto = e.target.value; })} className="h-8" />
                </label>
                <Color label="Texto" value={fmt.logo.wordmark.color} onChange={(v) => mutarFmt((f) => { f.logo.wordmark.color = v; })} />
                <Color label="Fondo" value={fmt.logo.wordmark.fondo} onChange={(v) => mutarFmt((f) => { f.logo.wordmark.fondo = v; })} />
              </div>
            )}
          </fieldset>

          {/* TEXTOS */}
          {fmt.textos.map((t, i) => (
            <fieldset key={t.id} className="space-y-2 rounded-md border border-border p-3">
              <legend className="px-1 text-xs font-medium capitalize">{t.id}</legend>
              <div className="grid grid-cols-3 gap-2">
                <Num label="X" value={t.x} onChange={(v) => mutarTexto(i, (x) => { x.x = v; })} />
                <Num label="Y" value={t.y} onChange={(v) => mutarTexto(i, (x) => { x.y = v; })} />
                <Num label="Ancho" value={t.w} onChange={(v) => mutarTexto(i, (x) => { x.w = v; })} />
                <Num label="Tamaño" value={t.tamano} onChange={(v) => mutarTexto(i, (x) => { x.tamano = v; })} />
                <Num label="Peso" value={t.peso} onChange={(v) => mutarTexto(i, (x) => { x.peso = v; })} />
                <Color label="Color" value={t.color} onChange={(v) => mutarTexto(i, (x) => { x.color = v; })} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={t.familia} onValueChange={(v) => mutarTexto(i, (x) => { x.familia = v as "sans" | "condensada"; })}>
                  <SelectTrigger className="h-8 w-36"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sans">Sans</SelectItem>
                    <SelectItem value="condensada">Condensada</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={t.alineacion} onValueChange={(v) => mutarTexto(i, (x) => { x.alineacion = v as CapaTexto["alineacion"]; })}>
                  <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="izquierda">Izquierda</SelectItem>
                    <SelectItem value="centro">Centro</SelectItem>
                    <SelectItem value="derecha">Derecha</SelectItem>
                  </SelectContent>
                </Select>
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={t.mayusculas} onChange={(e) => mutarTexto(i, (x) => { x.mayusculas = e.target.checked; })} />
                  Mayúsculas
                </label>
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={!!t.chip} onChange={(e) =>
                    mutarTexto(i, (x) => { x.chip = e.target.checked ? { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } : null; })
                  } />
                  Chip (pleca)
                </label>
                {t.chip && (
                  <Color label="Chip" value={t.chip.color} onChange={(v) => mutarTexto(i, (x) => { if (x.chip) x.chip.color = v; })} />
                )}
              </div>
              {t.binding && (
                <p className="text-[11px] text-muted-foreground">
                  Texto automático: {t.binding === "copy_in" ? "el copy-in de la pieza" : "la pleca por defecto"}.
                </p>
              )}
            </fieldset>
          ))}
        </div>
      </div>
    </div>
  );
}
