// Control de color reutilizable: muestra el color actual y, al abrirlo, ofrece el selector nativo
// más MUESTRAS de los colores ya usados en el diseño («paleta del documento») y los recientes.
// Pensado para reutilizar color de marca con un clic, sin tener que recordar el hex.
//
// Soporta TRANSPARENCIA: el color se guarda como `#RRGGBB` (opaco) o `#RRGGBBAA` (con alfa). Un
// deslizador de opacidad + botón «Transparente» permiten, p. ej., un degradado de negro a
// transparente (#000000 → #00000000). Las muestras se pintan sobre un tablero de ajedrez para que
// se vea la transparencia.
//
// El popover se renderiza en un PORTAL a `body` con posición fija: así NO lo recorta el
// `overflow` del panel inspector (antes quedaba oculto tras el lienzo).

import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

import type { CapaMarco, CapaOverlay, CapaTexto } from "./documento";
import { useEditor } from "./usarEditor";

// Fondo de tablero de ajedrez (GIMP/Adobe) para visualizar transparencia detrás de una muestra.
const TABLERO: CSSProperties = {
  backgroundImage:
    "linear-gradient(45deg,#bbb 25%,transparent 25%),linear-gradient(-45deg,#bbb 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#bbb 75%),linear-gradient(-45deg,transparent 75%,#bbb 75%)",
  backgroundSize: "8px 8px",
  backgroundPosition: "0 0,0 4px,4px -4px,-4px 0",
  backgroundColor: "#fff",
};

const RE_HEX = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

// Separa un color en su parte RGB (#RRGGBB, lo que entiende <input type=color>) y su alfa 0..255.
function partes(v: string): { rgb: string; alfa: number } {
  if (/^#[0-9a-fA-F]{8}$/.test(v)) return { rgb: v.slice(0, 7), alfa: parseInt(v.slice(7, 9), 16) };
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return { rgb: v, alfa: 255 };
  return { rgb: "#000000", alfa: 255 };
}

// Combina RGB + alfa en un color canónico: `#RRGGBB` si es opaco (no ensucia el JSON), `#RRGGBBAA` si no.
function combina(rgb: string, alfa: number): string {
  const a = Math.max(0, Math.min(255, Math.round(alfa)));
  if (a >= 255) return rgb.toUpperCase();
  return (rgb + a.toString(16).padStart(2, "0")).toUpperCase();
}

// Colores recientes a nivel de módulo (persisten entre selecciones y pestañas durante la sesión).
const recientes: string[] = [];
function recordar(color: string) {
  const c = color.toUpperCase();
  const i = recientes.indexOf(c);
  if (i >= 0) recientes.splice(i, 1);
  recientes.unshift(c);
  if (recientes.length > 10) recientes.length = 10;
}

// Recolecta los colores DISTINTOS presentes en el documento (texto, marcos, chips, overlays, fondo).
function coloresDelDocumento(
  capas: unknown[],
  fondo: { color?: string; degradado?: { desde: string; hasta: string } },
): string[] {
  const set = new Set<string>();
  const add = (c?: string | null) => { if (c && RE_HEX.test(c)) set.add(c.toUpperCase()); };
  for (const capa of capas as { tipo: string }[]) {
    if (capa.tipo === "texto") { add((capa as CapaTexto).color); add((capa as CapaTexto).chip?.color); add((capa as CapaTexto).contorno?.color); }
    if (capa.tipo === "marco") { add((capa as CapaMarco).relleno); add((capa as CapaMarco).borde?.color); }
    if (capa.tipo === "overlay") add((capa as CapaOverlay).color);
  }
  add(fondo.color);
  add(fondo.degradado?.desde);
  add(fondo.degradado?.hasta);
  return [...set];
}

// Colores de la MARCA ACTIVA (identidad de `plantillaMarca`: rojo/tinta/blanco), como lista de hex
// para ofrecerlos en el ColorControl con un clic. Obtiene la marca por su cuenta (`useMarcaActiva`),
// así el control se usa igual en todos los call-sites; si no hay marca activa => lista vacía.
function useColoresMarca(): string[] {
  const { marcaActiva } = useMarcaActiva();
  const { data } = useQuery({
    queryKey: ["plantilla-marca", marcaActiva],
    queryFn: ({ signal }) => api.plantillaMarca(marcaActiva!, signal),
    enabled: !!marcaActiva,
    staleTime: 5 * 60_000,
  });
  const p = data?.plantilla;
  if (!p) return [];
  // Dedup preservando orden (rojo, tinta, blanco), filtrando hex válidos.
  const vistos = new Set<string>();
  const out: string[] = [];
  for (const c of [p.rojo, p.tinta, p.blanco]) {
    if (c && RE_HEX.test(c)) {
      const up = c.toUpperCase();
      if (!vistos.has(up)) { vistos.add(up); out.push(up); }
    }
  }
  return out;
}

function Muestras({ colores, valor, onPick }: { colores: string[]; valor: string; onPick: (c: string) => void }) {
  if (colores.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {colores.map((c) => (
        <button
          key={c}
          onClick={() => onPick(c)}
          title={c}
          style={TABLERO}
          className={`h-5 w-5 overflow-hidden rounded border ${c.toUpperCase() === valor.toUpperCase() ? "border-primary ring-1 ring-primary" : "border-border"}`}
        >
          <span className="block h-full w-full" style={{ background: c }} />
        </button>
      ))}
    </div>
  );
}

export function ColorControl({ valor, onChange }: { valor: string; onChange: (c: string) => void }) {
  const [abierto, setAbierto] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const botonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const capas = useEditor((s) => s.documento.capas);
  const fondo = useEditor((s) => s.documento.fondo);
  const delDoc = coloresDelDocumento(capas, fondo);
  const deMarca = useColoresMarca();
  const { rgb, alfa } = partes(valor);

  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setAbierto(false);
    // Cierra al scrollear (capture: true) o cambiar tamaño de ventana.
    const cerrarEnScroll = () => cerrar();
    const cerrarEnResize = () => cerrar();
    const conTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cerrar();
        botonRef.current?.focus();
      }
    };
    // Enfoca el primer control al abrir.
    setTimeout(() => inputRef.current?.focus(), 0);
    window.addEventListener("click", cerrar);
    window.addEventListener("scroll", cerrarEnScroll, { capture: true });
    window.addEventListener("resize", cerrarEnResize);
    window.addEventListener("keydown", conTecla);
    return () => {
      window.removeEventListener("click", cerrar);
      window.removeEventListener("scroll", cerrarEnScroll, { capture: true });
      window.removeEventListener("resize", cerrarEnResize);
      window.removeEventListener("keydown", conTecla);
    };
  }, [abierto]);


  const abrir = () => {
    const r = botonRef.current?.getBoundingClientRect();
    if (r) {
      const ancho = 192; // w-48
      const left = Math.max(8, Math.min(window.innerWidth - ancho - 8, r.right - ancho));
      setPos({ top: r.bottom + 4, left });
    }
    setAbierto((v) => !v);
  };

  const elegir = (c: string) => { recordar(c); onChange(c); };
  const setRgb = (nuevoRgb: string) => elegir(combina(nuevoRgb, alfa));
  const setAlfa = (nuevoAlfa: number) => elegir(combina(rgb, nuevoAlfa));

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        ref={botonRef}
        onClick={abrir}
        style={TABLERO}
        className="relative h-6 w-10 overflow-hidden rounded border border-input"
        title="Color"
      >
        <span className="absolute inset-0" style={{ background: valor }} />
      </button>
      {abierto && pos &&
        createPortal(
          <div
            ref={popoverRef}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
            style={{ position: "fixed", top: pos.top, left: pos.left, width: 192 }}
            className="z-[100] rounded-md border border-border bg-popover p-2 shadow-lg"
          >
            <input
              ref={inputRef}
              type="color"
              value={rgb}
              onChange={(e) => setRgb(e.target.value)}
              className="mb-2 h-7 w-full cursor-pointer"
            />
            {/* Opacidad (alfa). 0 = transparente. */}
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <span>Opacidad</span>
              <span>{Math.round((alfa / 255) * 100)}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={255}
              value={alfa}
              onChange={(e) => setAlfa(Number(e.target.value))}
              className="mb-2 w-full"
            />
            <button
              onClick={() => setAlfa(0)}
              style={TABLERO}
              className="mb-2 w-full overflow-hidden rounded border border-border py-1 text-[11px] text-foreground hover:border-primary"
            >
              <span className="rounded bg-background/70 px-1">Transparente</span>
            </button>
            {deMarca.length > 0 && (
              <>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Marca</div>
                <Muestras colores={deMarca} valor={valor} onPick={elegir} />
              </>
            )}
            {delDoc.length > 0 && (
              <>
                <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">En el diseño</div>
                <Muestras colores={delDoc} valor={valor} onPick={elegir} />
              </>
            )}
            {recientes.length > 0 && (
              <>
                <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Recientes</div>
                <Muestras colores={recientes} valor={valor} onPick={elegir} />
              </>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
