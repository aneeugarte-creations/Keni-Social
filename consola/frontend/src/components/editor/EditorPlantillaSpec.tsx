/**
 * Editor visual de la PLANTILLA por marca y formato: lienzo grande + panel contextual.
 *
 * Seleccionas una capa (fondo, foto, logo, textos) y a la derecha aparecen SOLO sus propiedades.
 * La "vista real" la renderiza el SERVIDOR con el mismo motor que produce las placas (lo que
 * diseñas = lo que sale). Un único Guardar persiste el spec; a partir de ahí toda composición de
 * la marca (auto-generación al crear copy + integrar foto) usa este diseño.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlignHorizontalJustifyCenter,
  AlignVerticalJustifyCenter,
  ImageUp,
  Loader2,
  Maximize,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LienzoEditable } from "@/components/editor/LienzoEditable";
import { api, ApiError, urlMedia } from "@/lib/api";
import {
  ALINEACIONES,
  CATALOGO_FUENTES,
  centrar,
  type CapaTexto,
  familiaCatalogo,
  type FormatoId,
  FORMATOS,
  idsTextoDisponibles,
  nuevaCapaTexto,
  type PlantillaSpec,
  rotuloTexto,
} from "@/lib/specPlantilla";

function msg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Ocurrió un problema inesperado.";
}

function Num({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Input type="number" value={Math.round(value)} onChange={(e) => onChange(Number(e.target.value) || 0)} className="h-8" />
    </label>
  );
}

function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5">
        <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="h-8 w-9 shrink-0 cursor-pointer rounded border border-border bg-transparent" aria-label={label} />
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="h-8" />
      </span>
    </label>
  );
}

const CLAVES_FIJAS = [
  { clave: "fondo", etiqueta: "Fondo" },
  { clave: "foto", etiqueta: "Foto" },
  { clave: "logo", etiqueta: "Logo" },
];

export function EditorPlantillaSpec({
  marca,
  onGuardado,
}: {
  marca: string;
  /** Se invoca tras guardar el spec con éxito (p. ej. para cerrar el diálogo contenedor). */
  onGuardado?: () => void;
}) {
  const queryClient = useQueryClient();
  const [spec, setSpec] = React.useState<PlantillaSpec | null>(null);
  const [formato, setFormato] = React.useState<FormatoId>("feed");
  const [previewUrl, setPreviewUrl] = React.useState("");
  const [seleccion, setSeleccion] = React.useState("foto");
  const logoInputRef = React.useRef<HTMLInputElement>(null);
  const fondoInputRef = React.useRef<HTMLInputElement>(null);
  const debounceRef = React.useRef<number | undefined>(undefined);

  const specQuery = useQuery({
    queryKey: ["plantilla-spec", marca],
    queryFn: ({ signal }) => api.specPlantilla(marca, signal),
    enabled: marca.length > 0,
  });
  React.useEffect(() => {
    if (specQuery.data?.spec) setSpec(specQuery.data.spec);
  }, [specQuery.data]);

  const fmt = spec?.formatos[formato];

  const preview = useMutation({
    mutationFn: () => {
      if (!spec) throw new Error("Sin spec");
      return api.previewPlantilla(marca, spec, formato, "Titular de ejemplo");
    },
    onSuccess: (d) => setPreviewUrl(urlMedia(d.url)),
    onError: (e) => toast.error(msg(e)),
  });
  React.useEffect(() => {
    if (!spec) return;
    window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => preview.mutate(), 600);
    return () => window.clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, formato]);

  const guardar = useMutation({
    mutationFn: () => {
      if (!spec) throw new Error("Sin spec");
      return api.guardarSpecPlantilla(marca, spec);
    },
    onSuccess: (d) => {
      setSpec(d.spec);
      void queryClient.invalidateQueries({ queryKey: ["plantilla-spec", marca] });
      toast.success("Plantilla guardada");
      onGuardado?.();
    },
    onError: (e) => toast.error(msg(e)),
  });

  const subirLogo = useMutation({
    mutationFn: (a: File) => api.subirMedia(a),
    onSuccess: (d) => mutarFmt((f) => { f.logo = { ...f.logo, tipo: "imagen", media_id: d.id }; }),
    onError: (e) => toast.error(msg(e)),
  });
  const subirFondo = useMutation({
    mutationFn: (a: File) => api.subirMedia(a),
    onSuccess: (d) => mutarFmt((f) => { f.fondo = { tipo: "imagen", imagen: { media_id: d.id, ajuste: "cover" } }; }),
    onError: (e) => toast.error(msg(e)),
  });

  // --- mutación inmutable del spec / del formato activo / de una capa de texto ---
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
  function mutarTextoClave(clave: string, fn: (t: CapaTexto) => void) {
    const id = clave.replace("texto-", "");
    mutarFmt((f) => {
      const t = f.textos.find((x) => x.id === id);
      if (t) fn(t);
    });
  }

  function centrarSel(eje: "h" | "v") {
    if (!fmt) return;
    if (seleccion === "foto") {
      const c = centrar(fmt.foto_slot, fmt.lienzo, eje);
      mutarFmt((f) => { f.foto_slot.x = c.x; f.foto_slot.y = c.y; });
    } else if (seleccion === "logo") {
      const c = centrar(fmt.logo, fmt.lienzo, eje);
      mutarFmt((f) => { f.logo.x = c.x; f.logo.y = c.y; });
    } else if (seleccion.startsWith("texto-")) {
      mutarTextoClave(seleccion, (t) => {
        const c = centrar({ x: t.x, y: t.y, w: t.w, h: Math.round(t.tamano * 1.2) }, fmt.lienzo, eje);
        t.x = c.x; t.y = c.y;
      });
    }
  }

  function copiarLogoAFormatos() {
    mutarSpec((s) => {
      const src = s.formatos[formato].logo;
      (Object.keys(s.formatos) as FormatoId[]).forEach((k) => {
        if (k !== formato) {
          s.formatos[k].logo.tipo = src.tipo;
          s.formatos[k].logo.media_id = src.media_id;
          s.formatos[k].logo.wordmark = { ...src.wordmark };
        }
      });
    });
    toast.success("Logo copiado a los otros formatos");
  }

  if (specQuery.isLoading || !spec || !fmt) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando diseño…
      </div>
    );
  }

  const textoSel = seleccion.startsWith("texto-")
    ? fmt.textos.find((t) => t.id === seleccion.replace("texto-", ""))
    : undefined;
  const disponibles = idsTextoDisponibles(fmt);

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs value={formato} onValueChange={(v) => setFormato(v as FormatoId)}>
          <TabsList>
            {FORMATOS.map((f) => (
              <TabsTrigger key={f.id} value={f.id}>{f.etiqueta}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={guardar.isPending}>
          {guardar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar plantilla
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[auto_minmax(0,1fr)]">
        {/* Lienzo grande */}
        <div className="space-y-1.5">
          <LienzoEditable
            fmt={fmt}
            previewUrl={previewUrl}
            seleccion={seleccion}
            onSeleccion={setSeleccion}
            onFoto={(x, y, w, h) => mutarFmt((f) => { f.foto_slot = { ...f.foto_slot, x, y, w, h }; })}
            onLogo={(x, y, w, h) => mutarFmt((f) => { f.logo = { ...f.logo, x, y, w, h }; })}
            onTexto={(clave, x, y, w) => mutarTextoClave(clave, (t) => { t.x = x; t.y = y; t.w = w; })}
          />
          <p className="text-[11px] text-muted-foreground">
            Arrastra las capas (imantan a centros y guías). El recuadro punteado es la zona segura.
            {preview.isPending && <span className="text-sky-500"> · actualizando…</span>}
          </p>
        </div>

        {/* Panel contextual */}
        <div className="space-y-3">
          {/* Lista de capas */}
          <div className="flex flex-wrap gap-1.5">
            {CLAVES_FIJAS.map((c) => (
              <CapaChip key={c.clave} activa={seleccion === c.clave} onClick={() => setSeleccion(c.clave)}>
                {c.etiqueta}
              </CapaChip>
            ))}
            {fmt.textos.map((t) => (
              <CapaChip key={t.id} activa={seleccion === `texto-${t.id}`} onClick={() => setSeleccion(`texto-${t.id}`)}>
                {rotuloTexto(t.id)}
              </CapaChip>
            ))}
            {disponibles.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => { mutarFmt((f) => f.textos.push(nuevaCapaTexto(id, f.lienzo))); setSeleccion(`texto-${id}`); }}
                className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted-foreground hover:border-sky-400 hover:text-foreground"
              >
                <Plus className="h-3 w-3" /> {rotuloTexto(id)}
              </button>
            ))}
          </div>

          {/* Botones de centrado (capa seleccionada) */}
          {seleccion && seleccion !== "fondo" && (
            <div className="flex gap-1.5">
              <Button type="button" variant="outline" size="sm" onClick={() => centrarSel("h")}>
                <AlignHorizontalJustifyCenter className="h-4 w-4" /> Centrar H
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => centrarSel("v")}>
                <AlignVerticalJustifyCenter className="h-4 w-4" /> Centrar V
              </Button>
            </div>
          )}

          {/* === Propiedades de la capa seleccionada === */}
          <fieldset className="space-y-2 rounded-md border border-border p-3">
            <legend className="px-1 text-xs font-medium">
              {seleccion === "fondo" ? "Fondo"
                : seleccion === "foto" ? "Hueco de foto"
                : seleccion === "logo" ? "Logo"
                : textoSel ? rotuloTexto(textoSel.id) : "Capa"}
            </legend>

            {/* FONDO */}
            {seleccion === "fondo" && (
              <>
                <Select value={fmt.fondo.tipo} onValueChange={(v) => mutarFmt((f) => {
                  if (v === "color") f.fondo = { tipo: "color", color: f.fondo.color || "#111315" };
                  else if (v === "degradado") f.fondo = { tipo: "degradado", degradado: f.fondo.degradado || { desde: "#000000", hasta: "#111315", angulo: 180 } };
                  else f.fondo = { tipo: "imagen", imagen: f.fondo.imagen || { media_id: "", ajuste: "cover" } };
                })}>
                  <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="color">Color sólido</SelectItem>
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
                    <input ref={fondoInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => { const a = e.target.files?.[0]; if (a) subirFondo.mutate(a); e.target.value = ""; }} />
                    <Button type="button" variant="outline" size="sm" onClick={() => fondoInputRef.current?.click()}>
                      <ImageUp className="h-4 w-4" /> Subir fondo
                    </Button>
                    <span className="text-xs text-muted-foreground">{fmt.fondo.imagen?.media_id ? "imagen cargada" : "sin imagen"}</span>
                  </div>
                )}
              </>
            )}

            {/* FOTO */}
            {seleccion === "foto" && (
              <>
                <div className="grid grid-cols-4 gap-2">
                  <Num label="X" value={fmt.foto_slot.x} onChange={(v) => mutarFmt((f) => { f.foto_slot.x = v; })} />
                  <Num label="Y" value={fmt.foto_slot.y} onChange={(v) => mutarFmt((f) => { f.foto_slot.y = v; })} />
                  <Num label="Ancho" value={fmt.foto_slot.w} onChange={(v) => mutarFmt((f) => { f.foto_slot.w = v; })} />
                  <Num label="Alto" value={fmt.foto_slot.h} onChange={(v) => mutarFmt((f) => { f.foto_slot.h = v; })} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={fmt.foto_slot.ajuste} onValueChange={(v) => mutarFmt((f) => { f.foto_slot.ajuste = v as "cover" | "contain"; })}>
                    <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cover">Cubrir (recorta)</SelectItem>
                      <SelectItem value="contain">Contener (cabe entera)</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button type="button" variant="outline" size="sm" onClick={() => mutarFmt((f) => { f.foto_slot = { ...f.foto_slot, x: 0, y: 0, w: f.lienzo.w, h: f.lienzo.h }; })}>
                    <Maximize className="h-4 w-4" /> Ocupar todo
                  </Button>
                </div>
              </>
            )}

            {/* LOGO */}
            {seleccion === "logo" && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={fmt.logo.tipo} onValueChange={(v) => mutarFmt((f) => { f.logo.tipo = v as "imagen" | "wordmark"; })}>
                    <SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="imagen">Imagen (PNG)</SelectItem>
                      <SelectItem value="wordmark">Texto</SelectItem>
                    </SelectContent>
                  </Select>
                  {fmt.logo.tipo === "imagen" && (
                    <>
                      <input ref={logoInputRef} type="file" accept="image/png,image/*" className="hidden" onChange={(e) => { const a = e.target.files?.[0]; if (a) subirLogo.mutate(a); e.target.value = ""; }} />
                      <Button type="button" variant="outline" size="sm" onClick={() => logoInputRef.current?.click()}>
                        <ImageUp className="h-4 w-4" /> {fmt.logo.media_id ? "Cambiar logo" : "Subir logo"}
                      </Button>
                    </>
                  )}
                </div>
                {fmt.logo.tipo === "wordmark" && (
                  <div className="grid grid-cols-2 gap-2">
                    <label className="col-span-2 flex flex-col gap-0.5 text-xs">
                      <span className="text-muted-foreground">Texto del logo</span>
                      <Input value={fmt.logo.wordmark.texto} onChange={(e) => mutarFmt((f) => { f.logo.wordmark.texto = e.target.value; })} className="h-8" placeholder="p. ej. UnoTV" />
                    </label>
                    <Color label="Texto" value={fmt.logo.wordmark.color} onChange={(v) => mutarFmt((f) => { f.logo.wordmark.color = v; })} />
                    <Color label="Fondo" value={fmt.logo.wordmark.fondo} onChange={(v) => mutarFmt((f) => { f.logo.wordmark.fondo = v; })} />
                  </div>
                )}
                <div className="grid grid-cols-4 gap-2">
                  <Num label="X" value={fmt.logo.x} onChange={(v) => mutarFmt((f) => { f.logo.x = v; })} />
                  <Num label="Y" value={fmt.logo.y} onChange={(v) => mutarFmt((f) => { f.logo.y = v; })} />
                  <Num label="Ancho" value={fmt.logo.w} onChange={(v) => mutarFmt((f) => { f.logo.w = v; })} />
                  <Num label="Alto" value={fmt.logo.h} onChange={(v) => mutarFmt((f) => { f.logo.h = v; })} />
                </div>
                <Button type="button" variant="ghost" size="sm" className="text-xs text-muted-foreground" onClick={copiarLogoAFormatos}>
                  Copiar este logo a los otros formatos
                </Button>
              </>
            )}

            {/* TEXTO */}
            {textoSel && (
              <>
                {textoSel.binding ? (
                  <p className="rounded bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground">
                    Texto automático: {textoSel.binding === "copy_in" ? "el copy-in de la pieza" : "la etiqueta de la marca"}.
                  </p>
                ) : (
                  <label className="flex flex-col gap-0.5 text-xs">
                    <span className="text-muted-foreground">Texto fijo</span>
                    <Input value={textoSel.texto} onChange={(e) => mutarTextoClave(seleccion, (t) => { t.texto = e.target.value; })} className="h-8" />
                  </label>
                )}
                <div className="grid grid-cols-3 gap-2">
                  <Num label="Tamaño" value={textoSel.tamano} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.tamano = v; })} />
                  <Num label="Peso" value={textoSel.peso} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.peso = v; })} />
                  <Color label="Color" value={textoSel.color} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.color = v; })} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={familiaCatalogo(textoSel.familia)} onValueChange={(v) => mutarTextoClave(seleccion, (t) => { t.familia = v; })}>
                    <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CATALOGO_FUENTES.map((f) => (
                        <SelectItem key={f} value={f} style={{ fontFamily: f }}>{f}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={textoSel.alineacion} onValueChange={(v) => mutarTextoClave(seleccion, (t) => { t.alineacion = v as CapaTexto["alineacion"]; })}>
                    <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {ALINEACIONES.map((a) => (
                        <SelectItem key={a.id} value={a.id}>{a.etiqueta}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <label className="flex items-center gap-1.5 text-xs">
                    <input type="checkbox" checked={textoSel.mayusculas} onChange={(e) => mutarTextoClave(seleccion, (t) => { t.mayusculas = e.target.checked; })} /> Mayúsculas
                  </label>
                  <label className="flex items-center gap-1.5 text-xs">
                    <input type="checkbox" checked={!!textoSel.chip} onChange={(e) => mutarTextoClave(seleccion, (t) => { t.chip = e.target.checked ? { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } : null; })} /> Fondo de color
                  </label>
                  {textoSel.chip && (
                    <Color label="Fondo" value={textoSel.chip.color} onChange={(v) => mutarTextoClave(seleccion, (t) => { if (t.chip) t.chip.color = v; })} />
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <Num label="X" value={textoSel.x} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.x = v; })} />
                  <Num label="Y" value={textoSel.y} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.y = v; })} />
                  <Num label="Ancho" value={textoSel.w} onChange={(v) => mutarTextoClave(seleccion, (t) => { t.w = v; })} />
                </div>
                {textoSel.id !== "titular" && (
                  <Button type="button" variant="ghost" size="sm" className="text-xs text-destructive"
                    onClick={() => { const id = textoSel.id; mutarFmt((f) => { f.textos = f.textos.filter((t) => t.id !== id); }); setSeleccion("foto"); }}>
                    <Trash2 className="h-3.5 w-3.5" /> Quitar {rotuloTexto(textoSel.id).toLowerCase()}
                  </Button>
                )}
              </>
            )}
          </fieldset>
        </div>
      </div>
    </div>
  );
}

function CapaChip({ activa, onClick, children }: { activa: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-full border px-2.5 py-1 text-xs transition-colors " +
        (activa ? "border-sky-400 bg-sky-400/10 text-foreground" : "border-border text-muted-foreground hover:border-sky-300 hover:text-foreground")
      }
    >
      {children}
    </button>
  );
}
