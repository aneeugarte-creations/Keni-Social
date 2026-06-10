// Panel «Subidas» del rail del editor (patrón Canva): sube tus propias fotos y reutilízalas.
//
// SOLO mecanismos que ya existen — sin backend nuevo:
//  - Subir: `api.subirMedia` (POST /api/media) sube el binario al almacén (S3/Garage).
//  - Reutilizar: `api.guardarArte` (POST /api/artes, idempotente) cataloga el objeto con
//    `tipo: "subida"`, lo que lo PROTEGE del GC de media huérfana y lo hace listable.
//  - Recientes: `api.listarArtes({marca, tipo: "subida"})` es la fuente de verdad del grid
//    (más recientes primero; incluye las subidas globales de marca '').
//  - Insertar: el MISMO mecanismo que la Galería — clic inserta una capa imagen centrada
//    adoptando el aspect-ratio real de la foto; arrastrar publica el payload
//    `application/x-keni-activo` que el Lienzo ya entiende en su onDrop (sin tocar Lienzo).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, mensajeError, urlMedia } from "@/lib/api";
import type { Arte } from "@/types";

import { nuevaCapaImagen, zTope } from "./documento";
import { useStoreEditor } from "./usarEditor";
import { leerDimensionesUrl } from "./useImagen";

/** Una subida EN CURSO o fallida (las que terminan bien pasan al grid del catálogo). */
type SubidaEnCurso = { clave: string; nombre: string; error: string | null };

export function PanelSubidas({ marca }: { marca: string }) {
  const store = useStoreEditor();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const contadorRef = useRef(0);
  const [enCurso, setEnCurso] = useState<SubidaEnCurso[]>([]);
  // Realce visual de la zona de soltado mientras se arrastra un fichero encima.
  const [arrastrando, setArrastrando] = useState(false);

  // Recientes = artes catalogadas con tipo «subida» para esta marca (más recientes primero).
  const subidasQuery = useQuery({
    queryKey: ["artes", marca || "", "subida"],
    queryFn: ({ signal }) =>
      api.listarArtes({ marca: marca || undefined, tipo: "subida" }, signal),
  });
  const subidas = subidasQuery.data?.artes ?? [];

  // Sube UN fichero y lo cataloga como reutilizable. El ítem vive en `enCurso` (spinner)
  // hasta terminar: con éxito desaparece (el grid se refresca por invalidación); con error
  // se queda mostrando el mensaje hasta que el usuario lo quite.
  const subirUno = async (archivo: File) => {
    const clave = `subida-${++contadorRef.current}`;
    setEnCurso((xs) => [{ clave, nombre: archivo.name, error: null }, ...xs]);
    try {
      const media = await api.subirMedia(archivo);
      await api.guardarArte({
        objeto: media.id,
        tipo: "subida",
        marca: marca || undefined,
        titulo: archivo.name.replace(/\.[^.]+$/, ""),
      });
      setEnCurso((xs) => xs.filter((x) => x.clave !== clave));
      await qc.invalidateQueries({ queryKey: ["artes"] });
    } catch (e) {
      setEnCurso((xs) =>
        xs.map((x) => (x.clave === clave ? { ...x, error: mensajeError(e) } : x)),
      );
    }
  };

  const subirArchivos = (archivos: File[]) => {
    const imagenes = archivos.filter((f) => f.type.startsWith("image/"));
    if (imagenes.length === 0) {
      toast.error("Solo se pueden subir imágenes.");
      return;
    }
    imagenes.forEach((f) => void subirUno(f));
  };

  // Clic en una subida: la inserta centrada adoptando el ASPECT-RATIO real de la foto
  // (estilo Canva, mismo mecanismo que la Galería: caja == foto, sin recorte sorpresa).
  const insertar = async (a: Arte) => {
    const dims = await leerDimensionesUrl(urlMedia(a.objeto));
    const st = store.getState();
    const w = Math.round(st.documento.formato.w * 0.5);
    const h = dims && dims.w > 0 ? Math.round((w * dims.h) / dims.w) : w;
    st.agregar(
      nuevaCapaImagen(a.objeto, {
        z: zTope(st.documento),
        w,
        h,
        x: Math.round((st.documento.formato.w - w) / 2),
        y: Math.round((st.documento.formato.h - h) / 2),
      }),
    );
    // Estado FRESCO tras agregar (el set del store reemplaza `documento`; `st` quedó obsoleto).
    const capas = store.getState().documento.capas;
    st.seleccionar(capas[capas.length - 1]?.id ?? null);
  };

  const abrirSelector = () => fileRef.current?.click();

  return (
    <div className="flex h-full flex-col">
      {/* Subir: botón (selector múltiple) + zona de arrastre. */}
      <div className="shrink-0 space-y-2 border-b border-border p-3">
        <Button
          className="w-full"
          onClick={abrirSelector}
          title="Subir imágenes desde tu equipo"
        >
          <Upload className="mr-1.5 h-4 w-4" /> Subir imágenes
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          aria-label="Subir imágenes"
          onChange={(e) => {
            subirArchivos(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        <div
          role="button"
          tabIndex={0}
          title="Arrastra imágenes aquí para subirlas"
          onClick={abrirSelector}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") abrirSelector();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setArrastrando(true);
          }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastrando(false);
            subirArchivos(Array.from(e.dataTransfer.files ?? []));
          }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed px-3 py-4 text-center text-xs transition-colors ${
            arrastrando
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:border-primary/50"
          }`}
        >
          <ImagePlus className="h-5 w-5" />
          Arrastra y suelta tus imágenes aquí
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-2">
        {/* Subidas EN CURSO o con error (las completadas pasan al grid de recientes). */}
        {enCurso.length > 0 && (
          <div className="mb-2 space-y-1.5">
            {enCurso.map((s) => (
              <div
                key={s.clave}
                className={`flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs ${
                  s.error ? "border-destructive/50 bg-destructive/10" : "border-border"
                }`}
              >
                {s.error ? (
                  <>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{s.nombre}</p>
                      <p className="truncate text-destructive" title={s.error}>{s.error}</p>
                    </div>
                    <button
                      onClick={() => setEnCurso((xs) => xs.filter((x) => x.clave !== s.clave))}
                      title="Quitar"
                      className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                    <p className="min-w-0 flex-1 truncate" title={`Subiendo ${s.nombre}…`}>
                      {s.nombre}
                    </p>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {subidasQuery.isLoading && (
          <p className="p-2 text-sm text-muted-foreground">Cargando…</p>
        )}
        {subidasQuery.isError && (
          <p className="p-2 text-sm text-destructive">{mensajeError(subidasQuery.error)}</p>
        )}

        {/* Vacío con CTA clara (solo si tampoco hay nada subiéndose). */}
        {!subidasQuery.isLoading && !subidasQuery.isError && subidas.length === 0 && enCurso.length === 0 && (
          <div className="flex flex-col items-center gap-2 p-6 text-center text-muted-foreground">
            <ImagePlus className="h-6 w-6" />
            <p className="text-sm">Sube tus propias imágenes y reutilízalas en tus diseños.</p>
            <Button variant="outline" size="sm" onClick={abrirSelector} title="Subir imágenes desde tu equipo">
              <Upload className="mr-1.5 h-4 w-4" /> Subir imágenes
            </Button>
          </div>
        )}

        {/* Grid de subidas RECIENTES reutilizables (catálogo de artes tipo «subida»). */}
        {subidas.length > 0 && (
          <>
            <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Recientes
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {subidas.map((a) => (
                <button
                  key={a.id}
                  onClick={() => void insertar(a)}
                  draggable
                  onDragStart={(e) => {
                    // Mismo payload que la Galería: el Lienzo lo inserta donde se suelta
                    // con el aspect-ratio real de la foto (no es un logo => capa imagen).
                    e.dataTransfer.setData(
                      "application/x-keni-activo",
                      JSON.stringify({ objeto: a.objeto, tipo: "subida" }),
                    );
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  title={`${a.titulo || "Subida"} — clic para insertar, o arrástrala al lienzo`}
                  className="block aspect-square w-full overflow-hidden rounded border border-border bg-[repeating-conic-gradient(#0000_0_25%,#8884_0_50%)] bg-[length:16px_16px] hover:ring-2 hover:ring-primary"
                >
                  {/* draggable=false + pointer-events-none: el <img> nativo NO debe robar el
                      arrastre (payload del activo) ni el clic del botón contenedor. */}
                  <img
                    src={urlMedia(a.objeto)}
                    alt={a.titulo || "Subida"}
                    loading="lazy"
                    draggable={false}
                    className="pointer-events-none h-full w-full object-cover"
                  />
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
