// Layer NO interactiva con todo lo VISUAL del encuadre y los gestos: rejilla, márgenes, zonas
// seguras, guías del imán/espaciado-igual, contorno de hover y rectángulo de marquee. Extraída como
// subcomponente puro: el componente le pasa el contexto vivo y ella solo pinta. Sin `listening` =>
// nunca intercepta eventos; el export se renderiza en el servidor desde el documento, así que nada
// de esto sale al archivo.

import { Group, Layer, Line, Rect, Text } from "react-konva";

import type { FranjasZonaSegura } from "./lib";
import type { GuiasArrastre } from "./useArrastreCapas";

export function CapaGuias({
  grid,
  paso,
  w,
  h,
  escala,
  iman,
  hayMargenes,
  safeTop,
  safeBottom,
  safeLeft,
  safeRight,
  franjasZonas,
  guias,
  hoverBox,
  marquee,
}: {
  grid: boolean;
  paso: number;
  w: number;
  h: number;
  escala: number;
  iman: boolean;
  hayMargenes: boolean;
  safeTop: number;
  safeBottom: number;
  safeLeft: number;
  safeRight: number;
  franjasZonas: FranjasZonaSegura | null;
  guias: GuiasArrastre;
  hoverBox: { x: number; y: number; w: number; h: number; rot: number } | null;
  marquee: { x0: number; y0: number; x1: number; y1: number } | null;
}) {
  return (
    <Layer listening={false}>
      {/* Rejilla FINA con el `paso` configurable. Gris medio (no blanco): visible sobre fondos
          claros Y oscuros (el blanco a 0.1 desaparecía sobre el tablero/claros). */}
      {grid &&
        Array.from({ length: Math.max(0, Math.ceil(w / paso) - 1) }, (_, i) => (
          <Line key={`gx${i}`} points={[(i + 1) * paso, 0, (i + 1) * paso, h]} stroke="#888888" strokeWidth={1 / escala} opacity={0.35} />
        ))}
      {grid &&
        Array.from({ length: Math.max(0, Math.ceil(h / paso) - 1) }, (_, i) => (
          <Line key={`gy${i}`} points={[0, (i + 1) * paso, w, (i + 1) * paso]} stroke="#888888" strokeWidth={1 / escala} opacity={0.35} />
        ))}
      {/* MÁRGENES (encuadre): 4 líneas de guía. Se muestran cuando hay márgenes definidos (>0) y
          el imán está activo (para snap visible), o cuando la rejilla está activa. */}
      {(iman || grid) && hayMargenes && (
        <>
          {safeTop > 0 && <Rect x={0} y={safeTop} width={w} height={1 / escala} fill="#22d3ee" opacity={0.45} />}
          {safeBottom > 0 && <Rect x={0} y={h - safeBottom} width={w} height={1 / escala} fill="#22d3ee" opacity={0.45} />}
          {safeLeft > 0 && <Rect x={safeLeft} y={0} width={1 / escala} height={h} fill="#22d3ee" opacity={0.45} />}
          {safeRight > 0 && <Rect x={w - safeRight} y={0} width={1 / escala} height={h} fill="#22d3ee" opacity={0.45} />}
        </>
      )}
      {/* ZONAS SEGURAS (patrón Canva/IG): velo sutil sobre las franjas FUERA de la zona
          segura del formato (donde la UI de la plataforma tapa el diseño) + borde
          discontinuo fino en el límite + etiqueta discreta si cabe. Solo visual: vive en
          esta Layer sin listening y el export se renderiza en el SERVIDOR a partir del
          documento (render_node/dibujar.mjs), nunca del Stage => jamás sale al archivo. */}
      {franjasZonas && (
        <>
          {franjasZonas.velos.map((r, i) => (
            <Rect key={`zsv${i}`} x={r.x} y={r.y} width={r.w} height={r.h} fill="#000000" opacity={0.13} />
          ))}
          {franjasZonas.limites.map((p, i) => (
            <Line
              key={`zsl${i}`}
              points={p}
              stroke="#ffffff"
              strokeWidth={1 / escala}
              dash={[6 / escala, 4 / escala]}
              opacity={0.85}
            />
          ))}
          {/* Etiqueta solo si la franja superior mide al menos ~26 px de PANTALLA (si no,
              estorbaría más de lo que aclara). */}
          {safeTop * escala >= 26 && (
            <Text
              text="Zona segura"
              x={8 / escala}
              y={safeTop - 17 / escala}
              fontSize={11 / escala}
              fill="#ffffff"
              opacity={0.75}
            />
          )}
        </>
      )}
      {guias.x !== null && <Line points={[guias.x, 0, guias.x, h]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
      {guias.y !== null && <Line points={[0, guias.y, w, guias.y]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />}
      {/* ESPACIADO IGUAL (estilo Canva): un segmento con topes en cada hueco equidistante
          (la etiqueta px va en el overlay HTML de etiquetas, mutado por el hook). */}
      {guias.espX?.segmentos.map((s, i) => (
        <Group key={`espx${i}`}>
          <Line points={[s.desde, s.perp, s.hasta, s.perp]} stroke="#ec4899" strokeWidth={1.5 / escala} />
          <Line points={[s.desde, s.perp - 6 / escala, s.desde, s.perp + 6 / escala]} stroke="#ec4899" strokeWidth={1.5 / escala} />
          <Line points={[s.hasta, s.perp - 6 / escala, s.hasta, s.perp + 6 / escala]} stroke="#ec4899" strokeWidth={1.5 / escala} />
        </Group>
      ))}
      {guias.espY?.segmentos.map((s, i) => (
        <Group key={`espy${i}`}>
          <Line points={[s.perp, s.desde, s.perp, s.hasta]} stroke="#ec4899" strokeWidth={1.5 / escala} />
          <Line points={[s.perp - 6 / escala, s.desde, s.perp + 6 / escala, s.desde]} stroke="#ec4899" strokeWidth={1.5 / escala} />
          <Line points={[s.perp - 6 / escala, s.hasta, s.perp + 6 / escala, s.hasta]} stroke="#ec4899" strokeWidth={1.5 / escala} />
        </Group>
      ))}
      {/* HOVER (estilo Canva): contorno fino de acento sobre la capa bajo el cursor ANTES de
          seleccionarla. Solo visual (Layer sin listening). */}
      {hoverBox && (
        <Rect
          x={hoverBox.x}
          y={hoverBox.y}
          width={hoverBox.w}
          height={hoverBox.h}
          rotation={hoverBox.rot}
          stroke="#3b82f6"
          strokeWidth={1.5 / escala}
          listening={false}
        />
      )}
      {/* Rectángulo de selección (marquee): caja punteada en coords del documento. */}
      {marquee && (
        <Rect
          x={Math.min(marquee.x0, marquee.x1)}
          y={Math.min(marquee.y0, marquee.y1)}
          width={Math.abs(marquee.x1 - marquee.x0)}
          height={Math.abs(marquee.y1 - marquee.y0)}
          stroke="#3b82f6"
          strokeWidth={1 / escala}
          dash={[5 / escala, 4 / escala]}
          fill="#3b82f6"
          opacity={0.12}
        />
      )}
    </Layer>
  );
}
