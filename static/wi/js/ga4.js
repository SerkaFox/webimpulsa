(function () {
  'use strict';
  var GA_ID = 'G-7GM7ZGKSJF';

  var analyticsGranted = false;
  try {
    var stored = JSON.parse(localStorage.getItem('wi_cookie_consent') || 'null');
    analyticsGranted = !!(stored && stored.analytics);
  } catch (e) { /* no stored consent yet — stay denied */ }

  window.dataLayer = window.dataLayer || [];
  function gtag() { dataLayer.push(arguments); }
  window.gtag = gtag;

  gtag('consent', 'default', {
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
    analytics_storage: analyticsGranted ? 'granted' : 'denied'
  });
  gtag('js', new Date());
  gtag('config', GA_ID, { anonymize_ip: true });

  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
  document.head.appendChild(s);
})();
