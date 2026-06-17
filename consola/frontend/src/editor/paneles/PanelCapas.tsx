// Lista de capas (z-order): reordenar por drag&drop, renombrar, mostrar/ocultar, bloquear, borrar
// y agrupar/desagrupar. Opera sobre el store del documento via contexto.

import {
  Eye,
  EyeOff,
  GripVertical,
  Group as GroupIcon,
  Layers as LayersIcon,
  Lock,
  Trash2,
  Ungroup,
  Unlock,
} from "lucide-react";
import { useState } from "react";

import { urlMedia } from "@/lib/api";

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaTexto } from "../documento";
import { useEditor, useStoreEditor } from "../usarEditor";

import { ICONO_TIPO, nombreCapa } from "./lib";

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
    // El HUECO DE FOTO (`es_foto`) nace bloqueado (no se arrastra por error en el lienzo) pero SÍ se
    // puede borrar desde su papelera; al quitar el último hueco el editor avisa con el chip ámbar.
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
        disabled={capa.bloqueada && !esFoto}
        onClick={(e) => { e.stopPropagation(); store.getState().quitar(capa.id, esFoto); }}
        title={esFoto ? "Borrar hueco de foto" : capa.bloqueada ? "Capa bloqueada (no se puede borrar)" : "Borrar capa"}
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
