import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Newspaper, Plus, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
} from "@/types";

import { DialogoNuevaFuente } from "./algoritmos/DialogoNuevaFuente";
import { DialogoPropuesta } from "./algoritmos/DialogoPropuesta";
import { FilaFuente } from "./algoritmos/FilaFuente";
import { badgeNivel, TODAS } from "./algoritmos/lib";
import { TarjetaNoticia } from "./algoritmos/TarjetaNoticia";

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

  const inicializar = useMutation({
    mutationFn: () => api.inicializarAlgoritmos(),
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
    mutationFn: (n: NoticiaAlgoritmo) => api.algoritmoATexto(n.id),
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

  const fuentes = data?.fuentes ?? [];
  const fuenteOcupada = toggleFuente.isPending || borrarFuente.isPending;

  return (
    <div>
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu
            icono={RefreshCw}
            onClick={() => refrescar.mutate()}
            disabled={refrescar.isPending}
          >
            Refrescar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

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
            {/* Filtros */}
            <div className="flex flex-wrap items-center gap-2">
              <Select value={plataforma} onValueChange={setPlataforma}>
                <SelectTrigger className="w-52 shrink-0">
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
                <SelectTrigger className="w-44 shrink-0">
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
                        onProponer={async (noticia) => {
                          // Click izquierdo no ejecuta a ciegas: confirma antes de proponer.
                          if (
                            await confirmar({
                              mensaje: `¿Proponer "${noticia.titulo || "esta noticia"}" a Texto?`,
                              textoConfirmar: "Proponer",
                            })
                          )
                            proponer.mutate(noticia);
                        }}
                        onArchivar={(noticia) => archivar.mutate(noticia)}
                        archivando={archivar.isPending}
                      />
                    ))}
                  </ul>
                ) : fuentes.length === 0 ? (
                  <EstadoVacio
                    icono={Sparkles}
                    titulo="Sin fuentes todavía"
                    texto="Configura fuentes para ver noticias."
                    accion={
                      <Button onClick={() => inicializar.mutate()} disabled={inicializar.isPending} size="sm">
                        <Sparkles className="mr-1 h-4 w-4" aria-hidden="true" />
                        Añadir fuentes recomendadas
                      </Button>
                    }
                  />
                ) : (
                  <EstadoVacio
                    icono={Newspaper}
                    titulo="Nada que mostrar"
                    texto="No hay noticias con este filtro."
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
                      onClick={() => inicializar.mutate()}
                      disabled={inicializar.isPending}
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
                  <ul className="space-y-2">
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
                    Sin feed RSS oficial; cobertura vía agregadores.
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
