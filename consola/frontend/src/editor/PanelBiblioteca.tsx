// Panel de biblioteca de activos de la marca DENTRO del editor: logos, tipografías, artes,
// infografías, iconos, paletas y fondos. Click en un activo lo inserta como capa; también
// permite subir un activo nuevo. Cierra el Frente C (los activos del backend, ya en S3).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, urlMedia, type ActivoMarca } from "@/lib/api";

import { nuevaCapaImagen, nuevaCapaLogo, zTope } from "./documento";
import { useStoreEditor } from "./usarEditor";

// Tipos que se insertan como capa de imagen (el logo va como capa logo).
const TIPOS_IMAGEN = new Set(["arte", "infografia", "icono", "fondo"]);

const TIPOS_SUBIDA = ["logo", "arte", "infografia", "icono", "fondo"] as const;

export function PanelBiblioteca({ marca }: { marca: string }) {
  const store = useStoreEditor();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [tipoSubida, setTipoSubida] = useState<string>("arte");

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
        tipo: tipoSubida,
        marca: marca || undefined,
        objeto: media.id,
        nombre: archivo.name.replace(/\.[^.]+$/, ""),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["marca-activos", marca] });
      toast.success("Activo añadido a la biblioteca.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo subir."),
  });

  const insertar = (a: ActivoMarca) => {
    const st = store.getState();
    const doc = st.documento;
    const z = zTope(doc);
    if (a.tipo === "logo") {
      st.agregar(nuevaCapaLogo(a.objeto, { z, x: 56, y: 56, w: 320, h: 120 }));
    } else if (TIPOS_IMAGEN.has(a.tipo)) {
      // Centrado, a media anchura del lienzo.
      const w = Math.round(doc.formato.w * 0.5);
      const h = w;
      st.agregar(
        nuevaCapaImagen(a.objeto, {
          z,
          w,
          h,
          x: Math.round((doc.formato.w - w) / 2),
          y: Math.round((doc.formato.h - h) / 2),
        }),
      );
    } else {
      toast.info(a.tipo === "tipografia" ? "Las tipografías se aplican desde el inspector de texto." : "Las paletas se usan como referencia de color.");
      return;
    }
    st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
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
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Biblioteca</span>
        <div className="ml-auto flex items-center gap-1">
          <select
            value={tipoSubida}
            onChange={(e) => setTipoSubida(e.target.value)}
            className="rounded border border-input bg-background px-1 py-0.5 text-xs"
            aria-label="Tipo de activo a subir"
          >
            {TIPOS_SUBIDA.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={subir.isPending}
            onClick={() => fileRef.current?.click()}
            title="Subir activo"
          >
            <Upload className="h-4 w-4" />
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
                <button
                  key={a.id}
                  onClick={() => insertar(a)}
                  title={a.nombre || a.tipo}
                  className="group relative aspect-square overflow-hidden rounded border border-border bg-[repeating-conic-gradient(#0000_0_25%,#8884_0_50%)] bg-[length:16px_16px] hover:ring-2 hover:ring-primary"
                >
                  {a.objeto ? (
                    <img src={urlMedia(a.objeto)} alt={a.nombre} className="h-full w-full object-contain" />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center text-[10px] text-muted-foreground">
                      {a.tipo}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
