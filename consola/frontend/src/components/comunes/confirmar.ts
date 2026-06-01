/**
 * Confirmación PROPIA de la app (sustituye al `confirm` del navegador).
 *
 * Decisión de producto: la app NO usa diálogos/alertas por defecto del navegador.
 * Toda confirmación pasa por aquí, con el estilo de la app.
 *
 * API IMPERATIVA, al estilo de `toast` de sonner (que ya usamos): se importa la
 * función `confirmar(...)` y se llama desde cualquier handler; devuelve una
 * `Promise<boolean>` (true = el usuario confirmó). El contenedor visual
 * (`<ContenedorConfirmacion />`) se monta UNA sola vez cerca de la raíz, junto al
 * `<Toaster />` (en `main.tsx`), y se suscribe a este módulo.
 *
 *   if (await confirmar("¿Borrar esto?")) borrar.mutate();
 *
 *   if (
 *     await confirmar({
 *       titulo: "Borrar feed",
 *       mensaje: `¿Borrar el feed "${nombre}"?`,
 *       destructivo: true,
 *       textoConfirmar: "Borrar",
 *     })
 *   ) borrar.mutate();
 *
 * Este módulo es SOLO lógica (sin JSX): el componente vive en
 * `ContenedorConfirmacion.tsx`. Así cada fichero exporta una cosa coherente
 * (regla `react-refresh/only-export-components`).
 */
import type { ReactNode } from "react";

export interface OpcionesConfirmar {
  /** Título del diálogo. Por defecto "Confirmar acción". */
  titulo?: string;
  /** Cuerpo/pregunta. Es lo principal. */
  mensaje: ReactNode;
  /** Texto del botón de confirmar. Por defecto "Confirmar". */
  textoConfirmar?: string;
  /** Texto del botón de cancelar. Por defecto "Cancelar". */
  textoCancelar?: string;
  /** Si la acción es destructiva (borrar): botón rojo. */
  destructivo?: boolean;
}

export interface EstadoConfirmacion extends OpcionesConfirmar {
  id: number;
  resolver: (valor: boolean) => void;
}

type Emisor = (estado: EstadoConfirmacion) => void;

// Puente entre la función imperativa y el contenedor montado (misma idea que el
// store de sonner). `null` mientras el contenedor no está montado.
let _emitir: Emisor | null = null;
let _contador = 0;

/**
 * El contenedor montado se registra aquí. Devuelve la función para des-registrar
 * (se usa en el cleanup del efecto).
 */
export function suscribirConfirmacion(emisor: Emisor): () => void {
  _emitir = emisor;
  return () => {
    if (_emitir === emisor) _emitir = null;
  };
}

/**
 * Pide confirmación al usuario y resuelve `true`/`false`. Acepta un string corto
 * o un objeto de opciones. NUNCA usa el `confirm` del navegador.
 */
export function confirmar(opciones: OpcionesConfirmar | string): Promise<boolean> {
  const opts: OpcionesConfirmar =
    typeof opciones === "string" ? { mensaje: opciones } : opciones;
  return new Promise<boolean>((resolve) => {
    if (!_emitir) {
      // Contenedor no montado: no caemos al confirm del navegador (decisión de
      // producto). Resolvemos en false para no ejecutar nada destructivo a ciegas.
      console.warn(
        "ContenedorConfirmacion no está montado; confirmar() resolvió en false.",
      );
      resolve(false);
      return;
    }
    _contador += 1;
    _emitir({ ...opts, id: _contador, resolver: resolve });
  });
}
