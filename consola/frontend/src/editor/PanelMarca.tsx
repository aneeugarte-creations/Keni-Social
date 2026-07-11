// Panel «Marca» del rail (Brand Kit estilo Canva): la identidad de la marca del documento a un
// clic. Construido SOLO con datos de marca que YA existen en el sistema:
//   - Plantilla de marca (`api.plantillaMarca`): logo principal + colores (rojo/tinta/blanco)
//     + wordmark de respaldo.
//   - Activos de marca (`api.marcaActivos`): logos, paletas (metadatos.colores) y tipografías.
//     Los artes/infografías/iconos/fondos viven en «Galería»; aquí solo el KIT de identidad.
//   - Marca activa global (`MarcaActivaContexto`, opcional): aviso si difiere de la del documento.
//
// Interacciones (mismo mecanismo que PanelGaleria):
//   - Logo: clic inserta una capa logo (o arrástralo al lienzo con el payload x-keni-activo).
//   - Color: clic lo aplica a la capa seleccionada (texto/overlay: color; marco: relleno) o,
//     sin selección compatible, al FONDO del documento.
//   - Tipografía: clic aplica la familia a la capa de texto seleccionada.

import { useQuery } from "@tanstack/react-query";
import { useContext } from "react";
import { toast } from "sonner";

import { MarcaActivaContexto } from "@/hooks/marca-activa-contexto";
import { api, urlMedia, type ActivoMarca } from "@/lib/api";

import type { Capa } from "./documento";
import { nuevaCapaLogo, zTope } from "./documento";
import { useStoreEditor } from "./usarEditor";

/** Color de marca con etiqueta legible (para tooltip). */
type ColorMarca = { color: string; etiqueta: string };

/** Familia tipográfica de un activo `tipografia` (metadatos.familia con fallback al nombre). */
function familiaDe(a: ActivoMarca): string {
  return ((a.metadatos?.familia as string) || a.nombre || "").trim();
}

export function PanelMarca({ marca }: { marca: string }) {
  const store = useStoreEditor();
  // Contexto OPCIONAL (useContext directo, no el hook que lanza): el editor también se monta en
  // tests/overlays sin MarcaActivaProvider y el panel debe degradar sin romper (sin aviso).
  const ctxMarca = useContext(MarcaActivaContexto);

  // Identidad de la plantilla de marca (logo + colores + wordmark). 404 si la marca no existe en
  // el catálogo de plantillas: sin reintentos y el panel sigue con los activos.
  const plantillaQuery = useQuery({
    queryKey: ["plantilla-marca", marca],
    queryFn: ({ signal }) => api.plantillaMarca(marca, signal),
    enabled: !!marca,
    retry: false,
  });
  // Activos de la marca (misma queryKey que PanelGaleria: comparten caché).
  const activosQuery = useQuery({
    queryKey: ["marca-activos", marca],
    queryFn: ({ signal }) => api.marcaActivos({ marca: marca || undefined }, signal),
  });
  const cargando = plantillaQuery.isLoading || activosQuery.isLoading;

  const plantilla = plantillaQuery.data?.plantilla ?? null;
  const activos = activosQuery.data?.activos ?? [];
  const logosActivos = activos.filter((a) => a.tipo === "logo" && a.objeto);
  const paletas = activos.filter((a) => a.tipo === "paleta");
  const tipografias = activos.filter((a) => a.tipo === "tipografia");

  // Nombre legible de la marca del documento: catálogo del switch global → activos → id.
  const nombreMarca =
    ctxMarca?.marcasParaSwitch.find((m) => m.id === marca)?.nombre ??
    activos[0]?.marca_nombre ??
    marca;
  // Aviso si el documento es de OTRA marca que la activa global (con "Todas" no se avisa).
  const fueraDeMarca =
    !!ctxMarca && !!marca && ctxMarca.marcaActiva !== null && ctxMarca.marcaActiva !== marca;

  // ── Colores de marca: plantilla (rojo/tinta/blanco) + paletas de activos, sin duplicados. ──
  const colores: ColorMarca[] = [];
  const vistos = new Set<string>();
  const pon = (color: unknown, etiqueta: string) => {
    const c = typeof color === "string" ? color.trim() : "";
    if (!/^#[0-9a-fA-F]{3,8}$/.test(c)) return;
    const clave = c.toLowerCase();
    if (vistos.has(clave)) return;
    vistos.add(clave);
    colores.push({ color: c, etiqueta });
  };
  if (plantilla) {
    pon(plantilla.rojo, "Color principal");
    pon(plantilla.tinta, "Tinta");
    pon(plantilla.blanco, "Blanco");
  }
  for (const p of paletas) {
    const lista = (p.metadatos?.colores as unknown[] | undefined) ?? [];
    lista.forEach((c, i) => pon(c, `${p.nombre || "Paleta"} · ${i + 1}`));
  }

  // ── Tipografías: familias únicas (las FontFace ya las carga useFuentesMarca en el editor). ──
  const familias = [...new Set(tipografias.map(familiaDe).filter(Boolean))];

  /** Inserta un logo (id de media) como capa logo y la selecciona (igual que PanelGaleria). */
  const insertarLogo = (mediaId: string) => {
    const st = store.getState();
    st.agregar(nuevaCapaLogo(mediaId, { z: zTope(st.documento), x: 56, y: 56, w: 320, h: 120 }));
    // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
    const capas = store.getState().documento.capas;
    st.seleccionar(capas[capas.length - 1]?.id ?? null);
  };

  /** Aplica un color de marca a la capa seleccionada compatible; si no, al fondo del lienzo. */
  const aplicarColor = (color: string) => {
    const st = store.getState();
    const sel = st.seleccion;
    const capa = sel ? st.documento.capas.find((c) => c.id === sel) : null;
    if (capa && (capa.tipo === "texto" || capa.tipo === "overlay")) {
      // El degradado del relleno (si lo hay) manda sobre el color sólido: se limpia.
      st.actualizar(capa.id, { color, relleno_degradado: null } as Partial<Capa>);
      toast.success(`Color ${color} aplicado a la capa.`);
      return;
    }
    if (capa && capa.tipo === "marco") {
      st.actualizar(capa.id, { relleno: color, relleno_degradado: null } as Partial<Capa>);
      toast.success(`Color ${color} aplicado al marco.`);
      return;
    }
    st.setFondo({ tipo: "color", color });
    toast.success(`Color ${color} aplicado al fondo.`);
  };

  /** Aplica una familia tipográfica de marca a la capa de TEXTO seleccionada. */
  const aplicarFamilia = (familia: string) => {
    const st = store.getState();
    const sel = st.seleccion;
    const capa = sel ? st.documento.capas.find((c) => c.id === sel) : null;
    if (capa?.tipo === "texto") {
      st.actualizar(capa.id, { familia } as Partial<Capa>);
      toast.success(`Fuente «${familia}» aplicada al texto.`);
    } else {
      toast.info("Selecciona una capa de texto para aplicarle esta tipografía.");
    }
  };

  // Miniatura de logo clicable+arrastrable (mismo payload de drop que PanelGaleria: el lienzo ya
  // sabe recibir "application/x-keni-activo").
  const miniaturaLogo = (mediaId: string, nombre: string, url?: string) => (
    <button
      onClick={() => insertarLogo(mediaId)}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(
          "application/x-keni-activo",
          JSON.stringify({ objeto: mediaId, tipo: "logo" }),
        );
        e.dataTransfer.effectAllowed = "copy";
      }}
      title={`${nombre} — clic para insertar, o arrástralo al lienzo`}
      className="block aspect-square w-full overflow-hidden rounded border border-border bg-[repeating-conic-gradient(#0000_0_25%,#8884_0_50%)] bg-[length:16px_16px] hover:ring-2 hover:ring-primary"
    >
      <img
        src={url ?? urlMedia(mediaId)}
        alt={nombre}
        draggable={false}
        className="pointer-events-none h-full w-full object-contain"
      />
    </button>
  );

  return (
    <div className="flex h-full flex-col">
      {/* Cabecera: de QUÉ marca es este kit (la del documento, no la del switch global). */}
      <div className="border-b border-border px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Kit de marca
        </span>
        <div className="truncate text-sm font-semibold" title={nombreMarca || undefined}>
          {nombreMarca || "Sin marca"}
        </div>
      </div>

      {fueraDeMarca && (
        <div className="border-b border-border bg-amber-100 px-3 py-1.5 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-400">
          Este diseño es de «{nombreMarca}», pero tu marca activa es «
          {ctxMarca?.nombreActiva ?? ctxMarca?.marcaActiva}». El kit mostrado es el del diseño.
        </div>
      )}

      <div className="flex-1 overflow-auto p-3">
        {cargando && <p className="p-2 text-sm text-muted-foreground">Cargando…</p>}

        {!cargando && (
          <>
            {/* LOGOS: el principal de la plantilla + los activos tipo logo. */}
            <div className="mb-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Logos
              </div>
              {plantilla?.logo || logosActivos.length > 0 ? (
                <div className="grid grid-cols-3 gap-1.5">
                  {plantilla?.logo && (
                    <div>
                      {miniaturaLogo(plantilla.logo, "Logo principal", plantilla.logo_url || undefined)}
                      <div className="mt-0.5 truncate text-center text-[10px] text-muted-foreground">
                        Principal
                      </div>
                    </div>
                  )}
                  {logosActivos
                    .filter((a) => a.objeto !== plantilla?.logo)
                    .map((a) => (
                      <div key={a.id}>{miniaturaLogo(a.objeto, a.nombre || "Logo")}</div>
                    ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Esta marca aún no tiene logos. Súbelos desde la pestaña «Galería».
                  {plantilla?.wordmark
                    ? ` Mientras tanto se usa el wordmark «${plantilla.wordmark}».`
                    : ""}
                </p>
              )}
            </div>

            {/* COLORES: clic aplica a la capa seleccionada o al fondo. */}
            <div className="mb-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Colores
              </div>
              {colores.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {colores.map((c) => (
                    <button
                      key={c.color}
                      onClick={() => aplicarColor(c.color)}
                      title={`${c.etiqueta} ${c.color} — clic para aplicarlo a la capa seleccionada o al fondo`}
                      aria-label={`Aplicar color ${c.etiqueta} ${c.color}`}
                      className="h-9 w-9 rounded-md border border-border hover:ring-2 hover:ring-primary"
                      style={{ backgroundColor: c.color }}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Esta marca aún no tiene colores definidos. Se editan en la plantilla de marca o
                  subiendo una paleta a la galería.
                </p>
              )}
            </div>

            {/* TIPOGRAFÍAS: clic aplica la familia al texto seleccionado. */}
            <div className="mb-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Tipografías
              </div>
              {familias.length > 0 ? (
                <div className="flex flex-col gap-1">
                  {familias.map((f) => (
                    <button
                      key={f}
                      onClick={() => aplicarFamilia(f)}
                      title={`Aplicar «${f}» a la capa de texto seleccionada`}
                      className="truncate rounded-xl border bg-card px-2 py-1.5 text-left text-sm hover:bg-accent"
                      style={{ fontFamily: f }}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Esta marca aún no tiene tipografías propias. Súbelas (.woff2/.ttf/.otf) desde la
                  pestaña «Galería».
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
