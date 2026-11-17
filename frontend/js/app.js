/**
 * Cliente SPA para Libro Matriz FP · DETP Jujuy
 * Migrado desde Cliente.html con soporte para el circuito oficial de emisión de certificados
 * y bandeja de entrada centralizada del rol 'titulos'.
 */

var estado = {
  sesion: null,
  institucionUsuario: null,
  cursos: [],
  curso: null,
  datos: null,
  pestania: localStorage.getItem('lm_pestania') || 'notas',
  emailActual: localStorage.getItem('lm_email') || 'sge.detp.areapedagogica@jujuy.edu.ar',
  filtroBandeja: localStorage.getItem('lm_filtro_bandeja') || 'Pendiente',
  filtroNomina: localStorage.getItem('lm_filtro_nomina') || 'todos',
  vistaActual: localStorage.getItem('lm_vista') || ''
};

var $ = function (id) { return document.getElementById(id); };

function _guardarRutaLocal(vista, cursoId, pestania) {
  estado.vistaActual = vista || '';
  try {
    localStorage.setItem('lm_vista', vista || '');
    localStorage.setItem('lm_curso_id', cursoId || '');
    if (pestania !== undefined) {
      localStorage.setItem('lm_pestania', pestania || 'notas');
    }
  } catch (e) {}
}

function _fmtFechaCorta(val) {
  var s = String(val || '').trim();
  if (!s) return '';
  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return m[3] + '/' + m[2] + '/' + m[1];
  return s;
}

function _estadoAcademicoEstudiante(es) {
  if (!es) return 'AUSENTE';
  var notas = Array.isArray(es.notas) ? es.notas : [];
  var tieneDesaprobado = false;
  var tieneAusenteOVacio = false;
  var cantCargadas = 0;

  for (var i = 0; i < notas.length; i++) {
    var v = String(notas[i] == null ? '' : notas[i]).trim().toUpperCase();
    if (!v) {
      tieneAusenteOVacio = true;
      continue;
    }
    cantCargadas++;
    if (v === 'AUS' || v === 'AUSENTE') {
      tieneAusenteOVacio = true;
    } else {
      var n = parseFloat(v.replace(',', '.'));
      if (!isNaN(n) && n < 7) {
        tieneDesaprobado = true;
      }
    }
  }

  var nf = String(es.notaFinal == null ? '' : es.notaFinal).trim().toUpperCase();
  if (nf === 'AUS' || nf === 'AUSENTE') {
    if (tieneDesaprobado) return 'DESAPROBADO';
    return 'AUSENTE';
  }
  if (nf !== '') {
    var numNf = parseFloat(nf.replace(',', '.'));
    if (!isNaN(numNf)) {
      if (numNf < 7 || tieneDesaprobado) return 'DESAPROBADO';
      if (!tieneAusenteOVacio && cantCargadas > 0) return 'APROBADO';
    }
  }

  if (tieneDesaprobado) return 'DESAPROBADO';
  if (cantCargadas === 0 || tieneAusenteOVacio || nf === '') return 'AUSENTE';
  return 'APROBADO';
}

function _esEstudianteElegibleTitulos(es) {
  return _estadoAcademicoEstudiante(es) === 'APROBADO';
}

function _obtenerPaquetesLocales() {
  try {
    var raw = localStorage.getItem('lm_paquetes_cursos_v1');
    return raw ? (JSON.parse(raw) || {}) : {};
  } catch (e) {
    return {};
  }
}

function _guardarPaqueteLocal(paquete) {
  if (!paquete || !paquete.resumenCurso || !paquete.resumenCurso.id) return;
  try {
    var paqs = _obtenerPaquetesLocales();
    paqs[paquete.resumenCurso.id] = paquete;
    localStorage.setItem('lm_paquetes_cursos_v1', JSON.stringify(paqs));
  } catch (e) {
    console.warn('No se pudo persistir el curso en localStorage:', e);
  }
}

function _actualizarBarraEscuela(nombreEscuela) {
  var el = $('barraEscuela');
  if (!el) return;
  if (nombreEscuela) {
    el.textContent = nombreEscuela;
    return;
  }
  if (estado.datos && estado.datos.encabezado && estado.datos.encabezado.establecimiento) {
    var enc = estado.datos.encabezado;
    el.textContent = enc.establecimiento + (enc.localidad ? ' · ' + enc.localidad + ', Jujuy' : '');
    return;
  }
  if (estado.institucionUsuario && estado.institucionUsuario.nombre) {
    el.textContent = estado.institucionUsuario.nombre + (estado.institucionUsuario.localidad ? ' · ' + estado.institucionUsuario.localidad + ', Jujuy' : '');
    return;
  }
  if (estado.sesion && estado.sesion.esTitulos) {
    el.textContent = 'Dirección de Títulos · Todas las Instituciones';
    return;
  }
  if (estado.sesion && estado.sesion.verTodo) {
    el.textContent = 'Dirección de Educación Técnico Profesional · Todas las Instituciones';
    return;
  }
  if (estado.cursos && estado.cursos.length) {
    var ult = estado.cursos[estado.cursos.length - 1];
    el.textContent = ult.institucion || 'Escuela Profesional Nº 6';
    return;
  }
  el.textContent = 'Escuela Profesional Nº 6';
}

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
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escJsArg(t) {
  return esc(JSON.stringify(String(t == null ? '' : t)));
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
  if ($('btnTopDashboard')) {
    $('btnTopDashboard').addEventListener('click', function () {
      if (estado.sesion && (estado.sesion.verTodo || estado.sesion.esTitulos)) {
        verResumen();
      }
    });
  }
  if ($('btnTopImportar')) {
    $('btnTopImportar').addEventListener('click', mostrarModalImportarExcel);
  }
  if ($('btnTopUsuarios')) {
    $('btnTopUsuarios').addEventListener('click', async function () {
      if (!estado.sesion || !estado.sesion.puedeAdministrarUsuarios) {
        estado.emailActual = 'sge.detp.areapedagogica@jujuy.edu.ar';
        localStorage.setItem('lm_email', estado.emailActual);
        await cargarUsuariosPrueba();
        await iniciarSesion();
      }
      verAdminUsuarios();
    });
  }
  await cargarUsuariosPrueba();
  await iniciarSesion();
});

async function cargarUsuariosPrueba() {
  try {
    var res = await llamar('/api/usuarios');
    var listaU = res.usuarios || [];
    var existe = listaU.some(function (u) {
      return u.Email.toLowerCase() === (estado.emailActual || '').toLowerCase();
    });
    if (!existe && listaU.length > 0) {
      estado.emailActual = listaU[0].Email;
      localStorage.setItem('lm_email', estado.emailActual);
    }
    var select = $('selectorUsuario');
    select.innerHTML = '<option value="">-- Cambiar Usuario / Rol (Pruebas) --</option>';
    listaU.forEach(function (u) {
      var opt = document.createElement('option');
      opt.value = u.Email;
      opt.textContent = (u.Nombre || u.Email) + ' [' + u.Rol + ']';
      if (u.Email.toLowerCase() === (estado.emailActual || '').toLowerCase()) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    select.onchange = function () {
      if (select.value) {
        estado.emailActual = select.value;
        localStorage.setItem('lm_email', select.value);
        _guardarRutaLocal('', '', 'notas');
        iniciarSesion();
      }
    };
  } catch (err) {
    console.warn('No se pudo cargar la lista de usuarios para prueba:', err);
  }
}

async function iniciarSesion() {
  $('main').innerHTML = '<div class="cargando">Iniciando sesión…</div>';
  try {
    var paqsLocales = _obtenerPaquetesLocales();
    var r = await llamar('/api/inicio');
    var cuesUsuario = (r.sesion && r.sesion.cues) ? r.sesion.cues : [];
    function _alcanzaCueCliente(cueCurso) {
      if (r.sesion && (r.sesion.verTodo || r.sesion.esTitulos)) return true;
      var cLimpio = String(cueCurso || '').replace(/\D/g, '');
      if (!cLimpio) return false;
      var cBase = cLimpio.length >= 7 ? cLimpio.slice(0, 7) : cLimpio;
      return cuesUsuario.some(function (cu) {
        var uLimpio = String(cu || '').replace(/\D/g, '');
        var uBase = uLimpio.length >= 7 ? uLimpio.slice(0, 7) : uLimpio;
        return cLimpio === uLimpio || (cBase && cBase === uBase);
      });
    }

    var paqsPermitidos = {};
    Object.keys(paqsLocales).forEach(function (idLocal) {
      var p = paqsLocales[idLocal];
      if (p && p.resumenCurso && p.resumenCurso.id && _alcanzaCueCliente(p.resumenCurso.cue)) {
        paqsPermitidos[idLocal] = p;
      }
    });

    if (r.sesion && (r.sesion.puedeCargar || r.sesion.verTodo || r.sesion.esTitulos) && Object.keys(paqsPermitidos).length > 0) {
      try {
        var rSync = await llamar('/api/sincronizar-cursos', 'POST', { paquetes: paqsPermitidos });
        if (rSync && rSync.restaurados > 0) {
          r = await llamar('/api/inicio');
        }
      } catch (errSync) {
        console.warn('No se pudo sincronizar cursos locales:', errSync);
      }
    }

    estado.sesion = r.sesion;
    estado.institucionUsuario = r.institucionUsuario || null;
    var esDirTitulos = Boolean(r.sesion && r.sesion.esDirectoraTitulos);
    if ($('btnTopImportar')) {
      $('btnTopImportar').hidden = esDirTitulos || !(r.sesion.puedeCargar || r.sesion.verTodo || r.sesion.esTitulos);
    }
    if ($('btnTopUsuarios')) {
      $('btnTopUsuarios').hidden = !r.sesion.puedeAdministrarUsuarios;
    }
    if ($('btnTopDashboard')) {
      $('btnTopDashboard').hidden = !(r.sesion.verTodo || r.sesion.esTitulos || r.sesion.puedeVerDashboard || r.sesion.rol === 'Directivo');
    }
    var cursosServidor = r.cursos || [];
    var idsPresentes = {};
    cursosServidor.forEach(function (c) { if (c && c.id) idsPresentes[c.id] = true; });
    Object.keys(paqsPermitidos).forEach(function (idLocal) {
      var p = paqsPermitidos[idLocal];
      if (p && p.resumenCurso && p.resumenCurso.id && !idsPresentes[p.resumenCurso.id]) {
        cursosServidor.push(p.resumenCurso);
        idsPresentes[p.resumenCurso.id] = true;
      }
    });
    estado.cursos = cursosServidor;
    estado.emailActual = r.sesion.email;
    _actualizarBarraEscuela();

    $('usuario').innerHTML = '<b>' + esc(r.sesion.nombre) + '</b>' +
      '<span class="rol">' + esc(r.sesion.rol) + '</span>';

    var vistaGuardada = localStorage.getItem('lm_vista') || '';
    var cursoGuardado = localStorage.getItem('lm_curso_id') || '';
    var pestaniaGuardada = localStorage.getItem('lm_pestania') || 'notas';
    var existeCursoGuardado = cursoGuardado && estado.cursos.some(function (c) { return c.id === cursoGuardado; });

    if (esDirTitulos) {
      if (vistaGuardada === 'bandeja') {
        verBandejaTitulos();
      } else if (vistaGuardada === 'nomina') {
        verNominaEscuela();
      } else {
        verResumen();
      }
    } else if (vistaGuardada === 'curso' && existeCursoGuardado) {
      abrirCurso(cursoGuardado, pestaniaGuardada);
    } else if (vistaGuardada === 'nomina') {
      verNominaEscuela(existeCursoGuardado ? cursoGuardado : '');
    } else if (vistaGuardada === 'cursos') {
      verCursos();
    } else if (vistaGuardada === 'bandeja') {
      verBandejaTitulos();
    } else if (vistaGuardada === 'resumen' && (r.sesion.verTodo || r.sesion.esTitulos || r.sesion.puedeVerDashboard || r.sesion.rol === 'Directivo')) {
      verResumen();
    } else if (vistaGuardada === 'usuarios' && r.sesion.puedeAdministrarUsuarios) {
      verAdminUsuarios();
    } else if (r.sesion.esTitulos) {
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
  if (estado.curso) {
    verCursos();
  } else if (estado.sesion && estado.sesion.esTitulos && estado.vistaActual !== 'bandeja') {
    verBandejaTitulos();
  } else {
    verCursos();
  }
});

// ---------- LISTA DE CURSOS (ESCUELAS Y DIRECCIÓN) ----------
function verCursos() {
  estado.curso = null;
  estado.datos = null;
  _guardarRutaLocal('cursos', '', '');
  _actualizarBarraEscuela();
  if (estado.sesion && estado.sesion.esTitulos) {
    $('migas').hidden = false;
    $('volver').textContent = '← Volver a Bandeja de Títulos';
  } else {
    $('migas').hidden = true;
    $('volver').textContent = '← Volver a los cursos';
  }
  var m = $('main');
  var subtitulo = (estado.sesion && estado.sesion.verTodo)
    ? 'Acceso a todas las instituciones · ' + estado.cursos.length + ' curso(s).'
    : 'Acceso a tu institución · ' + estado.cursos.length + ' curso(s).';

  var puedeCargar = Boolean(estado.sesion && estado.sesion.puedeCargar);
  var esTitulos = Boolean(estado.sesion && estado.sesion.esTitulos);

  var aniosSet = { '2026': true, '2025': true, '2024': true };
  (estado.cursos || []).forEach(function (c) {
    var an = String(c.ciclo || '').trim();
    if (an) aniosSet[an] = true;
  });
  var aniosLista = Object.keys(aniosSet).sort().reverse();
  var anioSel = estado.filtroAnioCurso || '';
  var opsAnios = '<option value="">Todos los años</option>' +
    aniosLista.map(function (a) {
      return '<option value="' + esc(a) + '"' + (anioSel === a ? ' selected' : '') + '>Año / Ciclo ' + esc(a) + '</option>';
    }).join('');

  m.innerHTML =
    '<h1>Cursos' + (esTitulos ? ' y RAC' : '') + '</h1>' +
    '<p style="color:var(--suave);margin:0 0 12px">' + subtitulo + '</p>' +
    '<div class="acciones">' +
      (puedeCargar ? '<button class="boton" id="btnNuevoCurso">+ Nuevo curso</button>' : '') +
      ((puedeCargar || estado.sesion.verTodo || esTitulos) ? '<button class="boton" id="btnImportarExcel" style="background:#137333">📥 Importar Viejo Excel</button>' : '') +
      (esTitulos ? '<button class="boton" id="btnTitulos">📥 Bandeja de Títulos</button>' : '<button class="boton suave" id="btnTitulos">Certificados de Títulos</button>') +
      '<button class="boton suave" id="btnNominaEscuela">📋 Nómina de Egresados</button>' +
      ((estado.sesion.verTodo || esTitulos || estado.sesion.puedeVerDashboard || estado.sesion.rol === 'Directivo') ? '<button class="boton suave" id="btnResumen">📊 Dashboard de Estadísticas</button>' : '') +
      (estado.sesion.puedeAdministrarUsuarios ? '<button class="boton suave" id="btnUsuarios">👤 Administrar Usuarios</button>' : '') +
    '</div>' +
    '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px">' +
      '<input class="buscar" id="buscar" style="margin:0;flex:1;min-width:240px" placeholder="Buscar por institución, oferta o CUE…">' +
      '<select class="buscar" id="filtroAnioCurso" style="margin:0;width:auto;min-width:170px;font-weight:600">' + opsAnios + '</select>' +
    '</div>' +
    '<div class="tarjetas" id="lista"></div>';

  if ($('btnNuevoCurso')) $('btnNuevoCurso').addEventListener('click', mostrarModalNuevoCurso);
  if ($('btnImportarExcel')) $('btnImportarExcel').addEventListener('click', mostrarModalImportarExcel);
  if ($('btnResumen')) $('btnResumen').addEventListener('click', verResumen);
  if ($('btnTitulos')) $('btnTitulos').addEventListener('click', verBandejaTitulos);
  if ($('btnNominaEscuela')) $('btnNominaEscuela').addEventListener('click', function () { verNominaEscuela(); });
  if ($('btnUsuarios')) $('btnUsuarios').addEventListener('click', verAdminUsuarios);
  $('buscar').addEventListener('input', pintarLista);
  if ($('filtroAnioCurso')) {
    $('filtroAnioCurso').addEventListener('change', function () {
      estado.filtroAnioCurso = $('filtroAnioCurso').value;
      pintarLista();
    });
  }
  pintarLista();
}

function pintarLista() {
  var q = ($('buscar') ? $('buscar').value : '').toLowerCase().trim();
  var anioFiltro = ($('filtroAnioCurso') ? $('filtroAnioCurso').value : (estado.filtroAnioCurso || '')).trim();
  var cs = estado.cursos.filter(function (c) {
    if (anioFiltro && String(c.ciclo || '').trim() !== anioFiltro) return false;
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
    if (r.paquete) _guardarPaqueteLocal(r.paquete);
    var d = r.datos;
    estado.curso = d.curso;
    estado.datos = d;
    estado.pestania = pestaniaInicial || 'notas';
    _guardarRutaLocal('curso', estado.curso.id, estado.pestania);
    $('migas').hidden = false;
    $('volver').textContent = '← Volver a los cursos';
    pintarCurso();
  } catch (e) {
    problema(e);
    verCursos();
  }
}

function pintarCurso() {
  var d = estado.datos, e = d.encabezado;
  _actualizarBarraEscuela((e.establecimiento || (estado.curso && estado.curso.institucion) || 'Escuela Profesional') + (e.localidad ? ' · ' + e.localidad + ', Jujuy' : ''));
  var hsCatTotal = e.hsCatTotal || 510;
  var refIng = e.referencialIngreso || 'Primaria Completa';
  var famProf = e.familiaProfesional || '—';
  var nivelCurso = e.nivelCurso || 'II';
  var certificacion = e.certificacion || 'Diseño Curricular Jurisdiccional';
  var normaAprob = e.normaAprobacion || '—';
  var resDisenio = e.resolucionDisenio || e.disenio || '—';
  var validezNac = e.validezNacional || '—';
  var disposicion = e.disposicion || '-';
  var cursoAnio = e.cursoAnio || '1°';
  var divLetra = e.divisionLetra || '"U"';
  var fin1cFmt = _fmtFechaCorta(e.fechaFin1C);
  var fin2cFmt = _fmtFechaCorta(e.fechaFin2C);
  var fechasCuatHtml = (fin1cFmt || fin2cFmt)
    ? '<dt>Finalización de Cuatrimestres</dt><dd>' +
        (fin1cFmt ? '<b>1° Cuat.:</b> ' + esc(fin1cFmt) : '') +
        (fin1cFmt && fin2cFmt ? ' &nbsp;·&nbsp; ' : '') +
        (fin2cFmt ? '<b>2° Cuat.:</b> ' + esc(fin2cFmt) : '') +
      '</dd>'
    : '';
  $('main').innerHTML =
    '<h1>' + esc(e.oferta || estado.curso.oferta) + '</h1>' +
    '<dl class="ficha">' +
      '<dt>Establecimiento</dt><dd>' + esc(e.establecimiento) + (e.cue ? ' · CUE ' + esc(e.cue) : '') + (e.domicilio && e.domicilio !== 'S/D' ? ' · ' + esc(e.domicilio) : '') + '</dd>' +
      '<dt>Familia Profesional</dt><dd>' + esc(famProf) + (e.duracion ? ' &nbsp;·&nbsp; <b>Duración:</b> ' + esc(e.duracion) : '') + (e.docente && e.docente !== '—' ? ' &nbsp;·&nbsp; <b>Docente:</b> ' + esc(e.docente) : '') + '</dd>' +
      '<dt>Turno / División</dt><dd><b>Turno:</b> ' + esc(e.turno) + ' &nbsp;·&nbsp; <b>Curso:</b> ' + esc(cursoAnio) + ' &nbsp;·&nbsp; <b>División:</b> ' + esc(divLetra) + ' &nbsp;·&nbsp; Ciclo ' + esc(e.ciclo) +
        ' · ' + d.estudiantes.length + ' estudiantes</dd>' +
      fechasCuatHtml +
      '<dt>Referencial de ingreso</dt><dd><span id="ficha_ref_ingreso">' + esc(refIng) + '</span> &nbsp;·&nbsp; <b>Horas Cátedras:</b> <span id="ficha_hs_cat">' + esc(hsCatTotal) + '</span> &nbsp;·&nbsp; <b>Nivel:</b> ' + esc(nivelCurso) + ' &nbsp;·&nbsp; <b>Certificación:</b> ' + esc(certificacion) + '</dd>' +
      '<dt>Norma Jurisdiccional de Aprobación, Resolución N°</dt><dd>' + esc(normaAprob) + '</dd>' +
      '<dt>Resolución Diseño Curricular y/o Plan de Estudio Jurisdiccional N°</dt><dd>' + esc(resDisenio) + '</dd>' +
      '<dt>Validez Nacional R.M.E N°</dt><dd>' + esc(validezNac) + '</dd>' +
      '<dt>Disposición</dt><dd>' + esc(disposicion) + '</dd>' +
    '</dl>' +
    '<div class="pestanias" role="tablist">' +
      '<button role="tab" data-p="notas">Registro Anual de Calificaciones</button>' +
      '<button role="tab" data-p="acta">Acta de Examen</button>' +
      '<button role="tab" data-p="analitico">Certificado</button>' +
      '<button role="tab" data-p="nomina">Nómina de Egresados</button>' +
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

function _configurarPaginaImpresion(modo) {
  var st = document.getElementById('estiloPaginaImpresion');
  if (!st) {
    st = document.createElement('style');
    st.id = 'estiloPaginaImpresion';
    document.head.appendChild(st);
  }
  if (modo === 'oficio-horizontal') {
    st.textContent = '@media print { @page { size: landscape; margin: 5mm 7mm; } }';
  } else {
    st.textContent = '@media print { @page { size: portrait; margin: 10mm 12mm; } }';
  }
}

var _elementoZoomActivo = null;
function _limpiarZoomImpresion() {
  document.body.classList.remove('modo-medicion-impresion');
  document.body.classList.remove('medicion-vertical');
  if (_elementoZoomActivo) {
    _elementoZoomActivo.style.zoom = '';
    _elementoZoomActivo = null;
  }
}
window.addEventListener('afterprint', _limpiarZoomImpresion);

function _imprimirElementoEnUnaHoja(contenedor, orientacion) {
  _configurarPaginaImpresion(orientacion || 'oficio-horizontal');
  if (!contenedor) {
    window.print();
    return;
  }
  _limpiarZoomImpresion();
  document.body.classList.add('modo-medicion-impresion');
  if (orientacion === 'a4-vertical') {
    document.body.classList.add('medicion-vertical');
  }
  var tablaWrap = contenedor.querySelector('.tabla-ancha');
  var prevMaxH = tablaWrap ? tablaWrap.style.maxHeight : '';
  var prevOverflow = tablaWrap ? tablaWrap.style.overflow : '';
  if (tablaWrap) {
    tablaWrap.style.maxHeight = 'none';
    tablaWrap.style.overflow = 'visible';
  }
  var anchoReal = contenedor.scrollWidth || contenedor.offsetWidth || 1000;
  var altoReal = contenedor.scrollHeight || contenedor.offsetHeight || 700;
  if (tablaWrap) {
    tablaWrap.style.maxHeight = prevMaxH;
    tablaWrap.style.overflow = prevOverflow;
  }
  document.body.classList.remove('modo-medicion-impresion');
  document.body.classList.remove('medicion-vertical');

  // Área imprimible A4 apaisado con márgenes 5mm 7mm (~1040x710 px a 96dpi)
  var maxW = (orientacion === 'a4-vertical') ? 700 : 1040;
  var maxH = (orientacion === 'a4-vertical') ? 1020 : 710;
  var escala = Math.min(1, maxW / Math.max(1, anchoReal), maxH / Math.max(1, altoReal));
  if (escala < 0.45) escala = 0.45;
  if (escala < 0.995) {
    contenedor.style.zoom = escala.toFixed(3);
    _elementoZoomActivo = contenedor;
  }
  window.print();
  setTimeout(_limpiarZoomImpresion, 500);
}

function imprimirRacActual() {
  _imprimirElementoEnUnaHoja($('panel'), 'oficio-horizontal');
}

function imprimirNominaActual() {
  var hoja = document.querySelector('.planilla-nomina') || $('panel') || $('main');
  _imprimirElementoEnUnaHoja(hoja, 'oficio-horizontal');
}

function pintarPestania() {
  if (estado.curso && estado.curso.id) {
    _guardarRutaLocal('curso', estado.curso.id, estado.pestania);
  }
  Array.prototype.forEach.call(document.querySelectorAll('[role=tab]'), function (b) {
    b.setAttribute('aria-selected', b.dataset.p === estado.pestania);
  });
  if (estado.pestania === 'notas') { _configurarPaginaImpresion('oficio-horizontal'); pintarNotas(); }
  else if (estado.pestania === 'acta') { _configurarPaginaImpresion('a4-vertical'); pintarActa(); }
  else if (estado.pestania === 'analitico') { _configurarPaginaImpresion('a4-vertical'); pintarAnalitico(); }
  else if (estado.pestania === 'nomina') { _configurarPaginaImpresion('oficio-horizontal'); pintarNominaCurso(); }
  else if (estado.pestania === 'solicitudes') { _configurarPaginaImpresion('a4-vertical'); pintarSolicitudesCurso(); }
}

// ---------- PESTAÑA: REGISTRO ANUAL DE CALIFICACIONES (CON CONGELAMIENTO) ----------
// Regla: nota >= 7 → Aprobado | nota < 7 → Desaprobado | AUS → Ausente
function notaCondicion(val) {
  if (!val || val === '') return '';
  var v = String(val).trim().toUpperCase();
  if (v === 'AUS' || v === 'AUSENTE') return 'Ausente';
  var n = parseFloat(v);
  if (isNaN(n)) return '';
  return n >= 7 ? 'Aprobado' : 'Desaprobado';
}

function _etiquetaCuatrimestre(m) {
  var p = String(m.periodo || '').toLowerCase();
  if (m.cuatrimestre === 2 || p.indexOf('2') !== -1) return '2° Cuatrimestre';
  if (m.cuatrimestre === 3 || p.indexOf('3') !== -1) return '3° Cuatrimestre';
  if (p.indexOf('unico') !== -1 || p.indexOf('único') !== -1) return 'Cuatrimestre único';
  return '1° Cuatrimestre';
}

function _etiquetaCortaCuat(m) {
  var c = _etiquetaCuatrimestre(m);
  if (c.indexOf('2°') === 0) return '2°C';
  if (c.indexOf('3°') === 0) return '3°C';
  return '1°C';
}

function pintarNotas() {
  var d = estado.datos, editable = d.puedeCargar;
  if (!d.estudiantes.length) {
    $('panel').innerHTML =
      '<div class="vacio">' +
        '<p>El curso todavía no tiene estudiantes cargados en la pestaña RAC.</p>' +
        (editable
          ? '<button class="boton" style="margin-top:10px;background:#137333" onclick="mostrarModalNuevoEstudiante()">+ Agregar Alumno</button>'
          : '') +
      '</div>';
    return;
  }

  var filtroCuat = estado.filtroCuatrimestre || 'Todos';
  var cuatrimestresDisponibles = [];
  d.modulos.forEach(function (m) {
    var et = _etiquetaCuatrimestre(m);
    if (cuatrimestresDisponibles.indexOf(et) === -1) cuatrimestresDisponibles.push(et);
  });

  var modulosVisibles = d.modulos.filter(function (m) {
    if (filtroCuat === 'Todos') return true;
    return _etiquetaCuatrimestre(m) === filtroCuat;
  });
  if (!modulosVisibles.length) {
    modulosVisibles = d.modulos;
    filtroCuat = 'Todos';
  }

  var enc = d.encabezado || {};
  var fin1C = _fmtFechaCorta(enc.fechaFin1C);
  var fin2C = _fmtFechaCorta(enc.fechaFin2C);
  var esTitulos = Boolean(estado.sesion && estado.sesion.esTitulos);

  // Agrupar módulos visibles por cuatrimestre para la fila superior del encabezado
  var gruposCuat = [];
  modulosVisibles.forEach(function (m) {
    var et = _etiquetaCuatrimestre(m);
    if (!gruposCuat.length || gruposCuat[gruposCuat.length - 1].nombre !== et) {
      gruposCuat.push({ nombre: et, cantidad: 1 });
    } else {
      gruposCuat[gruposCuat.length - 1].cantidad++;
    }
  });

  var thGrupos = gruposCuat.map(function (g) {
    var bg = g.nombre.indexOf('2°') === 0 ? '#d9ead3' : (g.nombre.indexOf('3°') === 0 ? '#fce5cd' : '#cfe2f3');
    var colorTxt = g.nombre.indexOf('2°') === 0 ? '#135c2d' : '#1F4E78';
    var fechaSub = (g.nombre.indexOf('2°') === 0 || g.nombre.indexOf('3°') === 0) ? fin2C : fin1C;
    var etiquetaGrupo = fechaSub ? (g.nombre + ' (Fin: ' + fechaSub + ')') : g.nombre;
    return '<th colspan="' + g.cantidad + '" style="text-align:center;background:' + bg + ';color:' + colorTxt + ';font-size:11px;letter-spacing:0.3px;border-bottom:2px solid ' + colorTxt + '">' +
           esc(etiquetaGrupo) + '</th>';
  }).join('');

  var totalHsCatCurso = 0;
  d.modulos.forEach(function (m) {
    var hc = parseInt(m.hsCat, 10);
    if (isNaN(hc)) {
      var hr = parseInt(m.hsReloj, 10) || (m.tipo === 'Común' ? 32 : 96);
      hc = Math.round(hr * 1.5);
    }
    totalHsCatCurso += hc;
  });

  var th = modulosVisibles.map(function (m) {
    return '<th class="mod" title="' + esc(m.nombre) + ' (' + esc(_etiquetaCuatrimestre(m)) + ')"><div class="mod-txt">' +
           esc(m.nombre) + '</div></th>';
  }).join('');

  var refIngresoActual = enc.referencialIngreso || 'Primaria Completa';
  var acreditaConActual = enc.acreditaCon || 'Primaria Completa';
  var hsCatActual = enc.hsCatTotal || totalHsCatCurso || 510;
  var ofertaCursoActual = enc.oferta || (estado.curso && estado.curso.oferta) || '';
  var listaOpcionesRef = obtenerOpcionesReferencialIngreso(ofertaCursoActual);
  var listaOpcionesAcred = obtenerOpcionesAcreditacion(ofertaCursoActual);

  var tieneDosCuat = cuatrimestresDisponibles.indexOf('1° Cuatrimestre') !== -1 &&
                     cuatrimestresDisponibles.indexOf('2° Cuatrimestre') !== -1;

  var hayCongelados = false;
  var cantElegiblesSinAprobar = 0;
  var filas = d.estudiantes.map(function (es) {
    if (es.notasCongeladas) hayCongelados = true;
    var bloqueado = !editable || es.notasCongeladas;

    // Calcular promedios de 1°C, 2°C y Nota final si corresponde
    var suma1 = 0, cnt1 = 0, suma2 = 0, cnt2 = 0, sumaTot = 0, cntTot = 0;
    d.modulos.forEach(function (m, idxAll) {
      var valStr = es.notas[idxAll];
      var num = parseFloat(valStr);
      if (!isNaN(num)) {
        sumaTot += num;
        cntTot++;
        var et = _etiquetaCuatrimestre(m);
        if (et.indexOf('2°') === 0) { suma2 += num; cnt2++; }
        else { suma1 += num; cnt1++; }
      }
    });
    var prom1C = cnt1 ? Math.round(suma1 / cnt1) : '—';
    var prom2C = cnt2 ? Math.round(suma2 / cnt2) : '—';
    // La Calificación Final, Libro Actas N°, Folio N° y Fecha del RAC se alimentan desde el Acta de Examen
    var notaFinal = es.notaFinal || '';

    var celdas = modulosVisibles.map(function (m) {
      var idxReal = m.i;
      var n = (es.notas && idxReal < es.notas.length) ? es.notas[idxReal] : '';
      var cond = notaCondicion(n);
      var color = cond === 'Aprobado' ? '#137333' : cond === 'Desaprobado' ? '#b3261e' : '';
      var estilo = color ? 'style="text-align:center;color:' + color + ';font-weight:bold"' : 'style="text-align:center"';
      if (bloqueado) {
        return '<td class="nota" ' + estilo + '><input value="' + esc(n) + '" disabled ' +
               'title="' + (es.notasCongeladas ? '🔒 Calificaciones congeladas por certificado oficial aprobado' : '') + '"></td>';
      }
      return '<td class="nota" ' + estilo + '><input value="' + esc(n) + '" maxlength="3" ' +
             'data-fila="' + es.fila + '" data-mod="' + idxReal + '"></td>';
    }).join('');

    var candado = es.notasCongeladas ? ' <span title="Certificado Aprobado - Notas Congeladas">🔒</span>' : '';
    var celdasPromCuat = '';
    if (tieneDosCuat && filtroCuat === 'Todos') {
      celdasPromCuat =
        '<td style="text-align:center;background:#f4f8fc;font-weight:600;color:#1F4E78">' + esc(prom1C) + '</td>' +
        '<td style="text-align:center;background:#f3faf5;font-weight:600;color:#135c2d">' + esc(prom2C) + '</td>';
    }

    var acreditaEst = es.acreditaCon || es.nivel || acreditaConActual;
    var celdaAcreditaHtml = esc(acreditaEst);
    if (!bloqueado) {
      var opsEst = listaOpcionesAcred.slice();
      if (acreditaEst && opsEst.indexOf(acreditaEst) === -1) opsEst.unshift(acreditaEst);
      celdaAcreditaHtml =
        '<select class="sel-acredita-est" data-fila="' + es.fila + '" style="font-size:11px;padding:2px 4px;max-width:130px">' +
          opsEst.map(function (op) {
            var sel = String(op).toLowerCase() === String(acreditaEst).toLowerCase() ? ' selected' : '';
            return '<option value="' + esc(op) + '"' + sel + '>' + esc(op) + '</option>';
          }).join('') +
        '</select>';
    }
    var libroActaEst = notaFinal ? (es.libroActa || enc.libro || '1') : '—';
    var folioEst = notaFinal ? (es.folio || enc.folio || '1') : '—';
    var fechaEst = notaFinal ? (es.fechaEgreso || enc.fechaActa || '—') : '—';

    var celdaTitulosHtml = '';
    if (esTitulos) {
      var solEst = es.solicitudCertificado || {};
      var estCert = solEst.estado || 'No solicitado';
      var condAcadRac = _estadoAcademicoEstudiante(es);
      if (estCert === 'Aprobado') {
        celdaTitulosHtml = '<td class="no-imprimir" style="text-align:center;white-space:nowrap">' +
          '<span class="badge-estado badge-aprobado" title="Certificado Emitido: ' + esc(solEst.numeroCertificado || '') + '">APROBADO</span></td>';
      } else if (condAcadRac === 'APROBADO') {
        cantElegiblesSinAprobar++;
        celdaTitulosHtml = '<td class="no-imprimir" style="text-align:center;white-space:nowrap">' +
          '<span class="badge-estado badge-aprobado" style="cursor:pointer" title="Clic para aprobar certificado oficial" onclick="aprobarTitulosCurso([' + escJsArg(es.documento) + '], \'notas\')">APROBADO</span></td>';
      } else if (condAcadRac === 'DESAPROBADO') {
        celdaTitulosHtml = '<td class="no-imprimir" style="text-align:center;white-space:nowrap"><span class="badge-estado badge-observado">DESAPROBADO</span></td>';
      } else {
        celdaTitulosHtml = '<td class="no-imprimir" style="text-align:center;white-space:nowrap"><span class="badge-estado badge-no-solicitado">AUSENTE</span></td>';
      }
    }

    return '<tr><td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td class="col-nombre-est">' + esc(es.apellido) + ', ' + esc(es.nombres) + candado + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      '<td style="text-align:center">' + esc(es.fechaNac || '—') + '</td>' +
      '<td style="text-align:center">' + esc(es.provincia || 'Jujuy') + '</td>' +
      '<td style="text-align:center">' + esc(es.pais || 'Argentina') + '</td>' +
      '<td class="celda-acredita-rac" style="text-align:center">' + celdaAcreditaHtml + '</td>' +
      celdas +
      celdasPromCuat +
      '<td style="text-align:center;font-weight:bold;background:#fafafa">' + esc(notaFinal) + '</td>' +
      '<td style="text-align:center">' + esc(libroActaEst) + '</td>' +
      '<td style="text-align:center">' + esc(folioEst) + '</td>' +
      '<td style="text-align:center">' + esc(fechaEst) + '</td>' +
      celdaTitulosHtml +
    '</tr>';
  }).join('');

  var barraFiltroCuat = '';
  if (cuatrimestresDisponibles.length > 1) {
    barraFiltroCuat =
      '<div class="no-imprimir" style="display:flex;gap:8px;align-items:center;margin:8px 0 12px;flex-wrap:wrap">' +
        '<span style="font-size:12px;font-weight:600;color:var(--suave)">Ver período:</span>' +
        '<button type="button" class="boton ' + (filtroCuat === 'Todos' ? '' : 'suave') + '" style="padding:4px 12px;font-size:12px" data-cuat="Todos">Todos (' + d.modulos.length + ' módulos)</button>' +
        cuatrimestresDisponibles.map(function (c) {
          var activo = filtroCuat === c;
          return '<button type="button" class="boton ' + (activo ? '' : 'suave') + '" style="padding:4px 12px;font-size:12px" data-cuat="' + esc(c) + '">' + esc(c) + '</button>';
        }).join('') +
      '</div>';
  }

  var colsExtraFinal = (tieneDosCuat && filtroCuat === 'Todos') ? 6 : 4;
  var thGrupoProm = '<th colspan="' + colsExtraFinal + '" style="text-align:center;background:#e9eef4">CALIFICACIÓN Y CERTIFICACIÓN</th>';
  var thExtraFinal = (tieneDosCuat && filtroCuat === 'Todos')
    ? '<th class="mod" style="background:#e8f1fa"><div class="mod-txt">Prom. 1° Cuat.</div></th>' +
      '<th class="mod" style="background:#e6f4ea"><div class="mod-txt">Prom. 2° Cuat.</div></th>' +
      '<th class="mod"><div class="mod-txt">Calificación Final</div></th>' +
      '<th class="mod"><div class="mod-txt">Libro Actas N°</div></th>' +
      '<th class="mod"><div class="mod-txt">Folio N°</div></th>' +
      '<th class="mod"><div class="mod-txt">Fecha</div></th>'
    : '<th class="mod"><div class="mod-txt">Calificación Final</div></th>' +
      '<th class="mod"><div class="mod-txt">Libro Actas N°</div></th>' +
      '<th class="mod"><div class="mod-txt">Folio N°</div></th>' +
      '<th class="mod"><div class="mod-txt">Fecha</div></th>';

  var checksRefIngreso = listaOpcionesRef.map(function (op) {
    var marcado = String(refIngresoActual).toLowerCase().indexOf(op.toLowerCase()) !== -1;
    return '<label style="display:inline-flex;align-items:center;gap:4px;font-weight:normal;margin-right:8px;cursor:pointer">' +
      '<input type="checkbox" class="chk-ref-ingreso-rac" value="' + esc(op) + '"' + (marcado ? ' checked' : '') + '> ' + esc(op) +
    '</label>';
  }).join('');

  var nombreEscuelaEnc = (enc.establecimiento || (estado.curso && estado.curso.institucion) || 'Establecimiento Educativo').toUpperCase();
  var localidadEscuelaEnc = (enc.localidad || 'San Salvador de Jujuy').toUpperCase();
  var provinciaEscuelaEnc = 'JUJUY';

  var encabezadoImpresionRac =
    '<div class="solo-impresion" style="margin-bottom:6px;border-bottom:2px solid #222;padding-bottom:4px;font-family:\'Times New Roman\',serif">' +
      '<div style="text-align:center;margin-bottom:4px">' +
        '<div style="font-size:15px;font-weight:bold;letter-spacing:0.5px">SECRETARÍA DE GESTIÓN EDUCATIVA - DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL</div>' +
        '<div style="font-size:13px;font-weight:bold;letter-spacing:0.4px;margin-top:2px">' + esc(nombreEscuelaEnc) + ' · ' + esc(localidadEscuelaEnc) + ' · PROVINCIA DE ' + esc(provinciaEscuelaEnc) + '</div>' +
        '<h2 style="margin:4px 0 2px;font-size:14px;text-transform:uppercase;letter-spacing:1px">REGISTRO ANUAL DE CALIFICACIONES</h2>' +
      '</div>' +
      '<table style="width:100%;border-collapse:collapse;font-size:10px;border:none">' +
        '<tr>' +
          '<td style="border:none;padding:1px 4px"><b>Establecimiento:</b> ' + esc(enc.establecimiento || estado.curso.institucion || '—') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>CUE:</b> ' + esc(enc.cue || estado.curso.cue || '—') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Familia Profesional:</b> ' + esc(enc.familiaProfesional || '—') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td style="border:none;padding:1px 4px"><b>Oferta Formativa:</b> ' + esc(enc.oferta || estado.curso.oferta || '—') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Ciclo Lectivo:</b> ' + esc(enc.ciclo || estado.curso.ciclo || '—') + (enc.duracion ? ' · <b>Duración:</b> ' + esc(enc.duracion) : '') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Turno / Curso / División:</b> ' + esc(enc.turno || estado.curso.turno || '—') + ' · ' + esc(enc.cursoAnio || '1°') + ' ' + esc(enc.divisionLetra || '"U"') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td style="border:none;padding:1px 4px"><b>Referencial de ingreso:</b> <span id="imp_ref_ingreso">' + esc(refIngresoActual) + '</span></td>' +
          '<td style="border:none;padding:1px 4px"><b>Horas Cátedras:</b> <span id="imp_hs_cat">' + esc(hsCatActual) + '</span> · <b>Nivel:</b> ' + esc(enc.nivelCurso || 'II') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Certificación:</b> ' + esc(enc.certificacion || 'Diseño Curricular Jurisdiccional') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td style="border:none;padding:1px 4px"><b>Norma Jurisd. Aprobación, Res. N°:</b> ' + esc(enc.normaAprobacion || '—') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Res. Diseño Curricular N°:</b> ' + esc(enc.resolucionDisenio || enc.disenio || '—') + '</td>' +
          '<td style="border:none;padding:1px 4px"><b>Validez Nac. R.M.E N°:</b> ' + esc(enc.validezNacional || '—') + ' · <b>Disposición:</b> ' + esc(enc.disposicion || '-') + '</td>' +
        '</tr>' +
        ((fin1C || fin2C || (enc.docente && enc.docente !== '—'))
          ? '<tr>' +
              '<td style="border:none;padding:1px 4px">' + (fin1C ? '<b>Fin 1° Cuatrimestre:</b> ' + esc(fin1C) : '') + '</td>' +
              '<td style="border:none;padding:1px 4px">' + (fin2C ? '<b>Fin 2° Cuatrimestre:</b> ' + esc(fin2C) : '') + '</td>' +
              '<td style="border:none;padding:1px 4px">' + (enc.docente && enc.docente !== '—' ? '<b>Docente:</b> ' + esc(enc.docente) : '') + '</td>' +
            '</tr>'
          : '') +
      '</table>' +
    '</div>';

  var pieImpresionRac =
    '<div class="solo-impresion pie-firmas-rac" style="margin-top:30px;font-family:\'Times New Roman\',serif;font-size:11px;break-inside:avoid;page-break-inside:avoid">' +
      '<div style="display:flex;justify-content:space-around;align-items:flex-start;text-align:center">' +
        '<div style="width:220px;border-top:1px solid #000;padding-top:4px;margin:0"><b>Sello Institucional</b></div>' +
        '<div style="width:220px;border-top:1px solid #000;padding-top:4px;margin:0"><b>Director/a del Establecimiento</b><br><small>Firma y Sello</small></div>' +
      '</div>' +
    '</div>';

  var btnAprobarTodosRacHtml = esTitulos
    ? '<button type="button" class="boton" style="background:#137333" id="btnAprobarTodosRac"' +
        (cantElegiblesSinAprobar === 0 ? ' disabled title="No hay nuevos egresados pendientes de aprobación"' : '') +
      '>✅ Aprobar Todos los Egresados' + (cantElegiblesSinAprobar ? ' (' + cantElegiblesSinAprobar + ')' : '') + '</button>'
    : '';

  $('panel').innerHTML =
    '<h2 style="font-size:16px;margin:0 0 10px">Registro Anual de Calificaciones</h2>' +
    encabezadoImpresionRac +
    barraFiltroCuat +
    (hayCongelados
      ? '<div class="alerta-congelado">🔒 <b>Atención:</b> Los estudiantes con certificado oficial aprobado tienen sus calificaciones <b>congeladas e inmutables</b>.</div>'
      : '') +
    (editable
      ? '<div class="acciones">' +
          '<button class="boton" id="guardar" disabled>Guardar cambios</button>' +
          '<button type="button" class="boton" style="background:#137333" onclick="mostrarModalNuevoEstudiante()">+ Agregar Alumno</button>' +
          btnAprobarTodosRacHtml +
          '<button type="button" class="boton" style="background:#1F4E78" id="imprimirRac">🖨️ Imprimir Registro Anual</button>' +
          '<span style="color:var(--suave);font-size:12px">Nota de 1 a 10, o AUS si estuvo ausente. ≥7 Aprobado · <7 Desaprobado</span>' +
        '</div>'
      : '<div class="acciones">' +
          btnAprobarTodosRacHtml +
          '<button type="button" class="boton" style="background:#1F4E78" id="imprimirRac">🖨️ Imprimir Registro Anual</button>' +
          '<span style="color:var(--suave);font-size:12px">' + (esTitulos ? 'Rol Dirección de Títulos: puedes visualizar el RAC, imprimir y aprobar certificados.' : 'Tu rol es de consulta: puedes visualizar e imprimir, no modificar.') + '</span>' +
        '</div>') +
    '<div class="tabla-ancha"><table><thead>' +
      '<tr>' +
        '<th colspan="4" style="text-align:center;background:#e9eef4">DATOS DEL ESTUDIANTE</th>' +
        '<th colspan="2" style="text-align:center;background:#dce6f1">LUGAR DE NACIMIENTO</th>' +
        '<th style="text-align:center;background:#e9eef4">ESTUDIOS</th>' +
        thGrupos +
        thGrupoProm +
        (esTitulos ? '<th class="no-imprimir" rowspan="2" style="width:125px;text-align:center;background:#e6f4ea;color:#135c2d">Certificado / Títulos</th>' : '') +
      '</tr>' +
      '<tr>' +
        '<th class="col-meta-nro" style="width:26px;text-align:center">N°</th><th class="col-nombre-est">Apellido y nombres</th><th class="col-meta-doc" style="width:72px;text-align:center">Documento</th>' +
        '<th class="col-meta-fnac" style="width:76px;text-align:center">Fecha nac.</th>' +
        '<th class="col-meta-prov" style="width:66px;text-align:center">Provincia</th>' +
        '<th class="col-meta-pais" style="width:62px;text-align:center">País</th>' +
        '<th class="col-acredita-rac" style="width:95px;text-align:center">Acredita con</th>' +
        th + thExtraFinal +
      '</tr>' +
    '</thead><tbody>' + filas + '</tbody></table></div>' +
    pieImpresionRac;

  if ($('imprimirRac')) {
    $('imprimirRac').addEventListener('click', imprimirRacActual);
  }
  if ($('btnAprobarTodosRac')) {
    $('btnAprobarTodosRac').addEventListener('click', function () {
      aprobarTitulosCurso(null, 'notas');
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.chk-ref-ingreso-rac'), function (chk) {
    chk.addEventListener('change', function () {
      var seleccionados = [];
      Array.prototype.forEach.call(document.querySelectorAll('.chk-ref-ingreso-rac:checked'), function (c) {
        seleccionados.push(c.value);
      });
      var val = seleccionados.length ? seleccionados.join(' / ') : 'Primaria Completa';
      if (estado.datos && estado.datos.encabezado) {
        estado.datos.encabezado.referencialIngreso = val;
      }
      if ($('imp_ref_ingreso')) $('imp_ref_ingreso').textContent = val;
      if ($('ficha_ref_ingreso')) $('ficha_ref_ingreso').textContent = val;
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.chk-acredita-con-rac'), function (chk) {
    chk.addEventListener('change', function () {
      var seleccionados = [];
      Array.prototype.forEach.call(document.querySelectorAll('.chk-acredita-con-rac:checked'), function (c) {
        seleccionados.push(c.value);
      });
      var val = seleccionados.length ? seleccionados.join(' / ') : 'Primario completo';
      if (estado.datos && estado.datos.encabezado) {
        estado.datos.encabezado.acreditaCon = val;
      }
      if ($('imp_acredita_con')) $('imp_acredita_con').textContent = val;
      if ($('ficha_acredita_con')) $('ficha_acredita_con').textContent = val;
      Array.prototype.forEach.call(document.querySelectorAll('.celda-acredita-rac'), function (td) {
        td.textContent = val;
      });
    });
  });
  if ($('inpHsCatRac')) {
    $('inpHsCatRac').addEventListener('input', function () {
      var val = $('inpHsCatRac').value;
      if (estado.datos && estado.datos.encabezado) {
        estado.datos.encabezado.hsCatTotal = val;
      }
      if ($('imp_hs_cat')) $('imp_hs_cat').textContent = val;
      if ($('ficha_hs_cat')) $('ficha_hs_cat').textContent = val;
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-cuat]'), function (btn) {
    btn.addEventListener('click', function () {
      estado.filtroCuatrimestre = btn.dataset.cuat;
      pintarNotas();
    });
  });

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

  Array.prototype.forEach.call(document.querySelectorAll('.sel-acredita-est'), function (sel) {
    var original = sel.value;
    sel.addEventListener('change', function () {
      var k = sel.dataset.fila + '-acreditaCon';
      if (sel.value === original) delete pendientes[k];
      else pendientes[k] = { fila: +sel.dataset.fila, campo: 'acreditaCon', acreditaCon: sel.value };
      $('guardar').disabled = !Object.keys(pendientes).length;
    });
  });

  $('guardar').addEventListener('click', async function () {
    var cambios = Object.keys(pendientes).map(function (k) { return pendientes[k]; });
    $('guardar').disabled = true;
    avisar('Guardando notas en Google Sheets…');
    try {
      var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/notas', 'POST', { cambios: cambios });
      if (r.paquete) _guardarPaqueteLocal(r.paquete);
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
    var enc = estado.datos.encabezado || {};

    // Conversión de nota numérica a letras mayúsculas para el Acta
    var mapaNotaLetras = {
      '1': 'UNO', '2': 'DOS', '3': 'TRES', '4': 'CUATRO', '5': 'CINCO',
      '6': 'SEIS', '7': 'SIETE', '8': 'OCHO', '9': 'NUEVE', '10': 'DIEZ',
      'AUS': 'AUSENTE', 'AUSENTE': 'AUSENTE'
    };
    function notaALetras(val) {
      var v = String(val == null ? '' : val).trim().toUpperCase();
      return mapaNotaLetras[v] || '';
    }

    // Contadores Aprobados / Desaprobados / Ausentes
    var nApr = 0, nDes = 0, nAus = 0;
    var filas = a.estudiantes.map(function (es) {
      var campo = function (c, v) {
        return ed ? '<td class="nota"><input value="' + esc(v) + '" maxlength="3" ' +
                    'data-fila="' + es.filaActa + '" data-campo="' + c + '"></td>'
                  : '<td style="text-align:center">' + esc(v) + '</td>';
      };
      // Calcular condición en cliente
      var def = parseFloat(es.definitiva);
      var condStr = '';
      if (es.definitiva === 'AUS' || es.definitiva === 'AUSENTE') { condStr = 'Ausente'; nAus++; }
      else if (!isNaN(def)) { if (def >= 7) { condStr = 'Aprobado'; nApr++; } else { condStr = 'Desaprobado'; nDes++; } }

      var teoLetras = es.teoricoLetras || notaALetras(es.teorico);
      var pracLetras = es.practicoLetras || notaALetras(es.practico);
      var defLetras = es.definitivaLetras || notaALetras(es.definitiva);

      var badgeCond = '—';
      if (condStr === 'Aprobado') {
        badgeCond = '<span class="badge-estado badge-aprobado">APROBADO</span>';
      } else if (condStr === 'Desaprobado') {
        badgeCond = '<span class="badge-estado badge-observado">DESAPROBADO</span>';
      } else if (condStr === 'Ausente') {
        badgeCond = '<span class="badge-estado badge-no-solicitado">AUSENTE</span>';
      }

      return '<tr>' +
        '<td style="text-align:center">' + esc(es.orden) + '</td>' +
        '<td style="text-align:center">' + esc(es.documento) + '</td>' +
        '<td class="col-nombre-est">' + esc(es.nombre) + '</td>' +
        campo('teorico', es.teorico) +
        '<td style="text-align:center">' + esc(teoLetras) + '</td>' +
        campo('practico', es.practico) +
        '<td style="text-align:center">' + esc(pracLetras) + '</td>' +
        '<td style="text-align:center;font-weight:bold">' + esc(es.definitiva) + '</td>' +
        '<td style="text-align:center">' + esc(defLetras) + '</td>' +
        '<td style="text-align:center">' + badgeCond + '</td>' +
      '</tr>';
    }).join('');

    var totalEst = a.estudiantes.length;
    // Texto en letras del total (enteros 0 a 999 en español)
    var unidadesLetras = [
      'cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve',
      'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve',
      'veinte', 'veintiuno', 'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho', 'veintinueve'
    ];
    var decenasLetras = {
      3: 'treinta', 4: 'cuarenta', 5: 'cincuenta',
      6: 'sesenta', 7: 'setenta', 8: 'ochenta', 9: 'noventa'
    };
    var centenasLetras = {
      1: 'ciento', 2: 'doscientos', 3: 'trescientos', 4: 'cuatrocientos', 5: 'quinientos',
      6: 'seiscientos', 7: 'setecientos', 8: 'ochocientos', 9: 'novecientos'
    };
    function enLetras(n) {
      var num = Number(n);
      if (!isFinite(num) || Math.floor(num) !== num || num < 0 || num > 999) {
        return String(n);
      }
      if (num < 30) return unidadesLetras[num];
      if (num < 100) {
        var d = Math.floor(num / 10);
        var u = num % 10;
        return u === 0 ? decenasLetras[d] : (decenasLetras[d] + ' y ' + unidadesLetras[u]);
      }
      if (num === 100) return 'cien';
      var c = Math.floor(num / 100);
      var resto = num % 100;
      return resto === 0 ? centenasLetras[c] : (centenasLetras[c] + ' ' + enLetras(resto));
    }

    var libroNro = enc.libro || '1';
    var folioNro = enc.folio || '1';

    var inputMesa = function (idCampo, valorActual, placeholder, ancho) {
      if (!ed) return '<b>' + esc(valorActual || '—') + '</b>';
      return '<input id="' + idCampo + '" class="inp-mesa" value="' + esc(valorActual || '') + '" ' +
             'placeholder="' + esc(placeholder) + '" style="width:' + (ancho || '220px') + '">';
    };

    var nombreEscActa = (enc.establecimiento || (estado.curso && estado.curso.institucion) || 'Establecimiento Educativo').toUpperCase();
    var locEscActa = (enc.localidad || 'San Salvador de Jujuy').toUpperCase();
    var provEscActa = 'JUJUY';

    $('panel').innerHTML =
      // ── Encabezado con Secretaría, Datos de la Escuela, Libro y Folio ──
      '<div class="acta-encabezado">' +
        '<div style="text-align:center;font-family:\'Times New Roman\',serif;letter-spacing:0.5px;margin-bottom:6px">' +
          '<div style="font-size:15px;font-weight:bold">SECRETARÍA DE GESTIÓN EDUCATIVA - DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL</div>' +
          '<div style="font-size:13px;font-weight:bold;margin-top:2px">' + esc(nombreEscActa) + ' · ' + esc(locEscActa) + ' · PROVINCIA DE ' + esc(provEscActa) + '</div>' +
        '</div>' +
        '<div class="acta-libro-folio">' +
          '<span>Libro de Actas N°: ' + inputMesa('m_libro', libroNro, 'N° Libro', '60px') + '</span>' +
          '<span style="margin-left:32px">Folio N°: ' + inputMesa('m_folio', folioNro, 'N° Folio', '60px') + '</span>' +
        '</div>' +
        '<h2 class="acta-titulo">ACTA DE EXAMEN DE ALUMNOS REGULARES</h2>' +
        '<table class="acta-ficha">' +
          '<tr><td><b>Establecimiento:</b></td><td>' + esc(enc.establecimiento || '—') + ' · CUE ' + esc(enc.cue || '') + '</td></tr>' +
          '<tr><td><b>De:</b></td><td>' + esc(enc.oferta || '—') + '</td></tr>' +
          '<tr><td><b>Correspondiente al:</b></td><td>' + esc(enc.turno || '') + ' · ' + esc(enc.division || '') + ' · Ciclo lectivo: ' + esc(enc.ciclo || '') + '</td></tr>' +
          '<tr><td><b>Fecha del examen:</b></td><td>' + inputMesa('m_fecha', a.mesa.fecha, 'dd/mm/aaaa', '140px') + '</td></tr>' +
        '</table>' +
        '<p class="acta-texto-intro">En la fecha consignada, reunida la comisión examinadora del Trayecto Formativo con asistencia de sus tres miembros docentes:</p>' +
        '<table class="acta-ficha">' +
          '<tr><td><b>Presidente/a:</b></td><td colspan="3">' + inputMesa('m_presidente', a.mesa.presidente, 'Apellido y Nombre del Presidente/a', '260px') + '</td></tr>' +
          '<tr><td><b>Vocal 1°:</b></td><td>' + inputMesa('m_vocal1', a.mesa.vocal1, 'Apellido y Nombre del Vocal 1°', '240px') + '</td>' +
              '<td><b>Vocal 2°:</b></td><td>' + inputMesa('m_vocal2', a.mesa.vocal2, 'Apellido y Nombre del Vocal 2°', '240px') + '</td></tr>' +
        '</table>' +
        '<p class="acta-texto-intro">procedió a cumplir su cometido con el resultado que se consigna a continuación:</p>' +
        '<p style="font-size:11px;font-style:italic;margin:4px 0 10px">NOTA: Será considerada como fraudulenta toda enmienda o raspadura que no haya sido salvada expresamente con la firma de todos los miembros de la mesa. El número de alumnos examinados se anotará con letras y números.</p>' +
      '</div>' +

      // ── Acciones guardar e imprimir ──
      '<div class="acciones">' +
        (ed ? '<button class="boton" id="guardarActa" disabled>Guardar cambios (Docentes y Notas)</button>' : '') +
        '<button type="button" class="boton" style="background:#1F4E78" id="imprimirActa">🖨️ Imprimir Acta de Examen</button>' +
        '<span style="color:var(--suave);font-size:12px">Podés editar los docentes del tribunal (Presidente/a, Vocal 1°, Vocal 2°), la fecha y las calificaciones aquí mismo.</span>' +
      '</div>' +

      // ── Tabla de alumnos ──
      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:36px">N° de orden</th>' +
        '<th style="width:92px">N° doc. de identidad</th>' +
        '<th class="col-nombre-est">Apellido y nombre</th>' +
        '<th style="width:60px">Teórico N°</th><th style="width:70px">Teórico Letras</th>' +
        '<th style="width:60px">Práctico N°</th><th style="width:70px">Práctico Letras</th>' +
        '<th style="width:60px">Definitiva N°</th><th style="width:90px">Definitiva Letras</th>' +
        '<th style="width:105px">Condición</th>' +
      '</tr></thead><tbody>' + (filas || '') + '</tbody></table></div>' +

      // ── Resumen (sin tabla, 4 líneas separadas + texto) ──
      '<div class="acta-resumen">' +
        '<div class="acta-texto-intro" style="margin:6px 0;line-height:1.65">' +
          '<div><b>Aprobados:</b> ' + nApr + '</div>' +
          '<div><b>Desaprobados:</b> ' + nDes + '</div>' +
          '<div><b>Ausentes:</b> ' + nAus + '</div>' +
          '<div><b>Total:</b> ' + totalEst + '</div>' +
        '</div>' +
        '<p class="acta-texto-intro" style="margin-top:8px">Se hace constar que sobre un total de ' + enLetras(totalEst) + ' (' + totalEst + ') alumnos/as, ' +
          'resultaron ' + enLetras(nApr) + ' (' + nApr + ') aprobados/as, ' +
          enLetras(nDes) + ' (' + nDes + ') desaprobados/as y ' +
          enLetras(nAus) + ' (' + nAus + ') ausentes.</p>' +
      '</div>' +

      // ── Firmas ──
      '<div class="acta-firmas">' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><div id="f_txt_vocal2" style="font-weight:bold">' + esc(a.mesa.vocal2 || '') + '</div><b>Vocal 2°</b><br><small>Firma y aclaración</small></div>' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><div id="f_txt_presidente" style="font-weight:bold">' + esc(a.mesa.presidente || '') + '</div><b>Presidente/a</b><br><small>Firma y aclaración</small></div>' +
        '<div class="acta-firma"><div class="acta-firma-linea"></div><div id="f_txt_vocal1" style="font-weight:bold">' + esc(a.mesa.vocal1 || '') + '</div><b>Vocal 1°</b><br><small>Firma y aclaración</small></div>' +
      '</div>';

    if ($('imprimirActa')) {
      $('imprimirActa').addEventListener('click', function () { window.print(); });
    }

    if (!ed) return;
    var pend = {};
    var mesaModificada = false;

    ['m_libro', 'm_folio', 'm_fecha', 'm_presidente', 'm_vocal1', 'm_vocal2'].forEach(function (idM) {
      var el = $(idM);
      if (!el) return;
      el.addEventListener('input', function () {
        mesaModificada = true;
        $('guardarActa').disabled = false;
        if ($('f_txt_presidente') && $('m_presidente')) $('f_txt_presidente').textContent = $('m_presidente').value;
        if ($('f_txt_vocal1') && $('m_vocal1')) $('f_txt_vocal1').textContent = $('m_vocal1').value;
        if ($('f_txt_vocal2') && $('m_vocal2')) $('f_txt_vocal2').textContent = $('m_vocal2').value;
      });
    });

    Array.prototype.forEach.call(document.querySelectorAll('#panel td.nota input'), function (inp) {
      var orig = inp.value;
      inp.addEventListener('input', function () {
        inp.value = inp.value.toUpperCase();
        var k = inp.dataset.fila + '-' + inp.dataset.campo;
        if (inp.value === orig) delete pend[k];
        else pend[k] = { filaActa: +inp.dataset.fila, campo: inp.dataset.campo, valor: inp.value };
        $('guardarActa').disabled = !(Object.keys(pend).length || mesaModificada);
      });
    });

    $('guardarActa').addEventListener('click', async function () {
      var cambios = Object.keys(pend).map(function (k) { return pend[k]; });
      var mesaPayload = {
        libro: $('m_libro') ? $('m_libro').value.trim() : libroNro,
        folio: $('m_folio') ? $('m_folio').value.trim() : folioNro,
        fecha: $('m_fecha') ? $('m_fecha').value.trim() : (a.mesa.fecha || ''),
        presidente: $('m_presidente') ? $('m_presidente').value.trim() : (a.mesa.presidente || ''),
        vocal1: $('m_vocal1') ? $('m_vocal1').value.trim() : (a.mesa.vocal1 || ''),
        vocal2: $('m_vocal2') ? $('m_vocal2').value.trim() : (a.mesa.vocal2 || '')
      };
      if (estado.datos && estado.datos.encabezado) {
        estado.datos.encabezado.libro = mesaPayload.libro;
        estado.datos.encabezado.folio = mesaPayload.folio;
      }
      $('guardarActa').disabled = true;
      avisar('Guardando acta y tribunal examinador…');
      try {
        var rActaSave = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/acta', 'POST', {
          mesa: mesaPayload,
          cambios: cambios
        });
        if (rActaSave && rActaSave.paquete) _guardarPaqueteLocal(rActaSave.paquete);
        var rCurso = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id));
        if (rCurso && rCurso.paquete) _guardarPaqueteLocal(rCurso.paquete);
        if (rCurso && rCurso.datos) {
          estado.datos = rCurso.datos;
        }
        avisar('¡Acta de Examen guardada y reflejada en el Registro Anual de Calificaciones!', 'ok');
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

// ---------- PESTAÑA: CIRCUITO DE CERTIFICADOS (ESCUELA Y TÍTULOS) ----------
async function aprobarTitulosCurso(documentos, pestaniaDestino) {
  if (!estado.curso || !estado.curso.id) return;
  var esMasivo = !documentos || !documentos.length;
  if (esMasivo && !confirm('¿Aprobar en un clic a todos los egresados académicamente aprobados de este curso que aún no tienen certificado?')) {
    return;
  }
  avisar(esMasivo ? 'Aprobando todos los egresados del curso…' : 'Aprobando certificado…');
  try {
    var r = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/aprobar-titulos', 'POST', {
      documentos: esMasivo ? null : documentos
    });
    var nApr = r.cantidadAprobados || 0;
    var nYa = (r.yaAprobados || []).length;
    var nOm = (r.omitidos || []).length;
    if (nApr > 0) {
      avisar('¡Se aprobaron ' + nApr + ' certificado(s) con éxito!' + (nOm ? ' (' + nOm + ' omitido(s) por no estar aprobados).' : ''), 'ok');
    } else if (nYa > 0) {
      avisar('Los egresados elegibles de este curso ya contaban con certificado aprobado.', 'ok');
    } else {
      avisar('No se encontraron estudiantes elegibles para aprobar en este curso.', 'error');
    }
    abrirCurso(estado.curso.id, pestaniaDestino || estado.pestania);
  } catch (e) {
    problema(e);
  }
}

function pintarSolicitudesCurso() {
  var d = estado.datos;
  var esTitulos = Boolean(estado.sesion && estado.sesion.esTitulos);
  var cantElegiblesPend = 0;

  var filas = d.estudiantes.map(function (es) {
    var condAcadSol = _estadoAcademicoEstudiante(es);
    var aprobo = (condAcadSol === 'APROBADO');
    var sol = es.solicitudCertificado || {};
    var st = sol.estado || 'No solicitado';

    var badgeClass = 'badge-no-solicitado';
    if (st === 'Pendiente') badgeClass = 'badge-pendiente';
    else if (st === 'Observado') badgeClass = 'badge-observado';
    else if (st === 'Aprobado') badgeClass = 'badge-aprobado';

    var accionHtml = '';
    if (!aprobo) {
      if (condAcadSol === 'DESAPROBADO') {
        accionHtml = '<span class="badge-estado badge-observado">DESAPROBADO</span>';
      } else {
        accionHtml = '<span class="badge-estado badge-no-solicitado">AUSENTE</span>';
      }
    } else if (st === 'Aprobado') {
      accionHtml = '<span class="badge-estado badge-aprobado" title="Certificado N° ' + esc(sol.numeroCertificado || '') + '">APROBADO</span>';
    } else if (esTitulos) {
      cantElegiblesPend++;
      var nombreEst = (es.apellido || '') + ', ' + (es.nombres || '');
      accionHtml = '<span class="badge-estado badge-aprobado" style="cursor:pointer" title="Clic para aprobar certificado oficial" onclick="aprobarTitulosCurso([' + escJsArg(es.documento) + '], \'solicitudes\')">APROBADO</span>';
      if (st === 'Pendiente' && sol.idSolicitud) {
        accionHtml += ' <button type="button" class="boton suave" style="padding:2px 6px;font-size:11px;color:var(--mal);border-color:var(--mal)" onclick="abrirModalObservar(' + escJsArg(sol.idSolicitud) + ', ' + escJsArg(nombreEst) + ', true)">Observar</button>';
      }
    } else {
      if (st === 'No solicitado') {
        accionHtml = '<button class="boton" onclick="solicitarCertificadoEstudiante(' + escJsArg(es.documento) + ')">Solicitar Certificado</button>';
      } else if (st === 'Pendiente') {
        accionHtml = '<span style="color:#b06000;font-weight:600">⏳ En revisión por Títulos</span>';
      } else if (st === 'Observado') {
        accionHtml = '<button class="boton" style="background:#e37400" onclick="solicitarCertificadoEstudiante(' + escJsArg(es.documento) + ')">Reenviar a Títulos</button>';
      }
    }

    var alertaObs = '';
    if (st === 'Observado' && sol.motivoObservacion) {
      var obsAutor = sol.observadoPor ? (sol.observadoPor + (sol.observadoEmail ? ' (' + sol.observadoEmail + ')' : '')) : (sol.observadoEmail || 'Dirección de Títulos');
      var obsFecha = sol.fechaObservacion ? (' · ' + sol.fechaObservacion) : '';
      alertaObs = '<div class="alerta-observacion">' +
        '⚠️ <b>Observación de Títulos:</b> ' + esc(sol.motivoObservacion) +
        '<div style="margin-top:3px;font-size:11px;color:#5f6368">👤 <b>Observado por:</b> ' + esc(obsAutor) + esc(obsFecha) + '</div>' +
      '</div>';
    } else if (st === 'Aprobado' && (sol.aprobadoPor || sol.aprobadoEmail)) {
      var aprAutor = sol.aprobadoPor ? (sol.aprobadoPor + (sol.aprobadoEmail ? ' (' + sol.aprobadoEmail + ')' : '')) : sol.aprobadoEmail;
      var aprFecha = (sol.fechaHoraAprobacion || sol.fechaAprobacion) ? (' · ' + (sol.fechaHoraAprobacion || sol.fechaAprobacion)) : '';
      alertaObs = '<div style="margin-top:4px;font-size:11px;color:#137333">✅ <b>Aprobado por:</b> ' + esc(aprAutor) + esc(aprFecha) + '</div>';
    }

    var btnHistCurso = (sol.historial && sol.historial.length > 0)
      ? '<button type="button" class="boton suave" style="margin:0;padding:4px 8px;font-size:11.5px" title="Ver quién solicitó, observó o aprobó" onclick="verHistorialEstudianteCurso(' + escJsArg(es.documento) + ')">🕒 Historial (' + sol.historial.length + ')</button>'
      : '';

    return '<tr>' +
      '<td style="text-align:center">' + esc(es.orden) + '</td>' +
      '<td><b>' + esc(es.apellido) + ', ' + esc(es.nombres) + '</b>' + alertaObs + '</td>' +
      '<td style="text-align:center">' + esc(es.documento) + '</td>' +
      '<td>' + esc(es.situacion || '—') + '</td>' +
      '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(st) + '</span></td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(sol.numeroCertificado || '—') + '</td>' +
      '<td style="text-align:center;white-space:nowrap">' +
        '<div style="display:inline-flex;align-items:center;justify-content:center;gap:8px">' +
          '<span style="display:inline-block;min-width:105px;text-align:center">' + accionHtml + '</span>' +
          btnHistCurso +
          '<button class="boton suave" style="margin:0" onclick="verAnaliticoEstudiante(' + escJsArg(es.documento) + ')">Ver Analítico</button>' +
        '</div>' +
      '</td>' +
    '</tr>';
  }).join('');

  var barraTitulosHtml = esTitulos
    ? '<div class="acciones" style="background:#e6f4ea;padding:10px 14px;border:1px solid #34a853;border-radius:6px">' +
        '<button type="button" class="boton" style="background:#137333" id="btnAprobarTodosSol"' +
          (cantElegiblesPend === 0 ? ' disabled' : '') +
        '>✅ Aprobar Todos los Egresados' + (cantElegiblesPend ? ' (' + cantElegiblesPend + ')' : '') + '</button>' +
        '<span style="color:#135c2d;font-size:12px">Podés aprobar individualmente o en un clic a todos los egresados aprobados del curso (incluso sin solicitud previa).</span>' +
      '</div>'
    : '';

  $('panel').innerHTML =
    '<div class="ficha">' +
      '<dt>Regla de certificación:</dt>' +
      '<dd>Solo pueden recibir certificado oficial los alumnos académicamente aprobados (<b>"Aprobó"</b> y nota final ≥ 7). Quienes no aprobaron no tienen la opción habilitada.</dd>' +
    '</div>' +
    barraTitulosHtml +
    '<div class="tabla-ancha"><table><thead><tr>' +
      '<th style="width:36px">N°</th><th>Estudiante</th><th style="width:90px">DNI</th>' +
      '<th style="width:130px">Situación</th><th style="width:110px">Estado Pedido</th>' +
      '<th style="width:140px">N° Certificado</th><th style="width:260px">Acción</th>' +
    '</tr></thead><tbody>' + filas + '</tbody></table></div>';

  if ($('btnAprobarTodosSol')) {
    $('btnAprobarTodosSol').addEventListener('click', function () {
      aprobarTitulosCurso(null, 'solicitudes');
    });
  }
}

// ---------- PLANILLA POR ESCUELA · NÓMINA DE EGRESADOS ----------
function _renderPlanillaNominaHTML(nomina, opcionesExtra) {
  var enc = nomina.encabezado || {};
  var tot = nomina.totales || {};
  var filtroActual = nomina.filtro || estado.filtroNomina || 'todos';
  var filas = nomina.filas || [];
  var nombreEsc = (enc.establecimiento || 'ESTABLECIMIENTO EDUCATIVO').toUpperCase();
  var locEsc = (enc.localidad || 'JUJUY').toUpperCase();

  var filasHtml = filas.length
    ? filas.map(function (f) {
        return '<tr>' +
          '<td style="text-align:center;width:48px">' + esc(f.orden) + '</td>' +
          '<td class="col-nombre-est">' + esc(f.apellidoNombres) + '</td>' +
          '<td style="text-align:center;width:95px">' + esc(f.documento) + '</td>' +
          '<td style="text-align:center;width:90px">' + esc(f.fecha || '—') + '</td>' +
          '<td>' + esc(f.observaciones || '—') + '</td>' +
        '</tr>';
      }).join('')
    : '<tr><td colspan="5" style="text-align:center;padding:18px;color:var(--suave)">No hay estudiantes para el filtro seleccionado.</td></tr>';

  return (opcionesExtra || '') +
    '<div class="acciones no-imprimir" style="justify-content:space-between;flex-wrap:wrap">' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<button type="button" class="boton ' + (filtroActual === 'con_certificados' ? '' : 'suave') + '" data-nomina-filtro="con_certificados">Con Certificados (' + (tot.con_certificados || 0) + ')</button>' +
        '<button type="button" class="boton ' + (filtroActual === 'aprobados' ? '' : 'suave') + '" data-nomina-filtro="aprobados">Aprobados (' + (tot.aprobados || 0) + ')</button>' +
        '<button type="button" class="boton ' + (filtroActual === 'pendientes' ? '' : 'suave') + '" data-nomina-filtro="pendientes">Pendientes (' + (tot.pendientes || 0) + ')</button>' +
        '<button type="button" class="boton ' + (filtroActual === 'todos' ? '' : 'suave') + '" data-nomina-filtro="todos">Todos (' + (tot.todos || 0) + ')</button>' +
      '</div>' +
      '<button type="button" class="boton" id="btnImprimirNomina" style="background:#1F4E78">🖨️ Imprimir Nómina</button>' +
    '</div>' +
    '<div class="planilla-nomina" id="hojaNominaImpresion">' +
      '<div style="text-align:center;margin-bottom:8px">' +
        '<div style="font-size:13px;font-weight:700;letter-spacing:0.3px">SECRETARÍA DE GESTIÓN EDUCATIVA - DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL</div>' +
        '<div style="font-size:12px;font-weight:700;margin-top:2px">' + esc(nombreEsc) + (locEsc ? ' · ' + esc(locEsc) : '') + ' · PROVINCIA DE JUJUY</div>' +
      '</div>' +
      '<div class="nomina-titulo">NOMINA DE EGRESADOS Ciclo Lectivo ' + esc(enc.ciclo || '2026') + '</div>' +
      '<table class="nomina-meta-tabla">' +
        '<tr>' +
          '<td class="lbl">Establecimiento:</td><td>' + esc(enc.establecimiento || '—') + (enc.cue ? ' (CUE ' + esc(enc.cue) + ')' : '') + '</td>' +
          '<td class="lbl">Domicilio:</td><td>' + esc(enc.domicilio || 'S/D') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td class="lbl">Oferta Formativa:</td><td>' + esc(enc.oferta || '—') + '</td>' +
          '<td class="lbl">Duración de los Estudios:</td><td>' + esc(enc.duracion || '—') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td class="lbl">División:</td><td>' + esc(enc.division || '—') + '</td>' +
          '<td class="lbl">Turno:</td><td>' + esc(enc.turno || '—') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td class="lbl">Norma Jurisdiccional de Aprobación N°:</td><td>' + esc(enc.normaAprobacion || '—') + '</td>' +
          '<td class="lbl">Resolución Jurisdiccional N°:</td><td>' + esc(enc.resolucionDisenio || '—') + '</td>' +
        '</tr>' +
        '<tr>' +
          '<td class="lbl">Docente:</td><td colspan="3">' + esc(enc.docente || '—') + '</td>' +
        '</tr>' +
      '</table>' +
      '<table class="tabla-nomina">' +
        '<thead><tr>' +
          '<th style="width:52px">Orden</th>' +
          '<th class="col-nombre-est">Apellido y Nombres</th>' +
          '<th style="width:100px">DNI</th>' +
          '<th style="width:95px">Fecha</th>' +
          '<th>Observaciones</th>' +
        '</tr></thead>' +
        '<tbody>' + filasHtml + '</tbody>' +
      '</table>' +
    '</div>';
}

async function pintarNominaCurso() {
  if (!estado.curso || !estado.curso.id) return;
  $('panel').innerHTML = '<div class="cargando">Cargando Nómina de Egresados…</div>';
  var filtro = estado.filtroNomina || 'todos';
  try {
    var r = await llamar('/api/nomina?id_curso=' + encodeURIComponent(estado.curso.id) + '&filtro=' + encodeURIComponent(filtro));
    var nomina = r.nomina;
    $('panel').innerHTML = _renderPlanillaNominaHTML(nomina, '');
    Array.prototype.forEach.call($('panel').querySelectorAll('[data-nomina-filtro]'), function (btn) {
      btn.addEventListener('click', function () {
        estado.filtroNomina = btn.dataset.nominaFiltro;
        try { localStorage.setItem('lm_filtro_nomina', estado.filtroNomina); } catch (e) {}
        pintarNominaCurso();
      });
    });
    if ($('btnImprimirNomina')) {
      $('btnImprimirNomina').addEventListener('click', imprimirNominaActual);
    }
  } catch (e) {
    problema(e);
  }
}

async function verNominaEscuela(idCursoPre, cuePre) {
  estado.curso = null;
  estado.datos = null;
  _guardarRutaLocal('nomina', idCursoPre || '', '');
  $('migas').hidden = false;
  $('volver').textContent = (estado.sesion && estado.sesion.esTitulos) ? '← Volver a Bandeja de Títulos' : '← Volver a los cursos';

  var cursosDisp = estado.cursos || [];
  var mapaEscuelas = {};
  cursosDisp.forEach(function (c) {
    var k = String(c.cue || c.institucion || '').trim();
    if (k && !mapaEscuelas[k]) mapaEscuelas[k] = c.institucion || ('CUE ' + k);
  });

  var cueSel = cuePre;
  var cursoSel = idCursoPre || '';
  if (!cueSel && !cursoSel && cursosDisp.length) {
    cursoSel = cursosDisp[0].id;
    cueSel = cursosDisp[0].cue || '';
  }

  $('main').innerHTML = '<div class="cargando">Cargando Nómina de Egresados por Escuela…</div>';
  _configurarPaginaImpresion('oficio-horizontal');

  async function _cargarYRenderNomina(cueActual, idCursoActual) {
    var filtro = estado.filtroNomina || 'todos';
    var qs = 'filtro=' + encodeURIComponent(filtro);
    if (idCursoActual) qs += '&id_curso=' + encodeURIComponent(idCursoActual);
    else if (cueActual) qs += '&cue=' + encodeURIComponent(cueActual);

    try {
      var r = await llamar('/api/nomina?' + qs);
      var nomina = r.nomina;
      if (nomina.encabezado && nomina.encabezado.establecimiento) {
        _actualizarBarraEscuela(nomina.encabezado.establecimiento + (nomina.encabezado.localidad ? ' · ' + nomina.encabezado.localidad + ', Jujuy' : ''));
      }

      var esNivelCentral = Boolean(estado.sesion && (estado.sesion.verTodo || estado.sesion.esTitulos));
      var opsEscuelas = (esNivelCentral ? '<option value="">Todas las escuelas</option>' : '') +
        Object.keys(mapaEscuelas).map(function (k) {
          var sel = (String(cueActual || '') === k) ? ' selected' : '';
          return '<option value="' + esc(k) + '"' + sel + '>' + esc(mapaEscuelas[k]) + ' (CUE ' + esc(k) + ')</option>';
        }).join('');

      var cursosFiltradosEsc = cursosDisp.filter(function (c) {
        return !cueActual || String(c.cue || '') === String(cueActual);
      });
      var opsCursos = '<option value="">Todos los cursos de la escuela</option>' +
        cursosFiltradosEsc.map(function (c) {
          var sel = (String(idCursoActual || '') === String(c.id)) ? ' selected' : '';
          return '<option value="' + esc(c.id) + '"' + sel + '>' + esc(c.oferta) + ' · ' + esc(c.division) + ' (' + esc(c.ciclo) + ')</option>';
        }).join('');

      var selectorBar =
        '<div class="no-imprimir" style="background:#fff;border:1px solid var(--borde);border-radius:6px;padding:12px 14px;margin-bottom:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:end">' +
          '<div><label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">Escuela / Establecimiento</label>' +
            '<select id="selNominaEscuela" style="min-width:260px">' + opsEscuelas + '</select></div>' +
          '<div><label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px">Curso / Oferta Formativa</label>' +
            '<select id="selNominaCurso" style="min-width:260px">' + opsCursos + '</select></div>' +
        '</div>';

      $('main').innerHTML =
        '<h1 class="no-imprimir">Planilla por Escuela · Nómina de Egresados</h1>' +
        _renderPlanillaNominaHTML(nomina, selectorBar);

      if ($('selNominaEscuela')) {
        $('selNominaEscuela').addEventListener('change', function () {
          var nuevaCue = $('selNominaEscuela').value;
          _cargarYRenderNomina(nuevaCue, '');
        });
      }
      if ($('selNominaCurso')) {
        $('selNominaCurso').addEventListener('change', function () {
          var nuevoId = $('selNominaCurso').value;
          _guardarRutaLocal('nomina', nuevoId, '');
          _cargarYRenderNomina($('selNominaEscuela') ? $('selNominaEscuela').value : cueActual, nuevoId);
        });
      }
      Array.prototype.forEach.call($('main').querySelectorAll('[data-nomina-filtro]'), function (btn) {
        btn.addEventListener('click', function () {
          estado.filtroNomina = btn.dataset.nominaFiltro;
          try { localStorage.setItem('lm_filtro_nomina', estado.filtroNomina); } catch (e) {}
          _cargarYRenderNomina(cueActual, idCursoActual);
        });
      });
      if ($('btnImprimirNomina')) {
        $('btnImprimirNomina').addEventListener('click', imprimirNominaActual);
      }
    } catch (err) {
      problema(err);
    }
  }

  _cargarYRenderNomina(cueSel, cursoSel);
}

async function solicitarCertificadoEstudiante(doc) {
  avisar('Enviando pedido a la Dirección de Títulos…');
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
    if ($('selEst')) { $('selEst').value = doc; $('generar').click(); }
  }, 100);
}

// ---------- PESTAÑA: CERTIFICADO (CON CONTROL DE BORRADOR VS OFICIAL) ----------
function pintarAnalitico() {
  var opciones = estado.datos.estudiantes.map(function (e) {
    return '<option value="' + esc(e.documento) + '">' + esc(e.apellido) + ', ' +
           esc(e.nombres) + '</option>';
  }).join('');

  $('panel').innerHTML =
    '<h2 style="font-size:16px;margin:0 0 10px">Certificado</h2>' +
    '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px;align-items:center">' +
      '<label style="display:flex;align-items:center;gap:6px">Estudiante: <select id="selEst" style="min-width:220px">' + opciones + '</select></label>' +
      '<label style="display:flex;align-items:center;gap:6px">Emisión: <input type="date" id="fecha"></label>' +
      '<button class="boton" id="generar" style="background:#1F4E78">Ver el certificado</button>' +
      '<button class="boton suave" id="imprimir" disabled style="opacity:0.5;cursor:not-allowed">Imprimir</button>' +
    '</div>' +
    '<div id="bannerEstadoAnalitico"></div>' +
    '<div id="salida"></div>';

  $('fecha').valueAsDate = new Date();

  $('generar').addEventListener('click', async function () {
    var doc = $('selEst').value;
    if (!doc) { avisar('Ese estudiante no tiene documento registrado.', 'error'); return; }
    $('salida').innerHTML = '<div class="cargando">Generando certificado oficial…</div>';
    var f = $('fecha').value || '';
    try {
      var url = '/api/curso/' + encodeURIComponent(estado.curso.id) + '/analitico?documento=' + encodeURIComponent(doc) +
                '&fecha=' + encodeURIComponent(f);
      var r = await llamar(url);
      var an = r.analitico;
      var docOf = an.documentoOficial || {};
      var bannerBox = $('bannerEstadoAnalitico');
      var btnImp = $('imprimir');

      var rolActual = (estado.sesion && estado.sesion.rol) ? String(estado.sesion.rol).toLowerCase() : '';
      var puedeImprimirRol = (rolActual === 'administrativo' || rolActual === 'directivo');
      var solCert = an.solicitudCertificado || {};
      var yaImpreso = Boolean(solCert.impreso);

      if (an.esBorrador) {
        var msg = docOf.mensajeEstado || 'Documento en estado BORRADOR – no válido: requiere aprobación de la Dirección de Títulos para que el Administrativo o Directivo pueda imprimirlo.';
        bannerBox.innerHTML = '<div class="banner-aviso-analitico">' + esc(msg) + '</div>';
        btnImp.disabled = true; btnImp.style.opacity = '0.5'; btnImp.style.cursor = 'not-allowed';
        btnImp.textContent = 'Imprimir';
        btnImp.title = 'Impresión bloqueada: requiere aprobación de la Dirección de Títulos';
        $('salida').className = 'impresion-bloqueada';
      } else if (yaImpreso) {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#fce8e6;border-color:#d93025;color:#b3261e">' +
            '🔒 <b>CERTIFICADO IMPRESO Y BLOQUEADO:</b> N° <b>' + esc(an.numeroCertificado) + '</b>. ' +
            'Impreso por única vez el <b>' + esc(solCert.fechaImpresion || '—') + '</b> (' + esc(solCert.impresoPor || '') + '). ' +
            'No se permite volver a imprimir.' +
          '</div>';
        btnImp.disabled = true; btnImp.style.opacity = '0.5'; btnImp.style.cursor = 'not-allowed';
        btnImp.style.background = '#b3261e'; btnImp.style.color = '#fff';
        btnImp.textContent = '🔒 Ya impreso (Bloqueado)';
        btnImp.title = 'El certificado solo puede imprimirse una única vez y ya fue impreso.';
        $('salida').className = 'impresion-bloqueada';
      } else if (!puedeImprimirRol) {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#e6f4ea;border-color:#34a853;color:#137333">' +
            '✅ <b>Certificado Oficial APROBADO:</b> N° <b>' + esc(an.numeroCertificado) + '</b>. ' +
            '(Solo el rol <b>Administrativo</b> o <b>Directivo</b> de la institución tiene habilitado el botón de impresión).' +
          '</div>';
        btnImp.disabled = true; btnImp.style.opacity = '0.5'; btnImp.style.cursor = 'not-allowed';
        btnImp.textContent = 'Imprimir';
        btnImp.title = 'Solo el Administrativo o el Directivo de la escuela puede imprimir el certificado';
        $('salida').className = 'impresion-bloqueada';
      } else {
        bannerBox.innerHTML =
          '<div class="banner-aviso-analitico" style="background:#e6f4ea;border-color:#34a853;color:#137333">' +
            '✅ <b>Certificado Oficial APROBADO:</b> N° <b>' + esc(an.numeroCertificado) + '</b>. ' +
            'Habilitado para <b>una única impresión</b> por parte del Administrativo / Directivo.' +
          '</div>';
        btnImp.disabled = false; btnImp.style.opacity = '1'; btnImp.style.cursor = 'pointer';
        btnImp.style.background = 'var(--azul)'; btnImp.style.color = '#fff';
        btnImp.textContent = '🖨️ Imprimir (Única vez)';
        btnImp.title = 'Imprimir certificado oficial por única vez';
        $('salida').className = '';
      }

      $('salida').innerHTML = armarAnalitico(an);
    } catch (e) { problema(e); $('salida').innerHTML = ''; }
  });

  $('imprimir').addEventListener('click', async function () {
    if ($('imprimir').disabled) return;
    var doc = $('selEst').value;
    if (!confirm('¿Confirmás la impresión del Certificado Oficial?\n\nATENCIÓN: Solo se puede imprimir UNA SOLA VEZ y luego el certificado quedará bloqueado.')) {
      return;
    }
    try {
      $('imprimir').disabled = true;
      await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/analitico/imprimir', 'POST', { documento: doc });
      window.print();
      avisar('Certificado impreso y bloqueado.', 'ok');
      $('generar').click();
    } catch (e) {
      problema(e);
      $('generar').click();
    }
  });
  setTimeout(function () { if ($('generar')) $('generar').click(); }, 50);
}

function armarAnalitico(r) {
  var d = r.documentoOficial;
  if (!d) { return armarAnaliticoCeldas(r); }

  var anioDef = (d.fechaEmision && /^\d{4}/.test(d.fechaEmision)) ? d.fechaEmision.slice(0, 4) : String(new Date().getFullYear());
  var cueDef = String(d.cue || (estado.curso && estado.curso.cue) || '380000600').replace(/\D/g, '');
  if (cueDef.length === 7) cueDef = cueDef + '00';
  var nroLimpio = (d.certNro && d.certNro.indexOf('_') === -1) ? d.certNro : '';
  var certNroFormateado = nroLimpio || (anioDef + '-' + cueDef + '-00001');
  var watermark = d.esBorrador
    ? '<div class="marca-agua-borrador-oficial">BORRADOR<br>NO VÁLIDO</div>' : '';
  var escudoFondo = '<img src="/img/escudo_nacional.png?v=20261105b" class="hoja-fondo-escudo" alt="" aria-hidden="true">';

  var filasModulos = (d.trayecto || []).map(function (m) {
    var modAprobado = m.condicion ? (m.condicion === 'Aprobado') : (Boolean(m.nota && m.nota !== 'AUS') && parseFloat(m.nota) >= 7);
    var mesAnioVal = modAprobado ? (m.mesAnio || ('12/' + (d.cohorte || anioDef))) : '';
    var estabVal = m.establecimiento || (modAprobado ? (d.establecimiento || '') : '');
    return '<tr>' +
      '<td style="text-align:center">'                  + esc(m.nro)        + '</td>' +
      '<td>'                                             + esc(m.modulo)     + '</td>' +
      '<td style="text-align:center">'                  + esc(m.tipo)       + '</td>' +
      '<td style="text-align:center">'                  + esc(m.periodo)    + '</td>' +
      '<td style="text-align:center;font-weight:bold">' + esc(m.nota || '') + '</td>' +
      '<td style="text-align:center">'                  + esc(m.enLetras || '') + '</td>' +
      '<td style="text-align:center">'                  + esc(mesAnioVal)   + '</td>' +
      '<td style="text-align:center">'                  + esc(estabVal)     + '</td>' +
    '</tr>';
  }).join('');

  return _hojaOficialHTML(d, certNroFormateado, watermark, escudoFondo, filasModulos);
}

// ── Función interna compartida ──────────────────────────────────────────────
function _hojaOficialHTML(d, certNroFormateado, watermark, escudoFondo, filasModulos) {
  var idCursoQr = (estado.curso && estado.curso.id) ? estado.curso.id : 'curso-peluquero-ep6-demo';
  var validarPath = '/validar?nro=' + encodeURIComponent(certNroFormateado) +
                    '&dni=' + encodeURIComponent(String(d.dniFormateado || '').replace(/\./g, '')) +
                    '&curso=' + encodeURIComponent(idCursoQr);
  var validarFullUrl = window.location.origin + validarPath;
  var qrImgSrc = 'https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=' + encodeURIComponent(validarFullUrl);
  var qrHtml = '<a href="' + esc(validarPath) + '" target="_blank" title="Verificar validez del título">' +
    '<img src="' + esc(qrImgSrc) + '" alt="QR Validación" style="width:82px;height:82px;border:1px solid #222;padding:2px;background:#fff" ' +
    'onerror="this.outerHTML=\'<div class=hoja-qr-placeholder style=border-color:#000;font-weight:bold>VERIFICAR<br>VALIDEZ<br>QR</div>\'">' +
    '</a>';

  // Formatear fecha de otorgamiento ("el día X del mes de MES del año YYYY")
  var mesesNombres = [
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
  ];
  var hoy = new Date();
  var diaOtorgado = String(hoy.getDate()).padStart(2, '0');
  var mesOtorgado = mesesNombres[hoy.getMonth()];
  var anioOtorgado = String(hoy.getFullYear());
  if (d.fechaEmision && /^\d{4}-\d{2}-\d{2}$/.test(d.fechaEmision)) {
    var partesF = d.fechaEmision.split('-');
    anioOtorgado = partesF[0];
    mesOtorgado = mesesNombres[parseInt(partesF[1], 10) - 1] || mesOtorgado;
    diaOtorgado = partesF[2];
  }

  var cohorteStr = d.cohorte || anioOtorgado;
  var ofertaStr = d.oferta || (estado.curso && estado.curso.oferta) || 'FORMACIÓN PROFESIONAL';
  var normaStr = d.normaJurisdiccional || 'Res. Ministerial';

  return '<div class="hoja-oficial">' +
    escudoFondo + watermark +
    '<div class="hoja-cabecera">' +
      '<div class="hoja-qr">' + qrHtml + '</div>' +
      '<div class="hoja-escudo-bloque">' +
        '<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px">' +
          '<span class="hoja-republica" style="margin:0">República</span>' +
          '<img src="/img/escudo_nacional.png?v=20261105f" alt="Escudo Nacional" style="height:68px;display:block;margin:0;mix-blend-mode:multiply;filter:contrast(1.06) brightness(1.04)">' +
          '<span class="hoja-republica" style="margin:0">Argentina</span>' +
        '</div>' +
        '<p class="hoja-ley-nac">LEY DE EDUCACIÓN NACIONAL N° 26.206</p>' +
        '<p class="hoja-provincia">PROVINCIA DE JUJUY</p>' +
        '<p class="hoja-ley-nac" style="margin-top:6px">LEY PROVINCIAL N° 5807</p>' +
        '<p class="hoja-ley-nac">MINISTERIO DE EDUCACIÓN</p>' +
        '<p class="hoja-ley-nac">SECRETARÍA DE GESTIÓN EDUCATIVA</p>' +
        '<p class="hoja-ley-nac">DIRECCIÓN DE TÍTULOS</p>' +
      '</div>' +
      '<div class="hoja-cert-nro">' + esc(certNroFormateado) + '</div>' +
    '</div>' +
    '<div class="hoja-titulo-doc">CERTIFICADO</div>' +
    '<p class="hoja-parrafo">' +
      'La autoridad del establecimiento educativo, <b>' + esc(d.establecimiento) + '</b> CUE ' +
      esc(d.cue) + ', ubicado en <b>' + esc(d.domicilio) + '</b>, de <b>' + esc(d.localidad) +
      '</b>, provincia de JUJUY, certifica que <b>' + esc(d.estudianteNombre) + '</b>, con lugar ' +
      'de nacimiento en ' + esc(d.lugarNac) + ', el ' + esc(d.fechaNac) +
      ', Tipo de Documento ' + esc(d.tipoDoc) + ' N° <b>' + esc(d.dniFormateado) + '</b>' +
      ', aprobó los espacios curriculares que con sus respectivas calificaciones a continuación se expresan:' +
    '</p>' +
    '<div class="hoja-seccion">TRAYECTO CURRICULAR</div>' +
    '<table class="tabla-trayecto">' +
      '<thead><tr>' +
        '<th style="width:26px">N°</th>' +
        '<th>Módulo / Espacio Curricular</th>' +
        '<th style="width:68px">Tipo</th>' +
        '<th style="width:110px">Período</th>' +
        '<th style="width:38px">Nota</th>' +
        '<th style="width:68px">En letras</th>' +
        '<th style="width:62px">Mes / Año</th>' +
        '<th style="width:135px">Establecimiento</th>' +
      '</tr></thead>' +
      '<tbody>' +
        filasModulos +
        '<tr style="font-weight:bold;color:#000;background:transparent">' +
          '<td colspan="4" style="text-align:left;color:#000">Nota de la Trayectoria (Promedio de Módulos)</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.promedioTrayectoria || '—') + '</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.promedioTrayectoriaLetras || '—') + '</td>' +
          '<td colspan="2" style="text-align:center;color:#000">Carga horaria: ' + esc(d.cargaHorariaTotal.reloj) + ' hs reloj / ' + esc(d.cargaHorariaTotal.cat) + ' hs cát.</td>' +
        '</tr>' +
        '<tr style="font-weight:bold;color:#000;background:transparent">' +
          '<td colspan="4" style="text-align:left;color:#000">Calificación Final (Examen Final)</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.notaFinal || '—') + '</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.notaFinalLetras || '—') + '</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.fechaEgreso || '—') + '</td>' +
          '<td style="text-align:center;color:#000">' + esc(d.establecimiento || '') + '</td>' +
        '</tr>' +
      '</tbody>' +
    '</table>' +

    // ── Parte inferior oficial del Certificado / Título (según modelo provincial) ──
    '<div class="hoja-pie-legal" style="margin-top:16px;font-size:11.5px;line-height:1.5;position:relative;z-index:2">' +
      '<p style="margin:2px 0"><b>Cohorte:</b> ' + esc(cohorteStr) + ' &nbsp;·&nbsp; <b>Fecha de Egreso (Examen Final):</b> ' + esc(d.fechaEgreso || '—') + ' &nbsp;·&nbsp; <b>Acredita con:</b> ' + esc(d.acreditaCon || 'Primaria Completa') + '</p>' +
      '<p style="margin:2px 0 10px"><b>Observaciones:</b> ' + esc(d.observaciones || '—') + '</p>' +
      '<p style="margin:8px 0;text-align:justify">' +
        '<b>' + esc(d.estudianteNombre) + '</b>, con tipo de documento ' + esc(d.tipoDoc) + ' N° <b>' + esc(d.dniFormateado) + '</b>, ' +
        'aprobó los espacios curriculares expresados anteriormente de los estudios conducentes al certificado de ' +
        '<b>' + esc(ofertaStr) + '</b> que se corresponde con <b>EDUCACIÓN TÉCNICO PROFESIONAL</b>.' +
      '</p>' +
      '<p style="margin:3px 0"><b>NORMA JURISD. DE APROB. PLAN DE ESTUDIOS / DISEÑO CURRICULAR:</b> ' + esc(normaStr) + '</p>' +
      '<p style="margin:3px 0"><b>Libro Actas N°</b> ' + esc(d.libro) + ' &nbsp; <b>Folio N°</b> ' + esc(d.folio) + '</p>' +
      '<p style="margin:6px 0 18px"><b>Otorgado en la localidad de ' + esc(d.localidad) + ', provincia de JUJUY, República Argentina, el día ' + esc(diaOtorgado) + ' del mes de ' + esc(mesOtorgado) + ' del año ' + esc(anioOtorgado) + '</b></p>' +

      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:26px;align-items:start">' +
        '<div style="font-size:11px;line-height:1.35">' +
          '<div style="border-top:1px solid #333;width:220px;margin-bottom:4px"></div>' +
          '<b>Directora / Director</b><br>' +
          '<span>' + esc(d.establecimiento) + '</span>' +
        '</div>' +
        '<div style="font-size:11px;line-height:1.35">' +
          '<div style="font-size:12px;font-weight:bold;margin-bottom:1px">REINOSO TORRES Tatiana Marisel</div>' +
          '<b>Directora</b><br>' +
          '<span>Dirección de Títulos</span><br>' +
          '<span>Ministerio de Educación</span>' +
        '</div>' +
      '</div>' +
    '</div>' +
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
// BANDEJA DE ENTRADA CENTRALIZADA · DIRECCIÓN DE TÍTULOS (ROL 'titulos')
// =========================================================================

async function verBandejaTitulos() {
  estado.curso = null;
  estado.datos = null;
  _guardarRutaLocal('bandeja', '', '');
  _actualizarBarraEscuela();
  $('migas').hidden = (estado.sesion && estado.sesion.esTitulos);
  if (!$('migas').hidden) {
    $('volver').textContent = '← Volver a los cursos';
  }
  $('main').innerHTML = '<div class="cargando">Cargando bandeja de pedidos de títulos…</div>';

  try {
    var r = await llamar('/api/solicitudes');
    var solicitudes = r.solicitudes || [];
    estado.solicitudesBandeja = solicitudes;
    var esDirTitulos = Boolean(estado.sesion && estado.sesion.esDirectoraTitulos);
    var puedeAprobarBandeja = Boolean(estado.sesion && estado.sesion.puedeAprobarTitulos !== false && !esDirTitulos);
    var puedeVerRacBandeja = Boolean(!estado.sesion || (estado.sesion.puedeVerRac !== false && !esDirTitulos));

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

      var checkHtml = (puedeAprobarBandeja && s.estado !== 'Aprobado')
        ? '<input type="checkbox" class="chk-sol" value="' + esc(s.id) + '">'
        : (s.estado === 'Aprobado' ? '<span style="color:#137333">✓</span>' : '—');

      var detalleEstado = '';
      if (s.estado === 'Aprobado') {
        var aprAutor = s.aprobadoPor ? (s.aprobadoPor + (s.aprobadoEmail ? ' (' + s.aprobadoEmail + ')' : '')) : (s.aprobadoEmail || 'Dirección de Títulos');
        var aprFec = s.fechaHoraAprobacion || s.fechaAprobacion || '';
        detalleEstado =
          '<div style="color:#137333;font-size:12px;font-weight:bold">Cert. ' + esc(s.numeroCertificado) + ' (' + esc(s.fechaAprobacion) + ')</div>' +
          '<div style="font-size:11px;color:#135c2d;margin-top:2px">✅ <b>Aprobó:</b> ' + esc(aprAutor) + (aprFec ? ' · ' + esc(aprFec) : '') + '</div>';
      } else if (s.estado === 'Observado') {
        var obsAutor = s.observadoPor ? (s.observadoPor + (s.observadoEmail ? ' (' + s.observadoEmail + ')' : '')) : (s.observadoEmail || 'Dirección de Títulos');
        var obsFec = s.fechaObservacion || '';
        detalleEstado =
          '<div class="alerta-observacion"><b>Motivo:</b> ' + esc(s.motivoObservacion) +
            '<div style="font-size:11px;color:#5f6368;margin-top:3px">👤 <b>Observó:</b> ' + esc(obsAutor) + (obsFec ? ' · ' + esc(obsFec) : '') + '</div>' +
          '</div>';
      } else if (s.usuarioSolicitante || s.solicitadoPorNombre) {
        var solAutor = s.solicitadoPorNombre ? (s.solicitadoPorNombre + (s.usuarioSolicitante ? ' (' + s.usuarioSolicitante + ')' : '')) : s.usuarioSolicitante;
        detalleEstado = '<div style="font-size:11px;color:#5f6368;margin-top:2px">📤 <b>Solicitó:</b> ' + esc(solAutor) + '</div>';
      }

      var accionesHtml = '';
      if (puedeAprobarBandeja) {
        if (s.estado !== 'Aprobado') {
          accionesHtml =
            '<button class="boton" style="padding:4px 10px;font-size:12px" onclick="abrirModalAprobar(' + escJsArg(s.id) + ', ' + escJsArg(s.estudiante) + ')">Aprobar</button> ' +
            '<button class="boton suave" style="padding:4px 10px;font-size:12px;color:var(--mal);border-color:var(--mal)" onclick="abrirModalObservar(' + escJsArg(s.id) + ', ' + escJsArg(s.estudiante) + ')">Observar</button>';
        } else {
          accionesHtml = '<span style="color:var(--suave);font-size:12px">Calificaciones congeladas</span>';
        }
      } else {
        accionesHtml = '<span style="color:var(--suave);font-size:12px">Consulta de estado</span>';
      }
      var verRacBtn = (puedeVerRacBandeja && s.idCurso)
        ? ' <button class="boton suave" style="padding:4px 8px;font-size:12px" onclick="abrirCurso(' + escJsArg(s.idCurso) + ', \'notas\')">Ver RAC</button>'
        : '';
      var histCount = (s.historial && s.historial.length) ? s.historial.length : 1;
      var verHistBtn = ' <button class="boton suave" style="padding:4px 8px;font-size:12px" title="Ver historial de quién solicitó, observó o aprobó" onclick="verHistorialSolicitudBandeja(' + escJsArg(s.id) + ')">🕒 Historial (' + histCount + ')</button>';

      return '<tr>' +
        '<td style="text-align:center">' + checkHtml + '</td>' +
        '<td><b>' + esc(s.institucion) + '</b><br><small style="color:var(--suave)">CUE ' + esc(s.cue) + '</small></td>' +
        '<td>' + esc(s.oferta) + '<br><small style="color:var(--suave)">' + esc(s.ciclo) + '</small></td>' +
        '<td><b>' + esc(s.estudiante) + '</b><br><small>DNI ' + esc(s.documento) + '</small></td>' +
        '<td style="text-align:center;font-size:12px">' + esc(s.fechaSolicitud) + '</td>' +
        '<td style="text-align:center"><span class="badge-estado ' + badgeClass + '">' + esc(s.estado) + '</span>' + detalleEstado + '</td>' +
        '<td style="text-align:center;white-space:nowrap">' +
          accionesHtml +
          verRacBtn +
          verHistBtn +
          ' <button class="boton suave" style="padding:4px 8px;font-size:12px" onclick="inspeccionarAnaliticoModal(' + escJsArg(s.idCurso) + ', ' + escJsArg(s.documento) + ')">Ver Analítico</button>' +
        '</td>' +
      '</tr>';
    }).join('');

    $('main').innerHTML =
      '<h1>Bandeja de Entrada · Dirección de Títulos</h1>' +
      '<p style="color:var(--suave)">' + (esDirTitulos ? 'Supervisión de pedidos pendientes, observados y aprobados de Formación Profesional (modo consulta sin aprobación ni acceso a RAC).' : 'Gestión, revisión centralizada y emisión de certificados de Formación Profesional.') + '</p>' +

      '<div class="acciones" style="margin:12px 0">' +
        (puedeVerRacBandeja ? '<button class="boton" id="btnVerCursosRac" style="background:#1F4E78">📚 Ver Cursos y RAC</button>' : '') +
        '<button class="boton" id="btnDashboardTitulos" style="background:#1F4E78">📊 Dashboard de Estadísticas</button>' +
        '<button class="boton suave" id="btnNominaTitulos">📋 Nómina de Egresados</button>' +
      '</div>' +

      '<div style="display:flex;gap:12px;margin:16px 0;flex-wrap:wrap">' +
        '<button class="boton ' + (estado.filtroBandeja === 'Pendiente' ? '' : 'suave') + '" id="f_pen">Pendientes (' + nPendientes + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Observado' ? '' : 'suave') + '" id="f_obs">Observados (' + nObservados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Aprobado' ? '' : 'suave') + '" id="f_apr">Aprobados (' + nAprobados + ')</button>' +
        '<button class="boton ' + (estado.filtroBandeja === 'Todos' ? '' : 'suave') + '" id="f_tod">Todos (' + solicitudes.length + ')</button>' +
      '</div>' +

      (puedeAprobarBandeja
        ? '<div class="acciones" style="background:#fff;padding:10px 14px;border:1px solid var(--borde);border-radius:6px">' +
            '<label style="display:flex;align-items:center;gap:6px;font-weight:600">' +
              '<input type="checkbox" id="chkTodos"> Seleccionar todos' +
            '</label>' +
            '<button class="boton" id="btnAprobarLote" disabled>Aprobar seleccionados en lote</button>' +
          '</div>'
        : '') +

      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:36px;text-align:center">✓</th>' +
        '<th>Institución</th><th>Curso</th><th>Estudiante</th>' +
        '<th style="width:130px;text-align:center">Fecha Pedido</th>' +
        '<th style="width:130px;text-align:center">Estado</th>' +
        '<th style="width:290px;text-align:center">Acciones</th>' +
      '</tr></thead><tbody>' + (filasHtml || '<tr><td colspan="7" class="vacio">No hay pedidos en esta sección.</td></tr>') + '</tbody></table></div>';

    if ($('btnVerCursosRac')) $('btnVerCursosRac').addEventListener('click', verCursos);
    if ($('btnNominaTitulos')) $('btnNominaTitulos').addEventListener('click', function () { verNominaEscuela(); });
    if ($('btnDashboardTitulos')) $('btnDashboardTitulos').addEventListener('click', verResumen);

    $('f_pen').addEventListener('click', function () { estado.filtroBandeja = 'Pendiente'; try { localStorage.setItem('lm_filtro_bandeja', 'Pendiente'); } catch (e) {} verBandejaTitulos(); });
    $('f_obs').addEventListener('click', function () { estado.filtroBandeja = 'Observado'; try { localStorage.setItem('lm_filtro_bandeja', 'Observado'); } catch (e) {} verBandejaTitulos(); });
    $('f_apr').addEventListener('click', function () { estado.filtroBandeja = 'Aprobado'; try { localStorage.setItem('lm_filtro_bandeja', 'Aprobado'); } catch (e) {} verBandejaTitulos(); });
    $('f_tod').addEventListener('click', function () { estado.filtroBandeja = 'Todos'; try { localStorage.setItem('lm_filtro_bandeja', 'Todos'); } catch (e) {} verBandejaTitulos(); });

    var chkTodos = $('chkTodos');
    var chks = document.querySelectorAll('.chk-sol');
    if (chkTodos) {
      chkTodos.addEventListener('change', function () {
        chks.forEach(function (c) { c.checked = chkTodos.checked; });
        actualizarBotonLote();
      });
    }

    chks.forEach(function (c) {
      c.addEventListener('change', actualizarBotonLote);
    });

    function actualizarBotonLote() {
      var seleccionados = Array.from(document.querySelectorAll('.chk-sol:checked'));
      var btn = $('btnAprobarLote');
      if (!btn) return;
      btn.disabled = seleccionados.length === 0;
      btn.textContent = 'Aprobar seleccionados en lote (' + seleccionados.length + ')';
    }

    if ($('btnAprobarLote')) {
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
    }

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
        'Número de Certificado (dejar vacío para correlativo automático AÑO-CUE-00001):' +
        '<input id="m_numCert" style="width:100%;margin-top:6px" placeholder="Ej: 2026-3800006-00001">' +
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

function abrirModalObservar(idSol, nombre, desdeCurso) {
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
      if (desdeCurso && estado.curso && estado.curso.id) {
        abrirCurso(estado.curso.id, 'solicitudes');
      } else {
        verBandejaTitulos();
      }
    } catch (e) {
      problema(e);
    }
  });
}

function cerrarModal() {
  var m = $('modalActivo');
  if (m) m.remove();
}

function verHistorialSolicitudBandeja(idSol) {
  var sols = estado.solicitudesBandeja || [];
  var sol = sols.find(function (x) { return x.id === idSol; });
  if (!sol) return;
  var titulo = (sol.estudiante || 'Estudiante') + ' (DNI ' + (sol.documento || '—') + ') · ' + (sol.oferta || '');
  mostrarModalHistorialSolicitud(titulo, sol.historial || [], sol);
}

function verHistorialEstudianteCurso(documento) {
  if (!estado.datos || !estado.datos.estudiantes) return;
  var es = estado.datos.estudiantes.find(function (x) { return String(x.documento) === String(documento); });
  if (!es || !es.solicitudCertificado) return;
  var sol = es.solicitudCertificado;
  var titulo = (es.apellido || '') + ', ' + (es.nombres || '') + ' (DNI ' + (es.documento || '—') + ')';
  mostrarModalHistorialSolicitud(titulo, sol.historial || [], sol);
}

function mostrarModalHistorialSolicitud(tituloEst, historial, solObj) {
  cerrarModal();
  var lista = Array.isArray(historial) ? historial : [];
  var filas = lista.length
    ? lista.map(function (h, idx) {
        var colorAcc = '#163a5f';
        var accLow = String(h.accion || '').toLowerCase();
        if (accLow.indexOf('aprob') !== -1) colorAcc = '#137333';
        else if (accLow.indexOf('observ') !== -1) colorAcc = '#b3261e';
        var autorStr = h.usuario ? (h.usuario + (h.email && h.email !== h.usuario ? ' (' + h.email + ')' : '')) : (h.email || '—');
        return '<tr>' +
          '<td style="text-align:center;font-weight:700">' + (idx + 1) + '</td>' +
          '<td style="white-space:nowrap;font-size:12px">' + esc(h.fecha || '—') + '</td>' +
          '<td style="font-weight:700;color:' + colorAcc + '">' + esc(h.accion || '—') + '</td>' +
          '<td><b>' + esc(autorStr) + '</b>' + (h.rol ? '<br><small style="color:var(--suave)">Rol: ' + esc(h.rol) + '</small>' : '') + '</td>' +
          '<td style="font-size:12.5px">' + esc(h.detalle || '—') + '</td>' +
        '</tr>';
      }).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--suave);padding:14px">Sin movimientos registrados en el historial.</td></tr>';

  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja" style="max-width:780px;max-height:85vh;overflow:auto">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
        '<h2 style="margin:0">🕒 Historial de Revisión y Auditoría de Títulos</h2>' +
        '<button class="boton suave" onclick="cerrarModal()">Cerrar ✕</button>' +
      '</div>' +
      '<p style="margin:0 0 12px;font-size:13px;color:var(--suave)">Estudiante: <b>' + esc(tituloEst) + '</b>' +
        (solObj && solObj.numeroCertificado ? ' · Certificado N° <b>' + esc(solObj.numeroCertificado) + '</b>' : '') +
      '</p>' +
      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th style="width:40px">#</th>' +
        '<th style="width:135px">Fecha y Hora</th>' +
        '<th style="width:160px">Acción</th>' +
        '<th style="width:200px">Realizado por (Usuario / Rol)</th>' +
        '<th>Detalle / Motivo</th>' +
      '</tr></thead><tbody>' + filas + '</tbody></table></div>' +
    '</div>';
  document.body.appendChild(modal);
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

// Helper para opciones de Referencial de Ingreso (curso) y Acreditación de Ingreso (alumno) según la Oferta Formativa
function esCursoElectricistaOInstaladorRenovable(oferta) {
  var s = String(oferta || '').toLowerCase();
  if (s.normalize) s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  return (s.indexOf('electricista') !== -1 && s.indexOf('inmueble') !== -1) ||
         (s.indexOf('instalador') !== -1 && s.indexOf('sistema') !== -1 && s.indexOf('electric') !== -1);
}

function obtenerOpcionesReferencialIngreso(oferta) {
  var ops = ['Primaria Completa', 'Secundaria Completa', 'CB Completo'];
  if (esCursoElectricistaOInstaladorRenovable(oferta)) {
    ops.push('Montador Electricista Domiciliario');
  }
  return ops;
}

function obtenerOpcionesAcreditacion(oferta) {
  var ops = ['Primaria Completa', 'Secundaria Completa', 'CB Completo', 'Superior Completa'];
  if (esCursoElectricistaOInstaladorRenovable(oferta)) {
    ops.push('Montador Electricista Domiciliario');
  }
  return ops;
}

// Modal para cargar un nuevo alumno en el curso actual (Rol Administrativo / Dirección)
function mostrarModalNuevoEstudiante() {
  var ofertaActual = (estado.datos && estado.datos.encabezado && estado.datos.encabezado.oferta) ||
                     (estado.curso && estado.curso.oferta) || '';
  var opcionesAcr = obtenerOpcionesAcreditacion(ofertaActual);
  var opcionesAcrHtml = opcionesAcr.map(function (op) {
    return '<option value="' + esc(op) + '">' + esc(op) + '</option>';
  }).join('');

  var modal = document.createElement('div');
  modal.className = 'modal-backdrop';
  modal.id = 'modalActivo';
  modal.innerHTML =
    '<div class="modal-caja" style="max-width:520px">' +
      '<h2>+ Cargar Alumno en el Curso</h2>' +
      '<p style="font-size:12px;color:var(--suave);margin-top:2px">Completá los datos personales del estudiante para incorporarlo al Registro Anual de Calificaciones y al Acta de Examen.</p>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px">' +
        '<label style="display:block;font-size:12px;font-weight:600">Apellido(s) *' +
          '<input id="ne_apellido" style="width:100%;margin-top:4px" placeholder="Ej: GÓMEZ">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Nombre(s) *' +
          '<input id="ne_nombres" style="width:100%;margin-top:4px" placeholder="Ej: Juan Carlos">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Tipo Doc.' +
          '<select id="ne_tipodoc" style="width:100%;margin-top:4px"><option value="DNI">DNI</option><option value="CI">CI</option><option value="Pasaporte">Pasaporte</option></select>' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">N° de Documento (DNI) *' +
          '<input id="ne_documento" style="width:100%;margin-top:4px" placeholder="Ej: 42123456">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Fecha de Nacimiento' +
          '<input id="ne_fechanac" style="width:100%;margin-top:4px" placeholder="dd/mm/aaaa">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Folio N° (opcional)' +
          '<input id="ne_folio" style="width:100%;margin-top:4px" placeholder="Autocompletar">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Lugar de Nac. · Provincia' +
          '<input id="ne_provincia" style="width:100%;margin-top:4px" value="Jujuy">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600">Lugar de Nac. · País' +
          '<input id="ne_pais" style="width:100%;margin-top:4px" value="Argentina">' +
        '</label>' +
        '<label style="display:block;font-size:12px;font-weight:600;grid-column:1 / -1">Acreditación de Ingreso (Acredita con) *' +
          '<select id="ne_acreditacon" style="width:100%;margin-top:4px">' + opcionesAcrHtml + '</select>' +
        '</label>' +
      '</div>' +
      '<div class="acciones" style="justify-content:flex-end;margin-top:16px">' +
        '<button type="button" class="boton suave" onclick="cerrarModal()">Cancelar</button>' +
        '<button type="button" class="boton" style="background:#137333" id="btnGuardarEstudiante">Guardar Alumno</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(modal);
  if ($('ne_apellido')) $('ne_apellido').focus();

  $('btnGuardarEstudiante').addEventListener('click', async function () {
    var ape = $('ne_apellido').value.trim();
    var nom = $('ne_nombres').value.trim();
    var doc = $('ne_documento').value.trim();
    if (!ape || !nom || !doc) {
      avisar('Completá Apellido, Nombres y N° de Documento (DNI).', 'error');
      return;
    }
    var acrVal = $('ne_acreditacon') ? $('ne_acreditacon').value : 'Primaria Completa';
    $('btnGuardarEstudiante').disabled = true;
    try {
      var rEst = await llamar('/api/curso/' + encodeURIComponent(estado.curso.id) + '/estudiante', 'POST', {
        apellido: ape,
        nombres: nom,
        tipoDoc: $('ne_tipodoc').value,
        documento: doc,
        fechaNac: $('ne_fechanac').value.trim(),
        provincia: $('ne_provincia').value.trim(),
        pais: $('ne_pais').value.trim(),
        folio: $('ne_folio').value.trim(),
        acreditaCon: acrVal,
        nivel: acrVal
      });
      if (rEst && rEst.paquete) _guardarPaqueteLocal(rEst.paquete);
      cerrarModal();
      avisar('¡Alumno ' + ape.toUpperCase() + ', ' + nom + ' cargado con éxito!', 'ok');
      abrirCurso(estado.curso.id, 'notas');
    } catch (e) {
      problema(e);
      $('btnGuardarEstudiante').disabled = false;
    }
  });
}

// Modal para crear curso
function mostrarModalNuevoCurso() {
  var modal = document.createElement('div');
  modal.className = 'panel';
  modal.style.maxWidth = '580px';
  modal.style.margin = '20px auto';
  modal.style.border = '1px solid var(--borde)';
  modal.style.borderRadius = '8px';
  modal.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';

  var cueDef = (estado.sesion && estado.sesion.cues && estado.sesion.cues.length) ? estado.sesion.cues[0] : '';
  var instDef = (estado.institucionUsuario && estado.institucionUsuario.nombre) ? estado.institucionUsuario.nombre : '';
  var locDef = (estado.institucionUsuario && estado.institucionUsuario.localidad) ? estado.institucionUsuario.localidad : '';

  modal.innerHTML =
    '<h2>+ Registrar Nuevo Curso</h2>' +
    '<div style="display:flex;flex-direction:column;gap:10px;margin-top:12px">' +
      '<label><b>Institución *</b> <input id="nc_inst" placeholder="Ej: Escuela Profesional Nº 6" value="' + esc(instDef) + '"></label>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>CUE *</b> <input id="nc_cue" placeholder="Ej: 3800006" value="' + esc(cueDef) + '"></label>' +
        '<label><b>Localidad</b> <input id="nc_localidad" placeholder="Ej: San Salvador de Jujuy" value="' + esc(locDef) + '"></label>' +
      '</div>' +
      '<label><b>Domicilio</b> <input id="nc_domicilio" placeholder="Ej: Av. Fascio 1050" value=""></label>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>Oferta Formativa *</b> <input id="nc_oferta" placeholder="Ej: Electricista en Inmueble / Peluquero" value=""></label>' +
        '<label><b>Familia Profesional</b> <input id="nc_familia" placeholder="Ej: Textil - Indumentaria / Estética Profesional" value=""></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">' +
        '<label><b>Ciclo</b> <input id="nc_ciclo" placeholder="2026" value="2026"></label>' +
        '<label><b>Turno</b> <select id="nc_turno"><option value="Mañana">Mañana</option><option value="Tarde">Tarde</option><option value="Vespertino" selected>Vespertino</option></select></label>' +
        '<label><b>Curso / División</b> <input id="nc_division" placeholder=\'1° "U"\' value=\'1° "U"\'></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>Duración de los Estudios</b> <input id="nc_duracion" placeholder="Ej: 2 Cuatrimestres / 1 Cuatrimestre" value="2 Cuatrimestres"></label>' +
        '<label><b>Docente</b> <input id="nc_docente" placeholder="Apellido y Nombre del docente" value=""></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>Fecha de finalización 1° Cuatrimestre</b> <input type="date" id="nc_fecha_fin_1c"></label>' +
        '<label><b>Fecha de finalización 2° Cuatrimestre</b> <input type="date" id="nc_fecha_fin_2c"></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr 2fr;gap:10px">' +
        '<label><b>Horas Cátedras</b> <input id="nc_hscat" placeholder="768" value="768"></label>' +
        '<label><b>Nivel</b> <input id="nc_nivel" placeholder="II" value="II"></label>' +
        '<label><b>Certificación</b> <input id="nc_certificacion" placeholder="Diseño Curricular Jurisdiccional" value="Diseño Curricular Jurisdiccional"></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>Norma Jurisd. de Aprobación, Res. N°</b> <input id="nc_norma" placeholder="Ej: 4006-E/2023" value="4006-E/2023"></label>' +
        '<label><b>Res. Diseño Curricular y/o Plan de Estudio N°</b> <input id="nc_disenio" placeholder="Ej: 661-E/2022" value="661-E/2022"></label>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
        '<label><b>Validez Nacional R.M.E N°</b> <input id="nc_validez" placeholder="Ej: 530/23" value="530/23"></label>' +
        '<label><b>Disposición</b> <input id="nc_disposicion" placeholder="-" value="-"></label>' +
      '</div>' +
      '<div style="background:#f8fafc;border:1px solid var(--borde);border-radius:6px;padding:10px">' +
        '<div style="font-size:12px;font-weight:700;margin-bottom:6px;color:var(--azul)">Referencial de ingreso (podés marcar uno o más):</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:12px;font-size:13px">' +
          '<label style="display:inline-flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" class="nc_chk_ref" value="Primaria Completa" checked> Primaria Completa</label>' +
          '<label style="display:inline-flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" class="nc_chk_ref" value="Secundaria Completa"> Secundaria Completa</label>' +
          '<label style="display:inline-flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" class="nc_chk_ref" value="CB Completo"> CB Completo</label>' +
          '<label id="lbl_ref_montador" style="display:none;align-items:center;gap:5px;cursor:pointer;color:#137333;font-weight:600"><input type="checkbox" class="nc_chk_ref" id="chk_ref_montador" value="Montador Electricista Domiciliario"> Montador Electricista Domiciliario</label>' +
        '</div>' +
      '</div>' +
      '<label>ID del archivo de Google Drive <input id="nc_id" placeholder="Opcional (se genera automático si queda vacío)"></label>' +
      '<div class="acciones" style="justify-content:flex-end;margin-top:14px">' +
        '<button class="boton suave" id="nc_cancelar">Cancelar</button>' +
        '<button class="boton" id="nc_guardar">Guardar curso</button>' +
      '</div>' +
    '</div>';

  $('main').innerHTML = '';
  $('main').appendChild(modal);

  $('nc_oferta').addEventListener('input', function () {
    var mostrarMontador = esCursoElectricistaOInstaladorRenovable($('nc_oferta').value);
    if ($('lbl_ref_montador')) $('lbl_ref_montador').style.display = mostrarMontador ? 'inline-flex' : 'none';
    if (!mostrarMontador) {
      if ($('chk_ref_montador')) $('chk_ref_montador').checked = false;
    }
  });

  $('nc_cancelar').addEventListener('click', verCursos);
  $('nc_guardar').addEventListener('click', async function () {
    var instVal = $('nc_inst').value.trim();
    var cueVal = $('nc_cue').value.trim();
    var ofertaVal = $('nc_oferta').value.trim();
    if (!instVal || !cueVal || !ofertaVal) {
      alert('Por favor completá los datos obligatorios del curso: Institución, CUE y Oferta Formativa.');
      avisar('Completá Institución, CUE y Oferta Formativa antes de guardar.', 'error');
      return;
    }
    var refs = [];
    Array.prototype.forEach.call(document.querySelectorAll('.nc_chk_ref:checked'), function (c) { refs.push(c.value); });
    if (!refs.length) {
      alert('Seleccioná al menos una opción en "Referencial de ingreso".');
      return;
    }

    var payload = {
      cue: cueVal,
      institucion: instVal,
      localidad: $('nc_localidad') ? $('nc_localidad').value.trim() : '',
      domicilio: $('nc_domicilio') ? $('nc_domicilio').value.trim() : '',
      oferta: ofertaVal,
      familiaProfesional: $('nc_familia') ? $('nc_familia').value.trim() : '—',
      ciclo: $('nc_ciclo').value.trim() || '2026',
      turno: $('nc_turno').value,
      division: $('nc_division').value.trim() || '1° "U"',
      duracion: $('nc_duracion') ? $('nc_duracion').value.trim() : '2 Cuatrimestres',
      docente: $('nc_docente') ? $('nc_docente').value.trim() : '',
      fechaFin1C: $('nc_fecha_fin_1c') ? $('nc_fecha_fin_1c').value.trim() : '',
      fechaFin2C: $('nc_fecha_fin_2c') ? $('nc_fecha_fin_2c').value.trim() : '',
      disenio: $('nc_disenio').value.trim() || '661-E/2022',
      resolucionDisenio: $('nc_disenio').value.trim() || '661-E/2022',
      normaAprobacion: $('nc_norma') ? $('nc_norma').value.trim() : '4006-E/2023',
      validezNacional: $('nc_validez') ? $('nc_validez').value.trim() : '530/23',
      disposicion: $('nc_disposicion') ? $('nc_disposicion').value.trim() : '-',
      nivelCurso: $('nc_nivel') ? $('nc_nivel').value.trim() : 'II',
      certificacion: $('nc_certificacion') ? $('nc_certificacion').value.trim() : 'Diseño Curricular Jurisdiccional',
      hsCatTotal: $('nc_hscat').value.trim() || '768',
      referencialIngreso: refs.join(' / '),
      id: $('nc_id').value.trim(),
      estado: 'Abierto'
    };
    try {
      var r = await llamar('/api/cursos', 'POST', payload);
      if (r.paquete) _guardarPaqueteLocal(r.paquete);
      estado.cursos.push(r.curso);
      avisar('Curso registrado con éxito. Ahora podés cargar sus alumnos.', 'ok');
      abrirCurso(r.curso.id);
    } catch (e) {
      problema(e);
    }
  });
}

// ---------- MODAL IMPORTAR VIEJO EXCEL (.XLSM / .XLSX) (MÚLTIPLES ARCHIVOS O CARPETAS) ----------
function mostrarModalImportarExcel() {
  $('migas').hidden = false;
  var modal = document.createElement('div');
  modal.style.background = '#fff';
  modal.style.padding = '24px';
  modal.style.maxWidth = '620px';
  modal.style.margin = '20px auto';
  modal.style.border = '1px solid var(--borde)';
  modal.style.borderRadius = '8px';
  modal.style.boxShadow = '0 4px 16px rgba(0,0,0,0.15)';

  modal.innerHTML =
    '<h2>📥 Importar Viejo Excel (.xlsm / .xlsx) · Archivos o Carpetas</h2>' +
    '<p style="color:var(--suave);font-size:13px;line-height:1.5;margin-top:4px">' +
      'Podés seleccionar <b>uno o varios archivos Excel (.xlsm / .xlsx)</b> al mismo tiempo, o elegir una <b>carpeta completa</b> con planillas de distintas ofertas o escuelas. ' +
      'El conversor migrará automáticamente cada curso con su nómina de estudiantes, módulos, calificaciones y Acta de Examen.' +
    '</p>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0">' +
      '<div style="border:2px dashed var(--azul);background:var(--celeste);padding:16px;border-radius:8px;text-align:center">' +
        '<div style="font-weight:700;font-size:13px;color:var(--azul);margin-bottom:8px">📄 Seleccionar uno o más archivos</div>' +
        '<input type="file" id="inp_excel_file" accept=".xlsm,.xlsx" multiple style="font-size:12px;width:100%">' +
        '<div style="font-size:11px;color:var(--suave);margin-top:6px">Podés marcar varios archivos con Ctrl o Shift</div>' +
      '</div>' +
      '<div style="border:2px dashed #137333;background:#e6f4ea;padding:16px;border-radius:8px;text-align:center">' +
        '<div style="font-weight:700;font-size:13px;color:#137333;margin-bottom:8px">📁 Seleccionar carpeta completa</div>' +
        '<input type="file" id="inp_excel_folder" webkitdirectory directory multiple style="font-size:12px;width:100%">' +
        '<div style="font-size:11px;color:var(--suave);margin-top:6px">Detecta todos los .xlsm y .xlsx de la carpeta</div>' +
      '</div>' +
    '</div>' +
    '<div id="resumen_archivos_excel" style="font-size:12px;color:var(--texto);margin:8px 0"></div>' +
    '<div id="estado_importacion" style="font-size:13px;color:var(--azul);margin:8px 0"></div>' +
    '<div class="acciones" style="justify-content:flex-end;margin-top:14px">' +
      '<button class="boton suave" id="imp_cancelar">Cancelar</button>' +
      '<button class="boton" id="imp_procesar" style="background:#137333">Convertir e Importar Curso(s)</button>' +
    '</div>';

  $('main').innerHTML = '';
  $('main').appendChild(modal);

  var archivosSeleccionados = [];

  function _esArchivoExcelValido(f) {
    if (!f || !f.name) return false;
    var nom = f.name.toLowerCase();
    if (nom.indexOf('~$') === 0) return false;
    return nom.endsWith('.xlsm') || nom.endsWith('.xlsx');
  }

  function _actualizarListaArchivos(listaFileList) {
    var nuevos = Array.prototype.slice.call(listaFileList || []).filter(_esArchivoExcelValido);
    var mapaUnico = {};
    archivosSeleccionados.concat(nuevos).forEach(function (f) {
      var clave = (f.webkitRelativePath || f.name) + ':' + f.size;
      mapaUnico[clave] = f;
    });
    archivosSeleccionados = Object.keys(mapaUnico).map(function (k) { return mapaUnico[k]; });
    var caja = $('resumen_archivos_excel');
    if (!archivosSeleccionados.length) {
      caja.innerHTML = '';
      return;
    }
    var itemsHtml = archivosSeleccionados.slice(0, 15).map(function (f, i) {
      var ruta = f.webkitRelativePath || f.name;
      return '<li><b>' + (i + 1) + '.</b> ' + esc(ruta) + '</li>';
    }).join('');
    if (archivosSeleccionados.length > 15) {
      itemsHtml += '<li><i>… y ' + (archivosSeleccionados.length - 15) + ' archivo(s) más.</i></li>';
    }
    caja.innerHTML =
      '<div style="background:#f8fafc;border:1px solid var(--borde);border-radius:6px;padding:10px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
          '<b>✅ ' + archivosSeleccionados.length + ' archivo(s) Excel listos para importar:</b>' +
          '<button type="button" class="boton suave" id="btnLimpiarSeleccionExcel" style="padding:2px 8px;font-size:11px">Limpiar selección</button>' +
        '</div>' +
        '<ul style="margin:0;padding-left:18px;max-height:140px;overflow:auto">' + itemsHtml + '</ul>' +
      '</div>';
    if ($('btnLimpiarSeleccionExcel')) {
      $('btnLimpiarSeleccionExcel').addEventListener('click', function () {
        archivosSeleccionados = [];
        if ($('inp_excel_file')) $('inp_excel_file').value = '';
        if ($('inp_excel_folder')) $('inp_excel_folder').value = '';
        caja.innerHTML = '';
      });
    }
  }

  $('inp_excel_file').addEventListener('change', function () {
    _actualizarListaArchivos($('inp_excel_file').files);
  });
  $('inp_excel_folder').addEventListener('change', function () {
    _actualizarListaArchivos($('inp_excel_folder').files);
  });

  function _leerArchivoComoBase64(fileObj) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function (ev) { resolve(ev.target.result); };
      reader.onerror = function () { reject(new Error('No se pudo leer el archivo ' + fileObj.name)); };
      reader.readAsDataURL(fileObj);
    });
  }

  $('imp_cancelar').addEventListener('click', verCursos);
  $('imp_procesar').addEventListener('click', async function () {
    if (!archivosSeleccionados.length) {
      if ($('inp_excel_file') && $('inp_excel_file').files && $('inp_excel_file').files.length) {
        _actualizarListaArchivos($('inp_excel_file').files);
      }
      if ($('inp_excel_folder') && $('inp_excel_folder').files && $('inp_excel_folder').files.length) {
        _actualizarListaArchivos($('inp_excel_folder').files);
      }
    }
    if (!archivosSeleccionados.length) {
      $('estado_importacion').innerHTML = '<div style="background:#fce8e6;border:1px solid #ea4335;color:#c5221f;padding:10px;border-radius:6px;font-weight:bold">⚠️ No subió ningún archivo Excel (.xlsm o .xlsx). Seleccione uno o más archivos o una carpeta.</div>';
      alert('⚠️ No subió ningún archivo.\n\nPor favor seleccione uno o más archivos Excel (.xlsm o .xlsx) o una carpeta antes de presionar "Convertir e Importar Curso(s)".');
      avisar('No subió ningún archivo. Seleccioná archivos Excel (.xlsm o .xlsx) o una carpeta.', 'error');
      return;
    }

    $('imp_procesar').disabled = true;
    var total = archivosSeleccionados.length;
    var importados = [];
    var errores = [];
    var totalEstudiantes = 0;

    for (var i = 0; i < total; i++) {
      var archivo = archivosSeleccionados[i];
      $('estado_importacion').innerHTML =
        '<div style="background:#e8f1fa;border:1px solid var(--azul);padding:10px;border-radius:6px;font-weight:600">' +
          '⏳ Importando (' + (i + 1) + ' de ' + total + '): <b>' + esc(archivo.name) + '</b>…' +
        '</div>';
      try {
        var b64 = await _leerArchivoComoBase64(archivo);
        var res = await llamar('/api/importar-excel', 'POST', {
          nombreArchivo: archivo.name,
          contenidoBase64: b64
        });
        if (res.paquete) _guardarPaqueteLocal(res.paquete);
        var yaEstaba = estado.cursos.some(function (c) { return c.id === res.curso.id; });
        if (!yaEstaba) estado.cursos.push(res.curso);
        importados.push(res.curso);
        totalEstudiantes += (res.cantidadEstudiantes || 0);
      } catch (errArchivo) {
        errores.push(archivo.name + ': ' + ((errArchivo && errArchivo.message) ? errArchivo.message : String(errArchivo)));
      }
    }

    if (!importados.length) {
      $('imp_procesar').disabled = false;
      $('estado_importacion').innerHTML =
        '<div style="background:#fce8e6;border:1px solid #ea4335;color:#c5221f;padding:10px;border-radius:6px">' +
          '<b>❌ No se pudo importar ningún archivo:</b><br>' + errores.map(esc).join('<br>') +
        '</div>';
      avisar('Error al importar los archivos seleccionados.', 'error');
      return;
    }

    await cargarUsuariosPrueba();
    if (importados.length === 1 && !errores.length) {
      avisar('¡Excel importado con éxito! (' + totalEstudiantes + ' estudiantes)', 'ok');
      abrirCurso(importados[0].id);
      return;
    }

    avisar('¡Se importaron ' + importados.length + ' curso(s) con ' + totalEstudiantes + ' estudiantes en total!' + (errores.length ? ' (' + errores.length + ' con error)' : ''), 'ok');
    verCursos();
  });
}

// ---------- DASHBOARD DE ESTADÍSTICAS (DIRECCIÓN DETP Y TÍTULOS) ----------
var _filtrosDashboard = { escuela: '', cue: '', desde: '', hasta: '', estado: 'todos' };
var _ultimoDashboardData = null;

function _exportarDashboardCSV(est) {
  if (!est) return;
  var sep = ';';
  function csvEsc(v) {
    var s = String(v == null ? '' : v).replace(/"/g, '""');
    return '"' + s + '"';
  }
  var lineas = [];
  var k = est.kpis || {};
  lineas.push(['INDICADOR', 'VALOR'].map(csvEsc).join(sep));
  lineas.push(['Total Cursos', k.totalCursos].map(csvEsc).join(sep));
  lineas.push(['Total Estudiantes Matriculados', k.totalMatriculados].map(csvEsc).join(sep));
  lineas.push(['Total Aprobados', k.totalAprobados + ' (' + k.pctAprobacion + '%)'].map(csvEsc).join(sep));
  lineas.push(['Total Desaprobados / Adeudan', k.totalDesaprobados + ' (' + k.pctDesaprobacion + '%)'].map(csvEsc).join(sep));
  lineas.push(['Total Ausentes', k.totalAusentes].map(csvEsc).join(sep));
  lineas.push(['Certificados Aprobados', k.totalCertificadosAprobados + ' (Tasa Titulación ' + k.tasaTitulacion + '%)'].map(csvEsc).join(sep));
  lineas.push(['Pendientes en Títulos', k.totalPendientesTitulos].map(csvEsc).join(sep));
  lineas.push(['Errores / Observaciones de Títulos', k.totalObservados].map(csvEsc).join(sep));
  lineas.push('');
  lineas.push(['EGRESADOS SEGUN NIVEL DE ACREDITACION (ACREDITA CON)'].map(csvEsc).join(sep));
  lineas.push(['Nivel de Acreditación', 'Matriculados', 'Se Recibieron (Egresados)', '% Egreso', 'Desaprobados', 'Ausentes', 'Certificados Aprobados'].map(csvEsc).join(sep));
  (est.porAcreditacion || []).forEach(function (a) {
    lineas.push([
      a.acreditacion, a.matriculados, a.aprobados, (a.pctAprobacion || 0) + '%',
      a.desaprobados, a.ausentes, a.certificadosAprobados
    ].map(csvEsc).join(sep));
  });
  lineas.push('');
  lineas.push(['DESGLOSE POR ESCUELA Y CUE'].map(csvEsc).join(sep));
  lineas.push(['Escuela', 'CUE', 'Cursos', 'Matriculados', 'Aprobados', 'Desaprobados', 'Ausentes', 'Certificados Aprobados', 'Certificados Pendientes', 'Certificados Observados'].map(csvEsc).join(sep));
  (est.porEscuela || []).forEach(function (r) {
    lineas.push([
      r.institucion, r.cue, r.cursos, r.matriculados, r.aprobados,
      r.desaprobados, r.ausentes, r.certificadosAprobados,
      r.certificadosPendientes, r.certificadosObservados
    ].map(csvEsc).join(sep));
  });
  lineas.push('');
  lineas.push(['SOLICITUDES OBSERVADAS (ERRORES / OBSERVACIONES DE TÍTULOS)'].map(csvEsc).join(sep));
  lineas.push(['Escuela', 'CUE', 'Curso', 'Estudiante', 'DNI', 'Fecha', 'Motivo de Observación'].map(csvEsc).join(sep));
  (est.observacionesDetalle || []).forEach(function (o) {
    lineas.push([
      o.institucion, o.cue, o.oferta, o.estudiante, o.documento, o.fechaSolicitud, o.motivoObservacion
    ].map(csvEsc).join(sep));
  });

  var blob = new Blob(['\uFEFF' + lineas.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'dashboard_estadisticas_detp.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function verResumen() {
  estado.curso = null;
  estado.datos = null;
  _guardarRutaLocal('resumen', '', '');
  _actualizarBarraEscuela();
  $('main').innerHTML = '<div class="cargando">Calculando estadísticas institucionales…</div>';
  $('migas').hidden = false;
  $('volver').textContent = (estado.sesion && estado.sesion.esTitulos) ? '← Volver a Bandeja de Títulos' : '← Volver a los cursos';

  var qs =
    'escuela=' + encodeURIComponent(_filtrosDashboard.escuela || '') +
    '&cue=' + encodeURIComponent(_filtrosDashboard.cue || '') +
    '&desde=' + encodeURIComponent(_filtrosDashboard.desde || '') +
    '&hasta=' + encodeURIComponent(_filtrosDashboard.hasta || '') +
    '&estado=' + encodeURIComponent(_filtrosDashboard.estado || 'todos');

  try {
    var r = await llamar('/api/resumen?' + qs);
    var est = r.estadisticas || {};
    _ultimoDashboardData = est;
    var k = est.kpis || {};
    var porEscuela = est.porEscuela || r.resumen || [];
    var porAcreditacion = est.porAcreditacion || [];
    var porOferta = est.porOferta || [];
    var porFamilia = est.porFamilia || [];
    var porTurno = est.porTurno || [];
    var obsPorEscuela = est.observacionesPorEscuela || [];
    var obsDetalle = est.observacionesDetalle || [];
    var qrDetalle = est.consultasQrDetalle || [];
    var escuelasDisp = est.escuelasDisponibles || [];
    var cuesDisp = est.cuesDisponibles || [];

    var opsEsc = '<option value="">Todas las escuelas</option>' +
      escuelasDisp.map(function (nom) {
        var sel = _filtrosDashboard.escuela === nom ? ' selected' : '';
        return '<option value="' + esc(nom) + '"' + sel + '>' + esc(nom) + '</option>';
      }).join('');

    var opsCue = '<option value="">Todos los CUEs</option>' +
      cuesDisp.map(function (c) {
        var sel = _filtrosDashboard.cue === c ? ' selected' : '';
        return '<option value="' + esc(c) + '"' + sel + '>' + esc(c) + '</option>';
      }).join('');

    var filasEscuela = porEscuela.length
      ? porEscuela.map(function (i) {
          return '<tr>' +
            '<td><b>' + esc(i.institucion) + '</b></td>' +
            '<td style="text-align:center">' + esc(i.cue || '—') + '</td>' +
            '<td style="text-align:center">' + (i.cursos || 0) + '</td>' +
            '<td style="text-align:center">' + (i.matriculados || i.estudiantes || 0) + '</td>' +
            '<td style="text-align:center;color:#137333;font-weight:700">' + (i.aprobados || 0) + '</td>' +
            '<td style="text-align:center;color:#b3261e">' + (i.desaprobados || 0) + '</td>' +
            '<td style="text-align:center">' + (i.ausentes || 0) + '</td>' +
            '<td style="text-align:center;color:#137333;font-weight:700">' + (i.certificadosAprobados || 0) + '</td>' +
            '<td style="text-align:center;color:#b06000">' + (i.certificadosPendientes || 0) + '</td>' +
            '<td style="text-align:center;color:#c5221f;font-weight:700">' + (i.certificadosObservados || 0) + '</td>' +
            '<td style="text-align:center;color:#1F4E78;font-weight:700">' + (i.consultasQr || 0) + '</td>' +
          '</tr>';
        }).join('')
      : '<tr><td colspan="11" style="text-align:center;color:var(--suave);padding:16px">No hay datos para los filtros aplicados.</td></tr>';

    function _renderMiniTabla(titulo, items, campoClave) {
      var rows = items.length
        ? items.map(function (it) {
            return '<tr>' +
              '<td>' + esc(it[campoClave]) + '</td>' +
              '<td style="text-align:center">' + (it.cursos || 0) + '</td>' +
              '<td style="text-align:center">' + (it.matriculados || 0) + '</td>' +
              '<td style="text-align:center;color:#137333;font-weight:600">' + (it.aprobados || 0) + ' (' + (it.pctAprobacion || 0) + '%)</td>' +
              '<td style="text-align:center">' + (it.certificadosAprobados || 0) + '</td>' +
            '</tr>';
          }).join('')
        : '<tr><td colspan="5" style="text-align:center;color:var(--suave)">Sin datos</td></tr>';
      return '<div class="dash-card">' +
        '<h3>' + esc(titulo) + '</h3>' +
        '<div class="tabla-ancha" style="max-height:280px"><table><thead><tr>' +
          '<th>Categoría</th><th style="text-align:center">Cursos</th><th style="text-align:center">Matric.</th>' +
          '<th style="text-align:center">Aprobados</th><th style="text-align:center">Cert.</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '</div>';
    }

    var obsBadgesHtml = obsPorEscuela.length
      ? '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">' +
          obsPorEscuela.map(function (o) {
            return '<span class="badge-estado badge-observado">' + esc(o.institucion) + ' (CUE ' + esc(o.cue || '—') + '): ' + o.cantidad + '</span>';
          }).join('') +
        '</div>'
      : '';

    var filasObs = obsDetalle.length
      ? obsDetalle.map(function (o) {
          var autorObs = o.observadoPor ? (o.observadoPor + (o.observadoEmail && o.observadoEmail !== o.observadoPor ? ' (' + o.observadoEmail + ')' : '')) : (o.observadoEmail || 'Dirección de Títulos');
          return '<tr>' +
            '<td><b>' + esc(o.institucion) + '</b><br><small style="color:var(--suave)">CUE ' + esc(o.cue || '—') + '</small></td>' +
            '<td>' + esc(o.oferta) + '<br><small style="color:var(--suave)">' + esc(o.ciclo) + '</small></td>' +
            '<td><b>' + esc(o.estudiante) + '</b><br><small>DNI ' + esc(o.documento) + '</small></td>' +
            '<td style="text-align:center;font-size:12px">' + esc(o.fechaObservacion || o.fechaSolicitud || '—') + '</td>' +
            '<td style="color:#b3261e">' + esc(o.motivoObservacion || 'Sin detalle') +
              '<div style="font-size:11px;color:#5f6368;margin-top:2px">👤 <b>Observado por:</b> ' + esc(autorObs) + '</div>' +
            '</td>' +
          '</tr>';
        }).join('')
      : '<tr><td colspan="5" style="text-align:center;color:var(--suave);padding:14px">No se registran solicitudes observadas / errores para los filtros seleccionados.</td></tr>';

    var filasQr = qrDetalle.length
      ? qrDetalle.map(function (q) {
          return '<tr>' +
            '<td><b>' + esc(q.institucion) + '</b><br><small style="color:var(--suave)">CUE ' + esc(q.cue || '—') + '</small></td>' +
            '<td>' + esc(q.oferta) + '<br><small style="color:var(--suave)">' + esc(q.ciclo) + '</small></td>' +
            '<td><b>' + esc(q.estudiante) + '</b><br><small>DNI ' + esc(q.documento) + '</small></td>' +
            '<td style="text-align:center;font-weight:700">' + esc(q.numeroCertificado || '—') + '</td>' +
            '<td style="text-align:center;color:#1F4E78;font-weight:700">' + (q.consultasQr || 0) + '</td>' +
            '<td style="text-align:center;font-size:12px">' + esc(q.ultimaConsultaQr || '—') + '</td>' +
          '</tr>';
        }).join('')
      : '<tr><td colspan="6" style="text-align:center;color:var(--suave);padding:14px">Todavía no se registraron consultas externas mediante código QR.</td></tr>';

    var tarjetasAcreditacionHtml = porAcreditacion.map(function (ac) {
      return '<div class="dash-kpi ok" style="border-left-color:#1F4E78">' +
        '<div class="dash-kpi-lbl">Acredita con: ' + esc(ac.acreditacion) + '</div>' +
        '<div class="dash-kpi-val" style="color:#137333">' + (ac.aprobados || 0) + ' <span style="font-size:13px;font-weight:600;color:var(--suave)">recibidos</span></div>' +
        '<div class="dash-kpi-sub">De ' + (ac.matriculados || 0) + ' matriculados (' + (ac.pctAprobacion || 0) + '%) · ' + (ac.certificadosAprobados || 0) + ' con cert.</div>' +
      '</div>';
    }).join('');

    var filasAcreditacion = porAcreditacion.length
      ? porAcreditacion.map(function (ac) {
          return '<tr>' +
            '<td><b>' + esc(ac.acreditacion) + '</b></td>' +
            '<td style="text-align:center">' + (ac.matriculados || 0) + '</td>' +
            '<td style="text-align:center;color:#137333;font-weight:700">' + (ac.aprobados || 0) + '</td>' +
            '<td style="text-align:center;font-weight:600">' + (ac.pctAprobacion || 0) + '%</td>' +
            '<td style="text-align:center;color:#b3261e;font-weight:700">' + (ac.desaprobados || 0) + '</td>' +
            '<td style="text-align:center">' + (ac.ausentes || 0) + '</td>' +
            '<td style="text-align:center;color:#137333;font-weight:700">' + (ac.certificadosAprobados || 0) + '</td>' +
          '</tr>';
        }).join('')
      : '<tr><td colspan="7" style="text-align:center;color:var(--suave)">Sin datos</td></tr>';

    var esSoloDirectivoEsc = Boolean(estado.sesion && estado.sesion.rol === 'Directivo' && !estado.sesion.verTodo && !estado.sesion.esTitulos);
    var nombreEscDirectivo = (estado.institucionUsuario && estado.institucionUsuario.nombre) ? (' · ' + estado.institucionUsuario.nombre) : '';

    $('main').innerHTML =
      '<div class="solo-impresion" style="text-align:center;margin-bottom:10px">' +
        '<div style="font-size:15px;font-weight:bold">SECRETARÍA DE GESTIÓN EDUCATIVA - DIRECCIÓN DE EDUCACIÓN TÉCNICO PROFESIONAL</div>' +
        '<div style="font-size:13px;font-weight:bold">DASHBOARD DE ESTADÍSTICAS · FORMACIÓN PROFESIONAL' + esc(nombreEscDirectivo.toUpperCase()) + '</div>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">' +
        '<div><h1>📊 Dashboard de Estadísticas' + esc(esSoloDirectivoEsc ? (nombreEscDirectivo || ' · Mi Escuela') : '') + '</h1>' +
        '<p style="color:var(--suave);margin:0">' + (esSoloDirectivoEsc ? 'Indicadores exclusivos de tu establecimiento educativo: matrícula, egresados por nivel de acreditación, certificados y consultas QR.' : 'Indicadores académicos, certificación de Títulos, consultas por QR y observaciones por escuela.') + '</p></div>' +
        '<div class="acciones no-imprimir" style="margin:0">' +
          (esSoloDirectivoEsc
            ? '<button type="button" class="boton" id="btnDashVolverCursos" style="background:#1F4E78">📚 Ver Cursos de mi Escuela</button>'
            : '<button type="button" class="boton" id="btnDashVerPendientes" style="background:#137333">📥 Ver Pendientes de Títulos (' + (k.totalPendientesTitulos || 0) + ')</button>') +
          '<button type="button" class="boton suave" id="btnDashCsv">📥 Exportar CSV</button>' +
          '<button type="button" class="boton" id="btnDashImprimir">🖨️ Imprimir Dashboard</button>' +
        '</div>' +
      '</div>' +

      '<div class="dash-filtros no-imprimir">' +
        '<label>Escuela / Institución<select id="dash_escuela">' + opsEsc + '</select></label>' +
        '<label>CUE<select id="dash_cue">' + opsCue + '</select></label>' +
        '<label>Fecha Desde<input type="date" id="dash_desde" value="' + esc(_filtrosDashboard.desde || '') + '"></label>' +
        '<label>Fecha Hasta<input type="date" id="dash_hasta" value="' + esc(_filtrosDashboard.hasta || '') + '"></label>' +
        '<label>Estado Académico / Certificación' +
          '<select id="dash_estado">' +
            '<option value="todos"' + (_filtrosDashboard.estado === 'todos' ? ' selected' : '') + '>Todos</option>' +
            '<option value="aprobados"' + (_filtrosDashboard.estado === 'aprobados' ? ' selected' : '') + '>Aprobados</option>' +
            '<option value="desaprobados"' + (_filtrosDashboard.estado === 'desaprobados' ? ' selected' : '') + '>Desaprobados / En curso</option>' +
            '<option value="cert_aprobados"' + (_filtrosDashboard.estado === 'cert_aprobados' ? ' selected' : '') + '>Certificados Aprobados</option>' +
            '<option value="observados"' + (_filtrosDashboard.estado === 'observados' ? ' selected' : '') + '>Certificados Observados / Con errores</option>' +
          '</select>' +
        '</label>' +
        '<div style="display:flex;gap:8px">' +
          '<button type="button" class="boton" id="btnDashAplicar" style="flex:1">Aplicar</button>' +
          '<button type="button" class="boton suave" id="btnDashLimpiar">Limpiar</button>' +
        '</div>' +
      '</div>' +

      '<div class="dash-kpis">' +
        '<div class="dash-kpi"><div class="dash-kpi-lbl">Total Cursos</div><div class="dash-kpi-val">' + (k.totalCursos || 0) + '</div><div class="dash-kpi-sub">Ofertas activas / relevadas</div></div>' +
        '<div class="dash-kpi"><div class="dash-kpi-lbl">Matriculados</div><div class="dash-kpi-val">' + (k.totalMatriculados || 0) + '</div><div class="dash-kpi-sub">Total estudiantes</div></div>' +
        '<div class="dash-kpi ok"><div class="dash-kpi-lbl">Aprobados</div><div class="dash-kpi-val" style="color:#137333">' + (k.totalAprobados || 0) + '</div><div class="dash-kpi-sub">' + (k.pctAprobacion || 0) + '% de aprobación</div></div>' +
        '<div class="dash-kpi mal"><div class="dash-kpi-lbl">Desaprobados / Adeudan</div><div class="dash-kpi-val" style="color:#b3261e">' + (k.totalDesaprobados || 0) + '</div><div class="dash-kpi-sub">' + (k.pctDesaprobacion || 0) + '% del total</div></div>' +
        '<div class="dash-kpi"><div class="dash-kpi-lbl">Ausentes</div><div class="dash-kpi-val">' + (k.totalAusentes || 0) + '</div><div class="dash-kpi-sub">Examen final / módulos</div></div>' +
        '<div class="dash-kpi ok"><div class="dash-kpi-lbl">Certificados Aprobados</div><div class="dash-kpi-val" style="color:#137333">' + (k.totalCertificadosAprobados || 0) + '</div><div class="dash-kpi-sub">Tasa de titulación: ' + (k.tasaTitulacion || 0) + '%</div></div>' +
        '<div class="dash-kpi warn"><div class="dash-kpi-lbl">Pendientes en Títulos</div><div class="dash-kpi-val" style="color:#b06000">' + (k.totalPendientesTitulos || 0) + '</div><div class="dash-kpi-sub">En revisión</div></div>' +
        '<div class="dash-kpi mal"><div class="dash-kpi-lbl">Errores / Observaciones</div><div class="dash-kpi-val" style="color:#c5221f">' + (k.totalObservados || 0) + '</div><div class="dash-kpi-sub">Solicitudes observadas</div></div>' +
        '<div class="dash-kpi"><div class="dash-kpi-lbl">📱 Consultas por QR</div><div class="dash-kpi-val" style="color:#1F4E78">' + (k.totalConsultasQr || 0) + '</div><div class="dash-kpi-sub">' + (k.certificadosConsultadosQr || 0) + ' cert. verificados por QR</div></div>' +
      '</div>' +

      '<div class="dash-card">' +
        '<h3>Indicadores de Rendimiento y Titulación</h3>' +
        '<div class="dash-barra-item">' +
          '<div class="dash-barra-head"><span>Tasa de Aprobación Académica</span><span>' + (k.pctAprobacion || 0) + '%</span></div>' +
          '<div class="dash-barra-track"><div class="dash-barra-fill" style="width:' + Math.min(100, k.pctAprobacion || 0) + '%;background:#1e7a4b"></div></div>' +
        '</div>' +
        '<div class="dash-barra-item">' +
          '<div class="dash-barra-head"><span>Desaprobados / Adeudan Módulos</span><span>' + (k.pctDesaprobacion || 0) + '%</span></div>' +
          '<div class="dash-barra-track"><div class="dash-barra-fill" style="width:' + Math.min(100, k.pctDesaprobacion || 0) + '%;background:#b3261e"></div></div>' +
        '</div>' +
        '<div class="dash-barra-item" style="margin-bottom:0">' +
          '<div class="dash-barra-head"><span>Tasa de Egreso / Titulación (Egresados con Certificado Oficial)</span><span>' + (k.tasaTitulacion || 0) + '%</span></div>' +
          '<div class="dash-barra-track"><div class="dash-barra-fill" style="width:' + Math.min(100, k.tasaTitulacion || 0) + '%;background:#1F4E78"></div></div>' +
        '</div>' +
      '</div>' +

      '<div class="dash-card">' +
        '<h3>🎓 Egresados (Recibidos) según Nivel de Acreditación (Primaria · Secundaria · Ciclo Básico · Superior)</h3>' +
        '<div class="dash-kpis" style="margin-bottom:14px">' + tarjetasAcreditacionHtml + '</div>' +
        '<div class="tabla-ancha"><table><thead><tr>' +
          '<th>Nivel de Acreditación (Acredita con)</th>' +
          '<th style="text-align:center">Matriculados</th>' +
          '<th style="text-align:center">Se Recibieron (Aprobados)</th>' +
          '<th style="text-align:center">% de Egreso</th>' +
          '<th style="text-align:center">Desaprobados</th>' +
          '<th style="text-align:center">Ausentes</th>' +
          '<th style="text-align:center">Con Certificado Emitido</th>' +
        '</tr></thead><tbody>' + filasAcreditacion + '</tbody></table></div>' +
      '</div>' +

      '<div class="dash-card">' +
        '<h3>Desglose por Escuela y CUE</h3>' +
        '<div class="tabla-ancha"><table><thead><tr>' +
          '<th>Escuela</th><th style="text-align:center">CUE</th><th style="text-align:center">Cursos</th>' +
          '<th style="text-align:center">Matriculados</th><th style="text-align:center">Aprobados</th>' +
          '<th style="text-align:center">Desaprobados</th><th style="text-align:center">Ausentes</th>' +
          '<th style="text-align:center">Cert. Aprobados</th><th style="text-align:center">Cert. Pendientes</th>' +
          '<th style="text-align:center">Cert. Observados (Errores)</th><th style="text-align:center">Consultas QR</th>' +
        '</tr></thead><tbody>' + filasEscuela + '</tbody></table></div>' +
      '</div>' +

      '<div class="dash-grid-sub">' +
        _renderMiniTabla('Desglose por Oferta Formativa', porOferta, 'oferta') +
        _renderMiniTabla('Desglose por Familia Profesional', porFamilia, 'familiaProfesional') +
        _renderMiniTabla('Desglose por Turno', porTurno, 'turno') +
      '</div>' +

      '<div class="dash-card">' +
        '<h3>📱 Consultas de Certificados por Código QR (' + (k.totalConsultasQr || 0) + ' consultas totales)</h3>' +
        '<div class="tabla-ancha"><table><thead><tr>' +
          '<th>Escuela / CUE</th><th>Curso</th><th>Estudiante / DNI</th>' +
          '<th style="width:160px;text-align:center">N° Certificado</th><th style="width:110px;text-align:center">Veces Consultado</th>' +
          '<th style="width:140px;text-align:center">Última Consulta QR</th>' +
        '</tr></thead><tbody>' + filasQr + '</tbody></table></div>' +
      '</div>' +

      '<div class="dash-card">' +
        '<h3>Errores y Observaciones de Títulos (' + obsDetalle.length + ')</h3>' +
        obsBadgesHtml +
        '<div class="tabla-ancha"><table><thead><tr>' +
          '<th>Escuela / CUE</th><th>Curso</th><th>Estudiante / DNI</th>' +
          '<th style="width:130px;text-align:center">Fecha</th><th>Motivo de Error / Observación</th>' +
        '</tr></thead><tbody>' + filasObs + '</tbody></table></div>' +
      '</div>';

    if ($('btnDashVolverCursos')) {
      $('btnDashVolverCursos').addEventListener('click', function () {
        verCursos();
      });
    }
    if ($('btnDashVerPendientes')) {
      $('btnDashVerPendientes').addEventListener('click', function () {
        estado.filtroBandeja = 'Pendiente';
        verBandejaTitulos();
      });
    }

    if ($('btnDashAplicar')) {
      $('btnDashAplicar').addEventListener('click', function () {
        _filtrosDashboard = {
          escuela: $('dash_escuela') ? $('dash_escuela').value : '',
          cue: $('dash_cue') ? $('dash_cue').value : '',
          desde: $('dash_desde') ? $('dash_desde').value : '',
          hasta: $('dash_hasta') ? $('dash_hasta').value : '',
          estado: $('dash_estado') ? $('dash_estado').value : 'todos'
        };
        verResumen();
      });
    }
    if ($('btnDashLimpiar')) {
      $('btnDashLimpiar').addEventListener('click', function () {
        _filtrosDashboard = { escuela: '', cue: '', desde: '', hasta: '', estado: 'todos' };
        verResumen();
      });
    }
    if ($('btnDashCsv')) {
      $('btnDashCsv').addEventListener('click', function () { _exportarDashboardCSV(_ultimoDashboardData); });
    }
    if ($('btnDashImprimir')) {
      $('btnDashImprimir').addEventListener('click', function () {
        _configurarPaginaImpresion('oficio-horizontal');
        window.print();
      });
    }
  } catch (err) {
    problema(err);
  }
}

// ---------- ADMINISTRACIÓN DE USUARIOS (EXCLUSIVO ROL DIRECCIÓN DETP) ----------
async function verAdminUsuarios() {
  estado.curso = null;
  estado.datos = null;
  _guardarRutaLocal('usuarios', '', '');
  $('migas').hidden = false;
  $('volver').textContent = '← Volver a los cursos';
  $('main').innerHTML = '<div class="cargando">Cargando padrón de usuarios autorizados…</div>';
  try {
    var r = await llamar('/api/usuarios');
    var usuarios = r.usuarios || [];

    var filas = usuarios.map(function (u) {
      var esOficial = String(u.Email || '').toLowerCase().endsWith('@jujuy.edu.ar');
      var badgeCorreo = esOficial
        ? '<span class="badge-estado badge-aprobado" style="margin-left:6px">@jujuy.edu.ar</span>'
        : '<span class="badge-estado badge-pendiente" style="margin-left:6px">Autorizado</span>';
      var esPrincipal = String(u.Email || '').toLowerCase() === 'sge.detp.areapedagogica@jujuy.edu.ar';

      return '<tr>' +
        '<td><b>' + esc(u.Email) + '</b>' + badgeCorreo + '</td>' +
        '<td>' + esc(u.Nombre) + '</td>' +
        '<td><b>' + esc(u.Rol) + '</b></td>' +
        '<td style="text-align:center">' + esc(u.CUE || 'Todas (Global)') + '</td>' +
        '<td style="text-align:center">' +
          '<span class="badge-estado ' + (u.Activo === 'Sí' ? 'badge-aprobado' : 'badge-observado') + '">' + esc(u.Activo) + '</span>' +
        '</td>' +
        '<td style="text-align:center">' +
          '<button class="boton suave" style="padding:4px 8px;font-size:12px;margin-right:4px" onclick="cargarUsuarioEnFormulario(' + escJsArg(u.Email) + ', ' + escJsArg(u.Nombre) + ', ' + escJsArg(u.Rol) + ', ' + escJsArg(u.CUE || '') + ')">Editar Rol</button>' +
          (esPrincipal
            ? '<span style="color:var(--suave);font-size:11px">Principal</span>'
            : '<button class="boton suave" style="padding:4px 8px;font-size:12px;color:var(--mal);border-color:var(--mal)" onclick="borrarUsuarioSistema(' + escJsArg(u.Email) + ')">Borrar</button>') +
        '</td>' +
      '</tr>';
    }).join('');

    $('main').innerHTML =
      '<h1>Administración de Usuarios · Dirección DETP</h1>' +
      '<p style="color:var(--suave)">Pueden ingresar usuarios con <b>cualquier correo electrónico</b> (<code>@jujuy.edu.ar</code>, <code>@gmail.com</code>, etc.), siempre que un usuario con rol <b>Dirección DETP</b> los dé de alta aquí y les asigne su rol.</p>' +
      '<div style="background:#fff;border:1px solid var(--borde);border-radius:8px;padding:16px;margin:14px 0">' +
        '<h3 style="margin:0 0 12px;font-size:14px">+ Crear Usuario o Modificar Rol</h3>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;align-items:end">' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Correo electrónico (cualquier dominio)</label>' +
            '<input id="usr_email" class="buscar" style="margin:0;width:100%" placeholder="ejemplo@gmail.com o @jujuy.edu.ar"></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Nombre y Apellido / Área</label>' +
            '<input id="usr_nombre" class="buscar" style="margin:0;width:100%" placeholder="Ej: Dir. Escuela Prof. N° 6"></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">Rol asignado por Dirección</label>' +
            '<select id="usr_rol" class="buscar" style="margin:0;width:100%">' +
              '<option value="Administrativo">Administrativo (Carga escuela)</option>' +
              '<option value="Directivo">Directivo (Consulta escuela)</option>' +
              '<option value="titulos">titulos (Dirección de Títulos)</option>' +
              '<option value="Directora de Títulos">Directora de Títulos (Exclusivo Tatiana: Dashboard, QR y Pendientes)</option>' +
              '<option value="Dirección DETP">Dirección DETP (Crea/Borra usuarios)</option>' +
            '</select></div>' +
          '<div><label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px">CUE (solo para escuelas)</label>' +
            '<input id="usr_cue" class="buscar" style="margin:0;width:100%" placeholder="Ej: 3800006"></div>' +
          '<div><button class="boton" id="btnGuardarUsr" style="width:100%">Guardar Usuario y Rol</button></div>' +
        '</div>' +
      '</div>' +
      '<div class="tabla-ancha"><table><thead><tr>' +
        '<th>Correo Electrónico</th><th>Nombre / Cargo</th><th>Rol Asignado</th>' +
        '<th style="width:120px;text-align:center">CUE Asignado</th>' +
        '<th style="width:80px;text-align:center">Activo</th>' +
        '<th style="width:170px;text-align:center">Acciones</th>' +
      '</tr></thead><tbody>' + filas + '</tbody></table></div>';

    $('btnGuardarUsr').addEventListener('click', async function () {
      var payload = {
        Email: $('usr_email').value.trim(),
        Nombre: $('usr_nombre').value.trim(),
        Rol: $('usr_rol').value,
        CUE: $('usr_cue').value.trim(),
        Activo: 'Sí'
      };
      try {
        await llamar('/api/usuarios', 'POST', payload);
        avisar('Usuario guardado correctamente', 'ok');
        await cargarUsuariosPrueba();
        verAdminUsuarios();
      } catch (e) {
        problema(e);
      }
    });
  } catch (e) {
    problema(e);
  }
}

function cargarUsuarioEnFormulario(email, nombre, rol, cue) {
  if ($('usr_email')) $('usr_email').value = email;
  if ($('usr_nombre')) $('usr_nombre').value = nombre;
  if ($('usr_rol')) $('usr_rol').value = rol;
  if ($('usr_cue')) $('usr_cue').value = cue;
  if ($('usr_email')) $('usr_email').focus();
  avisar('Editando rol de ' + email + '. Modificá los datos arriba y tocá Guardar.');
}

async function borrarUsuarioSistema(emailObj) {
  if (!confirm('¿Seguro que deseas borrar al usuario ' + emailObj + '?')) return;
  try {
    await llamar('/api/usuarios', 'DELETE', { Email: emailObj });
    avisar('Usuario eliminado: ' + emailObj, 'ok');
    await cargarUsuariosPrueba();
    verAdminUsuarios();
  } catch (e) {
    problema(e);
  }
}
