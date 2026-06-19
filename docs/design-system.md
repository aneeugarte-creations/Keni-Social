# Design System — Consola Keni

Sistema de diseño único de la consola. **Antes de construir cualquier pantalla o componente, lee esto.**
La regla de oro: *no inventes lo que el sistema ya resuelve*. Casi todo existe; el trabajo es reutilizarlo.

Fuentes de verdad en código:
- Tokens: `consola/frontend/src/index.css` + `consola/frontend/tailwind.config.js`
- Primitivas: `consola/frontend/src/components/ui/*`
- Primitivas de dominio (capa DS fuera de shadcn): `consola/frontend/src/components/comunes/*`
- Color de estado: `consola/frontend/src/lib/estado-color.ts` + `components/comunes/ChipEstado.tsx`

---

## 1. Identidad visual

Dashboard **monocromo estilo Vercel/Geist**. Menos es más; menos IA de cara a la audiencia, más sistema hacia adentro.

- **Lienzo** gris muy sutil `#fafafa` (`bg-background`). **Superficies** blancas (`bg-card`) que *flotan* sobre el lienzo, separadas por **bordes hairline** `#f0f0f0` (`border-border`).
- **Texto**: principal `#171717` (`text-foreground`), secundario/metadata `#666` (`text-muted-foreground`).
- **Acciones**: el primario es negro Geist, pero en la práctica **el botón por defecto de la plataforma es `outline` gris**. El negro sólido se evita.
- **Acento de marca**: naranja Keni `#ff5a1f` (`keni`), reservado a CTA de marca (Lanzar, Generar). Raro por diseño.
- **Modo oscuro** por la clase `.dark` en `<html>`; todo se define con tokens, nunca con colores crudos.
- **Excepción deliberada**: el editor de imagen (`src/editor/`) usa cromo oscuro tipo Canva. NO se unifica con el dashboard; ahí el color es el dominio del usuario.

---

## 2. Tokens (no uses valores crudos)

Definidos en `index.css` como variables HSL y mapeados en `tailwind.config.js`.

| Token | Uso |
|---|---|
| `background` / `foreground` | lienzo / texto principal |
| `card` / `card-foreground` | superficie que flota / su texto |
| `muted` / `muted-foreground` | superficie sutil / metadata gris |
| `secondary`, `accent` | grises suaves (relleno / hover / activo) |
| `border`, `input`, `ring` | hairline / borde de input / anillo de foco |
| `primary` | acción negra (rara) |
| `destructive` | negativo real (borrar, error) |
| `keni` (+ 50–900) | naranja de marca (CTA de marca) |
| `--aviso-borde/-superficie/-texto/-texto-plano` | **avisos ámbar** → usa `<Aviso>` o estos tokens, nunca `amber-*` a mano |
| `--control-activo(-foreground)` | fondo de un toggle activo / menú abierto |

**Radios**: `--radius` 0.625rem → controles `rounded-md`, **tarjetas `rounded-xl`**, fichas flotantes `rounded-lg`. No uses radios arbitrarios.
**Sombras**: sutiles (`shadow-sm`); fichas flotantes `rounded-lg` + `shadow`.

### Prohibido (deriva de color)
- Hex/RGB crudos en `className`.
- Paleta Tailwind arbitraria para **chrome** (`bg-blue-*`, `text-indigo-*`, `bg-violet-*`…).
- **Color semántico de estado a mano** (`bg-emerald-500/15`, `text-amber-700`, `bg-red-500`…). Para eso están las variantes de `Badge`, `ChipEstado` y `<Aviso>` (§5).
- Permitido sin tokens: `src/editor/*` (lienzo gráfico), gráficas (`lib/coloresRed.ts` + safelist Tremor), y mocks de redes sociales (imitan IG/TikTok/X/YouTube — coméntalo).

---

## 3. Tipografía

- Fuente **Geist** (pesos 300–700; el más fino real es `font-light` — `font-thin/extralight` caen a 300). `font-medium` por defecto en controles.
- **Micro-labels de sección/KPI** → utilidad `.text-label` (mayúsculas + tracking + gris). No reescribas `text-xs font-medium uppercase…` a mano.
- **Texto pequeño**: mínimo `text-xs` (12px) en chrome. `text-[10px]/[11px]` solo en celdas densas justificadas (calendario, mocks).
- **Inputs en móvil ≥16px** para no disparar el auto-zoom de iOS: las primitivas `Input`/`Textarea` ya traen `text-base md:text-sm`. **No pongas `text-sm`/`text-xs` plano sobre ellas** (tailwind-merge lo deja en 14/12px y reaparece el zoom). Si necesitas denso en escritorio: `text-base md:text-xs`.

---

## 4. Primitivas (`components/ui/`)

Úsalas siempre; no rehagas un control que ya existe.

`button` · `badge` · `input` · `textarea` / `auto-textarea` · `select` · `dialog` · `alert-dialog` · `card` · `table` · `tabs` · `checkbox` · `switch` · `tooltip` · `toggle-group` · `label` · `skeleton` · `sonner` (toast) · `spinner` · `Markdown`.

### Botón — variantes (regla de uso)
| Variante | Cuándo |
|---|---|
| `outline` | **por defecto** (el "estilo de la plataforma") |
| `ghost` | acción discreta / icono suelto |
| `secondary` | relleno gris suave cuando `outline` se pierde sobre un fondo con borde |
| `default` | negro sólido: **una** acción dominante y solo si hace falta destacar (raro) |
| `brand` | CTA de marca (Lanzar/Generar) — naranja, raro |
| `destructive` | negativo real (la confirmación va por `confirmar()`, §6) |
| `link` | enlace en texto |

Regla de jerarquía: **una sola acción primaria por pantalla**; las demás `outline`/`ghost`. No empates dos botones en gris donde uno es la acción principal.
Tamaños: `default` (h-9) · `sm` (h-8) · `lg` (h-10) · `icon` (cuadrado).

### Badge — variantes
`default` · `secondary` · `outline` · `destructive` · **`ok`** (verde) · **`info`** (cielo) · **`aviso`** (ámbar) · **`error`** (rojo). Las semánticas usan pares 700/300 (claro/oscuro). Para estados de *trabajo* usa `ChipEstado` (§5), no el Badge a pelo.

---

## 5. Color de estado — UNA fuente

El estado nunca se pinta inline. Tres herramientas, por orden de preferencia:

1. **`ChipEstado` / `ChipNivelPresupuesto`** (`components/comunes/ChipEstado.tsx`): badge ÚNICO de estados de trabajo (generación, etapa/run de pipeline, job de cola, daemon). El mismo estado se llama y pinta igual en toda la consola. Si tu dominio tiene un estado nuevo, **añádelo al mapa `ASPECTO`**, no pintes un badge nuevo.
2. **Variantes semánticas de `Badge`** (`ok`/`info`/`aviso`/`error`) para flags puntuales (Conectado, Oficial, Pendiente).
3. **`<Aviso>`** (`components/comunes/Aviso.tsx`) para el bloque/callout ámbar de atención. Consume `--aviso-*`. Reemplaza el `border-amber-500/40 bg-amber-500/10 text-amber-700 dark:…` copiado a mano.

**Taxonomía de cobertura/turnos** (`lib/estado-color.ts`, fijada por `estado-color.test.ts`):
- **amarillo** (`yellow`) = `sin-cubrir` (hueco real, pide decisión).
- **ámbar** (`amber`) = `empieza-en` (PRE-LIVE, el saque está cerca). *No* uses ámbar para otra cosa (ni "media prioridad" ni "finde").
- **verde** = en-vivo / cubierto / terminado-OK.
- **gris** (`muted-foreground`) = programado / neutro / "media prioridad" / "off".
- **rojo** (`destructive`) = solo negativo real (vencido, prioridad alta, error, eliminar).

Color **siempre con texto o icono** (daltonismo): nunca solo color.

---

## 6. Patrones de interacción

- **Confirmar / elegir** (crear/editar/eliminar/duplicar destructivos o irreversibles): helper imperativo `confirmar()` (`components/comunes/confirmar.ts`) → un único `AlertDialog` en raíz (`ContenedorConfirmacion`). Action=`outline` (foco), Cancel=`ghost`, rojo solo en destructivas, abre con foco limpio. **Nunca** montes tu propio `Dialog` de borrado con botón rojo sólido.
- **Feedback efímero**: `toast()` de sonner. No banners ad-hoc para "guardado".
- **Fila accionable**: `FilaConAcciones` (click primario + menú contextual + kebab + teclado). No reinventes el menú.
- **Menú flotante / popover**: `MenuFlotante`/`MenuContextual` (`components/comunes/`) o el hook `use-menu-contextual`. No repitas el `useEffect` de cierre-fuera/Escape.
- **Segmentado / toggle**: `ToggleGroup` (`ui/toggle-group.tsx`). Estado activo **gris** (`bg-muted`/`secondary`), nunca negro sólido.

---

## 7. Estados de carga / vacío / error

- **Carga**: `Skeleton` para placeholders que espejan la anatomía real; **`<Spinner>`** (`ui/spinner.tsx`) para spinners (no `Loader2` suelto). En botón: `<Spinner className="mr-2" />`.
- **Vacío**: `EstadoVacio` (con Card) / `EstadoVacioTexto` (ligero). Da una **salida accionable** cuando exista.
- **Error**: `FronteraError` (boundary por ruta) + `BloqueError` (con reintento).

---

## 8. Navegación

- **Sidebar** data-driven (`/api/catalogo`, ADR 0005), agrupado por momento de flujo (Operación · Publicación · Datos); colapsable a rail. Gating por marca y por rol.
- **Hubs**: una entrada en el sidebar; sub-pestañas en la cabecera (escritorio = tira, móvil = `SelectorSeccion`).
- **Cabecera de página**: `TituloPagina` + `AccionesPagina` se portalizan a la barra superior vía contexto del `AppShell`. **No** hagas tu propio `<h1>` ni tu propia barra.
- **⌘K**: paleta de comandos.

---

## 9. Responsive

- La app es un cascarón de alto fijo con scroll interno en `<main>`. No rompas el `overflow` global.
- Inputs ≥16px en móvil (§3). Layouts con breakpoints `sm/md/lg`; evita anchos fijos que desborden.
- Misma identidad visual en escritorio/tablet/móvil: los componentes no cambian de lenguaje según el dispositivo.

---

## 10. Capa `comunes/` (primitivas de dominio)

Lo que shadcn no trae, vive aquí. **Mira `comunes/` antes de hacer a mano** un menú, un estado vacío, un chip de estado, una confirmación o un aviso:

`ChipEstado` · `ChipNivelPresupuesto` · `Aviso` · `EstadoVacio`/`EstadoVacioTexto` · `BloqueError` · `MenuFlotante`/`MenuContextual` · `FilaConAcciones` · `confirmar`/`ContenedorConfirmacion` · `TarjetaKpi` · `SelectorMarca`/`SelectorRed`/`SelectorRedMultiple`.

---

## Checklist antes de promover una pantalla

- [ ] ¿Algún color de estado pintado a mano? → `ChipEstado` / `Badge` semántico / `<Aviso>`.
- [ ] ¿Bloque ámbar con `amber-*`? → `<Aviso>` o tokens `--aviso-*`.
- [ ] ¿`Loader2` suelto? → `<Spinner>`.
- [ ] ¿`Dialog` de borrado a mano? → `confirmar({ destructivo: true })`.
- [ ] ¿Segmentado a mano? → `ToggleGroup` (activo gris).
- [ ] ¿`text-sm`/`text-xs` plano sobre `Input`/`Textarea`? → quítalo (zoom iOS).
- [ ] ¿Título/`<h1>` propio? → `TituloPagina`.
- [ ] ¿Una sola acción primaria, el resto `outline`/`ghost`?
- [ ] ¿Pasa `tsc -b`, `eslint` y `vite build`?
