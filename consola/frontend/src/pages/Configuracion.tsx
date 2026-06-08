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
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";

import {
  CLAVE_AJUSTES,
  CLAVE_ESFUERZO,
  CLAVE_IMAGEN,
  CLAVE_METRICOOL,
} from "./configuracion/lib";
import { SeccionApariencia } from "./configuracion/SeccionApariencia";
import { SeccionEsfuerzo } from "./configuracion/SeccionEsfuerzo";
import { SeccionFuncionalidad } from "./configuracion/SeccionFuncionalidad";
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

  const acciones = (
    <Button
      variant="outline"
      onClick={() => {
        void queryClient.invalidateQueries({ queryKey: CLAVE_ESFUERZO });
        if (puedeVerConexiones) {
          void queryClient.invalidateQueries({ queryKey: CLAVE_AJUSTES });
          void queryClient.invalidateQueries({ queryKey: CLAVE_IMAGEN });
          void queryClient.invalidateQueries({ queryKey: CLAVE_METRICOOL });
        }
      }}
      disabled={refrescando}
    >
      <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Configuración"
        descripcion="Automatización, Metricool y clave de imagen IA. Los secretos se guardan solo en esta máquina."
        acciones={acciones}
      />

      {/* Orden por frecuencia/criticidad, no por tema. Arriba del todo y SIEMPRE visible: el
          tema (preferencia personal, instantánea). Debajo, dos pestañas que doman una página
          muy llena. */}
      <div className="space-y-4">
        <SeccionApariencia />

        <Tabs defaultValue="basica" className="space-y-4">
          <TabsList>
            <TabsTrigger value="basica">Básica</TabsTrigger>
            <TabsTrigger value="avanzada">Avanzada</TabsTrigger>
          </TabsList>

          {/* Básica: controles clave de arriba (lo que más se toca) a abajo (setup-once).
              Funcionalidad (toggles del día) arranca abierta; las Conexiones (Imagen IA +
              Metricool) van AL FINAL y colapsadas: se configuran una vez y casi nunca se
              vuelven a abrir. Metricool, lo último. Todas: solo admin (#153). */}
          <TabsContent value="basica" className="space-y-4">
            {puedeVerConexiones && <SeccionFuncionalidad nivel="basica" />}
            {puedeVerConexiones && <SeccionImagen />}
            {puedeVerConexiones && <SeccionMetricool />}
          </TabsContent>

          {/* Avanzada: la granularidad que funciona en sus valores por defecto (ajustes finos
              + esfuerzo de generación); rara vez se toca. */}
          <TabsContent value="avanzada" className="space-y-4">
            {puedeVerConexiones && <SeccionFuncionalidad nivel="avanzada" />}
            <SeccionEsfuerzo />
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
