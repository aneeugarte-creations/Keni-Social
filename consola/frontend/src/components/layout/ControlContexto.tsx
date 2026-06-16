/**
 * CONTROL DE CONTEXTO unificado de la barra superior: junta en UN solo dropdown los tres
 * selectores que antes vivían sueltos (`SwitchMarca` + Red + Línea de `SwitchFiltrosPublicacion`).
 *
 *   - MARCA (workspace): la consola entera trabaja sobre la marca activa. Si el usuario es de
 *     una sola marca y la ruta no usa filtros, se muestra un chip fijo (nada que cambiar). Si
 *     está FUERA de su marca de casa, el trigger se resalta en ámbar y el panel ofrece "Volver",
 *     para no publicar en la marca equivocada por inercia.
 *   - RED y LÍNEA: filtros globales de la superficie de contenido/feed. Solo aparecen en las
 *     rutas donde aplican (`rutaUsaFiltrosPublicacion`).
 *
 * Es un popover hand-rolled (como `MenuAcciones`): cierra al hacer clic fuera o con Escape. No
 * anida `Select` de Radix (que portaliza) para evitar conflictos con el clic-fuera; pinta sus
 * opciones como filas, lo que además es más cómodo en móvil (objetivos de toque grandes).
 */
import { Building2, Check, ChevronDown, Undo2 } from "lucide-react";
import * as React from "react";
import { useLocation } from "react-router-dom";

import {
  FILTRO_TODOS,
  rutaUsaFiltrosPublicacion,
  useFiltrosPublicacion,
} from "@/hooks/filtros-contenido-contexto";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useFuentesDeMarcas } from "@/hooks/use-fuentes-marcas";
import { cn } from "@/lib/utils";

/** Una fila seleccionable del panel (opción de marca / red / línea). */
function Fila({
  activo,
  onClick,
  children,
  fontFamily,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
  // Tipografía de marca para el nombre (las opciones de MARCA se pintan con su fuente real). El
  // color no cambia: solo la familia.
  fontFamily?: string;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={activo}
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-sm px-2 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
        activo ? "font-medium text-foreground" : "text-muted-foreground",
      )}
    >
      <span className="truncate" style={fontFamily ? { fontFamily } : undefined}>
        {children}
      </span>
      {activo && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
    </button>
  );
}

/** Un grupo del panel con su encabezado en versalitas. */
function Grupo({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="px-1 py-1">
      <p className="px-2 pb-0.5 pt-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {titulo}
      </p>
      {children}
    </div>
  );
}

export function ControlContexto() {
  const { pathname } = useLocation();
  const {
    marcaActiva,
    esMultiMarca,
    puedeTodas,
    marcasParaSwitch,
    nombreActiva,
    enMarcaPrimaria,
    marcaPrimaria,
    cambiarMarca,
    volverAPrimaria,
  } = useMarcaActiva();
  const { red, linea, redes, lineasElegibles, cambiarRed, cambiarLinea } = useFiltrosPublicacion();

  const [abierto, setAbierto] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  // Tipografías de marca: el nombre de cada marca se pinta con su fuente real. Solo descargamos los
  // binarios de las marcas visibles —la activa siempre (chip/píldora) y, al abrir el panel, todas
  // las del selector— para no traer todas las fuentes en cada página.
  const idsFuentes = React.useMemo(() => {
    const ids = marcaActiva ? [marcaActiva] : [];
    if (abierto) ids.push(...marcasParaSwitch.map((m) => m.id));
    return ids;
  }, [abierto, marcaActiva, marcasParaSwitch]);
  const fuentesMarca = useFuentesDeMarcas(idsFuentes);
  const fuenteActiva = marcaActiva ? fuentesMarca.get(marcaActiva) : undefined;

  const usaFiltros = rutaUsaFiltrosPublicacion(pathname);
  const fueraDeCasa = !enMarcaPrimaria && marcaPrimaria !== null;
  const filtrosActivos = usaFiltros && (red !== FILTRO_TODOS || linea !== FILTRO_TODOS);
  const etiquetaMarca = marcaActiva ? (nombreActiva ?? marcaActiva) : "Todas las marcas";

  // Editor de una sola marca en una ruta SIN filtros: no hay nada que conmutar → chip fijo.
  if (!esMultiMarca && !usaFiltros) {
    if (!marcaActiva) return null;
    return (
      <span className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 text-sm font-medium text-foreground">
        <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="max-w-[140px] truncate" style={fuenteActiva ? { fontFamily: fuenteActiva } : undefined}>
          {etiquetaMarca}
        </span>
      </span>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-label="Marca y filtros"
        onClick={() => setAbierto((v) => !v)}
        className={cn(
          "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors",
          fueraDeCasa
            // Aviso «marca ajena» vía tokens `--aviso-*`: fuera del editor resuelven a los ámbar
            // de siempre (amber-500/60, amber-500/10, amber-700/400); en la barra naranja del
            // editor pasan a píldora BLANCA sólida con texto ámbar-700, que sí se lee (el ámbar
            // oscuro sobre el degradado era casi invisible, justo en el aviso de seguridad).
            ? "border-[hsl(var(--aviso-borde))] bg-[hsl(var(--aviso-superficie))] text-[hsl(var(--aviso-texto))]"
            // `hover:bg-accent` (no `bg-muted`): en la barra del editor `--muted` es blanco para la
            // píldora translúcida; un hover a muted sólido dejaría el texto ilegible. El
            // token `accent` es el de hover de toda la app (gris idéntico fuera del editor).
            // El hover accent solo CERRADO: abierto conserva la píldora `--control-activo`
            // (un hover naranja bajo el texto naranja la dejaría ilegible justo tras abrir).
            : cn("border-border bg-muted/40 text-foreground", !abierto && "hover:bg-accent"),
          // Panel ABIERTO con el mismo lenguaje que «Más»/«Adaptar»/campana: píldora
          // `--control-activo`. El aviso de marca ajena MANDA sobre este estado (no se pisa).
          !fueraDeCasa &&
            abierto &&
            "bg-[hsl(var(--control-activo))] text-[hsl(var(--control-activo-foreground))]",
        )}
      >
        <Building2 className="h-4 w-4 shrink-0 opacity-70" aria-hidden="true" />
        <span
          className="max-w-[120px] truncate font-medium"
          style={fuenteActiva ? { fontFamily: fuenteActiva } : undefined}
        >
          {etiquetaMarca}
        </span>
        {filtrosActivos && (
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-foreground" aria-hidden="true" />
        )}
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" aria-hidden="true" />
      </button>

      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 max-h-[70vh] w-64 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
        >
          {esMultiMarca ? (
            <Grupo titulo="Marca">
              {puedeTodas && (
                <Fila activo={!marcaActiva} onClick={() => cambiarMarca(null)}>
                  Todas las marcas
                </Fila>
              )}
              {marcasParaSwitch.map((m) => (
                <Fila
                  key={m.id}
                  activo={marcaActiva === m.id}
                  onClick={() => cambiarMarca(m.id)}
                  fontFamily={fuentesMarca.get(m.id)}
                >
                  {m.nombre}
                </Fila>
              ))}
              {fueraDeCasa && (
                <button
                  type="button"
                  onClick={volverAPrimaria}
                  className="mt-1 flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm font-medium text-amber-700 transition-colors hover:bg-amber-500/10 dark:text-amber-400"
                >
                  <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Volver a tu marca
                </button>
              )}
            </Grupo>
          ) : (
            marcaActiva && (
              <Grupo titulo="Marca">
                <p
                  className="px-2 py-1.5 text-sm font-medium text-foreground"
                  style={fuenteActiva ? { fontFamily: fuenteActiva } : undefined}
                >
                  {etiquetaMarca}
                </p>
              </Grupo>
            )
          )}

          {usaFiltros && (
            <>
              <div className="my-1 h-px bg-border" />
              <Grupo titulo="Red">
                <Fila activo={red === FILTRO_TODOS} onClick={() => cambiarRed(FILTRO_TODOS)}>
                  Todas las redes
                </Fila>
                {redes.map((r) => (
                  <Fila key={r.id} activo={red === r.id} onClick={() => cambiarRed(r.id)}>
                    {r.nombre}
                  </Fila>
                ))}
              </Grupo>
              <Grupo titulo="Línea editorial">
                <Fila activo={linea === FILTRO_TODOS} onClick={() => cambiarLinea(FILTRO_TODOS)}>
                  Todas las líneas editoriales
                </Fila>
                {lineasElegibles.map((l) => (
                  <Fila key={l.id} activo={linea === l.id} onClick={() => cambiarLinea(l.id)}>
                    {l.nombre}
                  </Fila>
                ))}
              </Grupo>
            </>
          )}
        </div>
      )}
    </div>
  );
}
