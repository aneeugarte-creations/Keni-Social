// Barra CONTEXTUAL de la capa seleccionada (patrón Canva): píldora FLOTANTE sobre el lienzo (la
// aloja la franja reservada del Lienzo, junto a alinear/orden/duplicar/borrar) con los controles
// MÁS usados. SOLO aparece con selección; sin capa seleccionada no pinta nada (los ajustes del
// lienzo/fondo viven en el Inspector, vía «Ajustes» del rail). Lo profundo (todos los ajustes)
// vive en el Inspector, que se abre desde el botón «Ajustes». Opera sobre el store vía contexto.
//
// COLOR: toda capa con color (texto, marco, overlay, logo wordmark) expone aquí su(s)
// ColorControl —el selector completo estilo Canva: espectro, hex, cuentagotas y muestras—, para
// poder recolorear lo seleccionado sin pasar por el Inspector.

import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  AlignVerticalSpaceAround,
  ArrowDownToLine,
  ArrowUpToLine,
  Bold,
  Crop,
  FoldVertical,
  Italic,
  Replace,
  Settings2,
  Strikethrough,
  Underline,
} from "lucide-react";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { tieneCursiva } from "../lib/placa/dibujar.mjs";

import { familiaReal } from "./capas/tipografia";
import { ColorControl } from "./ColorControl";
import type { Capa, CapaLogo, CapaMarco, CapaOverlay, CapaTexto } from "./documento";
import { CATALOGO_FUENTES } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

const ALIN_ICONO = { izquierda: AlignLeft, centro: AlignCenter, derecha: AlignRight, justificado: AlignJustify } as const;
const ALIN_CICLO = ["izquierda", "centro", "derecha", "justificado"] as const;

// Anclaje VERTICAL de la caja de texto (patrón Canva: en el popover de espaciado): valign del
// documento, soportado end-to-end (Konva `verticalAlign` y el camino caja de `dibujarTexto`).
const ANCLAJES = [
  { valor: "arriba", etiqueta: "Anclar arriba", Icono: ArrowUpToLine },
  { valor: "centro", etiqueta: "Anclar al centro", Icono: FoldVertical },
  { valor: "abajo", etiqueta: "Anclar abajo", Icono: ArrowDownToLine },
] as const;

function Sep() {
  return <div className="mx-0.5 h-5 w-px shrink-0 bg-border" />;
}

// Botón con icono, compacto. `deshabilitado` lo apaga (patrón Canva: el tooltip explica por qué).
function BotonIcono({
  onClick,
  activo,
  titulo,
  children,
  ariaLabel,
  deshabilitado,
}: {
  onClick: () => void;
  activo?: boolean;
  titulo: string;
  children: React.ReactNode;
  ariaLabel?: string;
  deshabilitado?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={titulo}
      aria-label={ariaLabel}
      aria-pressed={activo}
      disabled={deshabilitado}
      className={`flex h-8 shrink-0 items-center gap-1 rounded-md px-2 text-sm transition-colors ${
        deshabilitado
          ? "cursor-not-allowed text-muted-foreground/40"
          : activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

// Pequeño stepper numérico (−/valor/+) intuitivo para tamaños y espaciados.
function Stepper({ valor, onChange, min = 1, max = 9999, paso = 1, ancho = "w-12", etiqueta = "Tamaño de letra", icono }: {
  valor: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  paso?: number;
  ancho?: string;
  // Etiqueta accesible y tooltip del control (qué magnitud edita este stepper).
  etiqueta?: string;
  // Icono opcional delante del «−» para distinguir steppers vecinos de un vistazo.
  icono?: React.ReactNode;
}) {
  const [edicion, setEdicion] = useState<string>(String(Math.round(valor)));

  // Sincroniza el estado local SOLO cuando `valor` cambia desde fuera (undo, −/+, otra capa…),
  // nunca mientras se teclea. (El patrón anterior comparaba contra `edicion` y machacaba lo
  // tecleado en cuanto era un número "limpio": teclear en el stepper no funcionaba.)
  const [valorPrevio, setValorPrevio] = useState(valor);
  if (valor !== valorPrevio) {
    setValorPrevio(valor);
    setEdicion(String(Math.round(valor)));
  }

  const fija = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  const commitear = () => {
    const v = Number(edicion);
    if (!isNaN(v)) fija(v);
    setEdicion(String(Math.round(valor)));
  };

  return (
    <div title={etiqueta} className="flex h-8 shrink-0 items-center overflow-hidden rounded-md border border-input">
      {icono && <span className="pl-1.5 text-muted-foreground">{icono}</span>}
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor - paso)} title={`${etiqueta}: menos`}>−</button>
      <input
        type="number"
        value={edicion}
        onChange={(e) => setEdicion(e.target.value)}
        onBlur={commitear}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitear();
          if (e.key === "Escape") setEdicion(String(Math.round(valor)));
        }}
        aria-label={etiqueta}
        className={`${ancho} bg-background px-1 text-center text-sm outline-none`}
      />
      <button className="px-1.5 text-muted-foreground hover:bg-accent" onClick={() => fija(valor + paso)} title={`${etiqueta}: más`}>+</button>
    </div>
  );
}

// Icono de TABLERO DE AJEDREZ (transparencia, convención Canva/GIMP): lucide no trae uno, así que
// es un SVG inline mínimo (marco + dos celdas alternas rellenas).
function IconoTablero({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} aria-hidden="true" fill="none">
      <rect x="1.25" y="1.25" width="13.5" height="13.5" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <rect x="2.5" y="2.5" width="5.5" height="5.5" fill="currentColor" />
      <rect x="8" y="8" width="5.5" height="5.5" fill="currentColor" />
    </svg>
  );
}

// Botón de la barra que abre un POPOVER anclado (patrón Canva: espaciado, transparencia…). El
// popover va en un PORTAL a `body` con posición fija: la píldora tiene `overflow-x-auto` y
// recortaría cualquier hijo absoluto (mismo truco que `ColorControl`). Cierra con clic fuera,
// Escape, scroll o resize.
function BotonPopover({ titulo, ariaLabel, activo, icono, ancho = 256, children }: {
  titulo: string;
  ariaLabel: string;
  // Pinta el botón "encendido" aunque el popover esté cerrado (p. ej. transparencia < 100%).
  activo?: boolean;
  icono: React.ReactNode;
  ancho?: number;
  children: React.ReactNode;
}) {
  const [abierto, setAbierto] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const botonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setAbierto(false);
    const conTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cerrar();
        botonRef.current?.focus();
      }
    };
    window.addEventListener("click", cerrar);
    window.addEventListener("scroll", cerrar, { capture: true });
    window.addEventListener("resize", cerrar);
    window.addEventListener("keydown", conTecla);
    return () => {
      window.removeEventListener("click", cerrar);
      window.removeEventListener("scroll", cerrar, { capture: true });
      window.removeEventListener("resize", cerrar);
      window.removeEventListener("keydown", conTecla);
    };
  }, [abierto]);

  const abrir = () => {
    const r = botonRef.current?.getBoundingClientRect();
    if (r) {
      const left = Math.max(8, Math.min(window.innerWidth - ancho - 8, r.left));
      setPos({ top: r.bottom + 6, left });
    }
    setAbierto((v) => !v);
  };

  return (
    <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
      <button
        ref={botonRef}
        onClick={abrir}
        title={titulo}
        aria-label={ariaLabel}
        aria-expanded={abierto}
        aria-haspopup="dialog"
        className={`flex h-8 items-center gap-1 rounded-md px-2 text-sm transition-colors ${
          abierto || activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
        }`}
      >
        {icono}
      </button>
      {abierto && pos &&
        createPortal(
          <div
            role="dialog"
            aria-label={titulo}
            onClick={(e) => e.stopPropagation()}
            style={{ position: "fixed", top: pos.top, left: pos.left, width: ancho }}
            className="z-[100] flex flex-col gap-3 rounded-md border border-border bg-popover p-3 shadow-lg"
          >
            {children}
          </div>,
          document.body,
        )}
    </div>
  );
}

// Fila de SLIDER con caja numérica editable (patrón Canva del popover de espaciado): el slider
// cubre el rango habitual y la caja admite teclear valores EXACTOS, incluso fuera del paso del
// slider (p. ej. el interlineado 1.14 por defecto de las plantillas: compatibilidad con los
// documentos existentes). Slider y caja comparten etiqueta accesible (roles distintos).
function FilaSlider({ etiqueta, valor, min, max, paso, decimales = 0, onChange }: {
  etiqueta: string;
  valor: number;
  min: number;
  max: number;
  paso: number;
  decimales?: number; // decimales al formatear la caja (0 = enteros)
  onChange: (v: number) => void;
}) {
  // `null` = sin edición en curso (la caja muestra `valor` formateado); string mientras se teclea.
  const [edicion, setEdicion] = useState<string | null>(null);
  const fmt = (v: number) => (decimales ? String(Number(v.toFixed(decimales))) : String(Math.round(v)));
  const fija = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  const commitear = () => {
    if (edicion !== null) {
      const v = Number(edicion);
      if (!isNaN(v)) fija(v);
    }
    setEdicion(null);
  };
  return (
    <div className="flex flex-col gap-1" title={etiqueta}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{etiqueta}</span>
        <input
          type="number"
          aria-label={etiqueta}
          value={edicion ?? fmt(valor)}
          min={min}
          max={max}
          step={paso}
          onChange={(e) => setEdicion(e.target.value)}
          onBlur={commitear}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitear();
            if (e.key === "Escape") setEdicion(null);
          }}
          className="h-7 w-16 rounded-md border border-input bg-background px-1.5 text-center text-sm outline-none"
        />
      </div>
      <input
        type="range"
        aria-label={etiqueta}
        min={min}
        max={max}
        step={paso}
        value={Math.max(min, Math.min(max, valor))}
        onChange={(e) => {
          setEdicion(null);
          fija(Number(e.target.value));
        }}
        className="w-full"
      />
    </div>
  );
}

export function BarraContextual({
  fuentesExtra = [],
  onAbrirAjustes,
  onReencuadrar,
  onReemplazar,
}: {
  fuentesExtra?: string[];
  onAbrirAjustes: () => void;
  onReencuadrar: () => void;
  onReemplazar: () => void;
}) {
  const store = useStoreEditor();
  const capa = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  const seleccionMulti = useEditor((s) => s.seleccionMulti);
  const set = (cambios: Partial<Capa>) => capa && store.getState().actualizar(capa.id, cambios);
  const familias = [...CATALOGO_FUENTES, ...fuentesExtra.filter((f) => !CATALOGO_FUENTES.includes(f as never))];

  // Estilo de PÍLDORA flotante (mismo lenguaje que la barra de alinear/orden del Lienzo).
  const PILDORA =
    "flex min-w-0 max-w-full shrink items-center gap-1 overflow-x-auto rounded-md border border-border bg-popover p-1 shadow-md";

  // Varias capas: la barra contextual se mantiene minimalista (las acciones de alineación viven en
  // la píldora de al lado).
  if (seleccionMulti.length > 1) {
    return (
      <div className={PILDORA}>
        <span className="whitespace-nowrap px-1 text-xs text-muted-foreground">{seleccionMulti.length} capas</span>
        <Sep />
        <BotonIcono titulo="Ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    );
  }

  // Sin selección: nada (la barra solo existe para la capa seleccionada).
  if (!capa) return null;

  return (
    <div className={PILDORA}>
      {capa.tipo === "texto" && (
        <>
          <select
            value={(capa as CapaTexto).familia}
            onChange={(e) => set({ familia: e.target.value } as Partial<Capa>)}
            className="h-8 shrink-0 rounded-md border border-input bg-background px-2 text-sm"
            title="Fuente"
          >
            {familias.map((f) => <option key={f} value={f}>{f}</option>)}
            {!familias.includes((capa as CapaTexto).familia) && <option value={(capa as CapaTexto).familia}>{(capa as CapaTexto).familia}</option>}
          </select>
          <Stepper valor={(capa as CapaTexto).tamano} min={8} max={400} onChange={(v) => set({ tamano: v } as Partial<Capa>)} />
          {/* NEGRITA: toggle grueso 400<->700 (caras reales en todo el catálogo; nada se
              sintetiza). Los pesos finos (Ligera 300, Extranegrita 800, Black 900…) se eligen en
              Ajustes -> Peso y la B los NORMALIZA al usarla (Black+B => 400, Light+B => 700):
              mapeo honesto y predecible, igual que Canva/Docs. `activo` con peso >= 600. */}
          <BotonIcono
            titulo="Negrita (pesos finos en Ajustes → Peso)"
            ariaLabel="Negrita"
            activo={(capa as CapaTexto).peso >= 600}
            onClick={() => set({ peso: (capa as CapaTexto).peso >= 600 ? 400 : 700 } as Partial<Capa>)}
          >
            <Bold className="h-4 w-4" />
          </BotonIcono>
          {(() => {
            const c = capa as CapaTexto;
            // CURSIVA solo para familias con itálica REAL (la misma regla que `dibujar.mjs` y el
            // servidor): fuera de la lista el botón se apaga (patrón Canva) y nada se sintetiza.
            // `familiaReal` resuelve las familias lógicas legadas ("sans"/"condensada").
            const hayCursiva = tieneCursiva(familiaReal(c.familia));
            return (
              <BotonIcono
                titulo={hayCursiva ? "Cursiva" : "Esta fuente no tiene cursiva"}
                ariaLabel="Cursiva"
                activo={hayCursiva && !!c.cursiva}
                deshabilitado={!hayCursiva}
                onClick={() => set({ cursiva: !c.cursiva } as Partial<Capa>)}
              >
                <Italic className="h-4 w-4" />
              </BotonIcono>
            );
          })()}
          {(() => {
            const c = capa as CapaTexto;
            // El texto en ARCO (curva) no se subraya NI se tacha en ningún lado (ni Konva
            // TextPath ni el export): ambos botones se apagan para no prometer nada que la pieza
            // final no tenga.
            const enArco = !!c.curva?.radio;
            return (
              <>
                <BotonIcono
                  titulo={enArco ? "El texto en arco no admite subrayado" : "Subrayado"}
                  ariaLabel="Subrayado"
                  activo={!enArco && !!c.subrayado}
                  deshabilitado={enArco}
                  onClick={() => set({ subrayado: !c.subrayado } as Partial<Capa>)}
                >
                  <Underline className="h-4 w-4" />
                </BotonIcono>
                <BotonIcono
                  titulo={enArco ? "El texto en arco no admite tachado" : "Tachado"}
                  ariaLabel="Tachado"
                  activo={!enArco && !!c.tachado}
                  deshabilitado={enArco}
                  onClick={() => set({ tachado: !c.tachado } as Partial<Capa>)}
                >
                  <Strikethrough className="h-4 w-4" />
                </BotonIcono>
              </>
            );
          })()}
          {/* aA MAYÚSCULAS: transforma EN RENDER (toLocaleUpperCase("es") en Konva y en ambos
              dibujar.mjs) sin destruir lo escrito; la edición inline sigue mostrando el texto
              crudo. Vale también para el texto en arco (ambos renders lo aplican antes de pintar). */}
          <BotonIcono
            titulo="Mayúsculas"
            ariaLabel="Mayúsculas"
            activo={(capa as CapaTexto).mayusculas}
            onClick={() => set({ mayusculas: !(capa as CapaTexto).mayusculas } as Partial<Capa>)}
          >
            <span className="text-[13px] font-semibold leading-none">aA</span>
          </BotonIcono>
          {/* COLOR del texto con el selector completo. Elegir un sólido LIMPIA el degradado del
              relleno si lo había (mismo gesto que PanelMarca): es lo que el clic significa. */}
          <ColorControl
            valor={(capa as CapaTexto).color}
            onChange={(c) => set({ color: c, relleno_degradado: null } as Partial<Capa>)}
            titulo="Color del texto"
          />
          {(() => {
            const al = (capa as CapaTexto).alineacion;
            const Icono = ALIN_ICONO[al];
            return (
              <BotonIcono
                titulo={`Alineación: ${al}`}
                ariaLabel={`Alineación: ${al} (clic para cambiar)`}
                onClick={() => set({ alineacion: ALIN_CICLO[(ALIN_CICLO.indexOf(al) + 1) % ALIN_CICLO.length] } as Partial<Capa>)}
              >
                <Icono className="h-4 w-4" />
              </BotonIcono>
            );
          })()}
          {/* POPOVER DE ESPACIADO (patrón Canva): un solo icono que agrupa interletrado (tracking,
              px) e interlineado (line-height relativo) como sliders con caja numérica, más el
              ANCLAJE vertical de la caja. Todo soportado end-to-end: `interletra`/`interlineado`/
              `valign` viajan en el documento y los pintan igual el editor (Konva `letterSpacing`/
              `lineHeight`/`verticalAlign`) y el export del servidor (`dibujar.mjs`). */}
          {(() => {
            const c = capa as CapaTexto;
            // El anclaje vertical solo actúa en modo CAJA (h>0), igual en Konva (`enCaja` en
            // CapaNodo) y en el export (`boxH` en dibujarTexto): sin caja se apaga con tooltip.
            const enCaja = c.h > 0;
            return (
              <BotonPopover titulo="Espaciado" ariaLabel="Espaciado" icono={<AlignVerticalSpaceAround className="h-4 w-4" />}>
                <FilaSlider
                  etiqueta="Interletrado"
                  valor={c.interletra || 0}
                  min={-20}
                  max={200}
                  paso={1}
                  onChange={(v) => set({ interletra: v } as Partial<Capa>)}
                />
                <FilaSlider
                  etiqueta="Interlineado"
                  valor={c.interlineado}
                  min={1}
                  max={2.5}
                  paso={0.05}
                  decimales={2}
                  onChange={(v) => set({ interlineado: v } as Partial<Capa>)}
                />
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">Anclar caja de texto</span>
                  <div className="flex gap-1">
                    {ANCLAJES.map(({ valor, etiqueta, Icono }) => (
                      <BotonIcono
                        key={valor}
                        titulo={enCaja ? etiqueta : "El anclaje vertical aplica al texto con caja (estira primero el alto de la caja)"}
                        ariaLabel={etiqueta}
                        activo={enCaja && c.valign === valor}
                        deshabilitado={!enCaja}
                        onClick={() => set({ valign: valor } as Partial<Capa>)}
                      >
                        <Icono className="h-4 w-4" />
                      </BotonIcono>
                    ))}
                  </div>
                </div>
              </BotonPopover>
            );
          })()}
        </>
      )}

      {capa.tipo === "imagen" && (
        <>
          <BotonIcono titulo="Reemplazar imagen" onClick={onReemplazar}><Replace className="h-4 w-4" /> Reemplazar</BotonIcono>
          <BotonIcono titulo="Reencuadrar (arrastra la foto dentro del marco)" onClick={onReencuadrar}><Crop className="h-4 w-4" /> Reencuadrar</BotonIcono>
        </>
      )}

      {/* Marco: relleno y borde se recolorean desde la barra (selector completo); lo demás
          —forma, esquinas, degradado…— sigue en el Inspector. */}
      {capa.tipo === "marco" && (() => {
        const c = capa as CapaMarco;
        const borde = c.borde;
        return (
          <>
            {/* La forma «línea» no tiene relleno: solo borde. Elegir un sólido limpia el
                degradado del relleno, igual que en el texto. */}
            {c.forma !== "linea" && (
              <ColorControl
                valor={c.relleno ?? "#000000"}
                onChange={(v) => set({ relleno: v, relleno_degradado: null } as Partial<Capa>)}
                titulo="Color de relleno"
              />
            )}
            {borde && (
              <ColorControl
                valor={borde.color}
                onChange={(v) => set({ borde: { ...borde, color: v } } as Partial<Capa>)}
                titulo="Color del borde"
              />
            )}
          </>
        );
      })()}

      {capa.tipo === "overlay" && (
        <ColorControl
          valor={(capa as CapaOverlay).color}
          onChange={(v) => set({ color: v } as Partial<Capa>)}
          titulo="Color del overlay"
        />
      )}

      {capa.tipo === "logo" && (() => {
        const c = capa as CapaLogo;
        return (
          <>
            {/* Solo el logo WORDMARK (texto) tiene colores; el logo de imagen no. */}
            {c.tipo_logo === "wordmark" && (
              <>
                <ColorControl
                  valor={c.wordmark.color}
                  onChange={(v) => set({ wordmark: { ...c.wordmark, color: v } } as Partial<Capa>)}
                  titulo="Color del wordmark"
                />
                <ColorControl
                  valor={c.wordmark.fondo}
                  onChange={(v) => set({ wordmark: { ...c.wordmark, fondo: v } } as Partial<Capa>)}
                  titulo="Fondo del wordmark"
                />
              </>
            )}
            <BotonIcono titulo="Reemplazar logo" onClick={onReemplazar}><Replace className="h-4 w-4" /> Reemplazar</BotonIcono>
          </>
        );
      })()}

      <div className="ml-auto flex items-center gap-1">
        <Sep />
        {/* TRANSPARENCIA (patrón Canva, icono de tablero): para TODAS las capas. `opacidad` es de
            CapaBase y la respetan igual Konva (`opacity` en CapaNodo) y el export (`globalAlpha`
            en `dibujarCapa`). 100 = opaco (misma escala que Canva). */}
        <BotonPopover
          titulo="Transparencia"
          ariaLabel="Transparencia"
          activo={capa.opacidad < 1}
          ancho={224}
          icono={<IconoTablero className="h-4 w-4" />}
        >
          <FilaSlider
            etiqueta="Transparencia"
            valor={Math.round(capa.opacidad * 100)}
            min={0}
            max={100}
            paso={1}
            onChange={(v) => set({ opacidad: v / 100 } as Partial<Capa>)}
          />
        </BotonPopover>
        <BotonIcono titulo="Todos los ajustes" onClick={onAbrirAjustes}><Settings2 className="h-4 w-4" /> Ajustes</BotonIcono>
      </div>
    </div>
  );
}
