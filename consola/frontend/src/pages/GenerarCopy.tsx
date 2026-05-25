import * as React from "react";

import type { Skill } from "@/types";

import { esSkillDeImagen } from "./copy/dynamico";
import { FlujoGeneracion } from "./copy/FlujoGeneracion";

/** Clave de sessionStorage para reanudar la generación en curso al volver a la página. */
const CLAVE_GEN_COPY = "keni:generacion-copy";

/**
 * Generar copy. Es el flujo de generación con las skills editoriales de TEXTO:
 * todas MENOS las de imagen, que viven en su propia pestaña "Imágenes". Comparte
 * el motor (`FlujoGeneracion`) con esa pestaña, cambiando solo el filtro de skills.
 */
export default function GenerarCopy() {
  // Excluimos las skills de imagen (su sitio es la pestaña "Imágenes").
  const filtro = React.useCallback((skill: Skill) => !esSkillDeImagen(skill), []);

  return (
    <FlujoGeneracion
      titulo="Generar copy"
      descripcion="Crea borradores de publicaciones con las skills editoriales para cada marca."
      claveGen={CLAVE_GEN_COPY}
      filtroSkills={filtro}
      vacioMensaje="No hay skills editoriales disponibles. Revisa el catálogo en Skills."
    />
  );
}
