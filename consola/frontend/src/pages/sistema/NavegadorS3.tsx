import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  Copy,
  Download,
  File,
  Folder,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, mensajeError, urlS3Objeto } from "@/lib/api";
import type { MigaS3, ObjetoS3 } from "@/types";

import { copiarTexto, esImagen, formatoBytes, ordenarObjetos } from "./lib";
import { TablaObjetos } from "./TablaObjetos";
import type { OrdenS3 } from "./tipos";

/** Breadcrumb de navegación del explorador S3. */
function BreadcrumbS3({
  migas,
  onNavegar,
}: {
  migas: MigaS3[];
  onNavegar: (prefijo: string) => void;
}) {
  return (
    <nav className="flex items-center gap-1 text-sm" aria-label="Navegación del bucket">
      {migas.map((miga, idx) => {
        const esUltima = idx === migas.length - 1;
        return (
          <React.Fragment key={miga.prefijo}>
            {idx > 0 && (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            )}
            {esUltima ? (
              <span className="font-medium text-foreground">{miga.nombre}</span>
            ) : (
              <button
                type="button"
                onClick={() => onNavegar(miga.prefijo)}
                className="text-muted-foreground hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {miga.nombre}
              </button>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}

/** Lightbox/preview de un objeto (imagen grande o ficha) + descargar + key copiable. */
function PreviewObjeto({
  objeto,
  onClose,
  onBorrar,
  borrando,
}: {
  objeto: ObjetoS3 | null;
  onClose: () => void;
  onBorrar: (objeto: ObjetoS3) => void;
  borrando: boolean;
}) {
  const abierto = objeto != null;
  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl">
        {objeto && (
          <>
            <DialogHeader>
              <DialogTitle className="truncate">{objeto.nombre}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              {esImagen(objeto.key) ? (
                <div className="flex max-h-[60vh] justify-center overflow-auto rounded-md border bg-muted/20 p-2">
                  <img
                    src={urlS3Objeto(objeto.key)}
                    alt={objeto.nombre}
                    className="max-h-[56vh] w-auto object-contain"
                  />
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 rounded-md border bg-muted/20 p-8 text-muted-foreground">
                  <File className="h-10 w-10" aria-hidden="true" />
                  <span className="text-sm">
                    No es una imagen previsualizable. Puedes descargarla.
                  </span>
                </div>
              )}

              {/* Key copiable */}
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-muted px-2 py-1 text-xs">
                  {objeto.key}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void copiarTexto(objeto.key)}
                  aria-label="Copiar clave"
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatoBytes(objeto.tamano)}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    disabled={borrando}
                    onClick={() => onBorrar(objeto)}
                  >
                    {borrando ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
                    )}
                    Borrar
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() =>
                      window.open(urlS3Objeto(objeto.key, true), "_blank", "noopener,noreferrer")
                    }
                  >
                    <Download className="mr-2 h-4 w-4" aria-hidden="true" />
                    Descargar
                  </Button>
                </div>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Explorador de carpetas y objetos de un bucket S3/Garage (solo lectura). */
export function SeccionNavegadorS3() {
  const [prefijo, setPrefijo] = React.useState("");
  const [preview, setPreview] = React.useState<ObjetoS3 | null>(null);
  // Selección para borrado en masa (keys de objetos del nivel actual).
  const [seleccion, setSeleccion] = React.useState<Set<string>>(new Set());
  // Orden de la tabla. null = como lo devuelve el bucket (orden natural por key).
  const [orden, setOrden] = React.useState<OrdenS3 | null>(null);

  const query = useQuery({
    queryKey: ["sistema", "s3-objetos", prefijo],
    queryFn: ({ signal }) => api.s3Objetos(prefijo, signal),
    // Sin auto-refresco: el explorador se refresca manualmente o al navegar.
    staleTime: 30_000,
  });

  // Al cambiar de carpeta, la selección anterior deja de tener sentido: límpiala.
  React.useEffect(() => {
    setSeleccion(new Set());
  }, [prefijo]);

  const queryClient = useQueryClient();
  function invalidarBucket() {
    // Refresca el listado del nivel y el conteo/uso del bucket.
    void queryClient.invalidateQueries({ queryKey: ["sistema", "s3-objetos"] });
    void queryClient.invalidateQueries({ queryKey: ["sistema", "s3"] });
  }

  // Borrado de UN objeto. Sin confirmación: pulsar borrar borra (decisión de producto).
  const borrar = useMutation({
    mutationFn: (obj: ObjetoS3) => api.borrarObjetoS3(obj.key),
    onSuccess: (_data, obj) => {
      toast.success(`Objeto "${obj.nombre}" borrado.`);
      // Si el objeto borrado estaba en preview o seleccionado, sácalo.
      setPreview((p) => (p?.key === obj.key ? null : p));
      setSeleccion((s) => {
        if (!s.has(obj.key)) return s;
        const sig = new Set(s);
        sig.delete(obj.key);
        return sig;
      });
      invalidarBucket();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Borrado en MASA de los objetos seleccionados.
  const borrarLote = useMutation({
    mutationFn: (keys: string[]) => api.borrarObjetosS3(keys),
    onSuccess: (r) => {
      const n = r.borrados.length;
      if (r.fallidos.length === 0) {
        toast.success(`${n} objeto${n === 1 ? "" : "s"} borrado${n === 1 ? "" : "s"}.`);
      } else {
        toast.warning(
          `${n} borrado${n === 1 ? "" : "s"}, ${r.fallidos.length} no se pudieron borrar.`,
        );
      }
      const borrados = new Set(r.borrados);
      setPreview((p) => (p && borrados.has(p.key) ? null : p));
      setSeleccion(new Set());
      invalidarBucket();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrando = borrar.isPending || borrarLote.isPending;

  // Si S3 no está configurado, no mostramos esta sección en absoluto:
  // SeccionS3 ya lo avisa. Esperamos a tener datos para decidir.
  if (query.isPending) {
    return (
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
            <Folder className="h-4 w-4" aria-hidden="true" />
            Explorador del bucket
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <Skeleton className="h-32 w-full rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  if (query.isError) {
    const err = query.error;
    // 403: sin permisos (ya gestionado por la guardia superior, pero por si acaso).
    if (err instanceof ApiError && err.status === 403) return null;
    return (
      <BloqueError
        titulo="No se pudo leer el bucket"
        mensaje={mensajeError(err)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const datos = query.data;

  // Sin S3 configurado: SeccionS3 ya lo avisa; omitimos el explorador.
  if (!datos.configurado) return null;

  const { carpetas, objetos, migas } = datos;
  const hayContenido = carpetas.length > 0 || objetos.length > 0;
  // Bucket plano: en la raíz sin subcarpetas, lo decimos honestamente para que no
  // parezca roto. NO inventamos carpetas; son objetos en la raíz del bucket.
  const bucketPlano = prefijo === "" && carpetas.length === 0 && objetos.length > 0;

  // Orden y selección se aplican solo sobre los objetos (las carpetas no se borran ni pesan).
  const objetosOrdenados = ordenarObjetos(objetos, orden);
  const todosSeleccionados =
    objetos.length > 0 && objetos.every((o) => seleccion.has(o.key));
  const nSeleccionados = seleccion.size;

  function alternarUno(key: string) {
    setSeleccion((s) => {
      const sig = new Set(s);
      if (sig.has(key)) sig.delete(key);
      else sig.add(key);
      return sig;
    });
  }
  function alternarTodos() {
    setSeleccion(todosSeleccionados ? new Set() : new Set(objetos.map((o) => o.key)));
  }

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <Folder className="h-4 w-4" aria-hidden="true" />
            Explorador del bucket
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
            aria-label="Refrescar"
          >
            {query.isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {/* Breadcrumb */}
        <BreadcrumbS3 migas={migas} onNavegar={setPrefijo} />

        {/* Nota honesta cuando el bucket no usa carpetas */}
        {bucketPlano && (
          <p className="text-xs text-muted-foreground">
            Este bucket no usa carpetas; se listan los objetos en la raíz
          </p>
        )}

        {/* Error de sonda (S3 configurado pero fallo de red) */}
        {datos.error && (
          <p className="text-sm text-amber-600 dark:text-amber-400">{datos.error}</p>
        )}

        {/* Barra de acciones en masa: aparece al seleccionar objetos. Borra SIN confirmar. */}
        {nSeleccionados > 0 && (
          <div className="flex items-center justify-between gap-2 rounded-md border bg-muted/40 px-3 py-2">
            <span className="text-sm text-muted-foreground">
              {nSeleccionados} objeto{nSeleccionados === 1 ? "" : "s"} seleccionado
              {nSeleccionados === 1 ? "" : "s"}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSeleccion(new Set())}
                disabled={borrando}
              >
                Limpiar
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={borrando}
                onClick={() => borrarLote.mutate([...seleccion])}
              >
                {borrarLote.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Borrar {nSeleccionados}
              </Button>
            </div>
          </div>
        )}

        {/* Tabla de carpetas y objetos */}
        {!datos.error && !hayContenido ? (
          <p className="text-sm text-muted-foreground">Esta carpeta está vacía.</p>
        ) : (
          <TablaObjetos
            prefijo={prefijo}
            carpetas={carpetas}
            objetosOrdenados={objetosOrdenados}
            hayObjetos={objetos.length > 0}
            orden={orden}
            onOrden={setOrden}
            onNavegar={setPrefijo}
            seleccion={seleccion}
            todosSeleccionados={todosSeleccionados}
            onAlternarUno={alternarUno}
            onAlternarTodos={alternarTodos}
            onPreview={setPreview}
            onBorrar={(obj) => borrar.mutate(obj)}
            borrando={borrando}
            keyBorrando={borrar.isPending ? (borrar.variables?.key ?? null) : null}
          />
        )}
      </CardContent>

      <PreviewObjeto
        objeto={preview}
        onClose={() => setPreview(null)}
        onBorrar={(obj) => borrar.mutate(obj)}
        borrando={borrar.isPending}
      />
    </Card>
  );
}
