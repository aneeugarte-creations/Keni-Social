/**
 * Página de Ajustes (Configuración). Reúne en una sola pantalla:
 *   1. Alcance de marcas (qué marcas se incluyen).
 *   2. Métricas (Metricool) por marca: token + userId → descubrir blogId → guardar.
 *   3. Imagen con IA (clave del proveedor para «Generar con IA»).
 *
 * Las métricas se consumen vía Metricool (ADR 0005 §B): la antigua sección "Redes
 * sociales" (tokens por plataforma para la ingesta propia) se retiró. La sección de
 * Imagen vivía antes en la página "Conexiones", fusionada aquí (issue #87). Los
 * secretos son write-only: nunca se muestran; del servidor solo llega el estado/pista.
 *
 * Esta página es solo el CONTENEDOR fino que orquesta los paneles. Cada panel vive en
 * `pages/configuracion/` y gestiona su propio estado (react-query). El contenedor
 * compone, controla permisos (admin) y cablea el botón «Actualizar».
 */
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Settings } from "lucide-react";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";

import {
  CLAVE_AJUSTES,
  CLAVE_ESFUERZO,
  CLAVE_IMAGEN,
  CLAVE_METRICOOL,
} from "./configuracion/lib";
import { SeccionApariencia } from "./configuracion/SeccionApariencia";
import { SeccionEsfuerzo } from "./configuracion/SeccionEsfuerzo";
import { PanelMaquinaContenido, SeccionFuncionalidad } from "./configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "./configuracion/SeccionImagen";
import { SeccionMetricool } from "./configuracion/SeccionMetricool";

export default function Configuracion() {
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  // Metricool e Imagen IA son SECRETOS GLOBALES: el backend solo deja a un admin verlos
  // o cambiarlos (#153, /api/conexiones exige rol admin). Ocultamos esas secciones a un
  // editor para no mostrarle un error 403. Sin usuario de sesión (acceso por token
  // interino / modo local mono-usuario) cuenta como plenos permisos, así que se muestran.
  const puedeVerConexiones = usuario === null || usuario.rol === "admin";
  // ¿Hay alguna query (de cualquier sección) en vuelo? (para el spinner del botón).
  const refrescando = useIsFetching() > 0;

  const refrescar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
    if (puedeVerConexiones) {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AJUSTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
      void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
    }
  };

  return (
    <>
      <TituloPagina titulo="Configuración" icono={Settings} />
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={refrescando}>
            Actualizar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Arriba del todo y SIEMPRE visible: el tema (preferencia personal, instantánea).
          Debajo, pestañas por CONTENIDO (antes «Básica/Avanzada», con la Básica vacía de
          ajustes): AJUSTES = todo el catálogo global + esfuerzo de generación;
          CONEXIONES = secretos de proveedores (Imagen IA + Metricool), setup-once y solo
          admin. La máquina de contenido NO está aquí: se opera desde el Monitor. */}
      <div className="space-y-4">
        <SeccionApariencia />

        <Tabs defaultValue="ajustes" className="space-y-4">
          <TabsList>
            <TabsTrigger value="ajustes">Ajustes</TabsTrigger>
            {puedeVerConexiones && (
              <TabsTrigger value="maquina">Máquina de contenido</TabsTrigger>
            )}
            {puedeVerConexiones && <TabsTrigger value="conexiones">Conexiones</TabsTrigger>}
          </TabsList>

          <TabsContent value="ajustes" className="space-y-4">
            {puedeVerConexiones && <SeccionFuncionalidad />}
            <SeccionEsfuerzo />
          </TabsContent>

          {/* TODA la parametrización vive en Configuración: también la máquina de
              contenido (etapas, excepciones por marca, topes y economía de tokens),
              que antes era un panel del Monitor. El Monitor solo OPERA (acciones). */}
          {puedeVerConexiones && (
            <TabsContent value="maquina" className="space-y-4">
              <PanelMaquinaContenido />
            </TabsContent>
          )}

          {puedeVerConexiones && (
            <TabsContent value="conexiones" className="space-y-4">
              <SeccionImagen />
              <SeccionMetricool />
            </TabsContent>
          )}
        </Tabs>
      </div>
    </>
  );
}
