/**
 * Campañas: seguimiento de campañas de marca agrupadas por uno o varios HASHTAGS.
 *
 * Se elige una campaña (definida por sus hashtags) y un periodo, y se ven KPIs
 * (visualizaciones, interacciones, engagement) con comparativa, la tendencia diaria
 * y la tabla de piezas del periodo —solo las piezas cuyo texto lleva alguno
 * de los hashtags—. Las campañas son MULTIMARCA: no se acotan al switch de marca
 * de la barra superior, una misma campaña puede abarcar varias marcas a la vez
 * (cada pieza de la tabla lleva su propia marca).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare,
  Download,
  Link2,
  Megaphone,
  Pencil,
  Plus,
  Presentation,
  Square,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { hoyCDMX } from "@/lib/fecha";
import { api, mensajeError } from "@/lib/api";
import type { AnaliticaCampania, Campania } from "@/types";

import { CLAVE_CAMPANIAS } from "./campanias/claves";
import { DialogoCampania } from "./campanias/DialogoCampania";
import { DialogoDescargarPdf } from "./campanias/DialogoDescargarPdf";
import { DialogoEnlacesPublicos } from "./campanias/DialogoEnlacesPublicos";
import { enlaceVigentePara, urlEnlace } from "./campanias/formato";
import { PanelCampania } from "./campanias/PanelCampania";
import { SelectorTiempo } from "./metricas/Controles";
import { etiquetaPeriodo } from "./metricas/periodo";

/**
 * Token `rango:AAAA-MM-DD_AAAA-MM-DD` de los últimos `n` días (incluye `hoy`, día CDMX).
 * El backend (`resolver_rango`) lo entiende igual que los presets. Las campañas abarcan
 * semanas o meses, así que no basta con la ventana de 30 días: un post con el hashtag
 * publicado hace 2 meses (p. ej. de un evento) debe poder verse ampliando el periodo.
 */
// Formatos de descarga ofrecidos en el menú (CSV para Excel/Sheets, Markdown legible, JSON crudo).
const FORMATOS_DESCARGA: Array<{ formato: "csv" | "md" | "json"; etiqueta: string }> = [
  { formato: "csv", etiqueta: "CSV" },
  { formato: "md", etiqueta: "Markdown" },
  { formato: "json", etiqueta: "JSON" },
];

function tokenUltimosDias(hoy: string, n: number): string {
  // Aritmética de días anclada a mediodía UTC para que no desplace el día calendario.
  const d = new Date(`${hoy}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - (n - 1));
  return `rango:${d.toISOString().slice(0, 10)}_${hoy}`;
}

export default function Campanias() {
  const queryClient = useQueryClient();
  const [rango, setRango] = React.useState("mes");

  // Periodos ofrecidos para la analítica (tokens que entiende el backend). Los más largos se
  // calculan respecto al día CDMX de HOY; recalcula al cambiar de día (no congelados al cargar).
  const hoy = hoyCDMX();
  const RANGOS = React.useMemo(
    () => [
      { id: "semana", etiqueta: "Última semana" },
      { id: "mes", etiqueta: "Últimos 30 días" },
      { id: tokenUltimosDias(hoy, 90), etiqueta: "Últimos 90 días" },
      { id: tokenUltimosDias(hoy, 180), etiqueta: "Últimos 6 meses" },
    ],
    [hoy],
  );
  const [seleccionada, setSeleccionada] = React.useState<string | null>(null);
  // Modo cliente: oculta TODO lo de Ads (el cliente no debe ver que se usó pauta) y suma las
  // visualizaciones pagadas a las orgánicas. Persiste para que aguante al recargar/compartir.
  const [ocultarAds, setOcultarAds] = React.useState(
    () => localStorage.getItem("keni:campanias:ocultarAds") === "1",
  );
  React.useEffect(() => {
    localStorage.setItem("keni:campanias:ocultarAds", ocultarAds ? "1" : "0");
  }, [ocultarAds]);
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState<Campania | null>(null);
  const [enlacesAbierto, setEnlacesAbierto] = React.useState(false);
  // Diálogo «Descargar PDF»: al abrirlo se resuelve la analítica cacheada, el token del enlace
  // vigente y su QR (para pintar la lámina de cierre en la previa), y todo se congela aquí.
  const [pdf, setPdf] = React.useState<{
    datos: AnaliticaCampania;
    tokenEnlace: string | null;
    enlacePrevia: { url: string; qrDataUrl: string } | null;
  } | null>(null);

  // Las campañas son MULTIMARCA: no se acotan al switch de marca de la barra; se listan
  // todas. La elección de marcas vive en el diálogo (sobre las marcas de la persona).
  const listaQuery = useQuery({
    queryKey: [...CLAVE_CAMPANIAS, "lista"],
    queryFn: ({ signal }) => api.campanias({}, signal),
  });

  const campanias = React.useMemo(
    () => listaQuery.data?.campanias ?? [],
    [listaQuery.data],
  );

  // Mantener una campaña seleccionada válida cuando cambia la lista.
  React.useEffect(() => {
    if (campanias.length === 0) {
      if (seleccionada !== null) setSeleccionada(null);
      return;
    }
    if (!seleccionada || !campanias.some((c) => c.id === seleccionada)) {
      setSeleccionada(campanias[0].id);
    }
  }, [campanias, seleccionada]);

  const campaniaActual = campanias.find((c) => c.id === seleccionada) ?? null;

  const eliminar = useMutation({
    mutationFn: (id: string) => api.eliminarCampania(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CAMPANIAS });
      toast.success("Campaña eliminada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const abrirNueva = () => {
    setEditando(null);
    setDialogoAbierto(true);
  };
  const abrirEdicion = (c: Campania) => {
    setEditando(c);
    setDialogoAbierto(true);
  };

  // PDF "testigo" de la campaña: reusa la analítica ya cargada por el panel (misma queryKey, sin
  // volver a pedirla) y, si hay un enlace público vigente para este periodo/modo, prepara su QR
  // para el cierre. Se abre el diálogo de descarga (previa + selección); no descarga directo.
  const abrirDialogoPdf = async () => {
    if (!campaniaActual) return;
    const datos = queryClient.getQueryData<AnaliticaCampania>([
      ...CLAVE_CAMPANIAS,
      "analitica",
      campaniaActual.id,
      rango,
    ]);
    if (!datos) {
      toast.error("Aún no hay datos cargados para el PDF.");
      return;
    }
    try {
      const { enlaces } = await api.enlacesCampania(campaniaActual.id);
      const vigente = enlaceVigentePara(enlaces, rango, ocultarAds);
      let enlacePrevia: { url: string; qrDataUrl: string } | null = null;
      if (vigente) {
        const url = urlEnlace(vigente.token);
        const { default: qrcode } = await import("qrcode-generator");
        const qr = qrcode(0, "M");
        qr.addData(url);
        qr.make();
        enlacePrevia = { url, qrDataUrl: qr.createDataURL(8, 4) };
      }
      setPdf({ datos, tokenEnlace: vigente?.token ?? null, enlacePrevia });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo preparar el PDF.");
    }
  };

  return (
    <>
      {listaQuery.isPending ? (
        <Esqueleto />
      ) : listaQuery.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las campañas"
          mensaje={listaQuery.error instanceof Error ? listaQuery.error.message : undefined}
          onReintentar={() => void listaQuery.refetch()}
          cargando={listaQuery.isFetching}
        />
      ) : campanias.length === 0 ? (
        <EstadoVacio
          icono={Megaphone}
          titulo="Aún no hay campañas"
          texto="Crea una campaña para dar seguimiento a piezas con sus hashtags."
          accion={
            <Button onClick={abrirNueva}>
              <Plus className="h-4 w-4" />
              Nueva campaña
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={seleccionada ?? ""} onValueChange={setSeleccionada}>
                <SelectTrigger className="w-full sm:w-[260px]" aria-label="Campaña">
                  <SelectValue placeholder="Elige una campaña" />
                </SelectTrigger>
                <SelectContent>
                  {campanias.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {campaniaActual && (
                <MenuAcciones>
                  <ItemMenu icono={Plus} onClick={abrirNueva}>
                    Nueva campaña
                  </ItemMenu>
                  <ItemMenu icono={Pencil} onClick={() => abrirEdicion(campaniaActual)}>
                    Editar campaña
                  </ItemMenu>
                  <ItemMenu
                    icono={Trash2}
                    className="text-rose-600 dark:text-rose-400"
                    onClick={() => eliminar.mutate(campaniaActual.id)}
                  >
                    Eliminar campaña
                  </ItemMenu>
                  {/* Enlace público: capability-URL de solo lectura para compartir SOLO esta
                      campaña (sin login). Congela el periodo y el modo actuales. */}
                  <div role="separator" className="my-1 h-px bg-border" />
                  <ItemMenu icono={Link2} onClick={() => setEnlacesAbierto(true)}>
                    Enlace público…
                  </ItemMenu>
                  {/* Descargas de la analítica del periodo activo. Respeta el modo cliente
                      (`ocultarAds`): si está activo, el archivo sale sin rastro de pauta. */}
                  <div role="separator" className="my-1 h-px bg-border" />
                  {FORMATOS_DESCARGA.map(({ formato, etiqueta }) => (
                    <ItemMenu
                      key={`descarga-${formato}`}
                      icono={Download}
                      onClick={() =>
                        api.exportarCampania(campaniaActual.id, formato, { rango, ocultarAds })
                      }
                    >
                      {`Descargar (${etiqueta})`}
                    </ItemMenu>
                  ))}
                  <ItemMenu icono={Presentation} onClick={() => void abrirDialogoPdf()}>
                    Descargar PDF…
                  </ItemMenu>
                  {/* Modo cliente: ajuste de vista persistente, como toggle directo del menú
                      (oculta Ads y suma sus visualizaciones a las orgánicas). */}
                  <div role="separator" className="my-1 h-px bg-border" />
                  <ItemMenu
                    icono={ocultarAds ? CheckSquare : Square}
                    onClick={() => setOcultarAds((v) => !v)}
                  >
                    Modo cliente
                  </ItemMenu>
                </MenuAcciones>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* Aviso visible mientras el modo cliente está activo: que no se enseñen cifras
                  "sin Ads" creyendo que es la vista completa. */}
              {ocultarAds && (
                <Badge variant="secondary" title="Modo cliente activo: lo de Ads está oculto y sumado a lo orgánico. Se cambia en el menú «⋮».">
                  Ads ocultos
                </Badge>
              )}
              <SelectorTiempo rangos={RANGOS} valor={rango} onCambio={setRango} />
            </div>
          </div>

          {campaniaActual && (
            <div className="flex flex-wrap items-center gap-1.5">
              {campaniaActual.marcas_nombres.map((nombre) => (
                <Badge key={nombre} variant="outline">
                  {nombre}
                </Badge>
              ))}
              {campaniaActual.marcas_nombres.length > 0 && campaniaActual.hashtags.length > 0 && (
                <span className="mx-1 text-muted-foreground">·</span>
              )}
              {campaniaActual.hashtags.map((h) => (
                <Badge key={h} variant="secondary">
                  #{h}
                </Badge>
              ))}
            </div>
          )}

          {seleccionada && (
            <PanelCampania campaniaId={seleccionada} rango={rango} ocultarAds={ocultarAds} />
          )}
        </div>
      )}

      <DialogoCampania
        abierto={dialogoAbierto}
        campania={editando}
        onCerrar={() => setDialogoAbierto(false)}
      />

      <DialogoEnlacesPublicos
        abierto={enlacesAbierto}
        campania={campaniaActual}
        rango={rango}
        ocultarAds={ocultarAds}
        onCerrar={() => setEnlacesAbierto(false)}
      />

      <DialogoDescargarPdf
        abierto={pdf !== null}
        datos={pdf?.datos ?? null}
        periodoEtiqueta={etiquetaPeriodo(rango, RANGOS)}
        ocultarAds={ocultarAds}
        tokenEnlace={pdf?.tokenEnlace ?? null}
        enlacePrevia={pdf?.enlacePrevia ?? null}
        onCerrar={() => setPdf(null)}
      />
    </>
  );
}

function Esqueleto() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-72 rounded-lg" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 w-full rounded-xl" />
    </div>
  );
}
