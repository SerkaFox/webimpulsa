/* Utilidades i18n RU/ES compartidas por las páginas de prospección
   (dashboard, mapa interno, ficha de prospecto). Se comparte también con
   el resto del panel/CRM la misma clave de localStorage, para que el
   idioma elegido en cualquier página se recuerde en todas. */
(function(){
  var LANG_KEY = 'wi_crm_lang';

  function wiGetLang(){ return localStorage.getItem(LANG_KEY) || 'ru'; }
  function wiSetLangRaw(lang){ localStorage.setItem(LANG_KEY, lang); }
  window.wiGetLang = wiGetLang;

  // code -> {es, ru} para los choices de prospeccion/models.py — si se
  // añade/renombra un choice allí, añadirlo aquí también.
  window.WI_CODE_LABELS = {
    salesStatus: {
      discovered:          {es: 'Descubierto',       ru: 'Найден'},
      pre_audited:         {es: 'Pre-auditado',       ru: 'Есть предпроверка'},
      contacted:           {es: 'Contactado',         ru: 'На связи'},
      audited:             {es: 'Auditado',           ru: 'Проверено'},
      presupuesto_created: {es: 'Presupuesto creado', ru: 'Есть смета'},
      won:                 {es: 'Ganado',             ru: 'Клиент'},
      lost:                {es: 'Perdido',            ru: 'Отказ'},
      do_not_contact:      {es: 'No contactar',       ru: 'Не беспокоить'},
      archived:            {es: 'Archivado',          ru: 'В архиве'},
    },
    sector: {
      salon:        {es: 'Salón de belleza / peluquería / estética',      ru: 'Салон красоты / парикмахерская'},
      bar:          {es: 'Bar / cafetería / restaurante',                  ru: 'Бар / кафе / ресторан'},
      taller:       {es: 'Taller / automoción / servicio técnico',         ru: 'Автосервис / мастерская'},
      academia:     {es: 'Academia / cursos / formación',                  ru: 'Курсы / обучение'},
      clinica:      {es: 'Clínica / fisioterapia / salud privada',         ru: 'Клиника / физиотерапия / здоровье'},
      tienda:       {es: 'Tienda local',                                   ru: 'Местный магазин'},
      inmobiliaria: {es: 'Inmobiliaria / reformas / servicios profesionales', ru: 'Недвижимость / ремонт / услуги'},
      otro:         {es: 'Otro negocio local',                             ru: 'Другой местный бизнес'},
    },
    priority: {
      low:    {es: 'Baja',   ru: 'Низкий'},
      normal: {es: 'Normal', ru: 'Обычный'},
      high:   {es: 'Alta',   ru: 'Высокий'},
    },
    contactRole: {
      owner:         {es: 'Dueño/a',        ru: 'Владелец'},
      manager:       {es: 'Gerente',        ru: 'Управляющий'},
      administrator: {es: 'Administración', ru: 'Администрация'},
      employee:      {es: 'Empleado/a',     ru: 'Сотрудник'},
      marketing:     {es: 'Marketing',      ru: 'Маркетинг'},
      unknown:       {es: 'Desconocido',    ru: 'Не указано'},
    },
    channel: {
      whatsapp: {es: 'WhatsApp', ru: 'WhatsApp'},
      email:    {es: 'Email',    ru: 'Email'},
      phone:    {es: 'Teléfono', ru: 'Телефон'},
    },
    auditMode: {
      public:   {es: 'Público',   ru: 'Публичный'},
      personal: {es: 'Personal',  ru: 'Персональный'},
    },
    auditStage: {
      preliminar: {es: 'Preliminar', ru: 'Предварительный'},
      confirmado: {es: 'Confirmado', ru: 'Подтверждён'},
    },
  };

  function wiCodeLabel(table, code, lang){
    lang = lang || wiGetLang();
    var t = window.WI_CODE_LABELS[table];
    if(!t) return code;
    var entry = t[code];
    if(!entry) return code;
    return entry[lang] || entry.es || code;
  }
  window.wiCodeLabel = wiCodeLabel;

  // Aplica un diccionario T={es:{...},ru:{...}} a los elementos
  // [data-i18n]/[data-i18n-placeholder] de la página y a document.title
  // (si T tiene la clave 'page_title'). Devuelve la función tr(key) para
  // usarla también al construir HTML dinámico en JS.
  function wiApplyI18n(T, lang){
    lang = lang || wiGetLang();
    var cur = T[lang] || T.ru || T.es || {};
    var fb = T.ru || T.es || {};
    function tr(key){
      var v = cur[key];
      if(v === undefined) v = fb[key];
      return v === undefined ? key : v;
    }
    if(cur.page_title || fb.page_title) document.title = tr('page_title');
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var key = el.getAttribute('data-i18n');
      if(key) el.textContent = tr(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el){
      var key = el.getAttribute('data-i18n-placeholder');
      if(key) el.placeholder = tr(key);
    });
    return tr;
  }
  window.wiApplyI18n = wiApplyI18n;

  // Conecta cualquier botón .wi-lang-btn[data-lang=es|ru] presente en la
  // página: pinta el estado activo, persiste el idioma y llama a
  // onLangChange(lang) (una vez al cargar y en cada cambio).
  function wiWireLangSwitcher(onLangChange){
    var lang = wiGetLang();
    function paint(){
      document.querySelectorAll('.wi-lang-btn').forEach(function(b){
        b.classList.toggle('active', b.dataset.lang === lang);
      });
    }
    document.querySelectorAll('.wi-lang-btn').forEach(function(b){
      b.addEventListener('click', function(){
        lang = this.dataset.lang;
        wiSetLangRaw(lang);
        paint();
        onLangChange(lang);
      });
    });
    paint();
    onLangChange(lang);
  }
  window.wiWireLangSwitcher = wiWireLangSwitcher;
})();
