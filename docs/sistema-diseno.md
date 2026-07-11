# Sistema de diseño de la Consola

Decisiones de unificación visual cerradas por Ane el 11-jul-2026 tras auditar todo el
frontend (`consola/frontend/src/`). Este documento es la ÚNICA fuente de verdad del
estándar visual: cualquier pantalla nueva lo sigue y cualquier desviación existente es
deuda a migrar. Vista previa viva con los componentes reales: `/preview-diseno.html`
(con `npm run dev`).

## Botones

- **Primario** (Guardar / Crear / Generar): `variant="default"` — relleno oscuro
  (`bg-primary`: negro en claro, blanco en oscuro), plano, SIN sombra. Uno por vista o
  diálogo, siempre a la derecha.
- **Cancelar / secundario de diálogo**: `variant="ghost"`. Nunca outline en el par
  Cancelar/primario, y nunca atenuado con `text-muted-foreground` (parece deshabilitado).
- **Acción normal** (Editar, Filtrar, …): `variant="outline"` (el default del componente).
- **Destructivo** (Eliminar / Borrar): `variant="ghost"` + `text-destructive`, siempre.
  La protección la da el diálogo `confirmar()`; su botón de confirmación va neutro
  (`variant="default"`). Las variantes `destructive` rellena y outline-rojo no se usan.
- **Altura estándar: `h-7`** (compacta). Se formaliza como size del componente y se
  eliminan los ~300 parches `h-7` de className. `size="icon"` para botones de solo icono
  (cuadrado, nunca `<button>` nativo con `h-7 w-7` a mano).
- Iconos dentro de botones: el tamaño lo fuerza el componente (`[&_svg]:size-4`); no se
  pasan clases `h-3.5 w-3.5` que choquen con él.
- El CTA de marca (`variant="brand"`, naranja keni) queda reservado a Ralph/lanzadores ya
  existentes; no es el primario general.

## Color y badges

- **Badge de estado** (Completado / En curso / Revisar / Pendiente): receta única
  **tinte suave 700/300** — `bg-<color>-500/15 text-<color>-700 dark:text-<color>-300`,
  las variantes semánticas `ok/info/aviso` de `ui/badge.tsx`. `ChipEstado`, Pipelines,
  calendarios y semáforos migran a ella (desaparecen las recetas 600+borde, 50/800,
  outline y 800/200).
- **Error**: SIEMPRE el token semántico — `bg-destructive/10 text-destructive` en chips,
  `text-destructive` en textos. La variante `error` de Badge se reescribe al token; la
  paleta roja cruda (`bg-red-500/15 text-red-700`) desaparece.
- **Chips/etiquetas**: rectangulares `rounded-md` (la forma de `Badge`), texto `text-xs`
  (nada de `text-[10px]`/`text-[11px]`). `rounded-full` queda solo para contadores/avatares.
- **Paleta de marca** (módulo único; hoy está duplicada y contradictoria):
  - **UnoTV: `#16273F`** (el navy de la portada de informes).
  - **Claro Sports: `#DA291C`** (su rojo corporativo).
  - `lib/organigrama.ts` (azul `#2563eb` / rosa `#e11d48`) e `informe/Informe.tsx` beben
    de ese módulo. El rojo `#E4002B` queda solo como acento del wordmark UnoTV en
    informes si hace falta.
- Superficies temadas usan tokens (`text-foreground`, `text-muted-foreground`, …); las
  clases `text-neutral-*` quedan solo en informes/PDF claro-fijo.

## Tarjetas y listas

- Toda caja `rounded-xl border bg-card` se escribe con `<Card>`; sin sombra (canon).
- **Título de tarjeta: `text-sm font-semibold`** — `CardTitle` se alinea a esto y es la
  única vía (nada de `<h3>`/`text-base`/`text-lg` a mano para títulos de tarjeta).
- **Densidad**: ítems repetidos de lista (piezas, fuentes, noticias, tareas) **`p-3`**;
  tarjetas sueltas (KPIs, formularios, resúmenes) `p-4`/`p-6`. Desaparecen `p-2.5` y los
  paddings por página.
- Hover: filas-tarjeta accionables `hover:bg-accent` (vía `FilaConAcciones`); filas de
  tabla `hover:bg-muted/50` (vía `ui/table`). Ningún otro.
- Tablas siempre con `ui/table` (migran las reconstruidas a mano de `Marcas.tsx` y
  `rota/ReparteMes.tsx`).
- Grids de KPI: `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-N` (siempre con
  breakpoints).

## Layout y navegación

- Cabecera de página SIEMPRE portalizada a la barra superior (`TituloPagina` /
  `EncabezadoSeccion`); los detalles usan `TituloPagina onAtras`. Ninguna página pinta
  `<h1>` ni botón "Volver" en el cuerpo.
- **Pestañas de sección de página: SIEMPRE en la barra superior** (`PestanasSeccion` /
  `EncabezadoSeccion`, subrayado). Migran Inbox, Fuentes y ProgramaPlan. Las Tabs
  segmentadas (`ui/tabs` w-fit) y `ToggleGroup` quedan solo para conmutar vistas DENTRO
  del contenido.
- **Tooltips: SIEMPRE `ui/tooltip`**; `title=` nativo prohibido (lento, sin estilo,
  inexistente en móvil/teclado). Migración gradual de los ~110 ficheros.

## Feedback

- **Carga**: skeleton con forma de contenido para listados/dashboards; spinner
  (`ui/spinner`) centrado para diálogos y acciones. El texto pelado "Cargando…"
  desaparece. El `Cargando` local de Inbox sube a `comunes/`.
- **Éxito**: `toast.success` SIEMPRE tras una acción disparada por el usuario (guardar,
  crear, publicar…). El silencio queda solo para autoguardados.
- Confirmación destructiva: `confirmar()`/`elegir()` de `comunes/confirmar.ts`, sin
  excepciones (nada de `window.confirm` ni `AlertDialog` montado a mano).
- Estados vacíos: `EstadoVacio` (listados) / `EstadoVacioTexto` (paneles chicos de
  métricas); nada de `<p>No hay…</p>` a mano.
- Callouts de aviso: componente `Aviso`, nunca el bloque ámbar a mano.

## Formularios

- Campos con `Campo` (label + control + error inline); separación entre campos
  **`space-y-4`**, dentro del campo `space-y-1.5`.
- Inputs/selects/textarea de `ui/` (los nativos quedan confinados al editor de plantillas,
  que es sub-app deliberada).
- Errores de validación inline en rojo (token), no por toast.

## Tipografía

- Metadata de tarjetas/listas/tablas: **`text-xs text-muted-foreground`**. `text-sm`
  queda para párrafos y descripciones.
- Nada de tamaños ad-hoc `text-[10px]`/`text-[11px]` fuera del editor.

## Correcciones al canon (sin decisión, son violaciones)

- `pages/Fotos.tsx`: el único `window.confirm` → `confirmar()`.
- `DetalleHistoriaPagina` y `DetalleSugerenciaPagina`: cabecera en el cuerpo →
  `TituloPagina onAtras`.
- `maquina/Economia.tsx`: grids `grid-cols-4` sin breakpoints (no colapsan en móvil).
- `auth/PantallaLogin.tsx`: `text-neutral-*` → tokens temados.
- `sistema/SeccionCuentaClaude` y `SeccionGitHub`: AlertDialog a mano → `confirmar()`.
- `layout/CuentaUsuario.tsx`: dropdown a mano → `MenuFlotante`.
