# Design System — Consola Keni

Sistema de diseño único de la consola. **Antes de construir cualquier pantalla o componente, lee esto.**
La regla de oro: *no inventes lo que el sistema ya resuelve*. Casi todo existe; el trabajo es reutilizarlo.
Cada cosa tiene UN solo sitio: para cambiarla, vas ahí y la cambias una vez.

Fuentes de verdad en código:
- Tokens: `consola/frontend/src/index.css` + `consola/frontend/tailwind.config.js`
- Primitivas: `consola/frontend/src/components/ui/*`
- Primitivas de dominio (capa DS fuera de shadcn): `consola/frontend/src/components/comunes/*`
- Color de estado: `consola/frontend/src/lib/estado-color.ts` + `components/comunes/ChipEstado.tsx`

---

## 1. Identidad visual

Dashboard **monocromo estilo Vercel/Geist**, lo más sobrio posible. Menos es más; menos IA de cara a la audiencia, más sistema hacia adentro.

- **Lienzo** gris muy sutil `#fafafa` (`bg-background`). **Superficies** blancas (`bg-card`) que descansan sobre el lienzo, separadas **por contraste** (blanco sobre gris), **sin borde y sin sombra**. Cuida que sobre un fondo blanco una superficie no "desaparezca" (ahí sí necesita un hairline o reposar sobre lienzo gris).
- **Texto**: principal `#171717` (`text-foreground`), secundario/metadata `#666` (`text-muted-foreground`).
- **Botones: 100% monocromos en gris.** Por defecto `outline`. **La acción principal se distingue por su POSICIÓN (la de la derecha en un pie de diálogo/formulario), no por el color.** Sin negro, sin naranja, sin rojo en botones (§4).
- **Color, solo cuando significa algo**, nunca como decoración:
  - **Estado** (verde/ámbar/rojo/azul): comunica salud/etapa de un vistazo (§5).
  - **Naranja de marca** `#ff5a1f` (`keni`): SOLO en el logo, el marcador de **hoy** del calendario (celda con tinte `keni-50` + número naranja, sin aro) y el indicador **en vivo** (punto naranja; el texto "En vivo" va en negro). **Nunca** en botones.
- **Profundidad**: la app es **plana**. Tarjetas y paneles sin sombra. La sombra se reserva, y suave, para lo que de verdad *flota* sobre la página: menús, popovers, diálogos.
- **Modo oscuro** por la clase `.dark` en `<html>`; todo se define con tokens, nunca con colores crudos.
- **Excepción deliberada**: el editor de imagen (`src/editor/`) usa cromo oscuro tipo Canva. NO se unifica con el dashboard; ahí el color es el dominio del usuario.

---

## 2. Tokens (no uses valores crudos)

Definidos en `index.css` como variables HSL y mapeados en `tailwind.config.js`.

| Token | Uso |
|---|---|
| `background` / `foreground` | lienzo / texto principal |
| `card` / `card-foreground` | superficie / su texto |
| `muted` / `muted-foreground` | superficie sutil / metadata gris |
| `secondary`, `accent` | grises suaves (relleno / hover / activo) |
| `border`, `input`, `ring` | hairline / borde de input / anillo de foco |
| `primary` | negro Geist (texto/anillo; **no** como color de botón) |
| `destructive` | negativo real: rojo de **estado** (error/vencido), **no** de botón |
| `keni` (+ 50–900) | naranja de marca (logo / hoy / en vivo — §1) |
| `--aviso-borde/-superficie/-texto/-texto-plano` | **avisos ámbar** → usa `<Aviso>` o estos tokens, nunca `amber-*` a mano |
| `--control-activo(-foreground)` | fondo de un toggle activo / menú abierto |

**Radios**: `--radius` 0.625rem → controles `rounded-md`, **tarjetas `rounded-xl`**, fichas flotantes `rounded-lg`. No uses radios arbitrarios.
**Sombras**: la app es plana. Tarjetas/paneles **sin sombra**. Solo lo que flota (menú/popover/diálogo) lleva sombra, y **suave** (`shadow-md` máx.). No uses `shadow-lg/xl` en chrome.

### Prohibido (deriva de color)
- Hex/RGB crudos en `className`.
- Paleta Tailwind arbitraria para **chrome** (`bg-blue-*`, `text-indigo-*`, `bg-violet-*`…).
- **Color en botones** (naranja/rojo/negro): los botones son grises (§4). El rojo y el naranja viven en estado/marca, no en acciones.
- **Color semántico de estado a mano** (`bg-emerald-500/15`, `text-amber-700`, `bg-red-500`…). Para eso están las variantes de `Badge`, `ChipEstado` y `<Aviso>` (§5).
- Permitido sin tokens: `src/editor/*` (lienzo gráfico), gráficas (`lib/coloresRed.ts` + safelist Tremor), y mocks de redes sociales (imitan IG/TikTok/X/YouTube — coméntalo).
- **Guard ACTIVO (`eslint.config.js`)**: `no-restricted-syntax` ERRORA si pintas la píldora de estado / el callout inline con `bg-{emerald|amber|sky|red|rose}-{400|500}/{10|15|20}` en `src/pages`/`src/components`. Si tu caso es una excepción legítima nueva, añádela al `ignores` del rule con justificación; si no, usa la primitiva (§5).

---

## 3. Tipografía

- Fuente **Geist** (pesos 300–700; el más fino real es `font-light` — `font-thin/extralight` caen a 300). `font-medium` por defecto en controles.
- **Micro-labels de sección/KPI** (eyebrow, rótulo de métrica, título de lista, cabecera de tabla) → **tipo frase**, en gris, **sin mayúsculas ni tracking**. Usa la utilidad `.text-label` (`index.css`, fuente única; ya no hay `fontSize.label` que la pise). No reescribas el rótulo a mano.
- **Texto pequeño**: mínimo `text-xs` (12px) en chrome. `text-[10px]/[11px]` solo en celdas densas justificadas (calendario, mocks).
- **Inputs en móvil ≥16px** para no disparar el auto-zoom de iOS: las primitivas `Input`/`Textarea` ya traen `text-base md:text-sm`. **No pongas `text-sm`/`text-xs` plano sobre ellas**. Si necesitas denso en escritorio: `text-base md:text-xs`.

---

## 4. Primitivas (`components/ui/`)

Úsalas siempre; no rehagas un control que ya existe.

`button` · `badge` · `input` · `textarea` / `auto-textarea` · `select` · `dialog` · `alert-dialog` · `card` · `table` · `tabs` · `checkbox` · `switch` · `tooltip` · `toggle-group` · `label` · `skeleton` · `sonner` (toast) · `spinner` · `Markdown`.

### Botón — monocromo, regla de uso
`button.tsx` tiene `defaultVariants.variant = "outline"`: **omitir la variante da gris**, nunca negro.

| Variante | Cuándo |
|---|---|
| `outline` | **por defecto** (el "estilo de la plataforma"); incluye la acción principal |
| `ghost` | acción discreta / icono suelto |
| `secondary` | relleno gris suave cuando `outline` se pierde sobre la superficie (p. ej. la acción de `confirmar()`) |
| `link` | enlace en texto |

- **No uses `default` (negro), `brand` (naranja) ni `destructive` (rojo) como color de botón.** Siguen existiendo en el `cva` por compatibilidad, pero no se usan: el lenguaje es gris.
- **Jerarquía por POSICIÓN, no por color**: la acción principal es la de la derecha en el pie; las demás a su izquierda. No hace falta destacarla con color.
- **Borrar / destructivo**: también gris. El aviso de peligro lo da el **texto del diálogo** de confirmación (§6), no el botón.
- Tamaños: `default` (h-9) · `sm` (h-8) · `lg` (h-10) · `icon` (cuadrado).

### Badge — variantes
`default` · `secondary` · `outline` · `destructive` · **`ok`** (verde) · **`info`** (cielo) · **`aviso`** (ámbar) · **`error`** (rojo). Las semánticas usan pares 700/300 (claro/oscuro). Para estados de *trabajo* usa `ChipEstado` (§5), no el Badge a pelo.

---

## 5. Color de estado — UNA fuente

El color de estado **se mantiene** (es lo único, junto a la marca, que lleva color), porque comunica significado de un vistazo. Pero **nunca se pinta inline**. Tres herramientas, por orden de preferencia:

1. **`ChipEstado` / `ChipNivelPresupuesto`** (`components/comunes/ChipEstado.tsx`): badge ÚNICO de estados de trabajo (generación, etapa/run de pipeline, job de cola, daemon). Si tu dominio tiene un estado nuevo, **añádelo al mapa `ASPECTO`**, no pintes un badge nuevo.
2. **Variantes semánticas de `Badge`** (`ok`/`info`/`aviso`/`error`) para flags puntuales (Conectado, Oficial, Pendiente).
3. **`<Aviso>`** (`components/comunes/Aviso.tsx`) para el bloque/callout ámbar de atención. Consume `--aviso-*`. Reemplaza el `border-amber-500/40 bg-amber-500/10 text-amber-700 dark:…` copiado a mano.

**Taxonomía de cobertura/turnos** (`lib/estado-color.ts`, fijada por `estado-color.test.ts`):
- **amarillo** (`yellow`) = `sin-cubrir` (hueco real, pide decisión).
- **ámbar** (`amber`) = `empieza-en` (PRE-LIVE, el saque está cerca). *No* uses ámbar para otra cosa.
- **verde** = en-vivo / cubierto / terminado-OK.
- **gris** (`muted-foreground`) = programado / neutro / "media prioridad" / "off".
- **rojo** (`destructive`) = solo negativo real (vencido, prioridad alta, error). **No** en botones (§4).

Color **siempre con texto o icono** (daltonismo): nunca solo color.

---

## 6. Patrones de interacción

- **Confirmar / elegir** (crear/editar/eliminar/duplicar destructivos o irreversibles): helper imperativo `confirmar()` (`components/comunes/confirmar.ts`) → un único `AlertDialog` en raíz (`ContenedorConfirmacion`). Action = relleno gris (`secondary`, el foco), Cancel = `ghost`, abre con foco limpio. **Sin rojo**: el peligro de un borrado lo comunica el **texto** del diálogo; pasa `destructivo: true` (marca semántica, no cambia el color). **Nunca** montes tu propio `Dialog` de borrado.
- **Feedback efímero**: `toast()` de sonner. No banners ad-hoc para "guardado".
- **Fila accionable**: `FilaConAcciones` (click primario + menú contextual + kebab + teclado). No reinventes el menú.
- **Menú flotante / popover**: `MenuFlotante`/`MenuContextual` (`components/comunes/`) o el hook `use-menu-contextual`. No repitas el `useEffect` de cierre-fuera/Escape.
- **Pestañas — dos formas por nivel** (no las confundas):
  - **Navegar entre secciones** → subnav subrayado (`EncabezadoSeccion`/`PestanasSeccion` + `clasesPestanaSeccion`). La activa lleva un subrayado oscuro.
  - **Alternar una vista/filtro del mismo contenido** → control **segmentado** (`ui/tabs.tsx` o `ui/toggle-group.tsx`). Item activo **gris plano** (`bg-muted`, **sin sombra**), nunca negro.
  - Regla: si te lleva a otro sitio, subnav; si cambia cómo ves lo que ya tienes delante, segmentado.

---

## 7. Estados de carga / vacío / error

- **Carga**: `Skeleton` para placeholders que espejan la anatomía real; **`<Spinner>`** (`ui/spinner.tsx`) para spinners (no `Loader2` suelto). En botón: `<Spinner className="mr-2" />`.
- **Vacío**: `EstadoVacio` (con Card) / `EstadoVacioTexto` (ligero). Da una **salida accionable** cuando exista. No escribas tu propio `<p>No hay…`.
- **Error**: `FronteraError` (boundary por ruta) + `BloqueError` (con reintento).

---

## 8. Formularios

- **Campo**: usa el componente `Campo` (`components/comunes/Campo.tsx`) — etiqueta (tipo frase) arriba, control, y debajo la línea de ayuda/error. No montes `Label` + control + ayuda a mano (no más `<label>` crudo: usa `Label`/`Campo`).
- **Error de validación EN LÍNEA**: el campo con problema se marca (borde rojo) y el mensaje sale **justo debajo del campo**, no como toast. El rojo aquí es señal de error (§5), no decoración. Los errores de servidor sí van por `toast.error(mensajeError(e))`.
- **Guardar**: el botón principal va a la derecha del pie (gris, §4) y se deshabilita hasta que el formulario es válido (`disabled={!puedeGuardar}`).

---

## 9. Navegación

- **Sidebar** data-driven (`/api/catalogo`, ADR 0005), agrupado por momento de flujo (Operación · Publicación · Datos); colapsable a rail. Gating por marca y por rol.
- **Hubs**: una entrada en el sidebar; sub-pestañas de sección en la cabecera (subnav, §6).
- **Cabecera de página**: `TituloPagina` + `AccionesPagina` se portalizan a la barra superior vía contexto del `AppShell`. **No** hagas tu propio `<h1>` ni tu propia barra.
- **⌘K**: paleta de comandos.

---

## 10. Responsive

- La app es un cascarón de alto fijo con scroll interno en `<main>`. No rompas el `overflow` global.
- Inputs ≥16px en móvil (§3). Layouts con breakpoints `sm/md/lg`; evita anchos fijos que desborden.
- Misma identidad visual en escritorio/tablet/móvil: los componentes no cambian de lenguaje según el dispositivo.

---

## 11. Capa `comunes/` (primitivas de dominio)

Lo que shadcn no trae, vive aquí. **Mira `comunes/` antes de hacer a mano** un menú, un estado vacío, un chip de estado, una confirmación, un aviso o un campo:

`ChipEstado` · `ChipNivelPresupuesto` · `Aviso` · `EstadoVacio`/`EstadoVacioTexto` · `Campo` · `BloqueError` · `MenuFlotante`/`MenuContextual` · `FilaConAcciones` · `confirmar`/`ContenedorConfirmacion` · `TarjetaKpi` · `SelectorMarca`/`SelectorRed`/`SelectorRedMultiple`.

---

## Checklist antes de promover una pantalla

- [ ] ¿Algún botón con color (negro/naranja/rojo)? → gris (`outline`/`ghost`/`secondary`); la principal por posición.
- [ ] ¿Algún color de estado pintado a mano? → `ChipEstado` / `Badge` semántico / `<Aviso>`.
- [ ] ¿Bloque ámbar con `amber-*`? → `<Aviso>` o tokens `--aviso-*`.
- [ ] ¿Naranja fuera de logo / hoy / en vivo? → quítalo.
- [ ] ¿Tarjeta/panel con borde o sombra? → sin borde ni sombra (sombra solo si flota).
- [ ] ¿Rótulo pequeño en MAYÚSCULAS/tracking? → tipo frase (`.text-label`).
- [ ] ¿`Loader2` suelto? → `<Spinner>`.
- [ ] ¿`Dialog` de borrado a mano? → `confirmar({ destructivo: true })` (sin rojo).
- [ ] ¿Segmentado a mano o con sombra? → `ui/tabs`/`ToggleGroup` (activo gris plano). ¿Es navegación? → subnav.
- [ ] ¿`<label>` crudo o campo a mano? → `Campo`/`Label`; error en línea.
- [ ] ¿`text-sm`/`text-xs` plano sobre `Input`/`Textarea`? → quítalo (zoom iOS).
- [ ] ¿Título/`<h1>` propio? → `TituloPagina`.
- [ ] ¿Pasa `tsc -b`, `eslint` y `vite build`?
