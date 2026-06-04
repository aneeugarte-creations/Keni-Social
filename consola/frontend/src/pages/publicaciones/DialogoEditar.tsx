import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, History, Link2, Loader2, MessageSquare, Pencil } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Comentarios } from "@/components/contenido/Comentarios";
import { Versiones } from "@/components/contenido/Versiones";
import { BarraFormato } from "@/components/editor/BarraFormato";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorImagen } from "@/components/media/EditorImagen";
import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import type { Documento } from "@/editor/documento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { ConstructorUtm } from "@/components/utm/ConstructorUtm";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import {
  parsearEncuadre,
  serializarEncuadre,
  type EncuadreFoto,
} from "@/lib/placa/encuadre";
import type { CuerpoActualizarPublicacion, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { GestionHashtags } from "./GestionHashtags";
import { EtiquetaRed } from "./insignias";
import { metaRed } from "./meta";
import { agregarEnlace } from "./plantillas";
import { etapaDePublicacion } from "@/pages/feed/etapa";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Pestañas del editor: previsualización, edición, colaboración (comentarios) e historial. */
type VistaEditor = "editar" | "comentarios" | "versiones";

/** Diálogo de edición de una publicación: título, contenido e imagen (placa con titular inline).
 *  El estado, la programación y la aprobación los gestiona el flujo (no se editan aquí). */
export function DialogoEditar({
  publicacion,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  // Texto que va DENTRO de la imagen (copy-in), distinto del contenido que la acompaña.
  const [copyIn, setCopyIn] = React.useState("");
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
  const [vista, setVista] = React.useState<VistaEditor>("editar");
  // --- Autoguardado --- //
  // Estado del indicador de guardado (la pieza se guarda sola al editar; el botón es opcional).
  const [estadoGuardado, setEstadoGuardado] = React.useState<"idle" | "guardando" | "guardado">("idle");
  const cargandoRef = React.useRef(true); // true mientras se cargan los valores al abrir (no autoguarda)
  const guardandoRef = React.useRef(false); // hay un guardado en vuelo
  const pendienteRef = React.useRef(false); // hubo cambios durante el guardado en vuelo
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

  // Plantillas del estudio por MARCA: como todo es 4:5 y se postea lo mismo a todas las redes, la
  // plantilla la dicta la marca (no la red). Distintas plantillas cubren los tipos de post
  // (breaking, infografía con logo, cita textual, logo del mundial, sin nada…). Se cargan siempre
  // (con marca) porque el editor renderiza la plantilla EN VIVO y necesita su documento.
  const plantillasQuery = useQuery({
    queryKey: ["plantillas-diseno", publicacion?.marca],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: publicacion?.marca }, signal),
    enabled: !!publicacion?.marca,
  });
  const plantillas = React.useMemo(
    () => plantillasQuery.data?.plantillas ?? [],
    [plantillasQuery.data],
  );
  // Plantilla por defecto de la marca: la "Placa de marca" migrada (o la primera que haya).
  const idPlacaDeMarca =
    plantillas.find((p) => p.nombre === "Placa de marca")?.id ?? plantillas[0]?.id ?? "";
  // Plantilla efectiva = la elegida por la pieza, o la de marca por defecto si no eligió ninguna.
  const idEfectivo = plantillaId || idPlacaDeMarca;
  // Documento a renderizar en vivo: null en modo "solo foto" (placaOculta) o si no hay plantilla.
  const documentoSel = React.useMemo(() => {
    if (placaOculta) return null;
    const p = plantillas.find((x) => x.id === idEfectivo);
    return (p?.documento as Documento | undefined) ?? null;
  }, [placaOculta, plantillas, idEfectivo]);

  // Elegir una plantilla de la galería: previa EN VIVO (sin round-trip); se hornea al guardar.
  const elegirPlantilla = (idPlantilla: string) => {
    setPlantillaId(idPlantilla);
    setPlacaOculta(false);
    setGaleriaPlantillas(false);
  };

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!publicacion) return;
    cargandoRef.current = true; // no autoguardar por los cambios de estado que provoca esta carga
    setTitulo(publicacion.titulo);
    setContenido(publicacion.contenido);
    setCopyIn(publicacion.copy_in ?? "");
    setImagen(publicacion.imagen ?? "");
    setImagenUrl(publicacion.imagen_url ?? "");
    setFoto(publicacion.foto ?? "");
    setPlacaOculta(publicacion.placa_oculta ?? false);
    setPlantillaId(publicacion.plantilla_diseno_id ?? "");
    setEncuadre(parsearEncuadre(publicacion.foto_encuadre));
    setVista("editar");
    setEstadoGuardado("idle");
    // Reabrimos el autoguardado tras aplicar la carga (en un tick: así el render que dispara esta
    // carga ve `cargandoRef=true` y no guarda; solo los cambios del usuario posteriores guardan).
    const t = setTimeout(() => {
      cargandoRef.current = false;
    }, 0);
    return () => clearTimeout(t);
  }, [publicacion]);

  const limite = publicacion ? metaRed(publicacion.red).limite : null;

  // Persiste la pieza. NO cierra el diálogo: lo comparten el autoguardado y el botón.
  const persistir = React.useCallback(async () => {
    if (!publicacion) return;
    // RENDER ON-DEMAND: las piezas de MARCA ya no hornean un PNG al guardar. Persistimos su
    // RECETA (foto + copy_in + placa_oculta + plantilla + encuadre) y dejamos `imagen` vacío; la
    // imagen publicable se renderiza on-demand en el servidor (/api/publicaciones/{id}/compuesta).
    // Así no se duplica un PNG por cada edición de texto. Las piezas SIN marca conservan su
    // `imagen` (imagen subida/generada, sin receta de placa).
    const imagenFinal = publicacion.marca ? "" : imagen;
    const cuerpo: CuerpoActualizarPublicacion = {
      titulo: titulo.trim(),
      contenido,
      copy_in: copyIn,
      imagen: imagenFinal,
      foto,
      placa_oculta: placaOculta,
      // Recuerda (o limpia) la plantilla del estudio elegida.
      plantilla_diseno_id: plantillaId,
      // Reencuadre manual de la foto ("" si está centrada sin zoom).
      foto_encuadre: serializarEncuadre(encuadre),
    };
    // El estado, la fecha y evergreen NO se tocan aquí: el flujo los gestiona solo (autogen → QA →
    // me gusta → auto-programar). PATCH parcial: lo no enviado queda intacto.
    const { publicacion: actualizada } = await api.actualizarPublicacion(publicacion.id, cuerpo);
    // AUTO-AVANCE: una pieza autogenerada/editada que YA tiene todo el contenido entra sola a
    // revisión (abre los "me gusta" del equipo). Sustituye al botón manual "Enviar a revisión".
    if (actualizada.estado === "borrador" && etapaDePublicacion(actualizada) === "lista_para_revisar") {
      try {
        await api.enviarARevision(publicacion.id);
      } catch {
        /* carrera / ya en revisión: lo ignoramos (el feed reflejará el estado real) */
      }
    }
  }, [publicacion, foto, copyIn, placaOculta, plantillaId, encuadre, imagen, titulo, contenido]);

  // Solo se autoguarda cuando los datos mínimos son válidos (título + contenido).
  const datosValidos =
    !!publicacion && titulo.trim().length > 0 && contenido.trim().length > 0;

  // Autoguardado: persiste sin cerrar; coalesciona los cambios ocurridos durante un guardado en vuelo.
  const autoguardar = React.useCallback(async () => {
    if (!datosValidos) return;
    if (guardandoRef.current) {
      pendienteRef.current = true;
      return;
    }
    guardandoRef.current = true;
    setEstadoGuardado("guardando");
    try {
      await persistir();
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      // Editar puede RESETEAR las aprobaciones (vuelve a borrador): refresca la cadena para que la
      // tarjeta no siga mostrando los OK viejos.
      if (publicacion) {
        void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
      }
      setEstadoGuardado("guardado");
    } catch (e) {
      setEstadoGuardado("idle");
      toast.error(mensajeError(e));
    } finally {
      guardandoRef.current = false;
      if (pendienteRef.current) {
        pendienteRef.current = false;
        void autoguardar();
      }
    }
  }, [datosValidos, persistir, queryClient, publicacion]);

  const autoguardarRef = React.useRef(autoguardar);
  autoguardarRef.current = autoguardar;

  // Dispara el autoguardado (debounced 1.2 s) cuando el usuario cambia algo. La `imagen` NO entra
  // en la firma: es resultado del horneado, no una edición del usuario (evita un bucle de guardado).
  const firmaAutoguardado = JSON.stringify({
    titulo, contenido, copyIn, foto, placaOculta, plantillaId,
    encuadre: serializarEncuadre(encuadre),
  });
  React.useEffect(() => {
    if (cargandoRef.current || !publicacion) return;
    const t = setTimeout(() => void autoguardarRef.current(), 1200);
    return () => clearTimeout(t);
  }, [firmaAutoguardado, publicacion]);

  const guardar = useMutation({
    mutationFn: persistir,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      // El tablero (feed/lista) lee `/api/contenido`: invalidamos su clave para que
      // refleje el copy/estado/imagen recién guardados desde este editor unificado.
      void queryClient.invalidateQueries({ queryKey: ["contenido"] });
      // Editar puede RESETEAR las aprobaciones: refresca la cadena (los OK viejos desaparecen).
      if (publicacion) {
        void queryClient.invalidateQueries({ queryKey: ["cadena-aprobacion", publicacion.id] });
      }
      setEstadoGuardado("guardado");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    !!publicacion && titulo.trim().length > 0 && contenido.trim().length > 0 && !guardar.isPending;

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
                // SISTEMA ÚNICO: la plantilla del estudio se renderiza EN VIVO en el lienzo (con tu
                // foto + reencuadre + titular in-place). El selector (galería por marca) y "solo foto"
                // son nativos en la cabecera del editor.
                <EditorPlacaInline
                  marca={publicacion.marca}
                  documento={documentoSel}
                  copyIn={copyIn}
                  onCopyInCambio={setCopyIn}
                  foto={foto}
                  onCambioFoto={setFoto}
                  imagenFuente={publicacion.imagen_fuente}
                  sinPlantilla={placaOculta}
                  onAlternarSinPlantilla={() => setPlacaOculta((v) => !v)}
                  encuadre={encuadre}
                  onEncuadreCambio={setEncuadre}
                  onAbrirGaleria={() => setGaleriaPlantillas(true)}
                />
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

        <DialogFooter className="items-center gap-2 sm:justify-between">
          {/* Indicador de autoguardado: la pieza se guarda sola al editar. */}
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground" aria-live="polite">
            {estadoGuardado === "guardando" ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
              </>
            ) : estadoGuardado === "guardado" ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" /> Guardado
              </>
            ) : (
              "Los cambios se guardan solos"
            )}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
              Cerrar
            </Button>
            <Button variant="positive" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar y cerrar
            </Button>
          </div>
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

        {/* Selector de plantilla del estudio (miniaturas) por MARCA. Al elegir, la previa se
            actualiza EN VIVO en el lienzo (sin round-trip); se hornea al guardar. */}
        {galeriaPlantillas && (
          <GaleriaPlantillas
            plantillas={plantillas}
            onCargar={(p) => elegirPlantilla(p.id)}
            onCerrar={() => setGaleriaPlantillas(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
