(function () {
  'use strict';
  var STORE_KEY = 'wi_cookie_consent';

  var TEXT = {
    es: {
      banner: 'Usamos cookies necesarias para que la web funcione y, si lo aceptas, cookies opcionales de análisis para mejorar el sitio.',
      acceptAll: 'Aceptar todo', onlyNecessary: 'Solo necesarias', settings: 'Configurar',
      modalTitle: 'Preferencias de cookies',
      necessary: 'Necesarias', necessaryDesc: 'Imprescindibles para que la web funcione (idioma, sesión). Siempre activas.',
      analytics: 'Análisis', analyticsDesc: 'Nos ayudan a entender cómo se usa la web. Desactivadas por defecto.',
      save: 'Guardar preferencias', policyLink: 'Política de cookies',
    },
    en: {
      banner: 'We use necessary cookies to make the site work and, if you accept, optional analytics cookies to improve it.',
      acceptAll: 'Accept all', onlyNecessary: 'Necessary only', settings: 'Settings',
      modalTitle: 'Cookie preferences',
      necessary: 'Necessary', necessaryDesc: 'Required for the site to work (language, session). Always on.',
      analytics: 'Analytics', analyticsDesc: 'Help us understand how the site is used. Off by default.',
      save: 'Save preferences', policyLink: 'Cookie policy',
    },
    eu: {
      banner: 'Webgunea funtziona dadin beharrezko cookieak erabiltzen ditugu eta, onartzen baduzu, analisi-cookie aukerakoak hobetzeko.',
      acceptAll: 'Onartu guztiak', onlyNecessary: 'Beharrezkoak soilik', settings: 'Konfiguratu',
      modalTitle: 'Cookien hobespenak',
      necessary: 'Beharrezkoak', necessaryDesc: 'Webguneak funtziona dezan ezinbestekoak (hizkuntza, saioa). Beti aktibo.',
      analytics: 'Analisia', analyticsDesc: 'Webgunea nola erabiltzen den ulertzen laguntzen digute. Berez desaktibatuta.',
      save: 'Gorde hobespenak', policyLink: 'Cookien politika',
    },
    ru: {
      banner: 'Мы используем необходимые куки для работы сайта и, с вашего согласия, аналитические — для его улучшения.',
      acceptAll: 'Принять всё', onlyNecessary: 'Только необходимые', settings: 'Настроить',
      modalTitle: 'Настройки cookies',
      necessary: 'Необходимые', necessaryDesc: 'Нужны для работы сайта (язык, сессия). Всегда включены.',
      analytics: 'Аналитика', analyticsDesc: 'Помогают понять, как используется сайт. По умолчанию выключены.',
      save: 'Сохранить настройки', policyLink: 'Политика cookies',
    },
  };

  function lang() {
    return window.WI_LANG || localStorage.getItem('wi_lang') || 'es';
  }
  function t(key) {
    var d = TEXT[lang()] || TEXT.es;
    return d[key] || TEXT.es[key] || '';
  }

  function getConsent() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }
  function setConsent(analytics) {
    var consent = { necessary: true, analytics: !!analytics, ts: Date.now() };
    localStorage.setItem(STORE_KEY, JSON.stringify(consent));
    window.WI_COOKIE_CONSENT = consent;
    return consent;
  }
  window.WI_COOKIE_CONSENT = getConsent() || { necessary: true, analytics: false };

  var style = document.createElement('style');
  style.textContent =
    '.wi-cc-banner{position:fixed;left:16px;bottom:16px;max-width:380px;background:#fff;' +
    'border:1px solid rgba(10,50,150,.14);border-radius:14px;box-shadow:0 8px 32px rgba(10,50,150,.18);' +
    'padding:1rem 1.1rem;z-index:9999;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;' +
    'font-size:.84rem;color:#0c1c42;line-height:1.5}' +
    '.wi-cc-banner p{margin:0 0 .7rem}' +
    '.wi-cc-btns{display:flex;gap:.4rem;flex-wrap:wrap}' +
    '.wi-cc-btn{border:none;border-radius:8px;padding:.45rem .8rem;font-size:.78rem;font-weight:700;cursor:pointer}' +
    '.wi-cc-btn.primary{background:#1760d6;color:#fff}' +
    '.wi-cc-btn.ghost{background:rgba(23,96,214,.08);color:#1760d6}' +
    '.wi-cc-modal-backdrop{position:fixed;inset:0;background:rgba(10,20,50,.45);z-index:10000;' +
    'display:flex;align-items:center;justify-content:center;padding:1rem}' +
    '.wi-cc-modal{background:#fff;border-radius:16px;max-width:420px;width:100%;padding:1.4rem 1.5rem;' +
    'font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#0c1c42}' +
    '.wi-cc-modal h3{margin:0 0 1rem;font-size:1.05rem;font-weight:900}' +
    '.wi-cc-row{display:flex;justify-content:space-between;align-items:flex-start;gap:.8rem;' +
    'padding:.7rem 0;border-top:1px solid rgba(0,0,0,.08)}' +
    '.wi-cc-row:first-of-type{border-top:none}' +
    '.wi-cc-row-title{font-weight:750;font-size:.9rem}' +
    '.wi-cc-row-desc{font-size:.8rem;color:#5a6d8c;margin-top:.15rem}' +
    '.wi-cc-switch{position:relative;width:38px;height:22px;flex-shrink:0}' +
    '.wi-cc-switch input{opacity:0;width:0;height:0}' +
    '.wi-cc-slider{position:absolute;inset:0;background:#c7d4ea;border-radius:22px;cursor:pointer;transition:.2s}' +
    '.wi-cc-slider:before{content:"";position:absolute;width:16px;height:16px;left:3px;top:3px;' +
    'background:#fff;border-radius:50%;transition:.2s}' +
    '.wi-cc-switch input:checked + .wi-cc-slider{background:#1760d6}' +
    '.wi-cc-switch input:checked + .wi-cc-slider:before{transform:translateX(16px)}' +
    '.wi-cc-switch input:disabled + .wi-cc-slider{opacity:.5;cursor:not-allowed}' +
    '.wi-cc-save{margin-top:1.2rem;width:100%}';
  document.head.appendChild(style);

  function renderBanner() {
    if (document.getElementById('wiCcBanner')) return;
    var el = document.createElement('div');
    el.className = 'wi-cc-banner';
    el.id = 'wiCcBanner';
    el.innerHTML =
      '<p>' + t('banner') + '</p>' +
      '<div class="wi-cc-btns">' +
      '<button class="wi-cc-btn primary" data-act="accept">' + t('acceptAll') + '</button>' +
      '<button class="wi-cc-btn ghost" data-act="necessary">' + t('onlyNecessary') + '</button>' +
      '<button class="wi-cc-btn ghost" data-act="settings">' + t('settings') + '</button>' +
      '</div>';
    document.body.appendChild(el);
    el.querySelector('[data-act="accept"]').addEventListener('click', function () {
      setConsent(true); removeBanner();
    });
    el.querySelector('[data-act="necessary"]').addEventListener('click', function () {
      setConsent(false); removeBanner();
    });
    el.querySelector('[data-act="settings"]').addEventListener('click', function () {
      removeBanner(); openSettings();
    });
  }
  function removeBanner() {
    var el = document.getElementById('wiCcBanner');
    if (el) el.remove();
  }

  function openSettings() {
    closeSettings();
    var current = getConsent() || { analytics: false };
    var backdrop = document.createElement('div');
    backdrop.className = 'wi-cc-modal-backdrop';
    backdrop.id = 'wiCcModal';
    backdrop.innerHTML =
      '<div class="wi-cc-modal">' +
      '<h3>' + t('modalTitle') + '</h3>' +
      '<div class="wi-cc-row">' +
      '<div><div class="wi-cc-row-title">' + t('necessary') + '</div>' +
      '<div class="wi-cc-row-desc">' + t('necessaryDesc') + '</div></div>' +
      '<label class="wi-cc-switch"><input type="checkbox" checked disabled><span class="wi-cc-slider"></span></label>' +
      '</div>' +
      '<div class="wi-cc-row">' +
      '<div><div class="wi-cc-row-title">' + t('analytics') + '</div>' +
      '<div class="wi-cc-row-desc">' + t('analyticsDesc') + '</div></div>' +
      '<label class="wi-cc-switch"><input type="checkbox" id="wiCcAnalytics"' + (current.analytics ? ' checked' : '') + '><span class="wi-cc-slider"></span></label>' +
      '</div>' +
      '<button class="wi-cc-btn primary wi-cc-save" id="wiCcSave">' + t('save') + '</button>' +
      '</div>';
    document.body.appendChild(backdrop);
    backdrop.addEventListener('click', function (e) { if (e.target === backdrop) closeSettings(); });
    document.getElementById('wiCcSave').addEventListener('click', function () {
      var analytics = document.getElementById('wiCcAnalytics').checked;
      setConsent(analytics);
      closeSettings();
    });
  }
  function closeSettings() {
    var el = document.getElementById('wiCcModal');
    if (el) el.remove();
  }

  window.wiOpenCookieSettings = openSettings;

  document.addEventListener('DOMContentLoaded', function () {
    if (!getConsent()) renderBanner();
  });
})();
