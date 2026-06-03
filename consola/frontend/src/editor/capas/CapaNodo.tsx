// Render interactivo de UNA capa como nodo Konva. Es el "proxy" editable del lienzo: el archivo
// final lo hornea el servidor con `dibujarDocumento` (fidelidad exacta de fuentes/cover/degradados).
// Aquí priorizamos manipulación directa (seleccionar, arrastrar, escalar, rotar).

import Konva from "konva";
import { useEffect, useRef } from "react";
import { Ellipse, Group, Image as KonvaImage, Line, Rect, Text } from "react-konva";

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto } from "../documento";
import { useImagen } from "../useImagen";

export interface CapaNodoProps {
  capa: Capa;
  seleccionada: boolean;
  onSelect: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onChange: (cambios: Partial<Capa>) => void;
  onGesto: () => void;
}

const ALIN: Record<string, string> = {
  izquierda: "left",
  centro: "center",
  derecha: "right",
  justificado: "justify",
};

// Recorte estilo object-fit:cover en píxeles de la imagen natural.
function cropCover(img: HTMLImageElement, boxW: number, boxH: number, foco: [number, number]) {
  const ar = boxW / boxH;
  const iar = img.width / img.height;
  let cw: number;
  let ch: number;
  if (iar > ar) {
    ch = img.height;
    cw = ch * ar;
  } else {
    cw = img.width;
    ch = cw / ar;
  }
  return {
    x: (img.width - cw) * (foco[0] ?? 0.5),
    y: (img.height - ch) * (foco[1] ?? 0.5),
    width: cw,
    height: ch,
  };
}

// Imagen con FILTROS Konva (brillo/contraste/saturación/desenfoque) para vista WYSIWYG. El export
// final del servidor usa los mismos filtros (CSS filter, exacto); aquí damos feedback en vivo.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ImagenConFiltros({ img, c, props }: { img: HTMLImageElement; c: CapaImagen; props: any }) {
  const ref = useRef<Konva.Image | null>(null);
  const f = c.filtros;
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (!f) {
      node.filters([]);
      node.clearCache();
      node.getLayer()?.batchDraw();
      return;
    }
    const filtros: (typeof Konva.Filters.Brighten)[] = [];
    if (f.brillo != null && f.brillo !== 1) filtros.push(Konva.Filters.Brighten);
    if (f.contraste != null && f.contraste !== 1) filtros.push(Konva.Filters.Contrast);
    if (f.saturacion != null && f.saturacion !== 1) filtros.push(Konva.Filters.HSL);
    if (f.desenfoque) filtros.push(Konva.Filters.Blur);
    node.filters(filtros);
    node.brightness((f.brillo ?? 1) - 1);
    node.contrast(((f.contraste ?? 1) - 1) * 100);
    node.saturation((f.saturacion ?? 1) - 1);
    node.blurRadius(f.desenfoque ?? 0);
    try {
      node.cache();
    } catch {
      /* imagen aún sin dimensiones: se reintenta en el próximo render */
    }
    node.getLayer()?.batchDraw();
  }, [f, c.w, c.h, c.objeto, img]);

  return (
    <KonvaImage
      ref={ref}
      {...props}
      image={img}
      width={c.w}
      height={c.h}
      crop={c.ajuste === "cover" ? cropCover(img, c.w, c.h, c.foco) : undefined}
    />
  );
}

function textoMuestra(c: CapaTexto): string {
  const base = c.binding === "copy_in"
    ? c.texto || "Titular de ejemplo"
    : c.binding === "etiqueta_default"
      ? c.texto || "PLECA"
      : c.texto;
  return c.mayusculas ? base.toUpperCase() : base;
}

export function CapaNodo({ capa, onSelect, onChange, onGesto }: CapaNodoProps) {
  // Hook SIEMPRE llamado (regla de hooks); null para capas sin imagen.
  const objetoImg = capa.tipo === "imagen" ? capa.objeto : capa.tipo === "logo" ? capa.media_id : null;
  const img = useImagen(objetoImg);

  const comun = {
    id: capa.id,
    x: capa.x,
    y: capa.y,
    rotation: capa.rotacion,
    opacity: capa.opacidad,
    draggable: !capa.bloqueada,
    onMouseDown: onSelect,
    onTap: onSelect,
    onDragStart: onGesto,
    onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => {
      onChange({ x: e.target.x(), y: e.target.y() });
    },
  };

  // Transform genérico: convierte escala -> w/h (y tamaño de fuente en textos), resetea escala.
  const onTransformEnd = (e: Konva.KonvaEventObject<Event>) => {
    const nodo = e.target;
    const sx = nodo.scaleX();
    const sy = nodo.scaleY();
    nodo.scaleX(1);
    nodo.scaleY(1);
    const base: Partial<Capa> = {
      x: nodo.x(),
      y: nodo.y(),
      rotacion: nodo.rotation(),
    } as Partial<Capa>;
    if (capa.tipo === "texto") {
      onChange({
        ...base,
        w: Math.max(16, capa.w * sx),
        tamano: Math.max(8, Math.round((capa as CapaTexto).tamano * sy)),
      } as Partial<Capa>);
    } else {
      onChange({
        ...base,
        w: Math.max(8, capa.w * sx),
        h: Math.max(8, capa.h * sy),
      } as Partial<Capa>);
    }
  };

  const props = { ...comun, onTransformEnd };

  switch (capa.tipo) {
    case "imagen": {
      const c = capa as CapaImagen;
      if (!img) {
        return <Rect {...props} width={c.w} height={c.h} fill="#2a2d31" stroke="#4b5158" dash={[8, 8]} />;
      }
      return <ImagenConFiltros img={img} c={c} props={props} />;
    }
    case "logo": {
      const c = capa as CapaLogo;
      if (c.tipo_logo === "imagen" && img) {
        return <KonvaImage {...props} image={img} width={c.w} height={c.h} />;
      }
      return (
        <Group {...props}>
          <Rect width={c.w} height={c.h} fill={c.wordmark.fondo} cornerRadius={6} />
          <Text
            text={c.wordmark.texto || "LOGO"}
            width={c.w}
            height={c.h}
            align="center"
            verticalAlign="middle"
            fontFamily={c.wordmark.familia}
            fontSize={Math.round(c.h * 0.42)}
            fontStyle={c.wordmark.peso >= 600 ? "bold" : "normal"}
            fill={c.wordmark.color}
          />
        </Group>
      );
    }
    case "texto": {
      const c = capa as CapaTexto;
      return (
        <Text
          {...props}
          text={textoMuestra(c)}
          width={c.w}
          fontFamily={c.familia}
          fontSize={c.tamano}
          fontStyle={c.peso >= 600 ? "bold" : "normal"}
          fill={c.color}
          align={ALIN[c.alineacion] ?? "left"}
          lineHeight={c.interlineado}
          shadowColor={c.sombra?.color}
          shadowOffsetX={c.sombra?.dx}
          shadowOffsetY={c.sombra?.dy}
          shadowEnabled={!!c.sombra}
        />
      );
    }
    case "marco": {
      const c = capa as CapaMarco;
      if (c.forma === "linea") {
        return (
          <Line
            {...props}
            points={[0, 0, c.w, c.h]}
            stroke={c.borde?.color ?? "#FFFFFF"}
            strokeWidth={c.borde?.grosor ?? 4}
          />
        );
      }
      if (c.forma === "elipse") {
        return (
          <Ellipse
            {...props}
            x={c.x + c.w / 2}
            y={c.y + c.h / 2}
            radiusX={c.w / 2}
            radiusY={c.h / 2}
            fill={c.relleno ?? undefined}
            stroke={c.borde?.color}
            strokeWidth={c.borde?.grosor}
          />
        );
      }
      return (
        <Rect
          {...props}
          width={c.w}
          height={c.h}
          cornerRadius={c.radio}
          fill={c.relleno ?? undefined}
          stroke={c.borde?.color}
          strokeWidth={c.borde?.grosor}
        />
      );
    }
    case "overlay": {
      const c = capa as CapaOverlay;
      const band = Math.max(1, c.h * c.alto_frac);
      return (
        <Rect
          {...props}
          y={c.y + c.h - band}
          width={c.w}
          height={band}
          listening={!capa.bloqueada}
          fillLinearGradientStartPoint={{ x: 0, y: 0 }}
          fillLinearGradientEndPoint={{ x: 0, y: band }}
          fillLinearGradientColorStops={[0, `${c.color}00`, 1, c.color]}
        />
      );
    }
    case "grupo":
      // Los grupos se pintan pero no se editan capa a capa en esta versión.
      return (
        <Group {...comun}>
          {capa.capas.map((sub) => (
            <CapaNodo
              key={sub.id}
              capa={sub}
              seleccionada={false}
              onSelect={onSelect}
              onChange={() => {}}
              onGesto={onGesto}
            />
          ))}
        </Group>
      );
    default:
      return null;
  }
}
