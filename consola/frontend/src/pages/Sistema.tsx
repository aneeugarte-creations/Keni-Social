import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ChevronRight,
  Copy,
  Cpu,
  Database,
  Download,
  File,
  FileImage,
  Folder,
  HardDrive,
  Loader2,
  MemoryStick,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError, urlS3Objeto } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DiscoSistema, MigaS3, ObjetoS3, RespuestaProbarS3, RespuestaS3 } from "@/types";

const CABECERA = {
  titulo: "Sistema",
  descripcion:
    "Estado del servidor (CPU, memoria y disco) y del almacenamiento de objetos (S3/Garage). " +
    "Solo para administradores.",
};

// Auto-refresco de los recursos: cada 8 s da un pulso vivo sin martillear el back.
const INTERVALO_RECURSOS_MS = 8000;

/** Bytes → cadena legible (GB/MB/KB). 0 si no hay dato. */
function formatoBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const unidades = ["KB", "MB", "GB", "TB", "PB"];
  let valor = bytes / 1024;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i += 1;
  }
  return `${valor.toFixed(valor >= 100 || i === 0 ? 0 : 1)} ${unidades[i]}`;
}

function formatoPorcentaje(pct: number | null | undefined): string {
  return pct == null ? "—" : `${pct.toFixed(0)}%`;
}

/** Color de la barra según el nivel de uso (verde → ámbar → rojo). */
function colorUso(pct: number | null | undefined): string {
  if (pct == null) return "bg-muted-foreground/40";
  if (pct >= 90) return "bg-red-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

/** Barra de progreso simple (sin dependencia de un componente shadcn nuevo). */
function BarraUso({ porcentaje }: { porcentaje: number | null | undefined }) {
  const ancho = porcentaje == null ? 0 : Math.min(100, Math.max(0, porcentaje));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={porcentaje ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn("h-full rounded-full transition-all", colorUso(porcentaje))}
        style={{ width: `${ancho}%` }}
      />
    </div>
  );
}

/** Tarjeta de métrica con icono, valor grande, subtítulo y barra opcional. */
function TarjetaMetrica({
  icono: Icono,
  titulo,
  valor,
  subtitulo,
  porcentaje,
}: {
  icono: typeof Cpu;
  titulo: string;
  valor: React.ReactNode;
  subtitulo?: React.ReactNode;
  porcentaje?: number | null;
}) {
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icono className="h-4 w-4" aria-hidden="true" />
          {titulo}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-4 pt-0">
        <div className="text-2xl font-semibold tabular-nums">{valor}</div>
        {subtitulo && <div className="text-xs text-muted-foreground">{subtitulo}</div>}
        {porcentaje !== undefined && <BarraUso porcentaje={porcentaje} />}
      </CardContent>
    </Card>
  );
}

function TarjetaDisco({ disco }: { disco: DiscoSistema }) {
  return (
    <TarjetaMetrica
      icono={HardDrive}
      titulo={`Disco · ${disco.etiqueta}`}
      valor={formatoPorcentaje(disco.porcentaje)}
      subtitulo={
        <>
          {formatoBytes(disco.usado)} de {formatoBytes(disco.total)}{" "}
          <span className="text-muted-foreground/70">({disco.ruta})</span>
        </>
      }
      porcentaje={disco.porcentaje}
    />
  );
}

/** Sección de recursos del servidor (CPU/RAM/disco) con auto-refresco. */
function SeccionRecursos() {
  const query = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  if (query.isPending) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudieron leer los recursos del servidor"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { cpu, ram, discos, psutil } = query.data;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <TarjetaMetrica
          icono={Cpu}
          titulo="CPU"
          valor={formatoPorcentaje(cpu.porcentaje)}
          subtitulo={cpu.cores != null ? `${cpu.cores} núcleos` : "psutil no disponible"}
          porcentaje={cpu.porcentaje}
        />
        <TarjetaMetrica
          icono={MemoryStick}
          titulo="Memoria"
          valor={formatoPorcentaje(ram.porcentaje)}
          subtitulo={
            ram.total != null
              ? `${formatoBytes(ram.usado)} de ${formatoBytes(ram.total)}`
              : "psutil no disponible"
          }
          porcentaje={ram.porcentaje}
        />
        {discos.map((d) => (
          <TarjetaDisco key={d.ruta} disco={d} />
        ))}
      </div>
      {!psutil && (
        <p className="text-xs text-muted-foreground">
          CPU y memoria no disponibles (psutil no está instalado en este servidor). El
          disco se mide igualmente.
        </p>
      )}
    </div>
  );
}

/** Badge de salud para el bucket S3. */
function BadgeSalud({ salud }: { salud: RespuestaS3["salud"] }) {
  if (salud === "ok") {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
        Conectado
      </Badge>
    );
  }
  if (salud === "err") {
    return <Badge variant="destructive">Error de conexión</Badge>;
  }
  return <Badge variant="secondary">Sin configurar</Badge>;
}

/** Sección de almacenamiento S3/Garage: estado, uso y prueba de conexión. */
function SeccionS3() {
  const query = useQuery({
    queryKey: ["sistema", "s3"],
    queryFn: ({ signal }) => api.sistemaS3(signal),
  });

  const probar = useMutation({
    mutationFn: () => api.probarS3(),
    onSuccess: (r: RespuestaProbarS3) => {
      if (r.salud === "ok") {
        toast.success("Conexión con el almacenamiento correcta.");
        void query.refetch();
      } else {
        toast.error(r.error ?? "No se pudo conectar con el almacenamiento.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (query.isPending) {
    return <Skeleton className="h-40 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado del almacenamiento"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const s3 = query.data;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <Database className="h-4 w-4" aria-hidden="true" />
            Almacenamiento de objetos (S3 / Garage)
          </span>
          <BadgeSalud salud={s3.salud} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        {!s3.configurado ? (
          <p className="text-sm text-muted-foreground">
            S3 no está configurado en este servidor: la media vive en disco local.
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <Dato etiqueta="Endpoint" valor={s3.endpoint ?? "—"} />
              <Dato etiqueta="Bucket" valor={s3.bucket ?? "—"} />
              <Dato etiqueta="Región" valor={s3.region ?? "—"} />
              <Dato
                etiqueta="Objetos"
                valor={
                  s3.objetos == null
                    ? "—"
                    : `${s3.objetos.toLocaleString("es-MX")}${s3.truncado ? "+" : ""}`
                }
              />
              <Dato etiqueta="Tamaño total" valor={formatoBytes(s3.bytes)} />
            </dl>
            {s3.error && (
              <p className="text-sm text-amber-600 dark:text-amber-400">{s3.error}</p>
            )}
            {s3.truncado && (
              <p className="text-xs text-muted-foreground">
                Conteo truncado por volumen: la cifra es un mínimo.
              </p>
            )}
            <div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => probar.mutate()}
                disabled={probar.isPending}
              >
                {probar.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Probar conexión
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- #
// Navegador de carpetas/objetos del bucket S3                                  #
// --------------------------------------------------------------------------- #

const EXT_IMAGEN = new Set(["png", "jpg", "jpeg", "gif", "webp", "avif", "svg"]);

/** `true` si la key/nombre apunta a una imagen previsualizable (por extensión). */
function esImagen(key: string): boolean {
  const ext = key.split(".").pop()?.toLowerCase() ?? "";
  return EXT_IMAGEN.has(ext);
}

/** Copia un texto al portapapeles, con aviso. */
async function copiarTexto(texto: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success("Clave copiada al portapapeles.");
  } catch {
    toast.error("No se pudo copiar la clave.");
  }
}

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

/** Miniatura de una imagen del bucket (lazy). Si falla la carga, cae a un icono. */
function ThumbnailObjeto({ objeto }: { objeto: ObjetoS3 }) {
  const [error, setError] = React.useState(false);
  if (!esImagen(objeto.key) || error) {
    const Icono = esImagen(objeto.key) ? FileImage : File;
    return (
      <div className="flex h-12 w-12 items-center justify-center rounded-md border bg-muted/40">
        <Icono className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }
  return (
    <img
      src={urlS3Objeto(objeto.key)}
      alt={objeto.nombre}
      loading="lazy"
      onError={() => setError(true)}
      className="h-12 w-12 rounded-md border object-cover"
    />
  );
}

/** Lightbox/preview de un objeto (imagen grande o ficha) + descargar + key copiable. */
function PreviewObjeto({
  objeto,
  onClose,
}: {
  objeto: ObjetoS3 | null;
  onClose: () => void;
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Explorador de carpetas y objetos de un bucket S3/Garage (solo lectura). */
function SeccionNavegadorS3() {
  const [prefijo, setPrefijo] = React.useState("");
  const [preview, setPreview] = React.useState<ObjetoS3 | null>(null);

  const query = useQuery({
    queryKey: ["sistema", "s3-objetos", prefijo],
    queryFn: ({ signal }) => api.s3Objetos(prefijo, signal),
    // Sin auto-refresco: el explorador se refresca manualmente o al navegar.
    staleTime: 30_000,
  });

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
            Este bucket no usa carpetas: se listan los objetos en la raíz. Haz clic en una
            fila para previsualizar o descargar.
          </p>
        )}

        {/* Error de sonda (S3 configurado pero fallo de red) */}
        {datos.error && (
          <p className="text-sm text-amber-600 dark:text-amber-400">{datos.error}</p>
        )}

        {/* Tabla de carpetas y objetos */}
        {!datos.error && !hayContenido ? (
          <p className="text-sm text-muted-foreground">Esta carpeta está vacía.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16" />
                <TableHead>Nombre</TableHead>
                <TableHead className="text-right">Tamaño</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Modificado</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {/* Enlace ".." para subir un nivel */}
              {prefijo && (
                <TableRow
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => {
                    // Sube al nivel anterior: quita el último segmento del prefijo.
                    const partes = prefijo.replace(/\/$/, "").split("/");
                    partes.pop();
                    setPrefijo(partes.length > 0 ? `${partes.join("/")}/` : "");
                  }}
                >
                  <TableCell>
                    <div className="flex h-12 w-12 items-center justify-center">
                      <Folder className="h-5 w-5 text-blue-500" aria-hidden="true" />
                    </div>
                  </TableCell>
                  <TableCell className="font-medium text-muted-foreground">..</TableCell>
                  <TableCell />
                  <TableCell className="hidden sm:table-cell" />
                  <TableCell />
                </TableRow>
              )}

              {/* Subcarpetas */}
              {carpetas.map((carpeta) => {
                // Nombre legible: el ultimo segmento del prefijo (sin barra final).
                const nombre = carpeta.replace(/\/$/, "").split("/").pop() ?? carpeta;
                return (
                  <TableRow
                    key={carpeta}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setPrefijo(carpeta)}
                  >
                    <TableCell>
                      <div className="flex h-12 w-12 items-center justify-center">
                        <Folder className="h-5 w-5 text-blue-500" aria-hidden="true" />
                      </div>
                    </TableCell>
                    <TableCell className="font-medium">{nombre}/</TableCell>
                    <TableCell className="text-right text-muted-foreground">—</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground sm:table-cell">
                      —
                    </TableCell>
                    <TableCell />
                  </TableRow>
                );
              })}

              {/* Objetos del nivel actual */}
              {objetos.map((obj) => {
                const fechaCorta = obj.modificado
                  ? new Date(obj.modificado).toLocaleDateString("es-MX", {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })
                  : "—";
                return (
                  <TableRow
                    key={obj.key}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setPreview(obj)}
                  >
                    <TableCell>
                      <ThumbnailObjeto objeto={obj} />
                    </TableCell>
                    <TableCell className="font-medium">{obj.nombre}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatoBytes(obj.tamano)}
                    </TableCell>
                    <TableCell className="hidden text-right text-muted-foreground sm:table-cell">
                      {fechaCorta}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Descargar ${obj.nombre}`}
                        onClick={(e) => {
                          // No abrir el preview al pulsar descargar.
                          e.stopPropagation();
                          window.open(
                            urlS3Objeto(obj.key, true),
                            "_blank",
                            "noopener,noreferrer",
                          );
                        }}
                      >
                        <Download className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <PreviewObjeto objeto={preview} onClose={() => setPreview(null)} />
    </Card>
  );
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1 last:border-0">
      <dt className="shrink-0 text-muted-foreground">{etiqueta}</dt>
      <dd className="truncate text-right font-medium tabular-nums">{valor}</dd>
    </div>
  );
}

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un error inesperado.";
}

/**
 * Panel de SISTEMA (admin): monitorización del servidor (CPU/RAM/disco, auto-refresco)
 * y estado/gestión del almacenamiento S3/Garage (uso del bucket + probar conexión + explorador
 * de carpetas/objetos, solo lectura). El backend devuelve 403 si quien entra no es admin;
 * aquí lo avisamos al llegar por URL directa (el nav ya oculta la página para no-admin).
 */
export default function Sistema() {
  // Una sonda inicial para detectar el 403 y mostrar el aviso de permiso de forma unificada.
  const guardia = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const esProhibido =
    guardia.isError &&
    guardia.error instanceof ApiError &&
    guardia.error.status === 403;

  return (
    <>
      <PageHeader {...CABECERA} />
      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
          texto="Solo los administradores pueden ver el estado del sistema."
        />
      ) : (
        <div className="space-y-6">
          <SeccionRecursos />
          <SeccionS3 />
          <SeccionNavegadorS3 />
        </div>
      )}
    </>
  );
}
