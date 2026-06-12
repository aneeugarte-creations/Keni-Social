import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, Search } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { hojasDeApp } from "@/components/layout/apps-scope";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PaletaContexto, type ValorPaleta } from "@/hooks/paleta-contexto";

/** Una página navegable de la paleta (una hoja de una app del catálogo). */
interface Entrada {
  ruta: string;
  /** Etiqueta de la hoja. */
  etiqueta: string;
  /** Nombre de la app a la que pertenece. */
  app: string;
  /** Texto de búsqueda precomputado (app + página, en minúsculas, sin acentos). */
  busqueda: string;
}

/** Normaliza para buscar sin distinguir acentos ni mayúsculas. */
function normalizar(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/**
 * Paleta de comandos (⌘K / Ctrl-K), SOLO navegación. Diálogo accesible (sobre
 * `ui/dialog`, sin la dependencia `cmdk`): input de búsqueda + lista filtrable
 * de TODAS las páginas navegables (por cada app del catálogo, sus hojas
 * `hojasDeApp`, etiquetadas "App › Página"). ↑/↓ mueve, ↵ navega y cierra, Esc
 * cierra. El estado de apertura lo controla el provider (`PaletaProvider`).
 */
function PaletaDialogo({
  abierta,
  onAbierta,
}: {
  abierta: boolean;
  onAbierta: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const [consulta, setConsulta] = React.useState("");
  const [seleccion, setSeleccion] = React.useState(0);
  const listaRef = React.useRef<HTMLUListElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Catálogo (mismo queryKey que Sidebar/AppShell: se resuelve una sola vez).
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });
  const apps = catalogoQuery.data?.apps;

  // TODAS las páginas navegables: las hojas de cada app del catálogo.
  const entradas = React.useMemo<Entrada[]>(() => {
    const lista: Entrada[] = [];
    for (const app of apps ?? []) {
      for (const hoja of hojasDeApp(app)) {
        lista.push({
          ruta: hoja.ruta,
          etiqueta: hoja.etiqueta,
          app: app.etiqueta,
          busqueda: normalizar(`${app.etiqueta} ${hoja.etiqueta}`),
        });
      }
    }
    return lista;
  }, [apps]);

  // Filtro: match en etiqueta de app O de página (texto normalizado).
  const filtradas = React.useMemo(() => {
    const q = normalizar(consulta.trim());
    if (!q) return entradas;
    return entradas.filter((e) => e.busqueda.includes(q));
  }, [entradas, consulta]);

  // Al abrir: limpia consulta, resetea selección y enfoca el input (accesible:
  // foco al abrir el diálogo, en vez de `autoFocus`).
  React.useEffect(() => {
    if (abierta) {
      setConsulta("");
      setSeleccion(0);
      // El portal del diálogo monta tras este efecto; enfoca en el siguiente frame.
      const id = window.requestAnimationFrame(() => inputRef.current?.focus());
      return () => window.cancelAnimationFrame(id);
    }
  }, [abierta]);

  // Mantén la selección dentro del rango al filtrar.
  React.useEffect(() => {
    setSeleccion((s) => (s >= filtradas.length ? 0 : s));
  }, [filtradas.length]);

  // Lleva a la vista el ítem seleccionado al moverse con el teclado.
  React.useEffect(() => {
    const el = listaRef.current?.querySelector<HTMLElement>(`[data-indice="${seleccion}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [seleccion]);

  function irA(entrada: Entrada | undefined) {
    if (!entrada) return;
    onAbierta(false);
    navigate(entrada.ruta);
  }

  function onTeclaInput(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSeleccion((s) => (filtradas.length ? (s + 1) % filtradas.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSeleccion((s) => (filtradas.length ? (s - 1 + filtradas.length) % filtradas.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      irA(filtradas[seleccion]);
    }
    // Esc lo gestiona el Dialog (onOpenChange) por defecto.
  }

  return (
    <Dialog open={abierta} onOpenChange={onAbierta}>
      <DialogContent
        className="top-[20%] max-w-xl translate-y-0 gap-0 overflow-hidden p-0"
        aria-label="Paleta de comandos"
      >
        <DialogTitle className="sr-only">Buscar páginas</DialogTitle>
        <DialogDescription className="sr-only">
          Escribe para filtrar; usa las flechas y Enter para navegar.
        </DialogDescription>

        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            onKeyDown={onTeclaInput}
            placeholder="Buscar páginas…"
            aria-label="Buscar páginas"
            aria-controls="paleta-resultados"
            aria-activedescendant={
              filtradas[seleccion] ? `paleta-opcion-${seleccion}` : undefined
            }
            role="combobox"
            aria-expanded
            // `text-base md:text-sm`: 16px en móvil para no disparar el auto-zoom de iOS al enfocar.
            className="h-11 w-full bg-transparent text-base text-foreground placeholder:text-muted-foreground focus-visible:outline-none md:text-sm"
          />
        </div>

        <ul
          ref={listaRef}
          id="paleta-resultados"
          role="listbox"
          aria-label="Páginas"
          className="max-h-72 overflow-y-auto p-1"
        >
          {filtradas.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              Sin resultados
            </li>
          ) : (
            filtradas.map((entrada, i) => {
              const activa = i === seleccion;
              return (
                <li key={entrada.ruta}>
                  <button
                    type="button"
                    id={`paleta-opcion-${i}`}
                    data-indice={i}
                    role="option"
                    aria-selected={activa}
                    onClick={() => irA(entrada)}
                    onMouseMove={() => setSeleccion(i)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                      activa ? "bg-accent text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {entrada.app === "" && (
                      <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    {entrada.app !== "" && (
                      <span className="text-muted-foreground">{entrada.app}</span>
                    )}
                    {entrada.app !== "" && (
                      <span className="text-muted-foreground/60" aria-hidden="true">
                        ›
                      </span>
                    )}
                    <span className={cn(activa && "font-medium text-foreground")}>
                      {entrada.etiqueta}
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Provider de la paleta de comandos: monta el diálogo UNA vez y registra el
 * listener global de teclado (⌘K en mac / Ctrl-K en Windows/Linux). Expone
 * `abrir()` vía contexto para que el trigger del sidebar la abra sin
 * prop-drilling. Envuelve el shell (AppShell).
 */
export function PaletaProvider({ children }: { children: React.ReactNode }) {
  const [abierta, setAbierta] = React.useState(false);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setAbierta((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const valor = React.useMemo<ValorPaleta>(() => ({ abrir: () => setAbierta(true) }), []);

  return (
    <PaletaContexto.Provider value={valor}>
      {children}
      <PaletaDialogo abierta={abierta} onAbierta={setAbierta} />
    </PaletaContexto.Provider>
  );
}
