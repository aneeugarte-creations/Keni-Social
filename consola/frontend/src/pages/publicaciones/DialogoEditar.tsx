import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  History,
  Layers,
  LayoutTemplate,
  Link2,
  ListChecks,
  Loader2,
  MessageSquare,
  Pencil,
  Send,
  ShieldCheck,
  Sprout,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Comentarios } from "@/components/contenido/Comentarios";
import { Versiones } from "@/components/contenido/Versiones";
import { BarraFormato } from "@/components/editor/BarraFormato";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorImagen } from "@/components/media/EditorImagen";
import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { ConstructorUtm } from "@/components/utm/ConstructorUtm";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import {
  parsearEncuadre,
  serializarEncuadre,
  type EncuadreFoto,
} from "@/lib/placa/encuadre";
import { plural } from "@/lib/formato";
import type {
  CuerpoActualizarPlataforma,
  CuerpoActualizarPublicacion,
  EstadoOpcion,
  EstadoPublicacion,
  Publicacion,
} from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { GestionHashtags } from "./GestionHashtags";
import { EtiquetaRed } from "./insignias";
import { datetimeLocalAIso, formatearFechaHora, isoADatetimeLocal, metaRed } from "./meta";
import { agregarEnlace } from "./plantillas";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/**
 * Estados que el equipo elige A MANO en el desplegable de edición. La APROBACIÓN
 * (`en_revision` → `aprobado`) NO se elige aquí: se decide por la CADENA de aprobación
 * (botones Enviar a revisión / Aprobar / Rechazar), única vía de aprobación. Así nadie
 * salta la revisión poniendo el estado a mano. `programado`/`publicado` siguen disponibles.
 */
const ESTADOS_DECISION_CADENA = new Set(["en_revision", "aprobado"]);

/**
 * Panel de APROBACIÓN de una publicación: la cadena multinivel expresada para una pieza
 * suelta (cadena simple). Mantiene la aprobación ACCESIBLE desde la UI de Publicaciones:
 *  - `borrador`     → botón "Enviar a revisión" (crea la cadena y deja la pieza en revisión).
 *  - `en_revision`  → botones "Aprobar" / "Rechazar" (deciden el nivel actual; revisor != autor).
 *  - `aprobado`     → aviso de que ya está aprobada (lista para programar con su fecha).
 * Reusa los endpoints `/api/aprobacion/*`, que forwardean a la cadena.
 */
/** Checklist de producción por red (Copy/Imagen/Revisión/Publicar). Vive aquí, en el editor
 *  unificado (#fusion), desde que el tablero dejó de tener su lista propia. Marca = hecho
 *  (`!falta_X`); cada toque hace un PATCH a la fila por plataforma e invalida ambas superficies. */
const CHECKS_PRODUCCION = [
  { campo: "falta_copy", etiqueta: "Copy" },
  { campo: "falta_imagen", etiqueta: "Imagen" },
  { campo: "falta_revision", etiqueta: "Revisión" },
  { campo: "falta_publicar", etiqueta: "Publicar" },
] as const;

function ChecklistProduccion({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();
  const actualizar = useMutation({
    mutationFn: (cuerpo: CuerpoActualizarPlataforma) =>
      api.actualizarPlataforma(publicacion.contenido_id, publicacion.id, cuerpo),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["publicacion", publicacion.id] });
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // Sin tema padre (piezas legadas) no hay fila de tablero que togglear.
  if (!publicacion.contenido_id) return null;
  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ListChecks className="h-4 w-4 text-muted-foreground" />
        Checklist de producción
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        {CHECKS_PRODUCCION.map(({ campo, etiqueta }) => (
          <label key={campo} className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!publicacion[campo]}
              disabled={actualizar.isPending}
              onCheckedChange={(v) =>
                actualizar.mutate({ [campo]: !v } as CuerpoActualizarPlataforma)
              }
              aria-label={etiqueta}
            />
            {etiqueta}
          </label>
        ))}
      </div>
      {/* Exención de copy-in: el auto-avance exige copy-in salvo que se marque aquí (imágenes
          dramáticas/autoexplicativas a las que el texto dentro de la imagen solo estorba). */}
      <label className="flex cursor-pointer items-center gap-2 border-t border-border/60 pt-2 text-sm">
        <Checkbox
          checked={!!publicacion.copy_in_exento}
          disabled={actualizar.isPending}
          onCheckedChange={(v) => actualizar.mutate({ copy_in_exento: !!v })}
          aria-label="No necesita copy-in"
        />
        Esta imagen no necesita copy-in
      </label>
    </div>
  );
}

function PanelAprobacion({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();

  // La publicación ES una fila por plataforma: su id es el `plataforma_id` de la cadena.
  // Leemos la cadena para mostrar los GATES de gobernanza (item A: mínimo de aprobaciones;
  // item B: comentarios sin resolver) y avisar antes de programar.
  const cadenaQuery = useQuery({
    queryKey: ["cadena-aprobacion", publicacion.id],
    queryFn: ({ signal }) => api.cadenaAprobacion(publicacion.id, signal),
  });
  const cadena = cadenaQuery.data;
  const sinResolver = cadena?.comentarios_sin_resolver ?? 0;
  const minimo = cadena?.minimo_aprobaciones ?? 0;
  const aprobados = cadena?.aprobados ?? 0;
  const faltanFirmas = minimo > 0 && aprobados < minimo;

  // QA editorial como APROBADOR AUTOMATICO (item E): si el primer nivel es "QA Editorial" y lo
  // decidió la máquina (decisor "auto"), reflejamos el veredicto automático. 🟡 (pendiente) deja
  // el nivel abierto a un humano y no se sella decisor: se muestra como "requiere revisión".
  const nivelQa = (cadena?.niveles ?? []).find(
    (n) => n.etiqueta.trim().toLowerCase() === "qa editorial",
  );
  const qaAutoResuelto = nivelQa?.decisor_id === "auto" && nivelQa.decision !== "pendiente";

  const tras = (mensaje: string) => () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
    void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

  const enviar = useMutation({
    mutationFn: () => api.enviarARevision(publicacion.id),
    onSuccess: tras("Enviada a revisión."),
    onError,
  });
  const aprobar = useMutation({
    mutationFn: () => api.aprobarPublicacion(publicacion.id),
    onSuccess: tras("Publicación aprobada."),
    onError,
  });
  const rechazar = useMutation({
    mutationFn: () => api.rechazarPublicacion(publicacion.id),
    onSuccess: tras("Devuelta a borrador."),
    onError,
  });
  const ocupado = enviar.isPending || aprobar.isPending || rechazar.isPending;

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
        Aprobación
      </div>
      {nivelQa && (
        <p
          className={
            qaAutoResuelto && nivelQa.decision === "rechazado"
              ? "text-xs text-red-600 dark:text-red-400"
              : qaAutoResuelto
                ? "text-xs text-emerald-600 dark:text-emerald-400"
                : "text-xs text-muted-foreground"
          }
        >
          {qaAutoResuelto && nivelQa.decision === "aprobado"
            ? "🟢 QA editorial: aprobado automáticamente. La decisión final es humana."
            : qaAutoResuelto && nivelQa.decision === "rechazado"
              ? "🔴 QA editorial: rechazado automáticamente. Corrige el copy y vuelve a revisar."
              : "🟡 QA editorial: requiere revisión humana (sin veredicto automático que aplicar)."}
        </p>
      )}
      {publicacion.estado === "borrador" && (
        <>
          <p className="text-xs text-muted-foreground">
            Envíala a revisión para que otra persona la apruebe antes de programarla.
          </p>
          <Button size="sm" onClick={() => enviar.mutate()} disabled={ocupado}>
            {enviar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Enviar a revisión
          </Button>
        </>
      )}
      {sinResolver > 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {plural(sinResolver, "comentario")} sin resolver. Resuélvelos antes de programar.
        </p>
      )}
      {publicacion.estado === "en_revision" && (
        <>
          <p className="text-xs text-muted-foreground">
            En revisión. Quien aprueba no puede ser el autor (salvo admin).
          </p>
          <div className="flex gap-2">
            <Button variant="positive" size="sm" onClick={() => aprobar.mutate()} disabled={ocupado}>
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Aprobar
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => rechazar.mutate()}
              disabled={ocupado}
            >
              {rechazar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Rechazar
            </Button>
          </div>
        </>
      )}
      {(publicacion.estado === "aprobado" ||
        publicacion.estado === "programado" ||
        publicacion.estado === "publicado") && (
        <>
          <p className="text-xs text-muted-foreground">
            {publicacion.revisor_nombre
              ? `Aprobada por ${publicacion.revisor_nombre}.`
              : "Aprobada."}{" "}
            {faltanFirmas || sinResolver > 0
              ? "Aún no se puede programar (revisa los avisos)."
              : "Ya puedes programarla eligiendo el estado “Programado” y su fecha."}
          </p>
          {minimo > 0 && (
            <p
              className={
                faltanFirmas
                  ? "text-xs text-amber-600 dark:text-amber-400"
                  : "text-xs text-muted-foreground"
              }
            >
              Aprobaciones: {aprobados} de {minimo}.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Pestañas del editor: previsualización, edición, colaboración (comentarios) e historial. */
type VistaEditor = "editar" | "comentarios" | "versiones";

/** Diálogo de edición de una publicación: título, contenido, estado y fecha. */
export function DialogoEditar({
  publicacion,
  estados,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  estados: EstadoOpcion[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  // Texto que va DENTRO de la imagen (copy-in), distinto del contenido que la acompaña.
  const [copyIn, setCopyIn] = React.useState("");
  const [estado, setEstado] = React.useState<EstadoPublicacion>("borrador");
  const [evergreen, setEvergreen] = React.useState(false);
  const [fechaLocal, setFechaLocal] = React.useState("");
  // Imagen: nombre del archivo + url para previsualizar.
  const [imagen, setImagen] = React.useState("");
  const [imagenUrl, setImagenUrl] = React.useState("");
  // Foto cruda de fondo (media id) para el editor inline de placa; se hornea a `imagen` al guardar.
  const [foto, setFoto] = React.useState("");
  // "Quitar plantilla": publicar solo la foto, sin placa. Se persiste en la pieza (`placa_oculta`).
  const [placaOculta, setPlacaOculta] = React.useState(false);
  // Plantilla del estudio elegida ("" = placa de marca por defecto / editor en vivo). La pieza la
  // recuerda (`plantilla_diseno_id`); en modo plantilla el editor muestra el resultado renderizado.
  const [plantillaId, setPlantillaId] = React.useState("");
  // Reencuadre manual de la foto dentro del marco 4:5 (null = sin reencuadre). La pieza lo persiste.
  const [encuadre, setEncuadre] = React.useState<EncuadreFoto | null>(null);
  const [galeriaPlantillas, setGaleriaPlantillas] = React.useState(false);
  // Función de "bake" que registra el editor inline (hornea el canvas a un media id al guardar).
  const bakeRef = React.useRef<(() => Promise<string | null>) | null>(null);
  const [vista, setVista] = React.useState<VistaEditor>("editar");
  const [gestionHashtags, setGestionHashtags] = React.useState(false);
  const [utmAbierto, setUtmAbierto] = React.useState(false);
  const areaRef = React.useRef<HTMLTextAreaElement>(null);

  // Catálogo de marcas para la gestión de grupos de hashtags.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: publicacion !== null,
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // Plantillas del estudio para ESTA marca + red (la `categoria` de la plantilla es la red). Se
  // cargan al abrir la galería para no pedirlas si no se usan.
  const plantillasQuery = useQuery({
    queryKey: ["plantillas-diseno", publicacion?.marca, publicacion?.red],
    queryFn: ({ signal }) =>
      api.plantillasDiseno({ marca: publicacion?.marca, categoria: publicacion?.red }, signal),
    enabled: galeriaPlantillas && !!publicacion?.marca,
  });
  const plantillas = plantillasQuery.data?.plantillas ?? [];

  // Aplicar una plantilla del estudio: el servidor RE-RENDERIZA con la foto y el copy-in actuales
  // (los del editor, aún sin guardar) y persiste. Actualizamos la previa al resultado.
  const aplicarPlantilla = useMutation({
    mutationFn: (idPlantilla: string) =>
      api.aplicarPlantillaPublicacion(publicacion!.id, idPlantilla, {
        foto,
        copy_in: copyIn,
        foto_encuadre: serializarEncuadre(encuadre),
      }),
    onSuccess: ({ publicacion: p }) => {
      setImagen(p.imagen ?? "");
      setImagenUrl(p.imagen_url ?? "");
      setFoto(p.foto ?? "");
      setPlantillaId(p.plantilla_diseno_id ?? "");
      setEncuadre(parsearEncuadre(p.foto_encuadre));
      setGaleriaPlantillas(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success("Plantilla aplicada");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo aplicar la plantilla."),
  });

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!publicacion) return;
    setTitulo(publicacion.titulo);
    setContenido(publicacion.contenido);
    setCopyIn(publicacion.copy_in ?? "");
    setEstado(publicacion.estado);
    setEvergreen(publicacion.evergreen ?? false);
    setFechaLocal(isoADatetimeLocal(publicacion.fecha_programada));
    setImagen(publicacion.imagen ?? "");
    setImagenUrl(publicacion.imagen_url ?? "");
    setFoto(publicacion.foto ?? "");
    setPlacaOculta(publicacion.placa_oculta ?? false);
    setPlantillaId(publicacion.plantilla_diseno_id ?? "");
    setEncuadre(parsearEncuadre(publicacion.foto_encuadre));
    setVista("editar");
  }, [publicacion]);

  const limite = publicacion ? metaRed(publicacion.red).limite : null;
  const programado = estado === "programado";

  // El desplegable de estado NO ofrece los estados de la cadena de aprobación
  // (`en_revision`/`aprobado`): esos se alcanzan SOLO por los botones del panel de
  // aprobación. Si la pieza YA está en uno de ellos, lo dejamos visible (deshabilitado de
  // hecho por no estar en la lista de cambios) para no romper el Select controlado.
  const estadosElegibles = React.useMemo(
    () => estados.filter((e) => !ESTADOS_DECISION_CADENA.has(e.id) || e.id === estado),
    [estados, estado],
  );

  const guardar = useMutation({
    mutationFn: async () => {
      if (!publicacion) throw new Error("Sin publicación");
      // Piezas de marca SIN plantilla del estudio: HORNEAR el canvas de la placa (spec) a un media
      // id publicable. CON plantilla del estudio la imagen ya es el render del documento (vía
      // "aplicar plantilla"): NO se hornea el spec encima (lo pisaría). La `foto` cruda se persiste.
      let imagenFinal = imagen;
      if (publicacion.marca && !plantillaId && bakeRef.current) {
        const horneada = await bakeRef.current();
        if (horneada) imagenFinal = horneada;
      }
      const cuerpo: CuerpoActualizarPublicacion = {
        titulo: titulo.trim(),
        contenido,
        copy_in: copyIn,
        estado,
        evergreen,
        // Solo mandamos fecha si está programado; al salir de programado, la limpiamos.
        fecha_programada: programado ? datetimeLocalAIso(fechaLocal) : null,
        imagen: imagenFinal,
        foto,
        placa_oculta: placaOculta,
        // Recuerda (o limpia) la plantilla del estudio elegida.
        plantilla_diseno_id: plantillaId,
        // Reencuadre manual de la foto ("" si está centrada sin zoom).
        foto_encuadre: serializarEncuadre(encuadre),
      };
      return api.actualizarPublicacion(publicacion.id, cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      // El tablero (feed/lista) lee `/api/contenido`: invalidamos su clave para que
      // refleje el copy/estado/imagen recién guardados desde este editor unificado.
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      toast.success("Publicación actualizada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const faltaFecha = programado && !fechaLocal;
  const puedeGuardar =
    !!publicacion && titulo.trim().length > 0 && contenido.trim().length > 0 && !faltaFecha && !guardar.isPending;

  return (
    <Dialog open={publicacion !== null} onOpenChange={(o) => !o && onCerrar()}>
      {/* En móvil el editor ocupa toda la pantalla (h-dvh, ancho completo, sin
          radios) para que el revisor edite cómodo en el feed; en escritorio
          mantiene el modal centrado de 2xl. */}
      <DialogContent className="max-h-dvh h-dvh max-w-full overflow-y-auto rounded-none sm:h-auto sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg">
        <DialogHeader>
          <DialogTitle>Editar publicación</DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            {publicacion && (
              <>
                <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
                <span className="text-muted-foreground">· {publicacion.marca_nombre}</span>
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={vista} onValueChange={(v) => setVista(v as VistaEditor)}>
          <TabsList>
            <TabsTrigger value="editar" className="gap-1.5">
              <Pencil className="h-4 w-4" />
              Editar
            </TabsTrigger>
            <TabsTrigger
              value="comentarios"
              className="gap-1.5"
              disabled={!publicacion?.contenido_id}
            >
              <MessageSquare className="h-4 w-4" />
              Comentarios
            </TabsTrigger>
            <TabsTrigger value="versiones" className="gap-1.5" disabled={!publicacion}>
              <History className="h-4 w-4" />
              Versiones
            </TabsTrigger>
          </TabsList>

          <TabsContent value="editar" className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="editar-titulo">Título</Label>
              <Input
                id="editar-titulo"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                maxLength={200}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="editar-contenido">Contenido</Label>
                <ContadorCaracteres caracteres={contenido.length} limite={limite} />
              </div>
              <AutoTextarea
                ref={areaRef}
                id="editar-contenido"
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                maxHeight={420}
                className="min-h-[10rem] font-mono text-sm"
              />
              {publicacion && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8"
                    onClick={() => setUtmAbierto(true)}
                  >
                    <Link2 className="h-4 w-4" />
                    Enlace UTM
                  </Button>
                  <BarraFormato refArea={areaRef} valor={contenido} onContenido={setContenido} />
                </div>
              )}
            </div>

            {publicacion && (
              <HerramientasHashtags
                contenido={contenido}
                onContenido={setContenido}
                marca={publicacion.marca}
                red={publicacion.red}
                onGestionar={() => setGestionHashtags(true)}
              />
            )}

            {publicacion &&
              (publicacion.marca ? (
                plantillaId ? (
                  // MODO PLANTILLA DEL ESTUDIO: la imagen ya es el render del documento elegido
                  // (con tu foto + copy-in). Muestra el resultado y deja cambiar/quitar plantilla.
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-sm font-medium">
                        <LayoutTemplate className="h-4 w-4 text-muted-foreground" />
                        Imagen <span className="font-normal text-muted-foreground">· plantilla del estudio</span>
                      </span>
                      <div className="flex gap-1.5">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-7 gap-1.5 px-2 text-xs"
                          onClick={() => setGaleriaPlantillas(true)}
                          disabled={aplicarPlantilla.isPending}
                        >
                          {aplicarPlantilla.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <LayoutTemplate className="h-3.5 w-3.5" />
                          )}
                          Cambiar plantilla
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-xs"
                          onClick={() => setPlantillaId("")}
                          title="Volver a la placa de marca por defecto y editar la foto"
                        >
                          Quitar
                        </Button>
                      </div>
                    </div>
                    <div className="flex justify-center rounded-md border border-border bg-muted/20 p-2">
                      {imagenUrl ? (
                        <img src={imagenUrl} alt="" className="max-h-[22rem] w-auto rounded-md" />
                      ) : (
                        <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
                          Aplicando…
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Renderizada con tu foto y tu copy-in. Cambia de plantilla para comparar; «Quitar»
                      vuelve al editor de placa por defecto.
                    </p>
                  </div>
                ) : (
                  // MODO EDITOR (placa de marca por defecto): editor INLINE en vivo + probar una
                  // plantilla del estudio (diseñadas por marca y red en el estudio de diseño).
                  <div className="space-y-2.5">
                    <EditorPlacaInline
                      marca={publicacion.marca}
                      red={publicacion.red}
                      copyIn={copyIn}
                      foto={foto}
                      onCambioFoto={setFoto}
                      imagenFuente={publicacion.imagen_fuente}
                      placaOculta={placaOculta}
                      onPlacaOcultaCambio={setPlacaOculta}
                      encuadre={encuadre}
                      onEncuadreCambio={setEncuadre}
                      registrarBake={(fn) => {
                        bakeRef.current = fn;
                      }}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setGaleriaPlantillas(true)}
                    >
                      <LayoutTemplate className="h-4 w-4" />
                      Probar una plantilla del estudio
                    </Button>
                  </div>
                )
              ) : (
                // Pieza sin marca: foto cruda (sin placa) con el editor de imagen clásico.
                <EditorImagen
                  imagen={imagen}
                  imagenUrl={imagenUrl}
                  onCambio={(nombre, url) => {
                    setImagen(nombre);
                    setImagenUrl(url);
                  }}
                  idPrefijo="editar"
                  publicacionId={publicacion.id}
                  red={publicacion.red}
                  copy={contenido}
                  copyIn={copyIn}
                  imagenFuente={publicacion.imagen_fuente}
                />
              ))}

            {publicacion && (
              <a
                href={
                  `/contenido/editor?contenido=${encodeURIComponent(publicacion.contenido_id)}` +
                  `&plataforma=${encodeURIComponent(publicacion.id)}` +
                  `&marca=${encodeURIComponent(publicacion.marca || "")}` +
                  `&formato=${
                    publicacion.red === "tiktok"
                      ? "vertical"
                      : publicacion.red === "instagram"
                        ? "cuadrado"
                        : publicacion.red === "x" || publicacion.red === "twitter"
                          ? "horizontal"
                          : "feed"
                  }`
                }
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary underline"
              >
                <Layers className="h-3.5 w-3.5" /> Abrir en el editor por capas
              </a>
            )}

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="editar-copy-in">Texto en imagen</Label>
                <span className="text-xs text-muted-foreground">{copyIn.length} car.</span>
              </div>
              <AutoTextarea
                id="editar-copy-in"
                value={copyIn}
                onChange={(e) => setCopyIn(e.target.value)}
                maxHeight={200}
                className="min-h-[4rem] font-mono text-sm"
                placeholder="Titular o frase que va DENTRO de la imagen (placa)."
              />
              <p className="text-xs text-muted-foreground">
                El texto sobre la imagen, distinto del contenido que la acompaña. Sigue las
                reglas de texto-en-imagen de la marca.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="editar-estado">Estado</Label>
                <Select value={estado} onValueChange={(v) => setEstado(v as EstadoPublicacion)}>
                  <SelectTrigger id="editar-estado">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {estadosElegibles.map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.nombre}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {programado && (
                <div className="space-y-1.5">
                  <Label htmlFor="editar-fecha">Fecha y hora programada</Label>
                  <Input
                    id="editar-fecha"
                    type="datetime-local"
                    value={fechaLocal}
                    onChange={(e) => setFechaLocal(e.target.value)}
                  />
                  {faltaFecha && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      Elige una fecha para programar la publicación.
                    </p>
                  )}
                </div>
              )}
            </div>

            {publicacion && (publicacion.fecha_creacion || publicacion.fecha_fuente) && (
              // Trazabilidad de la pieza (sobre todo las que nacen del pipeline automático):
              // cuándo la generó el sistema y de qué fecha es la nota/fuente de origen. Ambas
              // en hora CDMX (los instantes del backend son UTC). "Fuente" se omite si la
              // fuente no traía fecha o si la pieza es de alta manual.
              <dl className="flex flex-wrap gap-x-6 gap-y-1 rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground">
                {publicacion.fecha_creacion && (
                  <div className="flex gap-1.5">
                    <dt className="font-medium text-foreground">Generado</dt>
                    <dd>{formatearFechaHora(publicacion.fecha_creacion)}</dd>
                  </div>
                )}
                {publicacion.fecha_fuente && (
                  <div className="flex gap-1.5">
                    <dt className="font-medium text-foreground">Fuente</dt>
                    <dd>{formatearFechaHora(publicacion.fecha_fuente)}</dd>
                  </div>
                )}
              </dl>
            )}

            {publicacion && <ChecklistProduccion publicacion={publicacion} />}

            {publicacion && <PanelAprobacion publicacion={publicacion} />}

            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/20 p-3">
              <Checkbox
                id="editar-evergreen"
                checked={evergreen}
                onCheckedChange={setEvergreen}
                aria-label="Marcar como perenne"
                className="mt-0.5"
              />
              <div className="space-y-0.5">
                <Label
                  htmlFor="editar-evergreen"
                  className="flex cursor-pointer items-center gap-1.5 font-normal"
                >
                  <Sprout className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  Contenido perenne
                </Label>
                <p className="text-xs text-muted-foreground">
                  Marca esta publicación como reutilizable para reciclarla y volver a publicarla
                  más adelante.
                </p>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="comentarios">
            {publicacion?.contenido_id && <Comentarios contenidoId={publicacion.contenido_id} />}
          </TabsContent>

          <TabsContent value="versiones">
            {publicacion && (
              <Versiones
                plataformaId={publicacion.id}
                copyActual={publicacion.contenido}
                redNombre={publicacion.red_nombre}
              />
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
            Cancelar
          </Button>
          <Button variant="positive" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar cambios
          </Button>
        </DialogFooter>

        <GestionHashtags
          abierto={gestionHashtags}
          onCerrar={() => setGestionHashtags(false)}
          marcas={marcas}
        />

        <ConstructorUtm
          abierto={utmAbierto}
          onCerrar={() => setUtmAbierto(false)}
          onInsertar={(enlace) => setContenido((prev) => agregarEnlace(prev, enlace))}
        />

        {/* Selector de plantilla del estudio (miniaturas) para ESTA marca+red. Al elegir, el
            servidor re-renderiza la imagen de la pieza con la plantilla y tu foto+copy-in. */}
        {galeriaPlantillas && (
          <GaleriaPlantillas
            plantillas={plantillas}
            onCargar={(p) => aplicarPlantilla.mutate(p.id)}
            onCerrar={() => setGaleriaPlantillas(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
