/**
 * Lienzo editable de la plantilla: arrastra/redimensiona/selecciona las capas sobre la "vista
 * real" del servidor (la imagen renderizada con el mismo motor que produce las placas).
 *
 * El editor NO re-dibuja los píxeles (eso lo hace el servidor): aquí solo se manipulan las CAJAS
 * (logo, hueco de foto, bloques de texto) escaladas al tamaño mostrado, con SNAPPING a centros,
 * zona segura y a las otras capas (guías visuales mientras imanta). Devuelve coordenadas en el
 * espacio del lienzo del formato; el padre refresca la vista real (debounced).
 */
import * as React from "react";

import { cn } from "@/lib/utils";
import type { FormatoSpec } from "@/lib/specPlantilla";

interface Caja {
  clave: string;
  etiqueta: string;
  x: number;
  y: number;
  w: number;
  h: number;
  aplicar: (x: number, y: number, w: number, h: number) => void;
}

type Arrastre = {
  modo: "mover" | "redim";
  px: number;
  py: number;
  orig: { x: number; y: number; w: number; h: number };
  caja: Caja;
};

export function LienzoEditable({
  fmt,
  previewUrl,
  seleccion,
  onSeleccion,
  onFoto,
  onLogo,
  onTexto,
  maxW = 560,
  maxH = 600,
}: {
  fmt: FormatoSpec;
  previewUrl: string;
  seleccion: string;
  onSeleccion: (clave: string) => void;
  onFoto: (x: number, y: number, w: number, h: number) => void;
  onLogo: (x: number, y: number, w: number, h: number) => void;
  onTexto: (clave: string, x: number, y: number, w: number) => void;
  maxW?: number;
  maxH?: number;
}) {
  const { w: LW, h: LH, safe_top, safe_bottom } = fmt.lienzo;
  const escala = Math.min(maxW / LW, maxH / LH);
  const [arrastre, setArrastre] = React.useState<Arrastre | null>(null);
  const [guias, setGuias] = React.useState<{ vx: number | null; hy: number | null }>({ vx: null, hy: null });

  const cajas: Caja[] = React.useMemo(() => {
    return [
      { clave: "foto", etiqueta: "Foto", x: fmt.foto_slot.x, y: fmt.foto_slot.y, w: fmt.foto_slot.w, h: fmt.foto_slot.h, aplicar: onFoto },
      { clave: "logo", etiqueta: "Logo", x: fmt.logo.x, y: fmt.logo.y, w: fmt.logo.w, h: fmt.logo.h, aplicar: onLogo },
      ...fmt.textos.map((t) => ({
        clave: `texto-${t.id}`,
        etiqueta: t.id === "titular" ? "Título" : t.id === "pleca" ? "Etiqueta" : "Antetítulo",
        x: t.x,
        y: t.y,
        w: t.w,
        h: Math.round(t.tamano * 1.2),
        aplicar: (x: number, y: number, w: number, _h: number) => onTexto(`texto-${t.id}`, x, y, w),
      })),
    ];
  }, [fmt, onFoto, onLogo, onTexto]);

  // Imanta los anclajes de la caja (bordes y centro) a líneas de referencia; devuelve guías.
  function snap(nx: number, ny: number, w: number, h: number, claveActiva: string) {
    const thr = 8 / escala; // 8 px de pantalla
    const otras = cajas.filter((c) => c.clave !== claveActiva);
    const vlines = [LW / 2, 56, LW - 56, ...otras.flatMap((c) => [c.x, c.x + c.w / 2, c.x + c.w])];
    const hlines = [LH / 2, safe_top, LH - safe_bottom, 56, LH - 56, ...otras.flatMap((c) => [c.y, c.y + c.h / 2, c.y + c.h])];
    let gx: number | null = null;
    let gy: number | null = null;
    let mejorX = thr + 1;
    for (const v of vlines) {
      for (const [val, off] of [[nx, 0], [nx + w / 2, w / 2], [nx + w, w]] as const) {
        const d = Math.abs(val - v);
        if (d < mejorX) { mejorX = d; nx = v - off; gx = v; }
      }
    }
    if (mejorX > thr) gx = null;
    let mejorY = thr + 1;
    for (const hh of hlines) {
      for (const [val, off] of [[ny, 0], [ny + h / 2, h / 2], [ny + h, h]] as const) {
        const d = Math.abs(val - hh);
        if (d < mejorY) { mejorY = d; ny = hh - off; gy = hh; }
      }
    }
    if (mejorY > thr) gy = null;
    return { x: Math.round(nx), y: Math.round(ny), gx, gy };
  }

  React.useEffect(() => {
    if (!arrastre) return;
    function mover(ev: PointerEvent) {
      const dx = (ev.clientX - arrastre!.px) / escala;
      const dy = (ev.clientY - arrastre!.py) / escala;
      const o = arrastre!.orig;
      const c = arrastre!.caja;
      if (arrastre!.modo === "mover") {
        const s = snap(o.x + dx, o.y + dy, o.w, o.h, c.clave);
        setGuias({ vx: s.gx, hy: s.gy });
        c.aplicar(s.x, s.y, o.w, o.h);
      } else {
        const w = Math.max(24, Math.round(o.w + dx));
        const h = Math.max(24, Math.round(o.h + dy));
        c.aplicar(o.x, o.y, w, h);
      }
    }
    function soltar() {
      setArrastre(null);
      setGuias({ vx: null, hy: null });
    }
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", soltar);
    return () => {
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", soltar);
    };
  }, [arrastre, escala]); // eslint-disable-line react-hooks/exhaustive-deps

  function iniciar(ev: React.PointerEvent, caja: Caja, modo: "mover" | "redim") {
    ev.preventDefault();
    ev.stopPropagation();
    onSeleccion(caja.clave);
    setArrastre({ modo, px: ev.clientX, py: ev.clientY, orig: { x: caja.x, y: caja.y, w: caja.w, h: caja.h }, caja });
  }

  return (
    <div
      className="relative select-none overflow-hidden rounded-lg border border-border bg-muted/30 shadow-sm"
      style={{ width: LW * escala, height: LH * escala }}
      onPointerDown={() => onSeleccion("")}
    >
      {previewUrl ? (
        <img src={previewUrl} alt="Vista de la plantilla" className="absolute inset-0 h-full w-full" draggable={false} />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">Cargando vista…</div>
      )}

      {/* Zona segura (referencia, no editable) */}
      <div
        className="pointer-events-none absolute border border-dashed border-white/25"
        style={{ left: 0, right: 0, top: safe_top * escala, bottom: safe_bottom * escala }}
      />

      {/* Guías de alineación mientras se imanta */}
      {guias.vx !== null && (
        <div className="pointer-events-none absolute bottom-0 top-0 w-px bg-fuchsia-500" style={{ left: guias.vx * escala }} />
      )}
      {guias.hy !== null && (
        <div className="pointer-events-none absolute left-0 right-0 h-px bg-fuchsia-500" style={{ top: guias.hy * escala }} />
      )}

      {cajas.map((c) => {
        const activa = seleccion === c.clave;
        return (
          <div
            key={c.clave}
            onPointerDown={(e) => iniciar(e, c, "mover")}
            className={cn(
              "absolute cursor-move rounded-sm border-2 transition-colors",
              activa ? "border-sky-400 bg-sky-400/10" : "border-white/40 hover:border-sky-300",
            )}
            style={{ left: c.x * escala, top: c.y * escala, width: c.w * escala, height: c.h * escala }}
            title={`${c.etiqueta} · arrastra para mover`}
          >
            <span
              className={cn(
                "absolute -top-px left-0 px-1 text-[10px] font-medium leading-tight text-white",
                activa ? "bg-sky-500" : "bg-black/55",
              )}
            >
              {c.etiqueta}
            </span>
            <span
              onPointerDown={(e) => iniciar(e, c, "redim")}
              className="absolute -bottom-1 -right-1 h-3.5 w-3.5 cursor-nwse-resize rounded-sm border border-white bg-sky-500"
              title="Arrastra para redimensionar"
            />
          </div>
        );
      })}
    </div>
  );
}
