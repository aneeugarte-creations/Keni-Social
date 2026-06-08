// Render del fondo del documento (color / degradado lineal o radial multi-stop / imagen patrón).

import { Rect } from "react-konva";

import { puntosGradiente } from "../capas/CapaNodo";
import type { Documento } from "../documento";
import { useImagen } from "../useImagen";

export function FondoNodo({ fondo, w, h }: { fondo: Documento["fondo"]; w: number; h: number }) {
  const img = useImagen(fondo.tipo === "imagen" ? fondo.imagen?.media_id : null);
  if (fondo.tipo === "color") return <Rect x={0} y={0} width={w} height={h} fill={fondo.color} listening={false} />;
  if (fondo.tipo === "degradado" && fondo.degradado) {
    // Soporta lineal/radial y multi-stop (mismo helper/convención que el render y las capas):
    // default lineal 180 = vertical (↓), sin cambio visual respecto al comportamiento previo.
    const deg = fondo.degradado;
    const stops: (number | string)[] =
      deg.stops && deg.stops.length >= 2
        ? [...deg.stops]
            .map((s) => ({ pos: Math.max(0, Math.min(1, s.pos || 0)), color: s.color }))
            .sort((a, b) => a.pos - b.pos)
            .flatMap((s) => [s.pos, s.color])
        : [0, deg.desde, 1, deg.hasta];
    if (deg.tipo === "radial") {
      const r = Math.sqrt(w * w + h * h) / 2;
      return (
        <Rect
          x={0} y={0} width={w} height={h} listening={false}
          fillRadialGradientStartPoint={{ x: w / 2, y: h / 2 }}
          fillRadialGradientEndPoint={{ x: w / 2, y: h / 2 }}
          fillRadialGradientStartRadius={0}
          fillRadialGradientEndRadius={r}
          fillRadialGradientColorStops={stops}
        />
      );
    }
    const g = puntosGradiente(w, h, deg.angulo);
    return (
      <Rect
        x={0} y={0} width={w} height={h} listening={false}
        fillLinearGradientStartPoint={g.start}
        fillLinearGradientEndPoint={g.end}
        fillLinearGradientColorStops={stops}
      />
    );
  }
  if (fondo.tipo === "imagen" && img) {
    return <Rect x={0} y={0} width={w} height={h} listening={false} fillPatternImage={img} fillPatternScale={{ x: w / img.width, y: h / img.height }} />;
  }
  return <Rect x={0} y={0} width={w} height={h} fill="#111315" listening={false} />;
}
