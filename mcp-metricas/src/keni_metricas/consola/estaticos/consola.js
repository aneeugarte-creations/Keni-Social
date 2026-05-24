// Consola Keni — JS vanilla minimo. Solo fetch a los endpoints locales.
// Sin librerias, sin red externa (coherente con privacidad por diseno).
"use strict";

// Marca un estado (ok/error/neutro) en un <span class="estado">.
function fijarEstado(el, texto, clase) {
  if (!el) return;
  el.textContent = texto || "";
  el.className = "estado" + (clase ? " " + clase : "");
}

async function postJSON(url, cuerpo) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  let datos = {};
  try {
    datos = await resp.json();
  } catch (e) {
    datos = {};
  }
  return { ok: resp.ok, datos };
}

// --- Pestana Proyectos ---

// Guardar el CLAUDE.md de un proyecto.
async function guardarClaudeMd(boton) {
  const tarjeta = boton.closest(".proyecto");
  const id = tarjeta.dataset.id;
  const textarea = tarjeta.querySelector("textarea.claude-md");
  const estado = tarjeta.querySelector(".estado");
  boton.disabled = true;
  fijarEstado(estado, "Guardando...", "");
  const { ok, datos } = await postJSON("/api/proyectos/claude-md", {
    id: id,
    contenido: textarea.value,
  });
  boton.disabled = false;
  if (ok) {
    fijarEstado(estado, datos.mensaje || "Guardado.", "ok");
  } else {
    fijarEstado(estado, datos.error || "No se pudo guardar.", "error");
  }
}

// Lanzar Claude Code en la carpeta del proyecto.
async function abrirEnClaude(boton) {
  const tarjeta = boton.closest(".proyecto");
  const id = tarjeta.dataset.id;
  const estado = tarjeta.querySelector(".estado");
  boton.disabled = true;
  fijarEstado(estado, "Abriendo Claude Code...", "");
  const { ok, datos } = await postJSON("/api/proyectos/abrir", { id: id });
  boton.disabled = false;
  if (ok) {
    fijarEstado(estado, datos.mensaje || "Abierto.", "ok");
  } else {
    fijarEstado(estado, datos.error || "No se pudo abrir.", "error");
  }
}

// Anadir una carpeta de proyecto.
async function anadirProyecto(form) {
  const estado = form.querySelector(".estado");
  const boton = form.querySelector("button[type=submit]");
  const nombre = form.querySelector("input[name=nombre]").value;
  const ruta = form.querySelector("input[name=ruta]").value;
  boton.disabled = true;
  fijarEstado(estado, "Validando...", "");
  const { ok, datos } = await postJSON("/api/proyectos/anadir", {
    nombre: nombre,
    ruta: ruta,
  });
  boton.disabled = false;
  if (ok) {
    fijarEstado(estado, (datos.mensaje || "Anadido.") + " Recargando...", "ok");
    setTimeout(function () {
      window.location.reload();
    }, 600);
  } else {
    fijarEstado(estado, datos.error || "No se pudo anadir.", "error");
  }
}

// --- Pestana Metricas ---

// Recarga el iframe del dashboard segun marca y rango seleccionados.
function actualizarDashboard() {
  const marcaSel = document.getElementById("sel-marca");
  const rangoSel = document.getElementById("sel-rango");
  const iframe = document.getElementById("iframe-dashboard");
  const csv = document.getElementById("enlace-csv");
  if (!iframe) return;
  const params = new URLSearchParams();
  params.set("rango", rangoSel ? rangoSel.value : "mes");
  if (marcaSel && marcaSel.value) params.set("marca", marcaSel.value);
  iframe.src = "/metricas/dashboard?" + params.toString();
  if (csv) csv.href = "/metricas/export.csv?" + params.toString();
}

// Enlaza los manejadores tras cargar el DOM (sin atributos inline onclick).
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-accion=guardar]").forEach(function (b) {
    b.addEventListener("click", function () {
      guardarClaudeMd(b);
    });
  });
  document.querySelectorAll("[data-accion=abrir]").forEach(function (b) {
    b.addEventListener("click", function () {
      abrirEnClaude(b);
    });
  });
  const formAnadir = document.getElementById("form-anadir");
  if (formAnadir) {
    formAnadir.addEventListener("submit", function (e) {
      e.preventDefault();
      anadirProyecto(formAnadir);
    });
  }
  const marcaSel = document.getElementById("sel-marca");
  const rangoSel = document.getElementById("sel-rango");
  if (marcaSel) marcaSel.addEventListener("change", actualizarDashboard);
  if (rangoSel) rangoSel.addEventListener("change", actualizarDashboard);
  if (document.getElementById("iframe-dashboard")) actualizarDashboard();
});
