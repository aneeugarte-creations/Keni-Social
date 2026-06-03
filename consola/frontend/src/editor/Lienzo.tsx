// Lienzo Konva del editor: fondo + capas (por z) a escala, con selección, arrastre con SMART
// GUIDES (alineación automática a otras capas y al lienzo), Transformer con aspect-ratio para
// imágenes/logos, zonas seguras y borrado con tecla Supr/Backspace.

import Konva from "konva";
import { useEffect, useRef, useState } from "react";
import { Layer, Line, Rect, Stage, Transformer } from "react-konva";

import { CapaNodo } from "./capas/CapaNodo";
import type { Capa, Documento } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";
import { useImagen } from "./useImagen";

// Tipos cuyo redimensionado mantiene proporción por defecto (esquinas).
const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);

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
    return (
      <Rect
        x={0}
        y={0}
        width={w}
        height={h}
        listening={false}
        fillPatternImage={img}
        fillPatternScale={{ x: w / img.width, y: h / img.height }}
      />
    );
  }
  return <Rect x={0} y={0} width={w} height={h} fill="#111315" listening={false} />;
}

export function Lienzo({ maxAncho = 620, maxAlto = 760 }: { maxAncho?: number; maxAlto?: number }) {
  const store = useStoreEditor();
  const documento = useEditor((s) => s.documento);
  const seleccion = useEditor((s) => s.seleccion);
  const { w, h } = documento.formato;
  const escala = Math.min(maxAncho / w, maxAlto / h, 1);

  const trRef = useRef<Konva.Transformer | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  // Guías de alineación activas (en coordenadas de documento). null = ninguna.
  const [guias, setGuias] = useState<{ x: number | null; y: number | null }>({ x: null, y: null });

  const capas: Capa[] = [...documento.capas].sort((a, b) => a.z - b.z);
  const capaSel = documento.capas.find((c) => c.id === seleccion) ?? null;
  const ratioFijo = capaSel ? RATIO_FIJO.has(capaSel.tipo) : false;

  // Adjunta el Transformer al nodo seleccionado.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    const nodo = seleccion ? stage.findOne<Konva.Node>(`#${seleccion}`) : null;
    tr.nodes(nodo ? [nodo] : []);
    tr.getLayer()?.batchDraw();
  }, [seleccion, documento]);

  // Borrar / duplicar la capa seleccionada con teclado (ignora si se está escribiendo).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const escribiendo = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (escribiendo) return;
      const sel = store.getState().seleccion;
      if (!sel) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        store.getState().quitar(sel);
      } else if ((e.key === "d" || e.key === "D") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        store.getState().duplicar(sel);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store]);

  // SMART GUIDES: al arrastrar, imanta los bordes/centros de la capa a los de OTRAS capas y del
  // lienzo, y dibuja las guías. Umbral en px de pantalla -> documento (depende de la escala).
  const onDragMove = (e: Konva.KonvaEventObject<DragEvent>) => {
    const nodo = e.target;
    const id = nodo.id();
    const capa = documento.capas.find((c) => c.id === id);
    if (!capa) return;
    const umbral = 6 / escala;

    const objetivosX: number[] = [0, w / 2, w];
    const objetivosY: number[] = [0, h / 2, h];
    for (const c of documento.capas) {
      if (c.id === id) continue;
      objetivosX.push(c.x, c.x + c.w / 2, c.x + c.w);
      objetivosY.push(c.y, c.y + c.h / 2, c.y + c.h);
    }

    const x = nodo.x();
    const y = nodo.y();
    const bordesX = [x, x + capa.w / 2, x + capa.w];
    const bordesY = [y, y + capa.h / 2, y + capa.h];

    let lineaX: number | null = null;
    let lineaY: number | null = null;
    for (let i = 0; i < 3 && lineaX === null; i++) {
      for (const t of objetivosX) {
        if (Math.abs(bordesX[i] - t) <= umbral) {
          nodo.x(x + (t - bordesX[i]));
          lineaX = t;
          break;
        }
      }
    }
    for (let i = 0; i < 3 && lineaY === null; i++) {
      for (const t of objetivosY) {
        if (Math.abs(bordesY[i] - t) <= umbral) {
          nodo.y(y + (t - bordesY[i]));
          lineaY = t;
          break;
        }
      }
    }
    setGuias({ x: lineaX, y: lineaY });
  };

  const limpiarGuias = () => setGuias({ x: null, y: null });

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
          if (e.target === e.target.getStage()) store.getState().seleccionar(null);
        }}
        onDragMove={onDragMove}
        onDragEnd={limpiarGuias}
      >
        <Layer>
          <FondoNodo fondo={documento.fondo} w={w} h={h} />
          {capas.map((capa) => (
            <CapaNodo
              key={capa.id}
              capa={capa}
              seleccionada={capa.id === seleccion}
              onSelect={() => store.getState().seleccionar(capa.id)}
              onChange={(cambios) => store.getState().actualizar(capa.id, cambios)}
              onGesto={() => store.getState().comenzarGesto()}
            />
          ))}
        </Layer>

        <Layer listening={false}>
          {/* Zona segura (guía fija). */}
          {documento.formato.safe_top > 0 && (
            <Rect x={0} y={documento.formato.safe_top} width={w} height={1} fill="#22d3ee" opacity={0.4} />
          )}
          {documento.formato.safe_bottom > 0 && (
            <Rect x={0} y={h - documento.formato.safe_bottom} width={w} height={1} fill="#22d3ee" opacity={0.4} />
          )}
          {/* Smart guides (mientras se arrastra). */}
          {guias.x !== null && (
            <Line points={[guias.x, 0, guias.x, h]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />
          )}
          {guias.y !== null && (
            <Line points={[0, guias.y, w, guias.y]} stroke="#ec4899" strokeWidth={1 / escala} dash={[6 / escala, 4 / escala]} />
          )}
        </Layer>

        <Layer>
          <Transformer
            ref={trRef}
            rotateEnabled
            keepRatio={ratioFijo}
            enabledAnchors={
              ratioFijo ? ["top-left", "top-right", "bottom-left", "bottom-right"] : undefined
            }
            ignoreStroke
            boundBoxFunc={(oldBox, newBox) => (newBox.width < 8 || newBox.height < 8 ? oldBox : newBox)}
          />
        </Layer>
      </Stage>
    </div>
  );
}
