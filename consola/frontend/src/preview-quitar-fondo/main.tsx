// Preview localhost de «Quitar fondo»: monta el LIENZO real + el INSPECTOR real (con el botón
// nuevo en la capa de imagen) sobre un store sembrado. El backend mínimo (:8765, rembg real)
// sirve `/api/media` y `/api/imagen/quitar-fondo` vía el proxy de Vite. No es la app real, pero
// los componentes y el motor SÍ son los que se envían a main.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { toast } from "sonner";

import { Toaster } from "@/components/ui/sonner";
import { ProveedorEditor } from "@/editor/contexto";
import type { Capa } from "@/editor/documento";
import { documentoVacio, nuevaCapaImagen } from "@/editor/documento";
import { Lienzo } from "@/editor/Lienzo";
import { Inspector } from "@/editor/paneles/Inspector";
import { crearStoreEditor } from "@/editor/store";
import { TemaProvider } from "@/hooks/use-tema";
import { api, mensajeError } from "@/lib/api";

import "@/index.css";

const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const MUESTRA = "demo/sujeto.png";

function crearStore() {
  const doc = documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "unotv");
  const foto = nuevaCapaImagen(MUESTRA, {
    id: "foto1",
    x: 60,
    y: 60,
    w: 960,
    h: 960,
    z: 1,
    nombre: "Foto",
    visible: true,
    ajuste: "contain",
  });
  doc.capas = [...doc.capas, foto];
  const store = crearStoreEditor(doc);
  store.getState().seleccionar("foto1");
  return store;
}

function Demo() {
  const store = useMemo(() => crearStore(), []);
  const [subiendo, setSubiendo] = useState(false);
  const [recorteId, setRecorteId] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).has("recorte") ? "foto1" : null,
  );
  const fileRef = useRef<HTMLInputElement>(null);

  // Solo para la captura `?recorte=1`: pre-aplica un recorte centrado sobre la muestra para ver el
  // marco ENCOGIDO + el velo oscuro (Canva). En uso normal el recorte lo hace el arrastre real.
  useEffect(() => {
    if (!new URLSearchParams(window.location.search).has("recorte")) return;
    const c = store.getState().documento.capas.find((x) => x.id === "foto1");
    if (!c || c.tipo !== "imagen" || c.objeto !== MUESTRA) return;
    store.getState().actualizar("foto1", {
      x: c.x + c.w * 0.1875,
      y: c.y + c.h * 0.1875,
      w: c.w * 0.625,
      h: c.h * 0.625,
      crop: { cx: 0.1875, cy: 0.1875, cw: 0.625, ch: 0.625 },
      zoom: 1,
      foco: [0.5, 0.5],
    } as Partial<Capa>);
  }, [store]);

  const usar = (objeto: string) => {
    store.getState().actualizar("foto1", { objeto } as Partial<Capa>);
    store.getState().seleccionar("foto1");
  };

  const onArchivo = async (file: File | undefined) => {
    if (!file) return;
    setSubiendo(true);
    try {
      const res = await api.subirMedia(file);
      usar(res.id);
      toast.success("Foto cargada. Pulsa «Quitar fondo» en el inspector →");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setSubiendo(false);
    }
  };

  return (
    <ProveedorEditor store={store}>
      <div className="flex min-h-dvh flex-col gap-4 overflow-y-auto bg-background p-6 text-foreground">
        <header className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold tracking-[0.2em] text-muted-foreground">KENI · DEMO</span>
            <h1 className="text-lg font-medium">Quitar fondo</h1>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Selecciona la capa de imagen y pulsa <b>Quitar fondo</b> en el inspector (columna derecha, sección
            «Imagen»). El sujeto se recorta y el fondo queda transparente (tablero a cuadros). Sube una foto real
            para ver la calidad de bordes con el motor <code>rembg</code>.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={subiendo}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm shadow-sm hover:bg-accent disabled:opacity-60"
            >
              {subiendo ? "Subiendo…" : "Subir una foto…"}
            </button>
            <button
              type="button"
              onClick={() => usar(MUESTRA)}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Usar la muestra
            </button>
            <button
              type="button"
              onClick={() => setRecorteId((r) => (r ? null : "foto1"))}
              className="rounded-lg border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              {recorteId ? "Salir de recortar" : "Recortar"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => onArchivo(e.target.files?.[0])}
            />
          </div>
        </header>

        <div className="flex flex-wrap items-start gap-6">
          <section className="flex flex-col gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lienzo</div>
            <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
              <Lienzo maxAncho={520} maxAlto={520} recorteId={recorteId} onSalirRecorte={() => setRecorteId(null)} />
            </div>
            <p className="max-w-[520px] text-xs text-muted-foreground">
              En <b>Recortar</b>, arrastra un tirador hacia dentro: el marco <b>encoge</b> y la parte cortada se
              <b> oscurece</b> (como Canva); la foto no se amplía. La rueda/arrastrar la foto reencuadra.
            </p>
          </section>

          <section className="flex w-[320px] flex-col gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Inspector</div>
            <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
              <Inspector />
            </div>
          </section>
        </div>
      </div>
    </ProveedorEditor>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <TemaProvider>
    <QueryClientProvider client={cliente}>
      <Demo />
      <Toaster />
    </QueryClientProvider>
  </TemaProvider>,
);
