import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Check,
  CircleCheck,
  CircleX,
  Clipboard,
  ExternalLink,
  Library,
  Lightbulb,
  Newspaper,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, mensajeError } from "@/lib/api";
import type {
  CuerpoFuenteAlgoritmo,
  FuenteAlgoritmo,
  NivelAlgoritmo,
  NoticiaAlgoritmo,
  OpcionAlgoritmo,
  SugerenciaEditorial,
} from "@/types";

const CABECERA = {
  titulo: "Algoritmos",
  descripcion:
    "Cambios de algoritmo y tendencias por plataforma, de los blogs oficiales y agregadores. " +
    "Ordenado por importancia para decisiones de marca y para actualizar la ficha editorial de cada red. " +
    "No inventa nada: solo muestra lo que devuelven las fuentes reales.",
};

const TODAS = "__todas__";

/** Variante de badge según el nivel de importancia. */
function badgeNivel(nivel: NivelAlgoritmo): { variante: "ok" | "secondary" | "outline"; texto: string } {
  if (nivel === "alta") return { variante: "ok", texto: "Importante" };
  if (nivel === "media") return { variante: "secondary", texto: "Media" };
  return { variante: "outline", texto: "Baja" };
}

// --------------------------------------------------------------------------- //
// Tarjeta de una noticia                                                        //
// --------------------------------------------------------------------------- //

function TarjetaNoticia({
  noticia,
  onProponer,
  onArchivar,
  archivando,
}: {
  noticia: NoticiaAlgoritmo;
  onProponer: (n: NoticiaAlgoritmo) => void;
  onArchivar: (n: NoticiaAlgoritmo) => void;
  archivando: boolean;
}) {
  const nivel = badgeNivel(noticia.nivel);
  return (
    <li className="rounded-lg border border-border/60 p-3">
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <Badge variant="outline">{noticia.plataforma_nombre || noticia.plataforma}</Badge>
        <Badge variant={nivel.variante}>{nivel.texto}</Badge>
        {noticia.es_cambio && (
          <Badge
            variant="outline"
            className="border-amber-500/40 text-amber-700 dark:text-amber-300"
            title="Parece un cambio de algoritmo confirmado: candidato a la ficha editorial."
          >
            Cambio de algoritmo
          </Badge>
        )}
        {noticia.tipo === "oficial" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            Oficial
          </Badge>
        )}
        {noticia.aplicada && (
          <Badge variant="ok" title="Ya propuesta a la biblioteca editorial.">
            En biblioteca
          </Badge>
        )}
      </div>

      <p className="text-sm font-medium">
        {noticia.enlace ? (
          <a
            href={noticia.enlace}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-start gap-1 hover:underline"
          >
            {noticia.titulo || "(sin título)"}
            <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
          </a>
        ) : (
          noticia.titulo || "(sin título)"
        )}
      </p>

      {noticia.resumen && (
        <p className="pt-1 text-xs text-muted-foreground">{noticia.resumen}</p>
      )}

      {noticia.senales.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 pt-2">
          {noticia.senales.map((s) => (
            <span
              key={s}
              className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-2">
        <span className="truncate text-xs text-muted-foreground">
          {[noticia.fuente_nombre, noticia.fecha].filter(Boolean).join(" · ")}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onProponer(noticia)}
            title="Proponer esta noticia a la ficha editorial de la plataforma"
          >
            <Library className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            A biblioteca
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onArchivar(noticia)}
            disabled={archivando}
            title="Archivar (ocultar de la lista)"
          >
            <Archive className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------- //
// Fila de una fuente (salud + activar/borrar)                                   //
// --------------------------------------------------------------------------- //

function FilaFuente({
  fuente,
  onToggle,
  onBorrar,
  ocupada,
}: {
  fuente: FuenteAlgoritmo;
  onToggle: (f: FuenteAlgoritmo) => void;
  onBorrar: (f: FuenteAlgoritmo) => void;
  ocupada: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          {fuente.ultimo_error ? (
            <CircleX className="h-3.5 w-3.5 shrink-0 text-rose-500" aria-hidden="true" />
          ) : (
            <CircleCheck className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
          )}
          <p className="truncate text-sm font-medium">{fuente.nombre}</p>
          <Badge variant="outline">{fuente.plataforma_nombre || fuente.plataforma}</Badge>
          {fuente.tipo === "oficial" && (
            <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
              Oficial
            </Badge>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground">
          {fuente.ultimo_error
            ? fuente.ultimo_error
            : `${fuente.ultimo_conteo} noticia(s)${
                fuente.ultima_actualizacion ? ` · ${fuente.ultima_actualizacion}` : ""
              }`}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Switch
          checked={fuente.activo}
          onCheckedChange={() => onToggle(fuente)}
          disabled={ocupada}
          aria-label={fuente.activo ? "Desactivar fuente" : "Activar fuente"}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onBorrar(fuente)}
          disabled={ocupada}
          title="Borrar fuente"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------- //
// Diálogo: alta de fuente                                                       //
// --------------------------------------------------------------------------- //

function DialogoNuevaFuente({
  abierto,
  onCerrar,
  onGuardar,
  guardando,
  plataformas,
  tipos,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onGuardar: (cuerpo: CuerpoFuenteAlgoritmo) => void;
  guardando: boolean;
  plataformas: OpcionAlgoritmo[];
  tipos: OpcionAlgoritmo[];
}) {
  const [nombre, setNombre] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [plataforma, setPlataforma] = React.useState("general");
  const [tipo, setTipo] = React.useState("agregador");

  React.useEffect(() => {
    if (abierto) {
      setNombre("");
      setUrl("");
      setPlataforma("general");
      setTipo("agregador");
    }
  }, [abierto]);

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva fuente de algoritmo</DialogTitle>
          <DialogDescription>
            Un feed RSS de un blog oficial o agregador. La URL se valida (solo http/https,
            sin direcciones internas).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="alg-nombre">Nombre</Label>
            <Input
              id="alg-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Meta Newsroom"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="alg-url">URL del feed</Label>
            <Input
              id="alg-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://about.fb.com/news/feed/"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Plataforma</Label>
              <Select value={plataforma} onValueChange={setPlataforma}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {plataformas.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Tipo</Label>
              <Select value={tipo} onValueChange={setTipo}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {tipos.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Button>
          <Button
            onClick={() => onGuardar({ nombre, url, plataforma, tipo })}
            disabled={guardando || !nombre.trim() || !url.trim()}
          >
            Añadir fuente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Diálogo: propuesta para la biblioteca                                         //
// --------------------------------------------------------------------------- //

function DialogoPropuesta({
  propuesta,
  onCerrar,
}: {
  propuesta: string | null;
  onCerrar: () => void;
}) {
  return (
    <Dialog open={propuesta !== null} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Propuesta para la biblioteca</DialogTitle>
          <DialogDescription>
            Borrador listo para pegar en la ficha editorial de la plataforma. La línea
            editorial la decide el equipo: cópialo y confírmalo en la Biblioteca.
          </DialogDescription>
        </DialogHeader>
        {propuesta && (
          <div className="rounded-md border bg-muted/40 p-3 text-sm">
            <Markdown>{propuesta}</Markdown>
          </div>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              if (propuesta) {
                void navigator.clipboard?.writeText(propuesta);
                toast.success("Copiado al portapapeles.");
              }
            }}
          >
            <Clipboard className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Copiar
          </Button>
          <Button asChild>
            <Link to="/contenido/biblioteca">Abrir Biblioteca</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------- //
// Página                                                                        //
// --------------------------------------------------------------------------- //

// --------------------------------------------------------------------------- //
// Tarjeta de una sugerencia editorial (digest diario)                           //
// --------------------------------------------------------------------------- //

function TarjetaSugerencia({
  sugerencia,
  onAplicar,
  onDescartar,
  ocupada,
}: {
  sugerencia: SugerenciaEditorial;
  onAplicar: (s: SugerenciaEditorial) => void;
  onDescartar: (s: SugerenciaEditorial) => void;
  ocupada: boolean;
}) {
  const esLimite = sugerencia.tipo === "limite";
  return (
    <li className="rounded-lg border border-border/60 p-3">
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <Badge variant="outline">{sugerencia.plataforma_nombre || sugerencia.plataforma}</Badge>
        <Badge
          variant="outline"
          className={
            esLimite
              ? "border-violet-500/40 text-violet-700 dark:text-violet-300"
              : "border-sky-500/40 text-sky-700 dark:text-sky-300"
          }
        >
          {esLimite ? "Límite" : "Ficha editorial"}
        </Badge>
      </div>
      <p className="text-sm font-medium">{sugerencia.titulo}</p>
      {sugerencia.detalle && (
        <div className="pt-1">
          <Markdown className="text-xs text-muted-foreground">{sugerencia.detalle}</Markdown>
        </div>
      )}
      <div className="flex items-center justify-end gap-1 pt-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onAplicar(sugerencia)}
          disabled={ocupada}
          title={
            esLimite
              ? "Marcar como atendida (los límites se cambian en el código)"
              : "Añadir esta propuesta a la ficha editorial de la plataforma"
          }
        >
          <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          {esLimite ? "Atendida" : "Aplicar a la ficha"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDescartar(sugerencia)}
          disabled={ocupada}
          title="Descartar"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}

export default function Algoritmos() {
  const queryClient = useQueryClient();
  const [plataforma, setPlataforma] = React.useState<string>(TODAS);
  const [nivel, setNivel] = React.useState<string>(TODAS);
  const [soloCambios, setSoloCambios] = React.useState(false);
  const [nuevaFuente, setNuevaFuente] = React.useState(false);
  const [propuesta, setPropuesta] = React.useState<string | null>(null);

  const filtros = {
    plataforma: plataforma === TODAS ? undefined : plataforma,
    nivel: nivel === TODAS ? undefined : (nivel as NivelAlgoritmo),
    solo_cambios: soloCambios || undefined,
  };

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["algoritmos", filtros],
    queryFn: ({ signal }) => api.algoritmos(filtros, signal),
  });

  const invalidar = () => queryClient.invalidateQueries({ queryKey: ["algoritmos"] });

  const refrescar = useMutation({
    mutationFn: () => api.refrescarAlgoritmos(),
    onSuccess: (r) => {
      const { insertadas, actualizadas, errores } = r.resumen;
      toast.success(
        `Ingesta: ${insertadas} nueva(s), ${actualizadas} actualizada(s).` +
          (errores.length ? ` ${errores.length} fuente(s) con error.` : ""),
      );
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const sembrar = useMutation({
    mutationFn: () => api.sembrarAlgoritmos(),
    onSuccess: (r) => {
      toast.success(`${r.total} fuente(s) recomendada(s) añadida(s).`);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const crearFuente = useMutation({
    mutationFn: (cuerpo: CuerpoFuenteAlgoritmo) => api.crearFuenteAlgoritmo(cuerpo),
    onSuccess: () => {
      toast.success("Fuente añadida.");
      setNuevaFuente(false);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const toggleFuente = useMutation({
    mutationFn: (f: FuenteAlgoritmo) =>
      api.actualizarFuenteAlgoritmo(f.id, { activo: !f.activo }),
    onSuccess: () => void invalidar(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrarFuente = useMutation({
    mutationFn: (f: FuenteAlgoritmo) => api.borrarFuenteAlgoritmo(f.id),
    onSuccess: () => {
      toast.success("Fuente borrada.");
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const proponer = useMutation({
    mutationFn: (n: NoticiaAlgoritmo) => api.algoritmoABiblioteca(n.id),
    onSuccess: (r) => {
      setPropuesta(r.propuesta);
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const archivar = useMutation({
    mutationFn: (n: NoticiaAlgoritmo) => api.archivarAlgoritmo(n.id, true),
    onSuccess: () => {
      toast.success("Noticia archivada.");
      void invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Sugerencias editoriales (digest diario): query independiente de las noticias.
  const sugerencias = useQuery({
    queryKey: ["algoritmos", "sugerencias"],
    queryFn: ({ signal }) => api.sugerenciasAlgoritmo("nueva", signal),
  });
  const invalidarSugerencias = () =>
    queryClient.invalidateQueries({ queryKey: ["algoritmos", "sugerencias"] });

  const generarSugerencias = useMutation({
    mutationFn: () => api.generarSugerenciasAlgoritmo(),
    onSuccess: (r) => toast.success(r.mensaje),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aplicarSugerencia = useMutation({
    mutationFn: (s: SugerenciaEditorial) => api.aplicarSugerenciaAlgoritmo(s.id),
    onSuccess: (r) => {
      toast.success(r.nota || "Aplicada a la ficha editorial.");
      void invalidarSugerencias();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarSugerencia = useMutation({
    mutationFn: (s: SugerenciaEditorial) => api.descartarSugerenciaAlgoritmo(s.id),
    onSuccess: () => {
      toast.success("Sugerencia descartada.");
      void invalidarSugerencias();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const fuentes = data?.fuentes ?? [];
  const fuenteOcupada = toggleFuente.isPending || borrarFuente.isPending;
  const sugerenciaOcupada = aplicarSugerencia.isPending || descartarSugerencia.isPending;
  const listaSugerencias = sugerencias.data?.sugerencias ?? [];

  return (
    <div>
      <PageHeader
        titulo={CABECERA.titulo}
        descripcion={CABECERA.descripcion}
        acciones={
          <>
            <Button
              onClick={() => generarSugerencias.mutate()}
              disabled={generarSugerencias.isPending}
              variant="outline"
              size="sm"
              title="Generar ahora las sugerencias editoriales a partir de las noticias importantes"
            >
              <Wand2 className="mr-1 h-4 w-4" aria-hidden="true" />
              Generar sugerencias
            </Button>
            <Button
              onClick={() => refrescar.mutate()}
              disabled={refrescar.isPending}
              variant="outline"
              size="sm"
            >
              <RefreshCw
                className={`mr-1 h-4 w-4 ${refrescar.isPending ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              Refrescar
            </Button>
          </>
        }
      />

      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-10 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      )}

      {isError && (
        <BloqueError
          titulo="No se pudo cargar Algoritmos"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Columna principal: noticias */}
          <div className="space-y-3 lg:col-span-2">
            {/* Sugerencias editoriales (digest diario): solo se muestra si hay nuevas. */}
            {listaSugerencias.length > 0 && (
              <Card className="border-amber-500/30 bg-amber-500/[0.03]">
                <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
                    Sugerencias editoriales
                    <Badge variant="secondary">{listaSugerencias.length}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="pb-2 text-xs text-muted-foreground">
                    Propuestas de cambio a la ficha de plataforma y a los límites, a partir de
                    las noticias importantes. Revisa y aplica o descarta; nunca se aplican solas.
                  </p>
                  <ul className="space-y-2">
                    {listaSugerencias.map((s) => (
                      <TarjetaSugerencia
                        key={s.id}
                        sugerencia={s}
                        onAplicar={(sug) => aplicarSugerencia.mutate(sug)}
                        onDescartar={(sug) => descartarSugerencia.mutate(sug)}
                        ocupada={sugerenciaOcupada}
                      />
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {/* Filtros */}
            <div className="flex flex-wrap items-center gap-2">
              <Select value={plataforma} onValueChange={setPlataforma}>
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="Plataforma" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODAS}>Todas las plataformas</SelectItem>
                  {data.plataformas.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={nivel} onValueChange={setNivel}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="Importancia" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={TODAS}>Toda importancia</SelectItem>
                  {data.niveles.map((n) => (
                    <SelectItem key={n} value={n}>
                      {badgeNivel(n).texto}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Switch
                  checked={soloCambios}
                  onCheckedChange={setSoloCambios}
                  aria-label="Solo cambios de algoritmo"
                />
                Solo cambios de algoritmo
              </label>
            </div>

            <Card>
              <CardHeader className="space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Newspaper className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Noticias de algoritmo
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.noticias.length > 0 ? (
                  <ul className="space-y-2">
                    {data.noticias.map((n) => (
                      <TarjetaNoticia
                        key={n.id}
                        noticia={n}
                        onProponer={(noticia) => proponer.mutate(noticia)}
                        onArchivar={(noticia) => archivar.mutate(noticia)}
                        archivando={archivar.isPending}
                      />
                    ))}
                  </ul>
                ) : fuentes.length === 0 ? (
                  <EstadoVacio
                    icono={Sparkles}
                    titulo="Sin fuentes todavía"
                    texto="Añade las fuentes recomendadas (Meta, YouTube, agregadores) y refresca para ver lo último en algoritmos."
                    accion={
                      <Button onClick={() => sembrar.mutate()} disabled={sembrar.isPending} size="sm">
                        <Sparkles className="mr-1 h-4 w-4" aria-hidden="true" />
                        Añadir fuentes recomendadas
                      </Button>
                    }
                  />
                ) : (
                  <EstadoVacio
                    icono={Newspaper}
                    titulo="Nada que mostrar"
                    texto="No hay noticias para este filtro. Pulsa Refrescar para ingerir lo último de los feeds."
                  />
                )}
              </CardContent>
            </Card>
          </div>

          {/* Columna lateral: fuentes + huecos */}
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
                <CardTitle className="text-base">Fuentes</CardTitle>
                <div className="flex items-center gap-1">
                  {fuentes.length === 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => sembrar.mutate()}
                      disabled={sembrar.isPending}
                    >
                      <Sparkles className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      Recomendadas
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => setNuevaFuente(true)}>
                    <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                    Añadir
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {fuentes.length > 0 ? (
                  <ul>
                    {fuentes.map((f) => (
                      <FilaFuente
                        key={f.id}
                        fuente={f}
                        onToggle={(fu) => toggleFuente.mutate(fu)}
                        onBorrar={(fu) => borrarFuente.mutate(fu)}
                        ocupada={fuenteOcupada}
                      />
                    ))}
                  </ul>
                ) : (
                  <p className="py-2 text-sm text-muted-foreground">
                    Aún no hay fuentes configuradas.
                  </p>
                )}
              </CardContent>
            </Card>

            {data.pendientes.length > 0 && (
              <Card>
                <CardHeader className="space-y-0">
                  <CardTitle className="text-base">Sin feed oficial</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="pb-2 text-xs text-muted-foreground">
                    Estas plataformas no publican un feed RSS oficial. Su cobertura llega vía
                    los agregadores (no se inventan datos).
                  </p>
                  <ul className="space-y-1.5">
                    {data.pendientes.map((p) => (
                      <li key={p.plataforma} className="text-xs">
                        <span className="font-medium">{p.nombre}</span>
                        <span className="text-muted-foreground"> — {p.motivo}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      <DialogoNuevaFuente
        abierto={nuevaFuente}
        onCerrar={() => setNuevaFuente(false)}
        onGuardar={(cuerpo) => crearFuente.mutate(cuerpo)}
        guardando={crearFuente.isPending}
        plataformas={data?.plataformas ?? []}
        tipos={data?.tipos ?? []}
      />
      <DialogoPropuesta propuesta={propuesta} onCerrar={() => setPropuesta(null)} />
    </div>
  );
}
