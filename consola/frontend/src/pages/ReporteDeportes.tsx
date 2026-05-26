import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Eye, Loader2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BadgeFuente } from "@/components/comunes/BadgeFuente";
import { BloqueError } from "@/components/comunes/BloqueError";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import type { CuerpoReporteDeportes, EventoAgenda, ReporteDeportes } from "@/types";

const NOMBRE_PLATAFORMA: Record<string, string> = {
  instagram: "Instagram",
  tiktok: "TikTok",
  facebook: "Facebook",
  x: "X",
  youtube: "YouTube",
};

const fmt = new Intl.NumberFormat("es-MX");

/** Recorta y descarta eventos sin nombre antes de mandarlos al backend. */
function limpiar(items: EventoAgenda[]): EventoAgenda[] {
  return items
    .map((e) => ({ nombre: e.nombre.trim(), plan: e.plan.trim() }))
    .filter((e) => e.nombre);
}

export default function ReporteDeportes() {
  const opciones = useQuery({
    queryKey: ["reporte-deportes", "opciones"],
    queryFn: ({ signal }) => api.reporteDeportesOpciones(signal),
  });

  const [rango, setRango] = useState("semana");
  const [top, setTop] = useState(3);
  const [principales, setPrincipales] = useState<EventoAgenda[]>([]);
  const [propios, setPropios] = useState<EventoAgenda[]>([]);
  const [descargando, setDescargando] = useState(false);

  const cuerpo = (): CuerpoReporteDeportes => ({
    rango,
    top,
    agenda: { principales: limpiar(principales), propios: limpiar(propios) },
  });

  const preview = useMutation({
    mutationFn: () => api.reporteDeportesPreview(cuerpo()),
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo previsualizar."),
  });

  async function descargar() {
    setDescargando(true);
    try {
      await api.descargarReporteDeportes(cuerpo());
      toast.success("Presentación generada.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo descargar la presentación.");
    } finally {
      setDescargando(false);
    }
  }

  if (opciones.isPending) {
    return (
      <>
        <PageHeader titulo="Reporte de deportes" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }
  if (opciones.isError) {
    return (
      <>
        <PageHeader titulo="Reporte de deportes" />
        <BloqueError
          titulo="No se pudieron cargar las opciones"
          mensaje={opciones.error instanceof Error ? opciones.error.message : undefined}
          onReintentar={() => opciones.refetch()}
        />
      </>
    );
  }

  const { rangos, cuenta } = opciones.data;

  return (
    <>
      <PageHeader
        titulo="Reporte de deportes"
        descripcion={`Deck semanal de ${cuenta.nombre}: mejores piezas por plataforma, promoción de cuentas hermanas y agenda de la próxima semana.`}
      />

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Parámetros</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="rango">Rango</Label>
              <Select value={rango} onValueChange={setRango}>
                <SelectTrigger id="rango" className="w-[180px]" aria-label="Rango">
                  <SelectValue placeholder="Rango" />
                </SelectTrigger>
                <SelectContent>
                  {rangos.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="top">Piezas por plataforma</Label>
              <Input
                id="top"
                type="number"
                min={1}
                max={10}
                value={top}
                onChange={(e) => setTop(Math.max(1, Math.min(Number(e.target.value) || 1, 10)))}
                className="w-[160px]"
              />
            </div>
          </CardContent>
        </Card>

        <EditorAgenda
          titulo="Eventos principales"
          descripcion="Eventos externos que vamos a cubrir (fútbol, tenis, básquetbol, béisbol, UFC ocasional…) y qué/cómo los cubrimos."
          items={principales}
          setItems={setPrincipales}
        />
        <EditorAgenda
          titulo="Transmisiones propias"
          descripcion="Lo que transmitimos nosotros: qué vamos a tener y cómo lo vamos a hacer."
          items={propios}
          setItems={setPropios}
        />

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => preview.mutate()} disabled={preview.isPending}>
            {preview.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Previsualizar
          </Button>
          <Button onClick={descargar} disabled={descargando}>
            {descargando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Descargar .pptx
          </Button>
        </div>

        {preview.data && <Previsualizacion rep={preview.data} />}
      </div>
    </>
  );
}

function EditorAgenda({
  titulo,
  descripcion,
  items,
  setItems,
}: {
  titulo: string;
  descripcion: string;
  items: EventoAgenda[];
  setItems: (items: EventoAgenda[]) => void;
}) {
  const actualizar = (i: number, campo: keyof EventoAgenda, valor: string) =>
    setItems(items.map((e, idx) => (idx === i ? { ...e, [campo]: valor } : e)));
  const agregar = () => setItems([...items, { nombre: "", plan: "" }]);
  const quitar = (i: number) => setItems(items.filter((_, idx) => idx !== i));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titulo}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{descripcion}</p>
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">Sin eventos todavía. Añade uno.</p>
        )}
        {items.map((ev, i) => (
          <div key={i} className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              className="sm:w-1/3"
              placeholder="Evento"
              value={ev.nombre}
              onChange={(e) => actualizar(i, "nombre", e.target.value)}
            />
            <Input
              className="sm:flex-1"
              placeholder="Qué / cómo lo cubrimos"
              value={ev.plan}
              onChange={(e) => actualizar(i, "plan", e.target.value)}
            />
            <Button variant="ghost" size="icon" onClick={() => quitar(i)} aria-label="Quitar evento">
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={agregar}>
          <Plus className="h-4 w-4" />
          Añadir evento
        </Button>
      </CardContent>
    </Card>
  );
}

function Previsualizacion({ rep }: { rep: ReporteDeportes }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold tracking-tight">
          Vista previa — {rep.cuenta.nombre} ({rep.rango})
        </h3>
        {/* Procedencia de los datos: muestra (ficticios) vs reales. Lectura
            defensiva: si `fuente` falta no se afirma nada (#90/residuo Ola 2). */}
        <BadgeFuente fuente={rep.fuente} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {rep.mejores_por_plataforma.map((b) => (
          <Card key={b.plataforma}>
            <CardHeader>
              <CardTitle className="text-base">
                Top {NOMBRE_PLATAFORMA[b.plataforma] ?? b.plataforma}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {b.piezas.length === 0 && (
                <p className="text-sm text-muted-foreground">Sin piezas en el periodo.</p>
              )}
              {b.piezas.map((p, i) => (
                <div key={i} className="text-sm">
                  <p className="font-medium">
                    {i + 1}. {p.titulo}
                  </p>
                  <p className="text-muted-foreground">
                    {fmt.format(p.visualizaciones)} vistas · {fmt.format(p.interacciones)} interacciones
                  </p>
                  {p.url && (
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all text-xs text-primary underline"
                    >
                      {p.url}
                    </a>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Promoción · cuentas hermanas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {rep.promocion_hermanas.length === 0 && (
            <p className="text-sm text-muted-foreground">Sin cuentas hermanas configuradas.</p>
          )}
          {rep.promocion_hermanas.map((h) => (
            <div key={h.cuenta}>
              <p className="font-medium">{h.nombre}</p>
              {h.piezas.length === 0 ? (
                <p className="text-sm text-muted-foreground">Sin posteos en el periodo.</p>
              ) : (
                <ul className="ml-4 list-disc text-sm text-muted-foreground">
                  {h.piezas.map((p, i) => (
                    <li key={i}>
                      {p.titulo} ({NOMBRE_PLATAFORMA[p.plataforma] ?? p.plataforma},{" "}
                      {fmt.format(p.visualizaciones)} vistas)
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
