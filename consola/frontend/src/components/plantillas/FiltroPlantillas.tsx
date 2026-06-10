// Piezas COMPARTIDAS de la organización de plantillas estilo Canva (galería inline del editor y
// galería modal): barra de búsqueda + chips de categoría horizontales + badge de categoría en
// tarjeta. El catálogo y la normalización viven en `lib/categoriasPlantilla.ts`.

import { Search, Tag } from "lucide-react";
import { useMemo, useState } from "react";

import type { PlantillaDiseno } from "@/lib/api";
import {
  CATEGORIAS_PLANTILLA,
  categoriasPresentes,
  coincideBusqueda,
  etiquetaCategoria,
  normalizarCategoria,
} from "@/lib/categoriasPlantilla";

/**
 * Estado de filtrado client-side de una galería: búsqueda (nombre/categoría, acento-insensible) +
 * chip de categoría activa. Los chips salen de las categorías PRESENTES en los datos (lista
 * completa, no la filtrada: así no desaparecen al buscar).
 */
export function useFiltroPlantillas(plantillas: PlantillaDiseno[]) {
  const [q, setQ] = useState("");
  const [categoria, setCategoria] = useState(""); // "" = chip «Todas»
  const presentes = useMemo(() => categoriasPresentes(plantillas), [plantillas]);
  const filtradas = useMemo(
    () =>
      plantillas.filter(
        (p) =>
          (!categoria || normalizarCategoria(p.categoria) === categoria) && coincideBusqueda(p, q),
      ),
    [plantillas, q, categoria],
  );
  return { q, setQ, categoria, setCategoria, presentes, filtradas };
}

/** Barra de búsqueda de plantillas (por nombre o categoría). */
export function BuscadorPlantillas({
  valor,
  onCambiar,
  placeholder = "Buscar plantillas…",
}: {
  valor: string;
  onCambiar: (q: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        type="search"
        role="searchbox"
        aria-label="Buscar plantillas"
        value={valor}
        onChange={(e) => onCambiar(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-input bg-background pl-8 pr-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

/**
 * Chips de categoría en carrusel horizontal (estilo Canva): «Todas» primero y después SOLO las
 * categorías presentes en los datos. Con menos de 2 categorías no se renderiza (sería ruido).
 */
export function ChipsCategoria({
  categorias,
  activa,
  onCambiar,
}: {
  categorias: string[];
  activa: string; // "" = todas
  onCambiar: (slug: string) => void;
}) {
  if (categorias.length < 2) return null;
  const chip = (slug: string, etiqueta: string) => {
    const activo = activa === slug;
    return (
      <button
        key={slug || "__todas__"}
        type="button"
        aria-pressed={activo}
        onClick={() => onCambiar(slug)}
        className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
          activo
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
        }`}
      >
        {etiqueta}
      </button>
    );
  };
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {chip("", "Todas")}
      {categorias.map((slug) => chip(slug, etiquetaCategoria(slug)))}
    </div>
  );
}

/**
 * Badge de categoría en la tarjeta. Con `onCambiar` (modo GESTIÓN) el badge es un selector: un
 * `<select>` nativo invisible encima (catálogo completo + el valor libre actual), así cambiar la
 * categoría de una plantilla existente es un clic, sin diálogo.
 */
export function BadgeCategoria({
  categoria,
  onCambiar,
}: {
  categoria?: string | null;
  onCambiar?: (slug: string) => void;
}) {
  const slug = normalizarCategoria(categoria);
  const etiqueta = etiquetaCategoria(slug);
  const badge = (
    <span
      className={`inline-flex max-w-full shrink items-center gap-0.5 truncate rounded bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground ${
        onCambiar ? "group-hover/badge:text-foreground" : ""
      }`}
    >
      <Tag className="h-2.5 w-2.5 shrink-0" />
      <span className="truncate">{etiqueta}</span>
    </span>
  );
  if (!onCambiar) return badge;
  const enCatalogo = CATEGORIAS_PLANTILLA.some((c) => c.slug === slug);
  return (
    <span className="group/badge relative inline-flex min-w-0" title="Cambiar categoría">
      {badge}
      <select
        aria-label={`Categoría: ${etiqueta}. Cambiar categoría`}
        value={slug}
        onChange={(e) => onCambiar(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {!enCatalogo && <option value={slug}>{etiqueta}</option>}
        {CATEGORIAS_PLANTILLA.map((c) => (
          <option key={c.slug} value={c.slug}>
            {c.etiqueta}
          </option>
        ))}
      </select>
    </span>
  );
}
