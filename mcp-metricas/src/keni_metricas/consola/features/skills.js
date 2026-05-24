// Feature Skills (Generar copy) — JS vanilla minimo, solo fetch local.
// Sin librerias ni red externa. Reusa fijarEstado()/postJSON() de consola.js.
"use strict";

// Muestra la descripcion de la skill elegida (de su data-desc).
function actualizarDescSkill() {
  const sel = document.getElementById("skills-skill");
  const desc = document.getElementById("skills-desc");
  if (!sel || !desc) return;
  const opcion = sel.options[sel.selectedIndex];
  desc.textContent = opcion ? opcion.getAttribute("data-desc") || "" : "";
}

// Envia el formulario, corre la skill por debajo y pinta el resultado.
async function generarSkill(form) {
  const estado = document.getElementById("skills-estado");
  const boton = document.getElementById("skills-generar");
  const wrap = document.getElementById("skills-resultado-wrap");
  const salida = document.getElementById("skills-resultado");

  const skill = form.querySelector("[name=skill]").value;
  const marca = form.querySelector("[name=marca]").value;
  const texto = form.querySelector("[name=texto]").value;

  if (!skill || !marca) {
    fijarEstado(estado, "Elige una skill y una marca.", "error");
    return;
  }
  if (!texto.trim()) {
    fijarEstado(estado, "Pega una nota o transcripcion.", "error");
    return;
  }

  boton.disabled = true;
  if (wrap) wrap.hidden = true;
  fijarEstado(estado, "Generando con Claude... esto puede tardar un poco.", "");

  const { ok, datos } = await postJSON("/api/skills/ejecutar", {
    skill: skill,
    marca: marca,
    texto: texto,
  });

  boton.disabled = false;
  if (ok) {
    fijarEstado(estado, "Listo. Revisa el borrador antes de usarlo.", "ok");
    if (salida) salida.textContent = datos.resultado || "";
    if (wrap) {
      wrap.hidden = false;
      wrap.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } else {
    fijarEstado(estado, datos.error || "No se pudo generar el borrador.", "error");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const sel = document.getElementById("skills-skill");
  if (sel) {
    sel.addEventListener("change", actualizarDescSkill);
    actualizarDescSkill();
  }
  const form = document.getElementById("form-skills");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      generarSkill(form);
    });
  }
});
