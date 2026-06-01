/**
 * Lienzo editable de la plantilla: arrastra/redimensiona las capas con el puntero sobre la
 * "vista real" del servidor (la imagen renderizada con el mismo motor que produce las placas).
 *
 * El editor NO re-dibuja los píxeles (eso lo hace el servidor); aquí solo se manipulan las CAJAS
 * (logo, hueco de foto, bloques de texto) escaladas al tamaño mostrado, y se devuelven las nuevas
 * coordenadas en el espacio del lienzo del formato. El padre refresca la vista real (debounced).
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
  resizable: boolean;
  aplicar: (x: number, y: number, w: number, h: number) => void;
}

type Arrastre = {
  clave: string;
  modo: "mover" | "redim";
  px: number;
  py: number;
  orig: { x: number; y: number; w: number; h: number };
  aplicar: Caja["aplicar"];
};

export function LienzoEditable({
  fmt,
  previewUrl,
  seleccion,
  onSeleccion,
  onFoto,
  onLogo,
  onTexto,
  anchoMostrado = 280,
}: {
  fmt: FormatoSpec;
  previewUrl: string;
  seleccion: string;
  onSeleccion: (clave: string) => void;
  onFoto: (x: number, y: number, w: number, h: number) => void;
  onLogo: (x: number, y: number, w: number, h: number) => void;
  onTexto: (i: number, x: number, y: number, w: number) => void;
  anchoMostrado?: number;
}) {
  const { w: LW, h: LH } = fmt.lienzo;
  const escala = anchoMostrado / LW;
  const [arrastre, setArrastre] = React.useState<Arrastre | null>(null);

  const cajas: Caja[] = [
    {
      clave: "foto",
      etiqueta: "Foto",
      x: fmt.foto_slot.x,
      y: fmt.foto_slot.y,
      w: fmt.foto_slot.w,
      h: fmt.foto_slot.h,
      resizable: true,
      aplicar: onFoto,
    },
    {
      clave: "logo",
      etiqueta: "Logo",
      x: fmt.logo.x,
      y: fmt.logo.y,
      w: fmt.logo.w,
      h: fmt.logo.h,
      resizable: true,
      aplicar: onLogo,
    },
    ...fmt.textos.map((t, i) => ({
      clave: `texto-${i}`,
      etiqueta: t.id,
      x: t.x,
      y: t.y,
      w: t.w,
      h: Math.max(t.tamano, 36),
      resizable: true, // solo ancho (alto es automático); el handle reescala w
      aplicar: (x: number, y: number, w: number, _h: number) => onTexto(i, x, y, w),
    })),
  ];

  React.useEffect(() => {
    if (!arrastre) return;
    function mover(ev: PointerEvent) {
      const dx = (ev.clientX - arrastre!.px) / escala;
      const dy = (ev.clientY - arrastre!.py) / escala;
      const o = arrastre!.orig;
      if (arrastre!.modo === "mover") {
        arrastre!.aplicar(Math.round(o.x + dx), Math.round(o.y + dy), o.w, o.h);
      } else {
        arrastre!.aplicar(o.x, o.y, Math.max(20, Math.round(o.w + dx)), Math.max(20, Math.round(o.h + dy)));
      }
    }
    function soltar() {
      setArrastre(null);
    }
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", soltar);
    return () => {
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", soltar);
    };
  }, [arrastre, escala]);

  function iniciar(ev: React.PointerEvent, caja: Caja, modo: "mover" | "redim") {
    ev.preventDefault();
    ev.stopPropagation();
    onSeleccion(caja.clave);
    setArrastre({
      clave: caja.clave,
      modo,
      px: ev.clientX,
      py: ev.clientY,
      orig: { x: caja.x, y: caja.y, w: caja.w, h: caja.h },
      aplicar: caja.aplicar,
    });
  }

  return (
    <div
      className="relative select-none overflow-hidden rounded-md border border-border bg-muted/30"
      style={{ width: anchoMostrado, height: LH * escala }}
    >
      {previewUrl ? (
        <img src={previewUrl} alt="Vista de la plantilla" className="absolute inset-0 h-full w-full" draggable={false} />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
          Cargando vista…
        </div>
      )}
      {cajas.map((c) => {
        const activa = seleccion === c.clave;
        return (
          <div
            key={c.clave}
            onPointerDown={(e) => iniciar(e, c, "mover")}
            className={cn(
              "absolute cursor-move border-2",
              activa ? "border-sky-500 bg-sky-500/10" : "border-white/50 hover:border-sky-400",
            )}
            style={{
              left: c.x * escala,
              top: c.y * escala,
              width: c.w * escala,
              height: c.h * escala,
            }}
            title={`${c.etiqueta} (arrastra para mover)`}
          >
            <span className="absolute left-0 top-0 bg-sky-600 px-1 text-[10px] leading-tight text-white">
              {c.etiqueta}
            </span>
            {c.resizable && (
              <span
                onPointerDown={(e) => iniciar(e, c, "redim")}
                className="absolute -bottom-1 -right-1 h-3 w-3 cursor-nwse-resize rounded-sm border border-white bg-sky-600"
                title="Arrastra para redimensionar"
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
