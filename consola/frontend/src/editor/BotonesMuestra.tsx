// Dos botones INDEPENDIENTES de "Vista con muestra" para la barra del editor:
//   · FOTO: rellena el hueco de foto vacío con una foto de muestra (editable: gris por defecto, o
//     una foto real que suba/pegue el equipo) para ver recorte/encuadre/forma/filtros sobre algo.
//   · COPY: rellena los bindings de texto con un titular/pleca de ejemplo (editable) para ver
//     saltos de línea y auto-encogido.
// Cada botón es un TOGGLE; un chevron al lado abre un popover para EDITAR su valor. Todo es
// PRESENTACIÓN: no toca el documento ni el export (se guarda en localStorage).

import { ChevronDown, ImagePlay, RotateCcw, Type, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Telon } from "./Telon";
import {
  ETIQUETA_MUESTRA_DEFECTO,
  getEtiquetaMuestra,
  getFotoMuestraSrc,
  getTitularMuestra,
  setEtiquetaMuestra,
  setFotoMuestra,
  setTitularMuestra,
  TITULAR_MUESTRA_DEFECTO,
} from "./muestra";

export function BotonesMuestra({
  verFoto,
  setVerFoto,
  verCopy,
  setVerCopy,
}: {
  verFoto: boolean;
  setVerFoto: (v: boolean) => void;
  verCopy: boolean;
  setVerCopy: (v: boolean) => void;
}) {
  // Qué popover de edición está abierto (o ninguno).
  const [editar, setEditar] = useState<"foto" | "copy" | null>(null);

  return (
    <div className="flex items-center gap-1">
      <BotonToggle
        icono={ImagePlay}
        etiqueta="Foto"
        activo={verFoto}
        titulo={
          verFoto
            ? "Foto de muestra activa: rellena el hueco vacío (no se guarda)"
            : "Activar foto de muestra: rellena el hueco vacío para previsualizar"
        }
        onToggle={() => setVerFoto(!verFoto)}
        onEditar={() => setEditar((e) => (e === "foto" ? null : "foto"))}
        editando={editar === "foto"}
        popover={<PopoverFoto onCerrar={() => setEditar(null)} onActivar={() => setVerFoto(true)} />}
        onCerrar={() => setEditar(null)}
      />
      <BotonToggle
        icono={Type}
        etiqueta="Copy"
        activo={verCopy}
        titulo={
          verCopy
            ? "Copy de muestra activo: titular/pleca de ejemplo en los bindings (no se guarda)"
            : "Activar copy de muestra: titular/pleca de ejemplo en los bindings"
        }
        onToggle={() => setVerCopy(!verCopy)}
        onEditar={() => setEditar((e) => (e === "copy" ? null : "copy"))}
        editando={editar === "copy"}
        popover={<PopoverCopy onCerrar={() => setEditar(null)} onActivar={() => setVerCopy(true)} />}
        onCerrar={() => setEditar(null)}
      />
    </div>
  );
}

function BotonToggle({
  icono: Icono,
  etiqueta,
  activo,
  titulo,
  onToggle,
  onEditar,
  editando,
  popover,
  onCerrar,
}: {
  icono: typeof ImagePlay;
  etiqueta: string;
  activo: boolean;
  titulo: string;
  onToggle: () => void;
  onEditar: () => void;
  editando: boolean;
  popover: React.ReactNode;
  onCerrar: () => void;
}) {
  return (
    <div className="relative flex items-center">
      {/* ACTIVO = lavado SUAVE del color del cromo (`--foreground` al 12%) con glifo a tinta
          plena, NO la píldora `--control-activo`: estos toggles están encendidos por defecto y
          una píldora sólida permanente pesaba como otro CTA junto a Exportar. Apagado = glifo
          atenuado. El chevron comparte el fondo para que el par toggle+chevron se lea como UNA
          sola píldora (rounded-l + rounded-r), no como un activo partido por la mitad. Ambas
          mitades llevan h-8 EXPLÍCITO (la altura no sale del padding): así la píldora es un
          rectángulo continuo de 32px, sin escalón en la mitad del chevron, con bordes
          exteriores simétricos (entra pl-2, sale pr-2). */}
      <button
        title={titulo}
        aria-label={etiqueta}
        aria-pressed={activo}
        onClick={onToggle}
        className={`flex h-8 items-center rounded-l-md pl-2 pr-1 ${
          // Encendido: lavado al 12% que se intensifica al hover (sigue legible: glifo a tinta).
          // Apagado: atenuado, con el hover accent de toda la barra.
          activo
            ? "bg-[hsl(var(--foreground)/0.12)] text-foreground hover:bg-[hsl(var(--foreground)/0.2)]"
            : "text-[hsl(var(--muted-foreground)/0.55)] hover:bg-accent hover:text-accent-foreground"
        }`}
      >
        <Icono className="h-4 w-4" />
      </button>
      <button
        title={`Editar ${etiqueta.toLowerCase()} de muestra`}
        aria-label={`Editar ${etiqueta.toLowerCase()} de muestra`}
        aria-expanded={editando}
        onClick={onEditar}
        className={`flex h-8 items-center rounded-r-md pl-0.5 pr-2 ${
          // Encendido: lavado al 12% que se intensifica al hover (sigue legible: glifo a tinta).
          // Apagado: atenuado, con el hover accent de toda la barra.
          activo
            ? "bg-[hsl(var(--foreground)/0.12)] text-foreground hover:bg-[hsl(var(--foreground)/0.2)]"
            : "text-[hsl(var(--muted-foreground)/0.55)] hover:bg-accent hover:text-accent-foreground"
        }`}
      >
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {editando && (
        <>
          <Telon onCerrar={onCerrar} etiqueta="Cerrar editor de muestra" className="fixed inset-0 z-30" />
          <div className="absolute right-0 top-full z-40 mt-1 w-64 rounded-md border border-border bg-popover p-3 shadow-md">
            {popover}
          </div>
        </>
      )}
    </div>
  );
}

// ── Editor de la FOTO de muestra ────────────────────────────────────────────────────────────────

function PopoverFoto({ onCerrar, onActivar }: { onCerrar: () => void; onActivar: () => void }) {
  const [src, setSrc] = useState(getFotoMuestraSrc());
  const fileRef = useRef<HTMLInputElement | null>(null);

  const aplicar = (nuevo: string) => {
    setSrc(nuevo);
    setFotoMuestra(nuevo);
    onActivar();
  };

  const onArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") aplicar(reader.result);
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Foto de muestra
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Solo para previsualizar (no se guarda en la plantilla). Por defecto una superficie gris.
      </p>
      <div className="aspect-[4/5] w-full overflow-hidden rounded border border-border bg-muted/40">
        {src ? (
          <img src={src} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-tr from-zinc-400 to-zinc-700 text-[11px] text-white/80">
            Superficie gris
          </div>
        )}
      </div>
      <input ref={fileRef} type="file" accept="image/*" onChange={onArchivo} className="hidden" />
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="flex flex-1 items-center justify-center gap-1 rounded border border-input bg-background px-2 py-1.5 text-xs hover:bg-accent"
        >
          <Upload className="h-3.5 w-3.5" /> Subir foto
        </button>
        <button
          type="button"
          onClick={() => aplicar("")}
          disabled={!src}
          title="Volver a la superficie gris por defecto"
          className="flex items-center justify-center gap-1 rounded border border-input bg-background px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-40"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Gris
        </button>
      </div>
      <input
        type="url"
        placeholder="…o pega una URL de imagen"
        defaultValue={/^https?:/.test(src) ? src : ""}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = (e.target as HTMLInputElement).value.trim();
            if (v) aplicar(v);
          }
        }}
        className="rounded border border-input bg-background px-2 py-1 text-xs"
      />
      <button
        type="button"
        onClick={onCerrar}
        className="self-end text-[11px] text-muted-foreground underline hover:text-foreground"
      >
        Cerrar
      </button>
    </div>
  );
}

// ── Editor del COPY de muestra ──────────────────────────────────────────────────────────────────

function PopoverCopy({ onCerrar, onActivar }: { onCerrar: () => void; onActivar: () => void }) {
  const [titular, setTitular] = useState(getTitularMuestra());
  const [etiqueta, setEtiqueta] = useState(getEtiquetaMuestra());

  const onTitular = (v: string) => {
    setTitular(v);
    setTitularMuestra(v);
    onActivar();
  };
  const onEtiqueta = (v: string) => {
    setEtiqueta(v);
    setEtiquetaMuestra(v);
    onActivar();
  };
  const restablecer = () => {
    onTitular(TITULAR_MUESTRA_DEFECTO);
    onEtiqueta(ETIQUETA_MUESTRA_DEFECTO);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Copy de muestra
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Titular y pleca de ejemplo para los bindings (no se guarda en la plantilla).
      </p>
      <label className="text-[11px] font-medium text-muted-foreground">Titular (binding copy_in)</label>
      <textarea
        value={titular}
        onChange={(e) => onTitular(e.target.value)}
        rows={3}
        className="resize-none rounded border border-input bg-background px-2 py-1 text-xs leading-snug"
      />
      <label className="text-[11px] font-medium text-muted-foreground">Pleca (binding etiqueta_default)</label>
      <input
        value={etiqueta}
        onChange={(e) => onEtiqueta(e.target.value)}
        className="rounded border border-input bg-background px-2 py-1 text-xs"
      />
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={restablecer}
          className="flex items-center gap-1 text-[11px] text-muted-foreground underline hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" /> Restablecer
        </button>
        <button
          type="button"
          onClick={onCerrar}
          className="text-[11px] text-muted-foreground underline hover:text-foreground"
        >
          Cerrar
        </button>
      </div>
    </div>
  );
}
