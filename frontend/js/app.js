/**
 * Cliente SPA para Libro Matriz FP · DETP Jujuy
 * Migrado desde Cliente.html con soporte para el circuito oficial de emisión de certificados
 * y bandeja de entrada centralizada del rol 'titulos'.
 */

var estado = {
  sesion: null,
  cursos: [],
  curso: null,
  datos: null,
  pestania: 'notas',
  emailActual: localStorage.getItem('lm_email') || 'titulos@educacion.jujuy.gob.ar',
  filtroBandeja: 'Pendiente'
};

var $ = function (id) { return document.getElementById(id); };

// Helper para llamadas a la API REST del backend
async function llamar(url, metodo, cuerpo) {
  metodo = metodo || 'GET';
  var headers = { 'Accept': 'application/json' };
  if (cuerpo) {
    headers['Content-Type'] = 'application/json';
  }
  if (estado.emailActual) {
    headers['X-User-Email'] = estado.emailActual;
  }

  var opt = { method: metodo, headers: headers };
  if (cuerpo && metodo !== 'GET') {
    opt.body = JSON.stringify(cuerpo);
  }

  var resp;
  try {
    resp = await fetch(url, opt);
  } catch (err) {
    throw new Error('No se pudo conectar con el servidor local. Verifica que el backend esté activo.');
  }

  var json;
  try {
    json = await resp.json();
  } catch (err) {
    throw new Error('Respuesta no válida del servidor.');
  }

  if (!resp.ok || json.ok === false) {
    throw new Error(json.error || ('Error en la solicitud HTTP ' + resp.status));
  }
  return json;
}

function esc(t) {
  return String(t == null ? '' : t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

var tiempoAviso;
function avisar(texto, tipo) {
  var a = $('aviso');
  a.textContent = texto;
  a.className = 'aviso ' + (tipo || '');
  a.hidden = false;
  clearTimeout(tiempoAviso);
  tiempoAviso = setTimeout(function () { a.hidden = true; }, tipo === 'error' ? 9000 : 3500);
}

function problema(e) {
  avisar((e && e.message) ? e.message : String(e), 'error');
}

// ---------- INICIALIZACIÓN ----------
window.addEventListener('load', async function () {
  await cargarUsuariosPrueba();
  await iniciarSesion();
});

async function cargarUsuariosPrueba() {
  try {
    var res = await llamar('/api/usuarios');
    var select = $('selectorUsuario');
    select.innerHTML = '<option value="">-- Cambiar Usuario / Rol (Pruebas) --</option>';
    (res.usuarios || []).forEach(function (u) {
      var opt = document.createElement('option');
      opt.value = u.Email;
      opt.textContent = (u.Nombre || u.Email) + ' [' + u.Rol + ']';
      if (u.Email.toLowerCase() === (estado.emailActual || '').toLowerCase()) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    select.addEventListener('change', function () {
      if (select.value) {
        estado.emailActual = select.value;
        localStorage.setItem('lm_email', select.value);
        iniciarSesion();
      }
    });
  } catch (err) {
    console.warn('No se pudo cargar la lista de usuarios para prueba:', err);
  }
}

async function iniciarSesion() {
  $('main').innerHTML = '<div class="cargando">Iniciando sesión…</div>';
  try {
    var r = await llamar('/api/inicio');
    estado.sesion = r.sesion;
    estado.cursos = r.cursos;
    estado.emailActual = r.sesion.email;

    $('usuario').innerHTML = '<b>' + esc(r.sesion.nombre) + '</b>' +
      '<span class="rol">' + esc(r.sesion.rol) + '</span>';

    // Si entra con rol 'titulos', llevarlo directamente a su bandeja de trabajo
    if (r.sesion.esTitulos) {
      verBandejaTitulos();
    } else {
      verCursos();
    }
  } catch (e) {
    $('main').innerHTML = '<div class="vacio">' + esc(e.message || e) +
      '<div style="margin-top:12px"><small>Configura tu <code>service_account.json</code> en <code>credentials/</code> y tu <code>PANEL_ID</code> en el archivo .env.</small></div></div>';
  }
}

$('volver').addEventListener('click', function () {
  if (estado.sesion && estado.sesion.esTitulos) {
    verBandejaTitulos();
  } else {
    verCursos();
  }
});

// ---------- LISTA DE CURSOS (ESCUELAS Y DIRECCIÓN) ----------
function verCursos() {
  estado.curso = null;
  $('migas').hidden = true;
  var m = $('main');
  var subtitulo = (estado.sesion && estado.sesion.verTodo)
    ? 'Acceso a todas las instituciones · ' + estado.cursos.length + ' curso(s).'
    : 'Acceso a tu institución · ' + estado.cursos.length + ' curso(s).';

  m.innerHTML =
    '<h1>Cursos</h1>' +
    '<p style="color:var(--suave);margin:0 0 12px">' + subtitulo + '</p>' +
    '<div class="acciones">' +
      (estado.sesion.puedeCargar || estado.sesion.verTodo ? '<button class="boton" id="btnNuevoCurso">+ Nuevo curso</button>' : '') +
      (estado.sesion.verTodo ? '<button class="boton suave" id="btnResumen">Resumen por institución</button>' : '') +
      '<button class="boton suave" id="btnTitulos">Certificados de Títulos</button>' +
    '</div>' +
    '<input class="buscar" id="buscar" placeholder="Buscar por institución, oferta o CUE…">' +
    '<div class="tarjetas" id="lista"></div>';

  if ($('btnNuevoCurso')) $('btnNuevoCurso').addEventListener('click', mostrarModalNuevoCurso);
  if ($('btnResumen')) $('btnResumen').addEventListener('click', verResumen);
  if ($('btnTitulos')) $('btnTitulos').addEventListener('click', verBandejaTitulos);
  $('buscar').addEventListener('input', pintarLista);
  pintarLista();
}

function pintarLista() {
  var q = ($('buscar').value || '').toLowerCase().trim();
  var cs = estado.cursos.filter(function (c) {
    return !q || (c.institucion + ' ' + c.oferta + ' ' + c.cue + ' ' + c.ciclo).toLowerCase().indexOf(q) >= 0;
  });
  $('lista').innerHTML = cs.length ? cs.map(function (c) {
    var cerrado = String(c.estado).toLowerCase() === 'cerrado';
    var claseEstado = cerrado ? 'cerrado' : 'abierto';
    return '<button class="tarjeta" data-id="' + esc(c.id) + '">' +
      '<span class="of">' + esc(c.oferta) + '</span>' +
      '<span class="inst">' + esc(c.institucion) + '</span>' +
      '<span class="meta">' + esc(c.ciclo) + ' · ' + esc(c.turno) + ' · ' + esc(c.division) + '</span>' +
      '<div><span class="etiqueta ' + claseEstado + '">' + esc(c.estado) + '</span></div></button>';
  }).join('') : '<div class="vacio">Ningún curso coincide con la búsqueda.</div>';

  Array.prototype.forEach.call(document.querySelectorAll('.tarjeta'), function (b) {
    b.addEventListener('click', function () { abrirCurso(b.dataset.id); });
  });
}

// ---------- DETALLE DE UN CURSO ----------
async function abrirCurso(id, pestaniaInicial) {
  $('main').innerHTML = '<div class="cargando">Abriendo el curso desde Google Drive…</div>';
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(id));
    var d = r.datos;
    estado.curso = d.curso;
    estado.datos = d;
    estado.pestania = pestaniaInicial || 'notas';
    $('migas').hidden = false;
    pintarCurso();
  } catch (e) {
    problema(e);
    verCursos();
  }
}

function pintarCurso() {
  var d = estado.datos, e = d.encabezado;
  $('main').innerHTML =
    '<h1>' + esc(e.oferta || estado.curso.oferta) + '</h1>' +
    '<dl class="ficha">' +
      '<dt>Establecimiento</dt><dd>' + esc(e.establecimiento) + (e.cue ? ' · CUE ' + esc(e.cue) : '') + '</dd>' +
      '<dt>Curso</dt><dd>' + esc(e.ciclo) + ' · ' + esc(e.turno) + ' · ' + esc(e.division) +
        ' · ' + d.estudiantes.length + ' estudiantes</dd>' +
      '<dt>Diseño curricular</dt><dd>' + esc(e.disenio) + '</dd>' +
    '</dl>' +
    '<div class="pestanias" role="tablist">' +
      '<button role="tab" data-p="notas">Notas por módulo</button>' +
      '<button role="tab" data-p="acta">Acta de examen</button>' +
      '<button role="tab" data-p="analitico">Analítico</button>' +
      '<button role="tab" data-p="solicitudes">Circuito de Certificados</button>' +
    '</div><div class="panel" id="panel"></div>';

  Array.prototype.forEach.call(document.querySelectorAll('[role=tab]'), function (b) {
    b.addEventListener('click', function () {
      estado.pestania = b.dataset.p;
      pintarPestania();
    });
  });
  pintarPestania();
}

function pintarPestania() {
  Array.prototype.forEach.call(document.querySelectorAll('[role=tab]'), function (b) {
    b.setAttribute('aria-selected', b.dataset.p === estado.pestania);
  });
  if (estado.pestania === 'notas') pintarNotas();
  else if (estado.pestania === 'acta') pintarActa();
  else if (estado.pestania === 'analitico') pintarAnalitico();
  else if (estado.pestania === 'solicitudes') pintarSolicitudesCurso();
}

// ---------- PESTAÑA: NOTAS POR MÓDULO (CON CONGELAMIENTO) ----------
function pintarNotas() {
  var d = estado.datos, editable = d.puedeCargar;
  if (!d.estudiantes.length) {
    $('panel').innerHTML = '<div class="vacio">El curso todavía no tiene estudiantes cargados en la pestaña RAC.</div>';
    return;
  }
  var th = d.modulos.map(function (m) {
    return '<th class="mod" title="' + esc(m.nombre) + '">' + esc(m.nombre) +
           (m.periodo ? ' · ' + esc(m.periodo) : '') + '</th>';
  }).join('');

  var hayCongelados = false;
  var filas = d.estudiantes.map(function (es) {
    if (es.notasCongeladas) hayCongelados = true;
    var bloqueado = !editable || es.notasCongeladas;

    var celdas = es.notas.map(function (n, i) {
      if (bloqueado) {
        return '<td class="nota" style="text-align:center"><input value="' + esc(n) + '" disabled ' +
               'title="' + (es.notasCongeladas ? '🔒 Calificaciones congeladas por certificado oficial aprobado' : '') + '"></td>';
      }
      return '<td class="nota"><input value="' + esc(n) + '" maxlength="3" ' +
             'data-fila="' + es.fila + '" data-mod="' + d.modulos[i].i + '"></td>';
    }).join('');

    var candado = es.notasCongeladas ? ' <span title="Certificado Aprobado - Notas Congeladas">🔒</span>' : '';

    return '<tr><td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td>' + esc(es.apellido) + ', ' + esc(es.nombres) + candado + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      celdas +
      '<td style="text-align:center">' + esc(es.notaFinal) + '</td>' +
      '<td style="font-size:12px">' + esc(es.situacion) + '</td></tr>';
  }).join('');

  $('panel').innerHTML =
    (hayCongelados
      ? '<div class="alerta-congelado">🔒 <b>Atención:</b> Los estudiantes con certificado oficial aprobado tienen sus calificaciones <b>congeladas e inmutables</b> para garantizar la fidelidad del documento emitido.</div>'
      : '') +
    (editable
      ? '<div class="acciones"><button class="boton" id="guardar" disabled>Guardar cambios</button>' +
        '<span style="color:var(--suave);font-size:12px">Nota de 1 a 10, o AUS si estuvo ausente.</span></div>'
      : '<div class="acciones"><span style="color:var(--suave);font-size:12px">' +
        'Tu rol es de consulta: puedes visualizar, no modificar.</span></div>') +
    '<div class="tabla-ancha"><table><thead><tr>' +
      '<th style="width:36px">N°</th><th>Apellido y nombres</th><th style="width:92px">Documento</th>' +
      th + '<th class="mod">Nota final</th><th style="width:150px">Situación</th>' +
    '</tr></thead><tbody>' + filas + '</tbody></table></div>';

  if (!editable) return;
  var pendientes = {};
  Array.prototype.forEach.call(document.querySelectorAll('td.nota input:not([disabled])'), function (inp) {
    var original = inp.value;
    inp.addEventListener('input', function () {
      inp.value = inp.value.toUpperCase();
      var k = inp.dataset.fila + '-' + inp.dataset.mod;
      if (inp.value === original) delete pendientes[k];
      else pendientes[k] = { fila: +inp.dataset.fila, modulo: +inp.dataset.mod, valor: inp.value };
      $('guardar').disabled = !Object.keys(pendientes).length;
    });
  });

  $('guardar').addEventListener('click', async function () {
    var cambios = Object.keys(pendientes).map(function (k) { return pendientes[k]; });
    $('guardar').disabled = true;
    avisar('Guardando notas en Google Sheets…');
    try {
      var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/notas', 'POST', { cambios: cambios });
      avisar(r.guardados + ' nota(s) guardadas con éxito', 'ok');
      abrirCurso(estado.curso.id);
    } catch (e) {
      problema(e);
      $('guardar').disabled = false;
    }
  });
}

// ---------- PESTAÑA: ACTA DE EXAMEN ----------
async function pintarActa() {
  $('panel').innerHTML = '<div class="cargando">Cargando el acta desde Google Sheets…</div>';
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/acta');
    var a = r.acta;
    var ed = a.puedeCargar;

    var filas = a.estudiantes.map(function (es) {
      var campo = function (c, v) {
        return ed ? '<td class="nota"><input value="' + esc(v) + '" maxlength="3" ' +
                    'data-fila="' + es.filaActa + '" data-campo="' + c + '"></td>'
                  : '<td style="text-align:center">' + esc(v) + '</td>';
      };
      return '<tr><td style="text-align:center">' + esc(es.orden) + '</td>' +
        '<td style="text-align:center">' + esc(es.documento) + '</td><td>' + esc(es.nombre) + '</td>' +
        campo('teorico', es.teorico) + campo('practico', es.practico) +
        '<td style="text-align:center"><b>' + esc(es.definitiva) + '</b></td>' +
        '<td>' + esc(es.definitivaLetras) + '</td></tr>';
    }).join('');

    $('panel').innerHTML =
      '<dl class="ficha"><dt>Fecha</dt><dd>' + esc(a.mesa.fecha || '—') + '</dd>' +
      '<dt>Mesa</dt><dd>' + esc([a.mesa.presidente, a.mesa.vocal1, a.mesa.vocal2]
        .filter(Boolean).join(' · ') || '—') + '</dd></dl>' +
      (ed ? '<div class="acciones"><button class="boton" id="guardarActa" disabled>Guardar cambios</button>' +
            '<span style="color:var(--suave);font-size:12px">La nota definitiva y en letras se calculan automáticamente.</span></div>' : '') +
      '<div class="tabla-ancha"><table><thead><tr><th style="width:36px">N°</th>' +
      '<th style="width:92px">Documento</th><th>Apellido y nombre</th>' +
      '<th style="width:70px">Teórico</th><th style="width:70px">Práctico</th>' +
      '<th style="width:70px">Definitiva</th><th style="width:110px">En letras</th>' +
      '</tr></thead><tbody>' + (filas || '') + '</tbody></table></div>';

    if (!ed) return;
    var pend = {};
    Array.prototype.forEach.call(document.querySelectorAll('#panel input'), function (inp) {
      var orig = inp.value;
      inp.addEventListener('input', function () {
        inp.value = inp.value.toUpperCase();
        var k = inp.dataset.fila + '-' + inp.dataset.campo;
        if (inp.value === orig) delete pend[k];
        else pend[k] = { filaActa: +inp.dataset.fila, campo: inp.dataset.campo, valor: inp.value };
        $('guardarActa').disabled = !Object.keys(pend).length;
      });
    });

    $('guardarActa').addEventListener('click', async function () {
      var cambios = Object.keys(pend).map(function (k) { return pend[k]; });
      $('guardarActa').disabled = true;
      avisar('Guardando acta…');
      try {
        var res = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/acta', 'POST', { cambios: cambios });
        avisar(res.guardados + ' nota(s) guardadas en el acta', 'ok');
        pintarActa();
      } catch (e) {
        problema(e);
        $('guardarActa').disabled = false;
      }
    });
  } catch (err) {
    problema(err);
  }
}

// ---------- PESTAÑA: CIRCUITO DE CERTIFICADOS (VISTA ESCUELA) ----------
function pintarSolicitudesCurso() {
  var d = estado.datos;
  var filas = d.estudiantes.map(function (es) {
    var aprobo = String(es.situacion || '').startsWith('Aprobó');
    var sol = es.solicitudCertificado || {};
    var st = sol.estado || 'No solicitado';

    var badgeClass = 'badge-no-solicitado';
    if (st === 'Pendiente') badgeClass = 'badge-pendiente';
    else if (st === 'Observado') badgeClass = 'badge-observado';
    else if (st === 'Aprobado') badgeClass = 'badge-aprobado';

    var accionHtml = '';
    if (!aprobo) {
      accionHtml = '<button class="boton" disabled style="opacity:0.4;background:var(--suave)" title="Solo habilitado para estudiantes con situación Aprobó">No elegible (No aprobó)</button>';
    } else {
      if (st === 'No solicitado') {
        accionHtml = '<button class="boton" onclick="solicitarCertificadoEstudiante(\'' + esc(es.documento) + '\')">Solicitar Certificado</button>';
      } else if (st === 'Pendiente') {
        accionHtml = '<span style="color:#b06000;font-weight:600">⏳ En revisión por Títulos</span>';
      } else if (st === 'Observado') {
        accionHtml = '<button class="boton" style="background:#e37400" onclick="solicitarCertificadoEstudiante(\'' + esc(es.documento) + '\')">Reenviar a Títulos</button>';
      } else if (st === 'Aprobado') {
        accionHtml = '<span style="color:#137333;font-weight:600">🔒 Aprobado (' + esc(sol.numeroCertificado) + ')</span>';
      }
    }

    var alertaObs = '';
    if (st === 'Observado' && sol.motivoObservacion) {
      alertaObs = '<div class="alerta-observacion">⚠️ <b>Observación de Títulos:</b> ' + esc(sol.motivoObservacion) + '</div>';
    }

    return '<tr>' +
      '<td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td><b>' + esc(es.apellido) + ', ' + esc(es.nombres) + '</b>' + alertaObs + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      '<td>' + esc(es.situacion || '—') + '</td>' +
      '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(st) + '</span></td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(sol.numeroCertificado || '—') + '</td>' +
      '<td style="text-align:center">' +
        accionHtml +
        ' <button class="boton suave" style="margin-left:4px" onclick="verAnaliticoEstudiante(\'' + esc(es.documento) + '\')">Ver Analítico</button>' +
      '</td>' +
    '</tr>';
  }).join('');

  $('panel').innerHTML =
    '<div class="ficha">' +
      '<dt>Regla de solicitud:</dt>' +
      '<dd>La escuela solo puede solicitar la emisión del certificado oficial para alumnos en estado <b>"Aprobó"</b>. Quienes no aprobaron no tienen la opción habilitada.</dd>' +
    '</div>' +
    '<div class="tabla-ancha"><table><thead><tr>' +
      '<th style="width:36px">N°</th><th>Estudiante</th><th style="width:90px">DNI</th>' +
      '<th style="width:130px">Situación</th><th style="width:110px">Estado Pedido</th>' +
      '<th style="width:140px">N° Certificado</th><th style="width:230px">Acción</th>' +
    '</tr></thead><tbody>' + filas + '</tbody></table></div>';
}

async function solicitarCertificadoEstudiante(doc) {
  avisar('Enviando pedido al Departamento de Títulos…');
  try {
    var r = await llamar('/api/solicitudes', 'POST', {
      idCurso: estado.curso.id,
      documento: doc
    });
    avisar('¡Solicitud enviada a la bandeja de Títulos con éxito!', 'ok');
    abrirCurso(estado.curso.id, 'solicitudes');
  } catch (e) {
    problema(e);
  }
}

function verAnaliticoEstudiante(doc) {
  estado.pestania = 'analitico';
  pintarPestania();
  setTimeout(function () {
    if ($('selEst')) {
      $('selEst').value = doc;
      $('generar').click();
    }
  }, 100);
}

// ---------- PESTAÑA: ANALÍTICO (CON CONTROL DE BORRADOR VS OFICIAL) ----------
function pintarAnalitico() {
  var opciones = estado.datos.estudiantes.map(function (e) {
    return '<option value="' + esc(e.documento) + '">' + esc(e.apellido) + ', ' +
           esc(e.nombres) + '</option>';
  }).join('');

  $('panel').innerHTML =
    '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px;align-items:center">' +
      '<label style="display:flex;align-items:center;gap:6px">Estudiante: <select id="selEst" style="min-width:220px">' + opciones + '</select></label>' +
      '<label style="display:flex;align-items:center;gap:6px">Emisión: <input type="date" id="fecha"></label>' +
      '<button class="boton" id="generar" style="background:#1F4E78">Ver el analítico</button>' +
      '<button class="boton suave" id="imprimir" disabled style="opacity:0.5;cursor:not-allowed">Imprimir</button>' +
    '</div>' +
    '<div id="bannerEstadoAnalitico"></div>' +
    '<div id="salida"></div>';

  $('fecha').valueAsDate = new Date();

  $('generar').addEventListener('click', async function () {
    var doc = $('selEst').value;
    if (!doc) {
      avisar('Ese estudiante no tiene documento registrado.', 'error');
      return;
    }
    $('salida').innerHTML = '<div class="cargando">Generando analítico oficial…</div>';
    var f = $('fecha').value || '';
    try {
      var url = '/api/curso/' + encodeURIComponent(estado.curso.id) + '/analitico?documento=' + encodeURIComponent(doc) +
                '&fecha=' + encodeURIComponent(f);
      var r = await llamar(url);
      var an = r.analitico;
      var docOf = an.documentoOficial || {};

      var bannerBox = $('bannerEstadoAnalitico');
      var btnImp = $('imprimir');

      if (an.esBorrador) {
        var msg = docOf.mensajeEstado || 'Este analítico se encuentra en estado BORRADOR - no válido: requiere aprobación del Departamento de Títulos para imprimir.';
        bannerBox.innerHTML = '<div class="banner-aviso-analitico">' + esc(msg) + '</div>';
        btnImp.disabled = true;
        btnImp.style.opacity = '0.5';
        btnImp.style.cursor = 'not-allowed';
        btnImp.title = 'Impresión bloqueada: requiere aprobación del Departamento de Títulos';
      } else {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#e6f4ea;border-color:#34a853;color:#137333">' +
            '✅ <b>Certificado Oficial APROBADO:</b> Registrado bajo el N° <b>' + esc(an.numeroCertificado) + '</b>. Calificaciones congeladas y habilitado para impresión oficial.' +
          '</div>';
        btnImp.disabled = false;
        btnImp.style.opacity = '1';
        btnImp.style.cursor = 'pointer';
        btnImp.style.background = 'var(--azul)';
        btnImp.style.color = '#fff';
        btnImp.title = 'Imprimir certificado oficial';
      }

      $('salida').innerHTML = armarAnalitico(an);
    } catch (e) {
      problema(e);
      $('salida').innerHTML = '';
    }
  });

  $('imprimir').addEventListener('click', function () {
    if (!$('imprimir').disabled) {
      window.print();
    }
  });

  // Auto-generar para el primer estudiante al abrir
  setTimeout(function () {
    if ($('generar')) $('generar').click();
  }, 50);
}

function armarAnalitico(r) {
  var d = r.documentoOficial;
  if (!d) {
    return armarAnaliticoCeldas(r);
  }

  var watermark = d.esBorrador
    ? '<div class="marca-agua-borrador-oficial">BORRADOR<br>NO VÁLIDO</div>'
    : '';

  var filasModulos = (d.trayecto || []).map(function (m) {
    return '<tr>' +
      '<td style="text-align:center">' + esc(m.nro) + '</td>' +
      '<td>' + esc(m.modulo) + '</td>' +
      '<td style="text-align:center">' + esc(m.tipo) + '</td>' +
      '<td style="text-align:center">' + esc(m.periodo) + '</td>' +
      '<td style="text-align:center">' + esc(m.hsReloj) + '</td>' +
      '<td style="text-align:center">' + esc(m.hsCat) + '</td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(m.nota || '') + '</td>' +
      '<td style="text-align:center">' + esc(m.enLetras || '') + '</td>' +
      '<td style="text-align:center">' + esc(m.condicion) + '</td>' +
    '</tr>';
  }).join('');

  return '<div class="hoja-oficial">' +
    watermark +
    '<div style="display:flex;justify-content:space-between;font-size:12px;font-weight:bold;margin-bottom:6px">' +
      '<div>Libro Nº ' + esc(d.libro) + ' Folio Nº ' + esc(d.folio) + '</div>' +
      '<div>CERT. Nº ' + esc(d.certNro || '_____') + '</div>' +
    '</div>' +
    '<div style="text-align:center;margin-bottom:12px">' +
      '<img src="/img/escudo.png" alt="Escudo de Jujuy" style="height:55px;display:block;margin:0 auto 4px">' +
      '<div style="font-size:12px">República Argentina</div>' +
      '<div style="font-size:13px;font-weight:bold;letter-spacing:0.5px;margin:2px 0">LEY DE EDUCACIÓN NACIONAL Nº 26.206</div>' +
      '<div style="font-size:13px;font-weight:bold;letter-spacing:0.5px">PROVINCIA DE JUJUY</div>' +
      '<div style="font-size:11px">LEY PROVINCIAL Nº 5807</div>' +
      '<div style="font-size:12px;font-weight:bold;margin:2px 0">MINISTERIO DE EDUCACIÓN</div>' +
      '<div style="font-size:11px">SECRETARÍA GESTIÓN EDUCATIVA</div>' +
    '</div>' +
    '<p style="text-align:justify;line-height:1.45;font-size:12px;margin:16px 0 12px">' +
      'La autoridad del establecimiento educativo, <b>' + esc(d.establecimiento) + '</b> CUE <b>' + esc(d.cue) + '</b>, ubicado en <b>' + esc(d.domicilio) + '</b>, de <b>' + esc(d.localidad) + '</b>, provincia de JUJUY, certifica que <b>' + esc(d.estudianteNombre) + '</b>, con lugar de nacimiento en ' + esc(d.lugarNac) + ', el ' + esc(d.fechaNac) + ', Tipo de Documento ' + esc(d.tipoDoc) + ' Nº <b>' + esc(d.dniFormateado) + '</b>, aprobó los espacios curriculares que con sus respectivas calificaciones a continuación se expresan:' +
    '</p>' +
    '<div style="text-align:center;font-weight:bold;font-size:13px;letter-spacing:1px;margin:14px 0 6px">TRAYECTO CURRICULAR</div>' +
    '<table class="tabla-trayecto">' +
      '<thead><tr>' +
        '<th style="width:28px">N°</th>' +
        '<th>Módulo</th>' +
        '<th style="width:75px">Tipo</th>' +
        '<th style="width:110px">Período</th>' +
        '<th style="width:55px">Hs reloj</th>' +
        '<th style="width:55px">Hs cát.</th>' +
        '<th style="width:40px">Nota</th>' +
        '<th style="width:75px">En letras</th>' +
        '<th style="width:80px">Condición</th>' +
      '</tr></thead>' +
      '<tbody>' +
        filasModulos +
        '<tr style="font-weight:bold">' +
          '<td colspan="4" style="text-align:left;font-weight:bold">Carga horaria total</td>' +
          '<td style="text-align:center">' + d.cargaHorariaTotal.reloj + '</td>' +
          '<td style="text-align:center">' + d.cargaHorariaTotal.cat + '</td>' +
          '<td colspan="3"></td>' +
        '</tr>' +
      '</tbody>' +
    '</table>' +
  '</div>';
}

function armarAnaliticoCeldas(r) {
  var ocultas = {};
  (r.combinadas || []).forEach(function (m) {
    for (var f = m.f; f < m.f + m.nf; f++)
      for (var c = m.c; c < m.c + m.nc; c++)
        if (!(f === m.f && c === m.c)) ocultas[f + ',' + c] = true;
  });
  var span = {};
  (r.combinadas || []).forEach(function (m) { span[m.f + ',' + m.c] = m; });

  var watermark = r.esBorrador
    ? '<div class="marca-agua-borrador-oficial">BORRADOR<br>NO VÁLIDO</div>'
    : '';

  var html = '<div class="hoja-oficial">' + watermark + '<table class="analitico">';
  for (var f = 1; f <= r.celdas.length; f++) {
    var fila = r.celdas[f - 1];
    if (fila.join('').trim() === '') continue;
    html += '<tr>';
    for (var c = 1; c <= fila.length; c++) {
      if (ocultas[f + ',' + c]) continue;
      var m = span[f + ',' + c];
      html += '<td' + (m && m.nc > 1 ? ' colspan="' + m.nc + '"' : '') +
                     (m && m.nf > 1 ? ' rowspan="' + m.nf + '"' : '') + '>' +
              esc(fila[c - 1]) + '</td>';
    }
    html += '</tr>';
  }
  return html + '</table></div>';
}

// =========================================================================
// BANDEJA DE ENTRADA CENTRALIZADA · DEPARTAMENTO DE TÍTULOS (ROL 'titulos')
// =========================================================================

async function verBandejaTitulos() {
  $('migas').hidden = false;
  $('main').innerHTML = '<div class="cargando">Cargando bandeja de pedidos de títulos…</div>';

  try {
    var r = await llamar('/api/solicitudes');
    var solicitudes = r.solicitudes || [];

    var nPendientes = solicitudes.filter(function (s) { return s.estado === 'Pendiente'; }).length;
    var nAprobados = solicitudes.filter(function (s) { return s.estado === 'Aprobado'; }).length;
    var nObservados = solicitudes.filter(function (s) { return s.estado === 'Observado'; }).length;

    var filtradas = solicitudes.filter(function (s) {
      if (estado.filtroBandeja === 'Todos') return true;
      return s.estado === estado.filtroBandeja;
    });

    var filasHtml = filtradas.map(function (s) {
      var badgeClass = 'badge-pendiente';
      if (s.estado === 'Aprobado') badgeClass = 'badge-aprobado';
      else if (s.estado === 'Observado') badgeClass = 'badge-observado';

      var checkHtml = (s.estado !== 'Aprobado')
        ? '<input type="checkbox" class="chk-sol" value="' + esc(s.id) + '">'
        : '<span style="color:#137333">✓</span>';

      var detalleEstado = '';
      if (s.estado === 'Aprobado') {
        detalleEstado = '<div style="color:#137333;font-size:12px;font-weight:bold">Cert. ' + esc(s.numeroCertificado) + ' (' + esc(s.fechaAprobacion) + ')</div>';
      } else if (s.estado === 'Observado') {
        detalleEstado = '<div class="alerta-observacion"><b>Motivo:</b> ' + esc(s.motivoObservacion) + '</div>';
      }

      var accionesHtml = '';
      if (s.estado !== 'Aprobado') {
        accionesHtml =
          '<button class="boton" style="padding:4px 10px;font-size:12px" onclick="abrirModalAprobar(\'' + esc(s.id) + '\', \'' + esc(s.estudiante) + '\')">Aprobar</button> ' +
          '<button class="boton suave" style="padding:4px 10px;font-size:12px;color:var(--mal);border-color:var(--mal)" onclick="abrirModalObservar(\'' + esc(s.id) + '\', \'' + esc(s.estudiante) + '\')">Observar</button>';
      } else {
        accionesHtml = '<span style="color:var(--suave);font-size:12px">Calificaciones congeladas</span>';
      }

      return '<tr>' +
        '<td style="text-align:center">' + checkHtml + '</td>' +
        '<td><b>' + esc(s.institucion) + '</b><br><small style="color:var(--suave)">CUE ' + esc(s.cue) + '</small></td>' +
        '<td>' + esc(s.oferta) + '<br><small style="color:var(--suave)">' + esc(s.ciclo) + '</small></td>' +
        '<td><b>' + esc(s.estudiante) + '</b><br><small>DNI ' + esc(s.documento) + '</small></td>' +
        '<td style="text-align:center;font-size:12px">' + esc(s.fechaSolicitud) + '</td>' +
        '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(s.estado) + '</span>' + detalleEstado + '</td>' +
        '<td style="text-align:center">' +
          accionesHtml +
          ' <button class="boton suave" style="padding:4px 8px;font-size:12px" onclick="inspeccionarAnaliticoModal(\'' + esc(s.idCurso) + '\', \'' + esc(s.documento) + '\')">Ver Analítico</button>' +
        '</td>' +
      '</tr>';
    }).join('');

    $('main').innerHTML =
      '<h1>Bandeja de Entrada · Departamento de Títulos</h1>' +
      '<p style="color:var(--suave)">Gestión, revisión centralizada y emisión de certificados de Formación Profesional.</p>' +

      '<div style="display:flex;gap:12px;margin:16px 0;flex-wrap:wrap">' +
        '<button class="boton ' + (estado.filtroBandeja === 'Pendiente' ? '' : 'suave') + '" id="f_pen">Pendientes (' + nPendientes + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Observado' ? '' : 'suave') + '" id="f_obs">Observados (' + nObservados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Aprobado' ? '' : 'suave') + '" id="f_apr">Aprobados (' + nAprobados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Todos' ? '' : 'suave') + '" id="f_tod">Todos (' + solicitudes.length + ')</button>' +
      '</div>' +

      '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px">' +
        '<label style="display:flex;align-items:center;gap:6px;font-weight:600">' +
          '<input type="checkbox" id="chkTodos"> Seleccionar todos' +
        '</label>' +
        '<button class="boton" id="btnAprobarLote" disabled>Aprobar seleccionados en lote</button>' +
      '</div>' +

      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:36px;text-align:center">✓</th>' +
        '<th>Institución</th><th>Curso</th><th>Estudiante</th>' +
        '<th style="width:130px;text-align:center">Fecha Pedido</th>' +
        '<th style="width:130px;text-align:center">Estado</th>' +
        '<th style="width:230px;text-align:center">Acciones</th>' +
      '</tr></thead><tbody>' + (filasHtml || '<tr><td colspan="7" class="vacio">No hay pedidos en esta sección.</td></tr>') + '</tbody></table></div>';

    $('f_pen').addEventListener('click', function () { estado.filtroBandeja = 'Pendiente'; verBandejaTitulos(); });
    $('f_obs').addEventListener('click', function () { estado.filtroBandeja = 'Observado'; verBandejaTitulos(); });
    $('f_apr').addEventListener('click', function () { estado.filtroBandeja = 'Aprobado'; verBandejaTitulos(); });
    $('f_tod').addEventListener('click', function () { estado.filtroBandeja = 'Todos'; verBandejaTitulos(); });

    var chkTodos = $('chkTodos');
    var chks = document.querySelectorAll('.chk-sol');
    chkTodos.addEventListener('change', function () {
      chks.forEach(function (c) { c.checked = chkTodos.checked; });
      actualizarBotonLote();
    });

    chks.forEach(function (c) {
      c.addEventListener('change', actualizarBotonLote);
    });

    function actualizarBotonLote() {
      var seleccionados = Array.from(document.querySelectorAll('.chk-sol:checked'));
      var btn = $('btnAprobarLote');
      btn.disabled = seleccionados.length === 0;
      btn.textContent = 'Aprobar seleccionados en lote (' + seleccionados.length + ')';
    }

    $('btnAprobarLote').addEventListener('click', async function () {
      var ids = Array.from(document.querySelectorAll('.chk-sol:checked')).map(function (c) { return c.value; });
      if (!ids.length) return;
      if (!confirm('¿Confirma la aprobación en lote de ' + ids.length + ' certificado(s)? Se generarán números correlativos oficiales y las notas quedarán congeladas.')) {
        return;
      }
      avisar('Aprobando en lote…');
      try {
        var res = await llamar('/api/solicitudes/aprobar-lote', 'POST', { ids: ids });
        avisar('¡Se aprobaron ' + res.cantidad + ' certificados con éxito!', 'ok');
        verBandejaTitulos();
      } catch (err) {
        problema(err);
      }
    });

  } catch (e) {
    problema(e);
  }
}

// Modales para Aprobar y Observar
function abrirModalAprobar(idSol, nombre) {
  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja">' +
      '<h2>Aprobar Certificado Oficial</h2>' +
      '<p>Estudiante: <b>' + esc(nombre) + '</b></p>' +
      '<p style="font-size:12px;color:var(--suave)">Al aprobar, se genera el número oficial y las notas del estudiante quedan bloqueadas permanentemente.</p>' +
      '<label style="display:block;margin:12px 0">' +
        'Número de Certificado (dejar vacío para correlativo automático):' +
        '<input id="m_numCert" style="width:100%;margin-top:6px" placeholder="Ej: 38-00041285-2026">' +
      '</label>' +
      '<div class="acciones" style="justify-content:flex-end">' +
        '<button class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button class="boton" id="btnConfirmarAprobar">Aprobar y Congelar Notas</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  $('btnConfirmarAprobar').addEventListener('click', async function () {
    var num = $('m_numCert').value.trim();
    cerrarModal();
    avisar('Aprobando certificado…');
    try {
      await llamar('/api/solicitudes/' + encodeURIComponent(idSol) + '/aprobar', 'POST', { numeroCertificado: num });
      avisar('¡Certificado aprobado exitosamente!', 'ok');
      verBandejaTitulos();
    } catch (e) {
      problema(e);
    }
  });
}

function abrirModalObservar(idSol, nombre) {
  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja">' +
      '<h2>Observar Solicitud de Certificado</h2>' +
      '<p>Estudiante: <b>' + esc(nombre) + '</b></p>' +
      '<p style="font-size:12px;color:var(--mal)">El motivo de observación es obligatorio. La escuela verá este texto para realizar las correcciones necesarias.</p>' +
      '<label style="display:block;margin:12px 0">' +
        '<b>Motivo de observación (Obligatorio):</b>' +
        '<textarea id="m_motivo" rows="4" style="width:100%;margin-top:6px;border:1px solid var(--borde);padding:8px" placeholder="Escriba detalladamente el motivo del rechazo u observación…"></textarea>' +
      '</label>' +
      '<div class="acciones" style="justify-content:flex-end">' +
        '<button class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button class="boton" style="background:var(--mal)" id="btnConfirmarObservar">Confirmar Observación</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);

  $('btnConfirmarObservar').addEventListener('click', async function () {
    var motivo = $('m_motivo').value.trim();
    if (!motivo) {
      alert('Debes ingresar un motivo de observación obligatorio.');
      return;
    }
    cerrarModal();
    avisar('Registrando observación…');
    try {
      await llamar('/api/solicitudes/' + encodeURIComponent(idSol) + '/observar', 'POST', { motivo: motivo });
      avisar('Solicitud observada y devuelta a la escuela.', 'ok');
      verBandejaTitulos();
    } catch (e) {
      problema(e);
    }
  });
}

function cerrarModal() {
  var m = $('modalActivo');
  if (m) m.remove();
}

async function inspeccionarAnaliticoModal(idCurso, doc) {
  avisar('Generando analítico de inspección…');
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(idCurso) + '/analitico?documento=' + encodeURIComponent(doc));
    var modal = document.createElement('div');
    modal.className = 'modal-backdrop';
    modal.id = 'modalActivo';
    modal.innerHTML =
      '<div class="modal-caja" style="max-width:850px;max-height:85vh;overflow:auto">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">' +
          '<h2>Inspección de Analítico</h2>' +
          '<button class="boton suave" onclick="cerrarModal()">Cerrar</button>' +
        '</div>' +
        armarAnalitico(r.analitico) +
      '</div>';
    document.body.appendChild(modal);
  } catch (e) {
    problema(e);
  }
}

// Modal para crear curso
function mostrarModalNuevoCurso() {
  var modal = document.createElement('div');
  modal.className = 'panel';
  modal.style.maxWidth = '550px';
  modal.style.margin = '20px auto';
  modal.style.border = '1px solid var(--borde)';
  modal.style.borderRadius = '8px';
  modal.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';

  modal.innerHTML =
    '<h2>+ Registrar Nuevo Curso</h2>' +
    '<div style="display:flex;flex-direction:column;gap:10px;margin-top:12px">' +
      '<label>Institución <input id="nc_inst" placeholder="Ej: Escuela Profesional Nº 6" value="Escuela Profesional Nº 6"></label>' +
      '<label>CUE <input id="nc_cue" placeholder="Ej: 3800006" value="3800006"></label>' +
      '<label>Oferta Formativa <input id="nc_oferta" placeholder="Ej: Peluquero" value="Peluquero"></label>' +
      '<label>Ciclo <input id="nc_ciclo" placeholder="2026" value="2026"></label>' +
      '<label>Turno <select id="nc_turno"><option>Vespertino</option><option>Mañana</option><option>Tarde</option><option>Noche</option></select></label>' +
      '<label>Curso / División <input id="nc_division" placeholder=\'1º "U"\' value=\'1º "U"\'></label>' +
      '<label>ID del archivo de Google Drive <input id="nc_id" placeholder="ID de la planilla de Google Drive"></label>' +
      '<div class="acciones" style="justify-content:flex-end;margin-top:14px">' +
        '<button class="boton suave" id="nc_cancelar">Cancelar</button>' +
        '<button class="boton" id="nc_guardar">Guardar curso</button>' +
      '</div>' +
    '</div>';

  $('main').innerHTML = '';
  $('main').appendChild(modal);

  $('nc_cancelar').addEventListener('click', verCursos);
  $('nc_guardar').addEventListener('click', function () {
    var nuevo = {
      cue: $('nc_cue').value.trim(),
      institucion: $('nc_inst').value.trim(),
      oferta: $('nc_oferta').value.trim(),
      ciclo: $('nc_ciclo').value.trim(),
      turno: $('nc_turno').value,
      division: $('nc_division').value.trim(),
      id: $('nc_id').value.trim() || ('curso-' + Date.now()),
      estado: 'Abierto'
    };
    estado.cursos.push(nuevo);
    avisar('Curso registrado con éxito', 'ok');
    verCursos();
  });
}

// ---------- RESUMEN DIRECCIÓN DETP ----------
async function verResumen() {
  $('main').innerHTML = '<div class="cargando">Calculando el resumen por institución…</div>';
  $('migas').hidden = false;
  try {
    var r = await llamar('/api/resumen');
    var lista = r.resumen || [];
    var tot = lista.reduce(function (a, i) {
      return {
        cursos: a.cursos + i.cursos,
        estudiantes: a.estudiantes + i.estudiantes,
        aprobados: a.aprobados + i.aprobados
      };
    }, { cursos: 0, estudiantes: 0, aprobados: 0 });

    $('main').innerHTML = '<h1>Resumen por institución</h1>' +
      '<p style="color:var(--suave)">' + tot.cursos + ' cursos · ' + tot.estudiantes +
      ' estudiantes · ' + tot.aprobados + ' con todos los módulos aprobados.</p>' +
      '<table><thead><tr><th>CUE</th><th>Institución</th><th>Cursos</th>' +
      '<th>Estudiantes</th><th>Aprobaron todo</th></tr></thead><tbody>' +
      lista.map(function (i) {
        return '<tr><td>' + esc(i.cue) + '</td><td>' + esc(i.institucion) + '</td>' +
          '<td style="text-align:center">' + i.cursos + '</td>' +
          '<td style="text-align:center">' + i.estudiantes + '</td>' +
          '<td style="text-align:center">' + i.aprobados + '</td></tr>';
      }).join('') + '</tbody></table>';
  } catch (err) {
    problema(err);
  }
}
