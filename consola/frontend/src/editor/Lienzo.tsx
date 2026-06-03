// Lienzo Konva del editor: pinta el fondo + las capas (por z) a escala, con selección, arrastre,
// Transformer (escala/rotación) y guías de zona segura. El estado vive en el store (contexto).

import Konva from "konva";
import { useEffect, useRef } from "react";
import { Layer, Rect, Stage, Transformer } from "react-konva";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, Documento } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";
import { useImagen } from "./useImagen";

function FondoNodo({ fondo, w, h }: { fondo: Documento["fondo"]; w: number; h: number }) {
  const img = useImagen(fondo.tipo === "imagen" ? fondo.imagen?.media_id : null);
  if (fondo.tipo === "color") {
    return <Rect x={0} y={0} width={w} height={h} fill={fondo.color} listening={false} />;
  }
  if (fondo.tipo === "degradado" && fondo.degradado) {
    return (
      <Rect
        x={0}
        y={0}
        width={w}
        height={h}
        listening={false}
        fillLinearGradientStartPoint={{ x: 0, y: 0 }}
        fillLinearGradientEndPoint={{ x: 0, y: h }}
        fillLinearGradientColorStops={[0, fondo.degradado.desde, 1, fondo.degradado.hasta]}
      />
    );
  }
  if (fondo.tipo === "imagen" && img) {
    return <Rect x={0} y={0} width={w} height={h} fillPatternImage={img} fillPatternScale={{ x: w / img.width, y: h / img.height }} listening={false} />;
  }
  return <Rect x={0} y={0} width={w} height={h} fill="#111315" listening={false} />;
}

export function Lienzo({ maxAncho = 720, maxAlto = 720 }: { maxAncho?: number; maxAlto?: number }) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const { w, h } = documento.formato;
  const escala = Math.min(maxAncho / w, maxAlto / h, 1);

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);

  // Adjunta el Transformer al nodo seleccionado cuando cambia la selección o las capas.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    const nodo = seleccion ? stage.findOne<Konva.Node>(`#${seleccion}`) : null;
    tr.nodes(nodo ? [nodo] : []);
    tr.getLayer()?.batchDraw();
  }, [seleccion, documento]);

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const st = store.getState();

  return (
    <div
      style={{ width: w * escala, height: h * escala }}
      className="overflow-hidden rounded-md border border-border shadow-sm"
    >
      <Stage
        ref={stageRef}
        width={w * escala}
        height={h * escala}
        scaleX={escala}
        scaleY={escala}
        onMouseDown={(e) => {
          // Click en vacío (el propio Stage) deselecciona.
          if (e.target === e.target.getStage()) st.seleccionar(null);
        }}
      >
        <Layer>
          <FondoNodo fondo={documento.fondo} w={w} h={h} />
          {capas.map((capa) => (
            <CapaNodo
              key={capa.id}
              capa={capa}
              seleccionada={capa.id === seleccion}
              onSelect={() => st.seleccionar(capa.id)}
              onChange={(cambios) => st.actualizar(capa.id, cambios)}
              onGesto={() => st.comenzarGesto()}
            />
          ))}
        </Layer>
        <Layer listening={false}>
          {/* Zona segura (guía): márgenes superior/inferior del formato. */}
          {documento.formato.safe_top > 0 && (
            <Rect x={0} y={documento.formato.safe_top} width={w} height={1} fill="#22d3ee" opacity={0.5} />
          )}
          {documento.formato.safe_bottom > 0 && (
            <Rect x={0} y={h - documento.formato.safe_bottom} width={w} height={1} fill="#22d3ee" opacity={0.5} />
          )}
        </Layer>
        <Layer>
          <Transformer
            ref={trRef}
            rotateEnabled
            keepRatio={false}
            ignoreStroke
            boundBoxFunc={(_oldBox, newBox) => {
              if (newBox.width < 8 || newBox.height < 8) return _oldBox;
              return newBox;
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}
