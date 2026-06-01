# Diseño de redes — AMX Contenido (UnoTV / ClaroSports)
### Skills de dirección de arte por marca · Keni AI · keni-social

> **[SUPERSEDED — histórico]** Este documento describe la dirección de arte por marca implementada como **skills** (`diseno-unotv`, `diseno-clarosports`) dentro del sistema de skills, que ya **se retiró**. La superficie vigente de imagen es el **Estudio** ([`diseno-estudio-imagen.md`](diseno-estudio-imagen.md)): el estilo y las reglas por marca son editables por el equipo desde la Biblioteca (dirección de arte por marca) y el motor vive en `consola/src/keni_consola/motores/estudio_imagen/`. Se conserva como registro del razonamiento de diseño; las referencias a skills y a `skills-copy/` de abajo son históricas.

- **Fecha:** 2026-05-24 · **Estado:** ~~en uso (beta)~~ histórico (superseded por el Estudio / `diseno-estudio-imagen.md`).
- **Para:** que cualquiera del equipo (UnoTV o Claro Sports) convierta su material bruto en una pieza **lista y en marca** con la menor fricción posible.
- **Alcance de este doc:** es la **sub-decisión de "dirección de arte por marca"** dentro de la arquitectura de imagen. La decisión de imagen completa (enrutador determinista vs. generativo, 2 motores + revisor, motor por API) vive en [`estudio-imagen.md`](estudio-imagen.md), que es el doc canónico de imagen. Aquí solo se cubre **cómo un Skill por marca dirige y verifica** una pieza visual.
- **Hermano de:** el sistema de copy (`skills-copy/` + contexto editorial; doc-origen en `docs/origen-automatizacion-redes.md`). Mismo patrón: **un activo de contexto + un Skill que lo consume.** Allí el activo es el *contexto editorial*; aquí es el *sistema de diseño*.

---

## 0. TL;DR

1. **El activo base es la guía de diseño por marca** (paleta, tipografía, logo, composición por formato, reglas). UnoTV y Claro Sports tienen cada uno la suya porque el contenido y el público son distintos. Es lo primero y lo que "todos tienen de base".
2. **Encima va un Skill por marca** (`diseno-unotv`, `diseno-clarosports`). El equipo lo usa así de simple: *traigo mi material → el Skill me da el prompt de marca para mi herramienta → genero → se lo enseño → lo verifica.*
3. **Realismo honesto:** Claude **no genera** la imagen/vídeo final (sí la *ve*). Por eso el Skill hace de **director de arte**: produce el **prompt exacto, ya con la identidad de la marca y adaptado a la herramienta** que uses (Nano Banana/Gemini, DALL·E, Ideogram, Sora/Runway, Canva…) y luego **revisa el resultado** contra la guía. Cero setup, sirve para cualquier herramienta.
4. **Versión 100% automática (opcional):** un script que llama por API a una herramienta de imagen (p. ej. Gemini "Nano Banana") y devuelve la pieza sin salir de la terminal. Requiere una API key configurada una vez. Se documenta abajo como mejora, no como base.

---

## 1. Por qué este encuadre

El dolor visual del equipo no es "que la IA dibuje": es que **cada pieza salga consistente, en marca y a buen nivel sin pensarlo cada vez**. Eso se resuelve codificando el sistema de diseño una vez (la guía) y dejando que un Skill lo aplique siempre igual — la misma tesis que ya enseñáis: *la IA diseña el proceso la primera vez → se vuelve repetible.*

Como Claude **ve** imágenes de forma nativa, su papel natural en diseño es el de **director de arte que dirige y verifica**, no el de diseñador que renderiza. Por eso el Skill:
- **Dirige:** convierte tu material + la marca en un prompt que cualquier herramienta de imagen ejecuta bien.
- **Verifica:** mira la pieza terminada y te dice si está en marca, si el texto es legible en móvil, si el logo y las zonas seguras están bien, y qué corregir.

Dato estratégico (de la investigación del piloto): **UnoTV** tiene mucho alcance y **poco engagement** — el diseño es justo su palanca para mejorarlo; **Claro Sports** mueve ~80M de vistas/mes con engagement 2-3% — su reto es **volumen con consistencia**. Cada guía está orientada a ese objetivo.

---

## 2. Estructura

```
docs/diseno-redes.md             ← este documento (la decisión)
skills-copy/.claude/skills/
  diseno-unotv/
    SKILL.md                     ← el Skill (cómo dirige y verifica)
    guia-diseno.md               ← la BASE: sistema de diseño UnoTV
    plantillas-prompt.md         ← prompts listos por formato × herramienta
  diseno-clarosports/
    SKILL.md
    guia-diseno.md               ← la BASE: sistema de diseño Claro Sports
    plantillas-prompt.md
```

Cada carpeta de skill es **autónoma y portátil**: para usarla, se copia dentro de `~/.claude/skills/` (todas las máquinas) o `.claude/skills/` (un proyecto). La persona de UnoTV instala solo `diseno-unotv`; la de Claro Sports, solo `diseno-clarosports`.

### Quickstart de instalación
```bash
# Instala el skill de tu marca (ejemplo: Claro Sports)
mkdir -p ~/.claude/skills
cp -R "skills-copy/.claude/skills/diseno-clarosports" ~/.claude/skills/
# (UnoTV sería: .../skills/diseno-unotv)
```
Luego, en Claude Code, basta con describir lo que tienes —*"tengo este frame, hazme la portada vertical, uso Nano Banana"*— y el skill se activa solo. La guía y las plantillas viajan dentro de la carpeta, así que funciona sin más configuración.

---

## 3. Cómo lo usa el equipo (el flujo simple)

1. Abre Claude Code y escribe lo que tiene, en lenguaje normal:
   > *"Tengo este frame del partido, hazme la portada vertical para Reels. Uso Nano Banana."*
2. El Skill carga la guía de su marca, te pide **solo lo que falte** (formato, herramienta, el material) y te entrega:
   - el **prompt de marca listo para pegar** en tu herramienta, y
   - un **checklist de marca** para que tú mismo lo revises de un vistazo.
3. Generas en tu herramienta, le enseñas el resultado a Claude, y el Skill lo **verifica** y te da el ajuste si algo no cuadra.

No hay que recordar hex, tipografías ni reglas: viven en la guía y el Skill las aplica.

---

## 4. Mejora opcional — versión 100% automática (Tier B)

Para quien quiera que "salga solo" sin copiar/pegar: un pequeño script puede llamar a la **API de Gemini (imagen, "Nano Banana")** o de otra herramienta y devolver la pieza directamente. Requiere:
- una **API key** guardada una vez (en gestor de credenciales / variable de entorno, nunca en el archivo),
- definir qué formato/relación de aspecto produce.

Va contra el principio de "cero setup", por eso es opcional. Ruta recomendada: validar primero el flujo simple (Tier A) con el equipo; montar Tier B solo para los formatos más repetitivos una vez la guía esté estable. Encaja con la "última milla" descrita en `docs/origen-automatizacion-redes.md`.

---

## 5. Estado y qué falta verificar

- ⚠️ **Valores de marca:** las guías traen **defaults razonados marcados `[VERIFICAR]`** (hex, tipografías, uso de logo). Hay que confirmarlos contra el manual real de AMX/UnoTV/Claro Sports antes de tratarlos como oficiales. No se inventan como definitivos.
- ⚠️ **Logos:** las guías describen el uso; los **archivos** de logo (versiones, márgenes) los aporta el cliente y se referencian desde la guía.
- **Regla legal ya conocida (de las entrevistas):** prohibido usar la bandera con escudo nacional; cuidado con menores. Incorporada a los "No hacer" visuales.

---

*Sub-decisión de dirección de arte por marca. La arquitectura de imagen completa está en [`estudio-imagen.md`](estudio-imagen.md). Siguiente paso natural: rellenar los `[VERIFICAR]` con el manual real, probar el Skill con 3-4 piezas reales por marca, y decidir si algún formato repetitivo justifica el Tier B.*
