// Panel «Elementos» del rail (patrón Canva): inserta capas nuevas con estilos listos para usar
// — textos (titular/subtítulo/cuerpo/pleca), formas (rectángulo/elipse/línea), imagen vacía y
// degradado de legibilidad. Cada inserción queda seleccionada para editarla al instante.

import { Minus, Square, Circle, Image as ImageIcon, Type, PanelBottom } from "lucide-react";

import type { Capa } from "./documento";
import { nuevaCapaImagen, nuevaCapaMarco, nuevaCapaOverlay, nuevaCapaTexto, zTope } from "./documento";
import { useStoreEditor } from "./usarEditor";

// Presets de texto: tamaños/pesos típicos de un post de noticias/deportes.
const TEXTOS: { etiqueta: string; clase: string; parcial: Parameters<typeof nuevaCapaTexto>[0] }[] = [
  { etiqueta: "Titular", clase: "text-2xl font-extrabold", parcial: { texto: "TITULAR", tamano: 96, peso: 800, mayusculas: true, ancla: "abajo" } },
  { etiqueta: "Subtítulo", clase: "text-lg font-bold", parcial: { texto: "Subtítulo", tamano: 56, peso: 700 } },
  { etiqueta: "Cuerpo", clase: "text-sm", parcial: { texto: "Texto de cuerpo", tamano: 40, peso: 400 } },
  { etiqueta: "Pleca / etiqueta", clase: "text-xs font-bold", parcial: { texto: "EN VIVO", tamano: 38, peso: 700, mayusculas: true, chip: { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } } },
];

const FORMAS: { etiqueta: string; Icono: typeof Square; parcial: Parameters<typeof nuevaCapaMarco>[0] }[] = [
  { etiqueta: "Rectángulo", Icono: Square, parcial: { forma: "rect", relleno: "#E30613", borde: null } },
  { etiqueta: "Elipse", Icono: Circle, parcial: { forma: "elipse", relleno: "#E30613", borde: null } },
  { etiqueta: "Línea", Icono: Minus, parcial: { forma: "linea", borde: { color: "#FFFFFF", grosor: 8 }, h: 0, w: 480 } },
  { etiqueta: "Marco", Icono: Square, parcial: { forma: "rect", relleno: null, borde: { color: "#FFFFFF", grosor: 8 } } },
];

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{titulo}</div>
      {children}
    </div>
  );
}

export function PanelElementos() {
  const store = useStoreEditor();

  const insertar = (capa: Capa) => {
    const st = store.getState();
    const doc = st.documento;
    // Centrada horizontalmente en el lienzo, dentro de la zona segura superior.
    const x = Math.round((doc.formato.w - capa.w) / 2);
    const y = capa.tipo === "texto" && capa.ancla === "abajo"
      ? doc.formato.h - doc.formato.safe_bottom
      : Math.max(doc.formato.safe_top, Math.round(doc.formato.h * 0.12));
    st.agregar({ ...capa, x, y, z: zTope(doc) } as Capa);
    st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
  };

  return (
    <div className="flex h-full flex-col overflow-auto p-3">
      <Seccion titulo="Texto">
        <div className="flex flex-col gap-1.5">
          {TEXTOS.map((t) => (
            <button
              key={t.etiqueta}
              onClick={() => insertar(nuevaCapaTexto({ w: 760, ...t.parcial }))}
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-left hover:border-primary hover:bg-accent/50"
            >
              <Type className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className={t.clase}>{t.etiqueta}</span>
            </button>
          ))}
        </div>
      </Seccion>

      <Seccion titulo="Formas">
        <div className="grid grid-cols-2 gap-1.5">
          {FORMAS.map((f) => (
            <button
              key={f.etiqueta}
              onClick={() => insertar(nuevaCapaMarco({ w: 360, h: 240, ...f.parcial }))}
              className="flex flex-col items-center gap-1 rounded-md border border-border px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
            >
              <f.Icono className="h-5 w-5" />
              {f.etiqueta}
            </button>
          ))}
        </div>
      </Seccion>

      <Seccion titulo="Otros">
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => insertar(nuevaCapaImagen("", { w: 540, h: 540 }))}
            className="flex flex-col items-center gap-1 rounded-md border border-border px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
          >
            <ImageIcon className="h-5 w-5" />
            Imagen
          </button>
          <button
            onClick={() => {
              const st = store.getState();
              const doc = st.documento;
              st.agregar(nuevaCapaOverlay({ w: doc.formato.w, h: doc.formato.h, z: zTope(doc) }));
              st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
            }}
            className="flex flex-col items-center gap-1 rounded-md border border-border px-2 py-3 text-xs text-muted-foreground hover:border-primary hover:bg-accent/50"
          >
            <PanelBottom className="h-5 w-5" />
            Degradado
          </button>
        </div>
      </Seccion>
    </div>
  );
}
