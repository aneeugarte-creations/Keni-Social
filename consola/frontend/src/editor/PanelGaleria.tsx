// Panel de GALERÍA de activos de la marca DENTRO del editor: logos, tipografías, artes,
// infografías, iconos, paletas y fondos. Click en un activo lo inserta como capa; también
// permite subir un activo nuevo. Cierra el Frente C (los activos del backend, ya en S3).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, Upload } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, urlMedia, type ActivoMarca } from "@/lib/api";

import type { Capa } from "./documento";
import { nuevaCapaImagen, nuevaCapaLogo, zTope } from "./documento";
import { useStoreEditor } from "./usarEditor";
import { leerDimensionesUrl } from "./useImagen";

// Tipos que se insertan como capa de imagen (el logo va como capa logo).
const TIPOS_IMAGEN = new Set(["arte", "infografia", "icono", "fondo"]);

// Deduce el tipo de activo del propio archivo (sin pedir nada al usuario): fuentes por extensión,
// «logo» si el nombre lo sugiere, y el resto como imagen/arte.
function tipoDeArchivo(nombre: string): string {
  const n = nombre.toLowerCase();
  if (/\.(woff2?|ttf|otf)$/.test(n)) return "tipografia";
  if (/\blogo\b|logotipo|isotipo/.test(n)) return "logo";
  return "arte";
}

export function PanelGaleria({
  marca,
  reemplazarId = null,
  onReemplazado,
}: {
  marca: string;
  // Si está activo, hacer clic en un activo de imagen REEMPLAZA el `objeto` de esta capa en vez
  // de insertar una nueva (modo «Reemplazar imagen» de la barra contextual).
  reemplazarId?: string | null;
  onReemplazado?: () => void;
}) {
  const store = useStoreEditor();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const activosQuery = useQuery({
    queryKey: ["marca-activos", marca],
    queryFn: ({ signal }) => api.marcaActivos({ marca: marca || undefined }, signal),
    enabled: true,
  });
  const activos = activosQuery.data?.activos ?? [];

  const subir = useMutation({
    mutationFn: async (archivo: File) => {
      const media = await api.subirMedia(archivo);
      return api.crearMarcaActivo({
        tipo: tipoDeArchivo(archivo.name),
        marca: marca || undefined,
        objeto: media.id,
        nombre: archivo.name.replace(/\.[^.]+$/, ""),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["marca-activos", marca] });
      toast.success("Activo añadido a la galería.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo subir."),
  });

  const borrar = useMutation({
    mutationFn: (id: string) => api.borrarMarcaActivo(id, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["marca-activos", marca] });
      toast.success("Activo borrado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo borrar."),
  });

  const insertar = (a: ActivoMarca) => {
    const st = store.getState();
    const doc = st.documento;
    const z = zTope(doc);
    // Modo reemplazo: cambia el objeto de la capa imagen seleccionada y sale del modo.
    if (reemplazarId && a.objeto && (a.tipo === "logo" || TIPOS_IMAGEN.has(a.tipo))) {
      const capa = doc.capas.find((c) => c.id === reemplazarId);
      if (capa?.tipo === "imagen") {
        st.actualizar(reemplazarId, { objeto: a.objeto } as Partial<Capa>);
        toast.success("Imagen reemplazada.");
        onReemplazado?.();
        return;
      }
    }
    if (a.tipo === "logo") {
      st.agregar(nuevaCapaLogo(a.objeto, { z, x: 56, y: 56, w: 320, h: 120 }));
    } else if (TIPOS_IMAGEN.has(a.tipo)) {
      // Centrado, a media anchura del lienzo, adoptando el ASPECT-RATIO natural de la foto (estilo
      // Canva): caja == foto, sin letterbox ni recorte sorpresa, y el marco de selección la abraza
      // exacto. Las dimensiones se leen del media (ya cacheado por la miniatura); si no decodifica,
      // cae al cuadrado de antes.
      void (async () => {
        const dims = await leerDimensionesUrl(urlMedia(a.objeto));
        const stN = store.getState();
        const w = Math.round(stN.documento.formato.w * 0.5);
        const h = dims && dims.w > 0 ? Math.round((w * dims.h) / dims.w) : w;
        stN.agregar(
          nuevaCapaImagen(a.objeto, {
            z: zTope(stN.documento),
            w,
            h,
            x: Math.round((stN.documento.formato.w - w) / 2),
            y: Math.round((stN.documento.formato.h - h) / 2),
          }),
        );
        // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `stN` quedó obsoleto).
        const capas = store.getState().documento.capas;
        stN.seleccionar(capas[capas.length - 1]?.id ?? null);
      })();
      return;
    } else if (a.tipo === "tipografia") {
      // Aplica la familia a la capa de TEXTO seleccionada; si no hay, informa cómo usarla.
      const sel = st.seleccion;
      const capaSel = sel ? doc.capas.find((c) => c.id === sel) : null;
      const familia = ((a.metadatos?.familia as string) || a.nombre || "").trim();
      if (capaSel?.tipo === "texto" && familia) {
        st.actualizar(sel!, { familia } as Partial<Capa>);
        toast.success(`Fuente «${familia}» aplicada al texto.`);
      } else {
        toast.info("Selecciona una capa de texto para aplicarle esta tipografía.");
      }
      return;
    } else if (a.tipo === "paleta") {
      // Aplica el primer color de la paleta al color de la capa de texto seleccionada.
      const sel = st.seleccion;
      const capaSel = sel ? doc.capas.find((c) => c.id === sel) : null;
      const colores = (a.metadatos?.colores as string[] | undefined) ?? [];
      const color = colores[0];
      if (capaSel?.tipo === "texto" && color) {
        st.actualizar(sel!, { color } as Partial<Capa>);
        toast.success(`Color «${color}» aplicado al texto.`);
      } else if (color) {
        toast.info("Selecciona una capa de texto para aplicar un color de la paleta.");
      } else {
        toast.info("Paleta sin colores definidos.");
      }
      return;
    } else {
      return;
    }
    // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
    const capas = store.getState().documento.capas;
    st.seleccionar(capas[capas.length - 1]?.id ?? null);
  };

  // Agrupa por tipo para mostrar secciones.
  const porTipo = new Map<string, ActivoMarca[]>();
  for (const a of activos) {
    const lista = porTipo.get(a.tipo) ?? [];
    lista.push(a);
    porTipo.set(a.tipo, lista);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Galería</span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            disabled={subir.isPending}
            onClick={() => fileRef.current?.click()}
            title="Subir imagen, logo o tipografía"
          >
            <Upload className="mr-1 h-4 w-4" /> Subir
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.woff2,.ttf,.otf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) subir.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {reemplazarId && (
        <div className="border-b border-border bg-primary/10 px-3 py-1.5 text-xs text-primary">
          Elige una imagen para reemplazar la capa seleccionada.
        </div>
      )}

      <div className="flex-1 overflow-auto p-2">
        {activosQuery.isLoading && <p className="p-2 text-sm text-muted-foreground">Cargando…</p>}
        {!activosQuery.isLoading && activos.length === 0 && (
          <p className="p-2 text-sm text-muted-foreground">
            Sin activos para esta marca. Sube un logo, arte o infografía.
          </p>
        )}
        {[...porTipo.entries()].map(([tipo, lista]) => (
          <div key={tipo} className="mb-3">
            <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {tipo}
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {lista.map((a) => (
                <div key={a.id} className="group relative">
                  <button
                    onClick={() => insertar(a)}
                    draggable={a.tipo !== "paleta" && a.tipo !== "tipografia"}
                    onDragStart={(e) => {
                      e.dataTransfer.setData(
                        "application/x-keni-activo",
                        JSON.stringify({ objeto: a.objeto, tipo: a.tipo }),
                      );
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                    title={`${a.nombre || a.tipo} — clic para insertar, o arrástralo al lienzo`}
                    className="block aspect-square w-full overflow-hidden rounded border border-border bg-[repeating-conic-gradient(#0000_0_25%,#8884_0_50%)] bg-[length:16px_16px] hover:ring-2 hover:ring-primary"
                  >
                    {a.objeto ? (
                      // draggable=false + pointer-events-none: el <img> nativo NO debe robar el
                      // arrastre (payload del activo) ni el click del botón contenedor.
                      <img src={urlMedia(a.objeto)} alt={a.nombre} draggable={false} className="pointer-events-none h-full w-full object-contain" />
                    ) : (
                      <span className="flex h-full w-full items-center justify-center text-[10px] text-muted-foreground">
                        {a.tipo}
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => {
                      if (window.confirm(`¿Borrar activo «${a.nombre}»?`)) {
                        borrar.mutate(a.id);
                      }
                    }}
                    title="Borrar activo"
                    className="absolute right-0.5 top-0.5 rounded bg-background/80 p-0.5 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
