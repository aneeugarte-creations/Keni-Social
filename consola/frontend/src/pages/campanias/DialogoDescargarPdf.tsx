/**
 * Diálogo «Descargar PDF» de una campaña: antes de descargar, la persona PREVISUALIZA el deck y
 * ajusta QUÉ entra —qué secciones y qué piezas («el testigo»)—. La previa refleja la selección en
 * vivo (mismo componente `DeckCampania` que se rasteriza), así que se ve exactamente la data que se
 * va a mostrar antes de generar el PDF. La descarga usa el deck montado fuera de pantalla a tamaño
 * real (calidad), no esta previa escalada.
 */
import { useMutation } from "@tanstack/react-query";
import { Presentation, Search } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

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
import { Spinner } from "@/components/ui/spinner";
import { nombreRed, numeroCompacto } from "@/lib/formato";
import type { AnaliticaCampania, PiezaCampania } from "@/types";

import { descargarPdfCampania } from "./exportarPdfCampania";
import { clavePieza, visEfectivas } from "./formato";
import {
  DeckCampania,
  SECCIONES_TODAS,
  type SeccionesDeck,
} from "./informe/DeckCampania";

/** Ancho real de una lámina del deck; la previa la escala a `ANCHO_PREVIA`. */
const ANCHO_LAMINA = 1280;
const ANCHO_PREVIA = 520;
const ESCALA = ANCHO_PREVIA / ANCHO_LAMINA;

const SECCIONES: Array<{ clave: keyof SeccionesDeck; etiqueta: string }> = [
  { clave: "kpis", etiqueta: "Resultados (KPIs)" },
  { clave: "tendencia", etiqueta: "Tendencia diaria" },
  { clave: "desgloseRed", etiqueta: "Desglose por red" },
  { clave: "piezas", etiqueta: "Piezas (el testigo)" },
];

/** Pieza con su clave estable y las vistas a mostrar, ordenadas por vistas efectivas desc (el
 * mismo orden con que salen en el deck). */
function piezasOrdenadas(
  datos: AnaliticaCampania,
  ocultarAds: boolean,
): Array<{ pieza: PiezaCampania; clave: string; vistas: number }> {
  return datos.piezas
    .map((pieza, i) => ({ pieza, clave: clavePieza(pieza, i), vistas: visEfectivas(pieza, ocultarAds) }))
    .sort((a, b) => b.vistas - a.vistas);
}

export function DialogoDescargarPdf({
  abierto,
  datos,
  periodoEtiqueta,
  ocultarAds,
  tokenEnlace,
  enlacePrevia,
  onCerrar,
}: {
  abierto: boolean;
  /** Analítica ya cargada de la campaña (misma que rasteriza el PDF). */
  datos: AnaliticaCampania | null;
  periodoEtiqueta: string;
  /** Modo cliente: la previa y el PDF suman lo pagado a lo orgánico (sin rastro de pauta). */
  ocultarAds: boolean;
  /** Token del enlace público vigente para este periodo/modo (para el QR de cierre), si existe. */
  tokenEnlace: string | null;
  /** Enlace ya resuelto (url + QR) para pintar la lámina de cierre EN LA PREVIA, si existe. */
  enlacePrevia: { url: string; qrDataUrl: string } | null;
  onCerrar: () => void;
}) {
  const [secciones, setSecciones] = React.useState<SeccionesDeck>(SECCIONES_TODAS);
  const [seleccion, setSeleccion] = React.useState<Set<string>>(new Set());
  const [busqueda, setBusqueda] = React.useState("");

  const ordenadas = React.useMemo(
    () => (datos ? piezasOrdenadas(datos, ocultarAds) : []),
    [datos, ocultarAds],
  );

  // Al abrir (o cambiar la campaña/periodo/modo), arranca con TODO activado y TODAS las piezas
  // marcadas: el comportamiento de hoy es el punto de partida, la persona quita lo que no quiere.
  React.useEffect(() => {
    if (!abierto) return;
    setSecciones(SECCIONES_TODAS);
    setSeleccion(new Set(ordenadas.map((x) => x.clave)));
    setBusqueda("");
  }, [abierto, ordenadas]);

  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return ordenadas;
    return ordenadas.filter(
      (x) =>
        (x.pieza.titulo || "").toLowerCase().includes(q) ||
        nombreRed(x.pieza.red).toLowerCase().includes(q) ||
        (x.pieza.marca || "").toLowerCase().includes(q),
    );
  }, [ordenadas, busqueda]);

  const alternarSeccion = (clave: keyof SeccionesDeck) =>
    setSecciones((s) => ({ ...s, [clave]: !s[clave] }));

  const alternarPieza = (clave: string) =>
    setSeleccion((prev) => {
      const proximo = new Set(prev);
      if (proximo.has(clave)) proximo.delete(clave);
      else proximo.add(clave);
      return proximo;
    });

  const todas = () => setSeleccion(new Set(ordenadas.map((x) => x.clave)));
  const ninguna = () => setSeleccion(new Set());

  // Si la selección coincide con TODAS las piezas, se pasa `null` al deck para conservar el
  // comportamiento de hoy (corte al tope + nota "+N más"); una selección parcial se pagina entera.
  const seleccionParaDeck = React.useMemo(() => {
    if (seleccion.size === ordenadas.length) return null;
    return seleccion;
  }, [seleccion, ordenadas.length]);

  const descargar = useMutation({
    mutationFn: () => {
      if (!datos) throw new Error("No hay datos cargados.");
      return descargarPdfCampania(datos, {
        periodoEtiqueta,
        ocultarAds,
        tokenEnlace,
        secciones,
        piezasSeleccionadas: seleccionParaDeck,
      });
    },
    onSuccess: () => {
      toast.success("PDF de la campaña descargado.");
      onCerrar();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo generar el PDF."),
  });

  const nPiezas = seleccion.size;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Descargar PDF de «{datos?.campania.nombre}»</DialogTitle>
          <DialogDescription>
            Elige qué secciones y qué piezas presentar. La previa muestra el deck tal como saldrá.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_320px]">
          {/* Previa: el mismo deck que se rasteriza, escalado. Refleja secciones + selección. */}
          <div
            className="max-h-[60vh] overflow-y-auto rounded-lg border border-border bg-neutral-100 p-4 dark:bg-neutral-900"
            aria-label="Previsualización del PDF"
          >
            {datos ? (
              <PreviaDeck
                datos={datos}
                periodoEtiqueta={periodoEtiqueta}
                ocultarAds={ocultarAds}
                secciones={secciones}
                seleccion={seleccionParaDeck}
                enlace={enlacePrevia}
              />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">Sin datos cargados.</p>
            )}
          </div>

          {/* Controles: secciones + selección de piezas. */}
          <div className="flex min-h-0 flex-col gap-5">
            <section className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Secciones
              </h3>
              <div className="space-y-1.5">
                {SECCIONES.map(({ clave, etiqueta }) => (
                  <label key={clave} className="flex cursor-pointer items-center gap-2.5 text-sm">
                    <Checkbox
                      checked={secciones[clave]}
                      onCheckedChange={() => alternarSeccion(clave)}
                      aria-label={etiqueta}
                    />
                    <span>{etiqueta}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                La portada va siempre.
                {enlacePrevia ? " El QR del enlace público cierra el deck." : ""}
              </p>
            </section>

            <section className="flex min-h-0 flex-1 flex-col space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Piezas · {nPiezas}/{ordenadas.length}
                </h3>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={todas} disabled={ordenadas.length === 0}>
                    Todas
                  </Button>
                  <Button variant="ghost" size="sm" onClick={ninguna} disabled={ordenadas.length === 0}>
                    Ninguna
                  </Button>
                </div>
              </div>

              {ordenadas.length > 8 && (
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={busqueda}
                    onChange={(e) => setBusqueda(e.target.value)}
                    placeholder="Buscar pieza…"
                    className="h-8 pl-8 text-sm"
                    aria-label="Buscar pieza"
                  />
                </div>
              )}

              <div className="min-h-0 flex-1 space-y-1 overflow-y-auto rounded-lg border border-border p-1">
                {filtradas.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    {ordenadas.length === 0 ? "No hay piezas en el periodo." : "Sin coincidencias."}
                  </p>
                ) : (
                  filtradas.map(({ pieza, clave, vistas }) => (
                    <label
                      key={clave}
                      className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
                    >
                      <Checkbox
                        checked={seleccion.has(clave)}
                        onCheckedChange={() => alternarPieza(clave)}
                        aria-label={pieza.titulo || "Publicación"}
                      />
                      <span className="min-w-0 flex-1 truncate" title={pieza.titulo}>
                        {pieza.titulo || "Publicación"}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {nombreRed(pieza.red)}
                      </span>
                      <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                        {numeroCompacto(vistas)}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </section>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            variant="outline"
            onClick={() => descargar.mutate()}
            disabled={descargar.isPending || !datos}
          >
            {descargar.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Presentation className="h-4 w-4" />
            )}
            Descargar PDF
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Previa escalada del deck: monta `DeckCampania` a tamaño real (1280px) y lo encoge con
 * `transform: scale`. El wrapper reserva la ALTURA escalada del contenido para que el scroll y el
 * borde encajen (transform no cambia el flujo, hay que compensar el hueco a mano).
 */
function PreviaDeck({
  datos,
  periodoEtiqueta,
  ocultarAds,
  secciones,
  seleccion,
  enlace,
}: {
  datos: AnaliticaCampania;
  periodoEtiqueta: string;
  ocultarAds: boolean;
  secciones: SeccionesDeck;
  seleccion: Set<string> | null;
  enlace: { url: string; qrDataUrl: string } | null;
}) {
  const [host, setHost] = React.useState<HTMLDivElement | null>(null);
  const [altura, setAltura] = React.useState(0);

  // La altura real depende de cuántas láminas emite el deck (secciones activas + páginas de
  // piezas). Se observa el host y se aplica su alto al hueco reservado (× escala): `transform`
  // no cambia el flujo, así que hay que reservar el hueco a mano o el scroll/borde no encajan.
  React.useLayoutEffect(() => {
    if (!host) return;
    const medir = () => setAltura(host.offsetHeight);
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(host);
    return () => ro.disconnect();
  }, [host]);

  return (
    <div style={{ height: altura * ESCALA }}>
      <div
        ref={setHost}
        className="flex flex-col gap-3"
        style={{
          width: ANCHO_LAMINA,
          transform: `scale(${ESCALA})`,
          transformOrigin: "top left",
        }}
      >
        <DeckCampania
          datos={datos}
          periodoEtiqueta={periodoEtiqueta}
          ocultarAds={ocultarAds}
          secciones={secciones}
          piezasSeleccionadas={seleccion}
          enlace={enlace}
        />
      </div>
    </div>
  );
}
