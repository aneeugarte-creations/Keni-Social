// Paneles del editor: barra de herramientas, lista de capas (z-order) e inspector de propiedades.
// Todos operan sobre el store del documento via contexto.

import {
  Eye,
  EyeOff,
  GripVertical,
  Group as GroupIcon,
  Image as ImageIcon,
  Layers as LayersIcon,
  Lock,
  PanelBottom,
  Square,
  Trash2,
  Type,
  Ungroup,
  Unlock,
} from "lucide-react";
import { useState } from "react";

import { urlMedia } from "@/lib/api";

import { ColorControl } from "./ColorControl";

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto, Sombra } from "./documento";
import { CATALOGO_FUENTES, ETIQUETA_BINDING } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ETIQUETA_TIPO: Record<Capa["tipo"], string> = {
  imagen: "Imagen",
  texto: "Texto",
  logo: "Logo",
  marco: "Marco",
  overlay: "Degradado",
  grupo: "Grupo",
};

const ICONO_TIPO: Record<Capa["tipo"], typeof Type> = {
  imagen: ImageIcon,
  texto: Type,
  logo: ImageIcon,
  marco: Square,
  overlay: PanelBottom,
  grupo: GroupIcon,
};

// Nombre a mostrar: el `nombre` editable, o una etiqueta derivada del tipo/contenido.
function nombreCapa(c: Capa): string {
  if (c.nombre) return c.nombre;
  if (c.tipo === "texto") return (c as CapaTexto).texto?.slice(0, 22) || "Texto";
  return ETIQUETA_TIPO[c.tipo];
}

// Miniatura/icono de una capa para el panel.
function MiniCapa({ capa }: { capa: Capa }) {
  const Icono = ICONO_TIPO[capa.tipo];
  const obj = capa.tipo === "imagen" ? (capa as CapaImagen).objeto : capa.tipo === "logo" ? (capa as CapaLogo).media_id : "";
  if (obj) {
    return <img src={urlMedia(obj)} alt="" className="h-7 w-7 shrink-0 rounded border border-border object-cover" />;
  }
  const fondo =
    capa.tipo === "marco" ? (capa as CapaMarco).relleno ?? (capa as CapaMarco).borde?.color ?? "#888" :
    capa.tipo === "texto" ? (capa as CapaTexto).color : undefined;
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-border bg-muted" style={fondo ? { color: fondo } : undefined}>
      <Icono className="h-4 w-4" />
    </span>
  );
}

export function PanelCapas() {
  const store = useStoreEditor();
  const capas = useEditor((s) => s.documento.capas);
  const seleccion = useEditor((s) => s.seleccion);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);
  const [renombrando, setRenombrando] = useState<string | null>(null);

  // Más alta (z mayor) arriba en la lista.
  const ordenadas = [...capas].sort((a, b) => b.z - a.z);

  const capaSel = capas.find((c) => c.id === seleccion) ?? null;
  const multi = seleccionMulti.length > 1;

  // Suelta `arrastrando` justo antes de `destino` (reordena z según el nuevo orden visual).
  const soltar = (destinoId: string) => {
    if (!arrastrando || arrastrando === destinoId) return;
    const ids = ordenadas.map((c) => c.id).filter((id) => id !== arrastrando);
    const idx = ids.indexOf(destinoId);
    ids.splice(idx, 0, arrastrando);
    store.getState().ordenarZ(ids);
    setArrastrando(null);
    setSobre(null);
  };

  // Fila como FUNCIÓN (no componente): se llama inline para no crear un tipo de componente nuevo
  // en cada render (que remontaría las filas y perdería el foco al renombrar).
  const fila = (capa: Capa) => {
    // El HUECO DE FOTO (`es_foto`) es obligatorio: siempre bloqueado y no se puede borrar.
    const esFoto = capa.tipo === "imagen" && !!(capa as CapaImagen).es_foto;
    return (
    <div
      draggable
      onDragStart={() => setArrastrando(capa.id)}
      onDragEnd={() => { setArrastrando(null); setSobre(null); }}
      onDragOver={(e) => { if (arrastrando) { e.preventDefault(); setSobre(capa.id); } }}
      onDrop={() => soltar(capa.id)}
      onClick={(e) => {
        if (e.shiftKey || e.metaKey || e.ctrlKey) store.getState().alternar(capa.id);
        else store.getState().seleccionar(capa.id);
      }}
      className={`flex items-center gap-1.5 border-b border-border/50 py-1.5 pl-1 pr-2 text-sm ${
        seleccionMulti.includes(capa.id) ? "bg-accent" : "hover:bg-accent/50"
      } ${sobre === capa.id ? "border-t-2 border-t-primary" : ""} ${arrastrando === capa.id ? "opacity-40" : ""}`}
    >
      <GripVertical className="h-3.5 w-3.5 shrink-0 cursor-grab text-muted-foreground/60" />
      <MiniCapa capa={capa} />
      {renombrando === capa.id ? (
        <input
          autoFocus
          defaultValue={nombreCapa(capa)}
          onClick={(e) => e.stopPropagation()}
          onBlur={(e) => { store.getState().actualizar(capa.id, { nombre: e.target.value.trim() } as Partial<Capa>); setRenombrando(null); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") setRenombrando(null);
          }}
          className="min-w-0 flex-1 rounded border border-input bg-background px-1 py-0.5 text-sm"
        />
      ) : (
        <span
          className="flex min-w-0 flex-1 items-center gap-1 truncate"
          onDoubleClick={(e) => { e.stopPropagation(); setRenombrando(capa.id); }}
          title="Doble clic para renombrar"
        >
          <span className="truncate">{nombreCapa(capa)}</span>
          {capa.tipo === "texto" && (capa as CapaTexto).binding && (
            <span className="shrink-0 rounded bg-primary/15 px-1 text-[9px] font-semibold uppercase text-primary">
              {(capa as CapaTexto).binding === "copy_in" ? "copy" : "pleca"}
            </span>
          )}
          {esFoto && (
            <span
              className="shrink-0 rounded bg-emerald-500/15 px-1 text-[9px] font-semibold uppercase text-emerald-600 dark:text-emerald-400"
              title="Hueco de foto: aquí entra la foto de la pieza"
            >
              foto
            </span>
          )}
        </span>
      )}
      <button
        className="shrink-0 text-muted-foreground hover:text-foreground"
        onClick={(e) => { e.stopPropagation(); store.getState().actualizar(capa.id, { visible: !capa.visible } as Partial<Capa>); }}
        title={capa.visible ? "Ocultar" : "Mostrar"}
      >
        {capa.visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
      </button>
      <button
        className="shrink-0 text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        disabled={esFoto}
        onClick={(e) => { e.stopPropagation(); store.getState().actualizar(capa.id, { bloqueada: !capa.bloqueada } as Partial<Capa>); }}
        title={esFoto ? "Hueco de foto: siempre bloqueado" : capa.bloqueada ? "Desbloquear" : "Bloquear"}
      >
        {capa.bloqueada ? <Lock className="h-3.5 w-3.5" /> : <Unlock className="h-3.5 w-3.5" />}
      </button>
      <button
        className="shrink-0 text-muted-foreground hover:text-destructive disabled:cursor-not-allowed disabled:opacity-40"
        disabled={capa.bloqueada}
        onClick={(e) => { e.stopPropagation(); store.getState().quitar(capa.id); }}
        title={capa.bloqueada ? "Capa bloqueada (no se puede borrar)" : "Borrar capa"}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border px-3 py-2">
        <LayersIcon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Capas</span>
        <div className="ml-auto flex items-center gap-1">
          {multi && (
            <button
              onClick={() => store.getState().agrupar()}
              className="flex items-center gap-1 rounded border border-input px-1.5 py-0.5 text-xs hover:bg-accent"
              title="Agrupar selección"
            >
              <GroupIcon className="h-3.5 w-3.5" /> Agrupar
            </button>
          )}
          {!multi && capaSel?.tipo === "grupo" && (
            <button
              onClick={() => store.getState().desagrupar(capaSel.id)}
              className="flex items-center gap-1 rounded border border-input px-1.5 py-0.5 text-xs hover:bg-accent"
              title="Desagrupar"
            >
              <Ungroup className="h-3.5 w-3.5" /> Desagrupar
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {ordenadas.length === 0 && (
          <p className="p-3 text-sm text-muted-foreground">Sin capas. Añade texto, marco o imagen desde «Elementos».</p>
        )}
        {ordenadas.map((capa) => (
          <div key={capa.id}>
            {fila(capa)}
            {capa.tipo === "grupo" &&
              [...capa.capas].sort((a, b) => b.z - a.z).map((sub) => (
                // Hijas del grupo: solo lectura; al pulsar se selecciona el grupo (se edita
                // desagrupando). Indentadas para mostrar la jerarquía.
                <div
                  key={sub.id}
                  onClick={() => store.getState().seleccionar(capa.id)}
                  className="flex items-center gap-1.5 border-b border-border/40 py-1 pl-8 pr-2 text-xs text-muted-foreground hover:bg-accent/40"
                >
                  <MiniCapa capa={sub} />
                  <span className="min-w-0 flex-1 truncate">{nombreCapa(sub)}</span>
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{etiqueta}</span>
      {children}
    </label>
  );
}

function Num({
  valor,
  onChange,
  paso = 1,
}: {
  valor: number;
  onChange: (v: number) => void;
  paso?: number;
}) {
  return (
    <input
      type="number"
      step={paso}
      value={Math.round(valor * 100) / 100}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-20 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
    />
  );
}

// Campos comunes de una Sombra (dx, dy, desenfoque, opacidad, color). Reutilizado por texto,
// imagen y marco. `onChange` recibe la sombra completa actualizada.
function CamposSombra({ sombra, onChange }: { sombra: Sombra; onChange: (s: Sombra) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 pl-2">
      <Campo etiqueta="Desp. X"><Num valor={sombra.dx} onChange={(v) => onChange({ ...sombra, dx: v })} /></Campo>
      <Campo etiqueta="Desp. Y"><Num valor={sombra.dy} onChange={(v) => onChange({ ...sombra, dy: v })} /></Campo>
      <Campo etiqueta="Desenfoque">
        <input
          type="range"
          min={0}
          max={60}
          step={1}
          value={sombra.desenfoque ?? 0}
          onChange={(e) => onChange({ ...sombra, desenfoque: Number(e.target.value) })}
          className="w-20"
        />
      </Campo>
      <Campo etiqueta="Opacidad">
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={sombra.opacidad ?? 1}
          onChange={(e) => onChange({ ...sombra, opacidad: Number(e.target.value) })}
          className="w-20"
        />
      </Campo>
      <Campo etiqueta="Color">
        <ColorControl valor={sombra.color} onChange={(c) => onChange({ ...sombra, color: c })} />
      </Campo>
    </div>
  );
}

export function Inspector({ fuentesExtra = [] }: { fuentesExtra?: string[] }) {
  const store = useStoreEditor();
  const capa = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  const fondo = useEditor((s) => s.documento.fondo);
  const formato = useEditor((s) => s.documento.formato);
  // Familias disponibles: catálogo embebido + tipografías propias de la marca (sin duplicar).
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  // Sin capa seleccionada: editar el LIENZO (tamaño/aspect ratio) y el FONDO del documento.
  if (!capa) {
    const setFondo = (f: typeof fondo) => store.getState().setFondo(f);
    const setFmt = (f: typeof formato) => store.getState().setFormato(f);
    const PRESETS: { etiqueta: string; f: typeof formato }[] = [
      { etiqueta: "9:16", f: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 } },
      { etiqueta: "4:5", f: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 } },
      { etiqueta: "1:1", f: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 } },
      { etiqueta: "16:9", f: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 } },
    ];
    const activo = (f: typeof formato) => f.w === formato.w && f.h === formato.h;
    return (
      <div className="flex flex-col gap-3 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lienzo</div>
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.etiqueta}
              onClick={() => setFmt(p.f)}
              className={`rounded border px-2 py-1 text-xs ${activo(p.f) ? "border-primary bg-accent" : "border-input hover:bg-accent/50"}`}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="Ancho"><Num valor={formato.w} onChange={(v) => setFmt({ ...formato, w: Math.max(16, Math.round(v)) })} /></Campo>
          <Campo etiqueta="Alto"><Num valor={formato.h} onChange={(v) => setFmt({ ...formato, h: Math.max(16, Math.round(v)) })} /></Campo>
        </div>
        <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Fondo</div>
        <Campo etiqueta="Tipo">
          <select
            value={fondo.tipo}
            onChange={(e) => {
              const tipo = e.target.value as typeof fondo.tipo;
              if (tipo === "color") setFondo({ tipo: "color", color: fondo.color || "#111315" });
              else if (tipo === "degradado")
                setFondo({ tipo: "degradado", degradado: fondo.degradado || { desde: "#0a3d62", hasta: "#111315", angulo: 180 } });
              else if (tipo === "imagen")
                setFondo({ tipo: "imagen", imagen: fondo.imagen || { media_id: "", ajuste: "cover" } });
            }}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            <option value="color">Color</option>
            <option value="degradado">Degradado</option>
            <option value="imagen">Imagen</option>
          </select>
        </Campo>
        {fondo.tipo === "color" && (
          <Campo etiqueta="Color">
            <ColorControl valor={fondo.color || "#111315"} onChange={(c) => setFondo({ tipo: "color", color: c })} />
          </Campo>
        )}
        {fondo.tipo === "degradado" && fondo.degradado && (
          <>
            <Campo etiqueta="Desde">
              <ColorControl valor={fondo.degradado.desde} onChange={(c) => setFondo({ tipo: "degradado", degradado: { ...fondo.degradado!, desde: c } })} />
            </Campo>
            <Campo etiqueta="Hasta">
              <ColorControl valor={fondo.degradado.hasta} onChange={(c) => setFondo({ tipo: "degradado", degradado: { ...fondo.degradado!, hasta: c } })} />
            </Campo>
            <Campo etiqueta="Ángulo">
              <Num
                valor={fondo.degradado.angulo ?? 180}
                onChange={(v) => setFondo({ tipo: "degradado", degradado: { ...fondo.degradado!, angulo: v } })}
              />
            </Campo>
          </>
        )}
        {fondo.tipo === "imagen" && (
          <>
            <Campo etiqueta="Media ID">
              <input
                type="text"
                value={fondo.imagen?.media_id ?? ""}
                placeholder="id de media"
                onChange={(e) =>
                  setFondo({ tipo: "imagen", imagen: { media_id: e.target.value.trim(), ajuste: fondo.imagen?.ajuste ?? "cover" } })
                }
                className="w-40 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
              />
            </Campo>
            <Campo etiqueta="Ajuste">
              <select
                value={fondo.imagen?.ajuste ?? "cover"}
                onChange={(e) =>
                  setFondo({ tipo: "imagen", imagen: { media_id: fondo.imagen?.media_id ?? "", ajuste: e.target.value as "cover" | "contain" } })
                }
                className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
              >
                <option value="cover">Cubrir</option>
                <option value="contain">Contener</option>
              </select>
            </Campo>
          </>
        )}
      </div>
    );
  }

  const set = (cambios: Partial<Capa>) => store.getState().actualizar(capa.id, cambios);
  // Edita un filtro de imagen fusionando con el resto (neutros por defecto). Si el resultado es
  // neutro (brillo=contraste=saturacion=1, desenfoque=0) colapsa a `null`, igual que el back.
  const setFiltro = (k: "brillo" | "contraste" | "saturacion" | "desenfoque", v: number) => {
    const next = { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0, ...(capa as CapaImagen).filtros, [k]: v };
    const neutro = next.brillo === 1 && next.contraste === 1 && next.saturacion === 1 && next.desenfoque === 0;
    set({ filtros: neutro ? null : next } as Partial<Capa>);
  };
  const fil = (capa as CapaImagen).filtros ?? { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0 };

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {ETIQUETA_TIPO[capa.tipo]}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo etiqueta="X"><Num valor={capa.x} onChange={(v) => set({ x: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Y"><Num valor={capa.y} onChange={(v) => set({ y: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Ancho"><Num valor={capa.w} onChange={(v) => set({ w: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Alto"><Num valor={capa.h} onChange={(v) => set({ h: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Rotación"><Num valor={capa.rotacion} onChange={(v) => set({ rotacion: v } as Partial<Capa>)} /></Campo>
        <Campo etiqueta="Opacidad">
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={capa.opacidad}
            onChange={(e) => set({ opacidad: Number(e.target.value) } as Partial<Capa>)}
            className="w-20"
          />
        </Campo>
      </div>

      {capa.tipo === "texto" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Rol en la plantilla">
            <select
              value={(capa as CapaTexto).binding ?? "fijo"}
              onChange={(e) => set({ binding: e.target.value === "fijo" ? null : (e.target.value as CapaTexto["binding"]) } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="fijo">{ETIQUETA_BINDING.fijo}</option>
              <option value="copy_in">{ETIQUETA_BINDING.copy_in}</option>
              <option value="etiqueta_default">{ETIQUETA_BINDING.etiqueta_default}</option>
            </select>
          </Campo>
          <textarea
            value={(capa as CapaTexto).texto}
            onChange={(e) => set({ texto: e.target.value } as Partial<Capa>)}
            placeholder={(capa as CapaTexto).binding ? "Texto de ejemplo (se sustituye por el de la pieza)…" : "Texto…"}
            className="min-h-[60px] rounded border border-input bg-background p-1.5 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <Campo etiqueta="Tamaño"><Num valor={(capa as CapaTexto).tamano} onChange={(v) => set({ tamano: v } as Partial<Capa>)} /></Campo>
            <Campo etiqueta="Peso"><Num valor={(capa as CapaTexto).peso} paso={100} onChange={(v) => set({ peso: v } as Partial<Capa>)} /></Campo>
            <Campo etiqueta="Color">
              <ColorControl valor={(capa as CapaTexto).color} onChange={(c) => set({ color: c } as Partial<Capa>)} />
            </Campo>
            <Campo etiqueta="Mayúsculas">
              <input type="checkbox" checked={(capa as CapaTexto).mayusculas} onChange={(e) => set({ mayusculas: e.target.checked } as Partial<Capa>)} />
            </Campo>
          </div>
          <Campo etiqueta="Fuente">
            <select
              value={(capa as CapaTexto).familia}
              onChange={(e) => set({ familia: e.target.value } as Partial<Capa>)}
              className="max-w-[140px] rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              {familias.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
              {/* Si la capa usa una familia que ya no está en la lista, la mostramos igual. */}
              {!familias.includes((capa as CapaTexto).familia) && (
                <option value={(capa as CapaTexto).familia}>{(capa as CapaTexto).familia}</option>
              )}
            </select>
          </Campo>
          <Campo etiqueta="Alineación">
            <select
              value={(capa as CapaTexto).alineacion}
              onChange={(e) => set({ alineacion: e.target.value as CapaTexto["alineacion"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="izquierda">Izquierda</option>
              <option value="centro">Centro</option>
              <option value="derecha">Derecha</option>
              <option value="justificado">Justificado</option>
            </select>
          </Campo>
          <Campo etiqueta="Alineación vertical">
            <div className="flex gap-1">
              {(["arriba", "centro", "abajo"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => set({ valign: v } as Partial<Capa>)}
                  className={`rounded border px-1.5 py-0.5 text-xs capitalize ${
                    ((capa as CapaTexto).valign ?? "centro") === v
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </Campo>
          <div className="grid grid-cols-2 gap-2">
            <Campo etiqueta="Máx. líneas">
              <Num
                valor={(capa as CapaTexto).auto_ajuste?.max_lineas ?? 4}
                onChange={(v) =>
                  set({ auto_ajuste: { ...(capa as CapaTexto).auto_ajuste, max_lineas: Math.max(1, v) } } as Partial<Capa>)
                }
              />
            </Campo>
            <Campo etiqueta="Tamaño mínimo">
              <Num
                valor={(capa as CapaTexto).auto_ajuste?.tam_min ?? 40}
                onChange={(v) =>
                  set({ auto_ajuste: { ...(capa as CapaTexto).auto_ajuste, tam_min: Math.max(1, v) } } as Partial<Capa>)
                }
              />
            </Campo>
          </div>
          <Campo etiqueta="Interlineado">
            <Num valor={(capa as CapaTexto).interlineado} paso={0.05} onChange={(v) => set({ interlineado: v } as Partial<Capa>)} />
          </Campo>
          <Campo etiqueta="Interletra">
            <Num valor={(capa as CapaTexto).interletra ?? 0} paso={0.5} onChange={(v) => set({ interletra: v } as Partial<Capa>)} />
          </Campo>
          <Campo etiqueta="Contorno">
            <input
              type="checkbox"
              checked={!!(capa as CapaTexto).contorno}
              onChange={(e) => set({ contorno: e.target.checked ? { color: "#000000", grosor: 6 } : null } as Partial<Capa>)}
            />
          </Campo>
          {(capa as CapaTexto).contorno && (
            <>
              <Campo etiqueta="Color del contorno">
                <ColorControl
                  valor={(capa as CapaTexto).contorno!.color}
                  onChange={(c) => set({ contorno: { ...(capa as CapaTexto).contorno!, color: c } } as Partial<Capa>)}
                />
              </Campo>
              <Campo etiqueta="Grosor del contorno">
                <Num
                  valor={(capa as CapaTexto).contorno!.grosor}
                  onChange={(v) => set({ contorno: { ...(capa as CapaTexto).contorno!, grosor: Math.max(0, v) } } as Partial<Capa>)}
                />
              </Campo>
            </>
          )}
          <Campo etiqueta="Relleno">
            <select
              value={(capa as CapaTexto).relleno_degradado ? "degradado" : "solido"}
              onChange={(e) =>
                set({
                  relleno_degradado:
                    e.target.value === "degradado"
                      ? { desde: (capa as CapaTexto).color, hasta: "#111315", angulo: 180 }
                      : null,
                } as Partial<Capa>)
              }
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="solido">Sólido</option>
              <option value="degradado">Degradado</option>
            </select>
          </Campo>
          {(capa as CapaTexto).relleno_degradado && (
            <>
              <Campo etiqueta="Desde">
                <ColorControl
                  valor={(capa as CapaTexto).relleno_degradado!.desde}
                  onChange={(c) => set({ relleno_degradado: { ...(capa as CapaTexto).relleno_degradado!, desde: c } } as Partial<Capa>)}
                />
              </Campo>
              <Campo etiqueta="Hasta">
                <ColorControl
                  valor={(capa as CapaTexto).relleno_degradado!.hasta}
                  onChange={(c) => set({ relleno_degradado: { ...(capa as CapaTexto).relleno_degradado!, hasta: c } } as Partial<Capa>)}
                />
              </Campo>
              <Campo etiqueta="Ángulo">
                <Num
                  valor={(capa as CapaTexto).relleno_degradado!.angulo ?? 180}
                  onChange={(v) => set({ relleno_degradado: { ...(capa as CapaTexto).relleno_degradado!, angulo: v } } as Partial<Capa>)}
                />
              </Campo>
            </>
          )}
          <Campo etiqueta="Sombra">
            <input
              type="checkbox"
              checked={!!(capa as CapaTexto).sombra}
              onChange={(e) => set({ sombra: e.target.checked ? { dx: 2, dy: 2, color: "#000000" } : null } as Partial<Capa>)}
            />
          </Campo>
          {(capa as CapaTexto).sombra && (
            <CamposSombra sombra={(capa as CapaTexto).sombra!} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
          )}
          <Campo etiqueta="Fondo (chip)">
            <input
              type="checkbox"
              checked={!!(capa as CapaTexto).chip}
              onChange={(e) =>
                set({ chip: e.target.checked ? { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } : null } as Partial<Capa>)
              }
            />
          </Campo>
          {(capa as CapaTexto).chip && (
            <>
              <Campo etiqueta="Color del chip">
                <ColorControl
                  valor={(capa as CapaTexto).chip!.color}
                  onChange={(c) => set({ chip: { ...(capa as CapaTexto).chip!, color: c } } as Partial<Capa>)}
                />
              </Campo>
              <div className="grid grid-cols-2 gap-2">
                <Campo etiqueta="Margen X">
                  <Num valor={(capa as CapaTexto).chip!.pad_x} onChange={(v) => set({ chip: { ...(capa as CapaTexto).chip!, pad_x: Math.max(0, v) } } as Partial<Capa>)} />
                </Campo>
                <Campo etiqueta="Margen Y">
                  <Num valor={(capa as CapaTexto).chip!.pad_y} onChange={(v) => set({ chip: { ...(capa as CapaTexto).chip!, pad_y: Math.max(0, v) } } as Partial<Capa>)} />
                </Campo>
              </div>
              <Campo etiqueta="Redondeo">
                <Num valor={(capa as CapaTexto).chip!.radio} onChange={(v) => set({ chip: { ...(capa as CapaTexto).chip!, radio: Math.max(0, v) } } as Partial<Capa>)} />
              </Campo>
            </>
          )}
        </div>
      )}

      {capa.tipo === "imagen" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          {/* Hueco de foto: la capa donde entra la foto de la pieza. Único y obligatorio por
              plantilla; al marcar otra, esta se desmarca. Marcarlo lo deja bloqueado. */}
          <Campo etiqueta="Hueco de foto">
            {(capa as CapaImagen).es_foto ? (
              <div className="flex items-center gap-1.5">
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                  Sí · bloqueado
                </span>
                <button
                  type="button"
                  onClick={() =>
                    store.getState().actualizar(capa.id, { es_foto: false, bloqueada: false } as Partial<Capa>)
                  }
                  className="rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
                >
                  Quitar
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => store.getState().marcarHuecoFoto(capa.id)}
                className="rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
              >
                Marcar como hueco
              </button>
            )}
          </Campo>
          {(capa as CapaImagen).es_foto && (
            <p className="text-[11px] text-muted-foreground">La plantilla requiere un hueco de foto.</p>
          )}
          <Campo etiqueta="Forma">
            <select
              value={(capa as CapaImagen).forma ?? "rect"}
              onChange={(e) => set({ forma: e.target.value as CapaImagen["forma"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="rect">Rectángulo</option>
              <option value="elipse">Círculo</option>
            </select>
          </Campo>
          {(capa as CapaImagen).forma !== "elipse" && (
            <Campo etiqueta="Esquinas">
              <Num
                valor={(capa as CapaImagen).radio ?? 0}
                onChange={(v) => set({ radio: Math.max(0, v) } as Partial<Capa>)}
              />
            </Campo>
          )}
          <Campo etiqueta="Ajuste">
            <select
              value={(capa as CapaImagen).ajuste}
              onChange={(e) => set({ ajuste: e.target.value as CapaImagen["ajuste"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="cover">Cubrir</option>
              <option value="contain">Contener</option>
            </select>
          </Campo>
          <Campo etiqueta="Zoom (reencuadre)">
            <input
              type="range"
              min={1}
              max={6}
              step={0.05}
              value={(capa as CapaImagen).zoom ?? 1}
              onChange={(e) => set({ zoom: Number(e.target.value) } as Partial<Capa>)}
              className="w-24"
            />
          </Campo>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Filtros</div>
          <Campo etiqueta="Brillo">
            <input type="range" min={0.2} max={1.8} step={0.05} value={fil.brillo ?? 1} onChange={(e) => setFiltro("brillo", Number(e.target.value))} className="w-24" />
          </Campo>
          <Campo etiqueta="Contraste">
            <input type="range" min={0.2} max={1.8} step={0.05} value={fil.contraste ?? 1} onChange={(e) => setFiltro("contraste", Number(e.target.value))} className="w-24" />
          </Campo>
          <Campo etiqueta="Saturación">
            <input type="range" min={0} max={2} step={0.05} value={fil.saturacion ?? 1} onChange={(e) => setFiltro("saturacion", Number(e.target.value))} className="w-24" />
          </Campo>
          <Campo etiqueta="Desenfoque">
            <input type="range" min={0} max={20} step={1} value={fil.desenfoque ?? 0} onChange={(e) => setFiltro("desenfoque", Number(e.target.value))} className="w-24" />
          </Campo>
          <button onClick={() => set({ filtros: null } as Partial<Capa>)} className="self-start text-xs text-muted-foreground underline">
            Quitar filtros
          </button>
          <Campo etiqueta="Sombra">
            <input
              type="checkbox"
              checked={!!(capa as CapaImagen).sombra}
              onChange={(e) => set({ sombra: e.target.checked ? { dx: 0, dy: 12, color: "#000000", desenfoque: 24, opacidad: 0.5 } : null } as Partial<Capa>)}
            />
          </Campo>
          {(capa as CapaImagen).sombra && (
            <CamposSombra sombra={(capa as CapaImagen).sombra!} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
          )}
        </div>
      )}

      {capa.tipo === "marco" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Forma">
            <select
              value={(capa as CapaMarco).forma}
              onChange={(e) => set({ forma: e.target.value as CapaMarco["forma"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="rect">Rectángulo</option>
              <option value="elipse">Elipse</option>
              <option value="linea">Línea</option>
            </select>
          </Campo>
          <Campo etiqueta="Relleno">
            <select
              value={(capa as CapaMarco).relleno_degradado ? "degradado" : "solido"}
              onChange={(e) =>
                set({
                  relleno_degradado:
                    e.target.value === "degradado"
                      ? { desde: (capa as CapaMarco).relleno ?? "#E30613", hasta: "#111315", angulo: 180 }
                      : null,
                } as Partial<Capa>)
              }
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="solido">Sólido</option>
              <option value="degradado">Degradado</option>
            </select>
          </Campo>
          {(capa as CapaMarco).relleno_degradado ? (
            <>
              <Campo etiqueta="Desde">
                <ColorControl
                  valor={(capa as CapaMarco).relleno_degradado!.desde}
                  onChange={(c) => set({ relleno_degradado: { ...(capa as CapaMarco).relleno_degradado!, desde: c } } as Partial<Capa>)}
                />
              </Campo>
              <Campo etiqueta="Hasta">
                <ColorControl
                  valor={(capa as CapaMarco).relleno_degradado!.hasta}
                  onChange={(c) => set({ relleno_degradado: { ...(capa as CapaMarco).relleno_degradado!, hasta: c } } as Partial<Capa>)}
                />
              </Campo>
              <Campo etiqueta="Ángulo">
                <Num
                  valor={(capa as CapaMarco).relleno_degradado!.angulo ?? 180}
                  onChange={(v) => set({ relleno_degradado: { ...(capa as CapaMarco).relleno_degradado!, angulo: v } } as Partial<Capa>)}
                />
              </Campo>
            </>
          ) : (
            <Campo etiqueta="Color de relleno">
              <ColorControl valor={(capa as CapaMarco).relleno ?? "#000000"} onChange={(c) => set({ relleno: c } as Partial<Capa>)} />
            </Campo>
          )}
          <Campo etiqueta="Borde">
            <ColorControl
              valor={(capa as CapaMarco).borde?.color ?? "#FFFFFF"}
              onChange={(c) => set({ borde: { color: c, grosor: (capa as CapaMarco).borde?.grosor ?? 6 } } as Partial<Capa>)}
            />
          </Campo>
          <Campo etiqueta="Grosor">
            <Num
              valor={(capa as CapaMarco).borde?.grosor ?? 0}
              onChange={(v) =>
                set({
                  // Grosor <= 0: el back descarta el borde (borde:null); el front hace lo mismo.
                  borde: v > 0 ? { color: (capa as CapaMarco).borde?.color ?? "#FFFFFF", grosor: v } : null,
                } as Partial<Capa>)
              }
            />
          </Campo>
          <Campo etiqueta="Radio"><Num valor={(capa as CapaMarco).radio} onChange={(v) => set({ radio: v } as Partial<Capa>)} /></Campo>
          <Campo etiqueta="Sombra">
            <input
              type="checkbox"
              checked={!!(capa as CapaMarco).sombra}
              onChange={(e) => set({ sombra: e.target.checked ? { dx: 0, dy: 12, color: "#000000", desenfoque: 24, opacidad: 0.5 } : null } as Partial<Capa>)}
            />
          </Campo>
          {(capa as CapaMarco).sombra && (
            <CamposSombra sombra={(capa as CapaMarco).sombra!} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
          )}
        </div>
      )}

      {capa.tipo === "overlay" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Color">
            <ColorControl valor={(capa as CapaOverlay).color} onChange={(c) => set({ color: c } as Partial<Capa>)} />
          </Campo>
          <Campo etiqueta="Altura (frac)">
            <Num valor={(capa as CapaOverlay).alto_frac} paso={0.05} onChange={(v) => set({ alto_frac: v } as Partial<Capa>)} />
          </Campo>
          <Campo etiqueta="Opacidad (0-255)">
            <Num valor={(capa as CapaOverlay).alpha} onChange={(v) => set({ alpha: v } as Partial<Capa>)} />
          </Campo>
        </div>
      )}

      {capa.tipo === "logo" && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <Campo etiqueta="Tipo">
            <select
              value={(capa as CapaLogo).tipo_logo}
              onChange={(e) => set({ tipo_logo: e.target.value as CapaLogo["tipo_logo"] } as Partial<Capa>)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
            >
              <option value="imagen">Imagen</option>
              <option value="wordmark">Wordmark</option>
            </select>
          </Campo>
          {(capa as CapaLogo).tipo_logo === "imagen" && (
            <Campo etiqueta="Media ID">
              <input
                type="text"
                value={(capa as CapaLogo).media_id}
                placeholder="id de media"
                onChange={(e) => set({ media_id: e.target.value.trim() } as Partial<Capa>)}
                className="w-40 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
              />
            </Campo>
          )}
          {(capa as CapaLogo).tipo_logo === "wordmark" && (
            <>
              <textarea
                value={(capa as CapaLogo).wordmark.texto}
                onChange={(e) => set({ wordmark: { ...(capa as CapaLogo).wordmark, texto: e.target.value } } as Partial<Capa>)}
                placeholder="Texto del wordmark…"
                className="min-h-[44px] rounded border border-input bg-background p-1.5 text-sm"
              />
              <div className="grid grid-cols-2 gap-2">
                <Campo etiqueta="Color">
                  <ColorControl valor={(capa as CapaLogo).wordmark.color} onChange={(c) => set({ wordmark: { ...(capa as CapaLogo).wordmark, color: c } } as Partial<Capa>)} />
                </Campo>
                <Campo etiqueta="Fondo">
                  <ColorControl valor={(capa as CapaLogo).wordmark.fondo} onChange={(c) => set({ wordmark: { ...(capa as CapaLogo).wordmark, fondo: c } } as Partial<Capa>)} />
                </Campo>
              </div>
              <Campo etiqueta="Fuente">
                <select
                  value={(capa as CapaLogo).wordmark.familia}
                  onChange={(e) => set({ wordmark: { ...(capa as CapaLogo).wordmark, familia: e.target.value } } as Partial<Capa>)}
                  className="max-w-[140px] rounded border border-input bg-background px-1.5 py-0.5 text-xs"
                >
                  {familias.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                  {!familias.includes((capa as CapaLogo).wordmark.familia) && (
                    <option value={(capa as CapaLogo).wordmark.familia}>{(capa as CapaLogo).wordmark.familia}</option>
                  )}
                </select>
              </Campo>
              <Campo etiqueta="Peso">
                <Num valor={(capa as CapaLogo).wordmark.peso} paso={100} onChange={(v) => set({ wordmark: { ...(capa as CapaLogo).wordmark, peso: v } } as Partial<Capa>)} />
              </Campo>
            </>
          )}
        </div>
      )}
    </div>
  );
}
