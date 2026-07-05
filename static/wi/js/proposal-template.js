(function(){
'use strict';

var VAT_RATE=.21;

// Editar aqui los datos legales y fiscales reales de WebImpulsa cuando esten confirmados.
var WEBIMPULSA_COMPANY={
  tradeName:'WebImpulsa',
  legalName:'Titular / razon social pendiente',
  taxId:'NIF/CIF/NIE pendiente',
  email:'info@webimpulsa.es',
  phone:'WhatsApp pendiente',
  website:'https://webimpulsa.es',
  address:'Direccion fiscal pendiente',
  logoUrl:'/static/wi/img/logo.webp'
};

var PROJECT_SCOPES={
  'Landing page':['Pagina principal optimizada para conversion','Diseno responsive adaptado a movil, tablet y ordenador','Secciones de servicios, beneficios, contacto y llamada a la accion','Formulario de contacto basico','Integracion con WhatsApp','Optimizacion basica SEO on-page','Publicacion inicial'],
  'Web profesional':['Hasta 5 secciones o paginas principales','Diseno responsive adaptado a la imagen del negocio','Formulario de contacto','Integracion WhatsApp','Optimizacion SEO basica','Configuracion basica de analitica si aplica','Publicacion inicial'],
  'Web con reservas':['Todo lo incluido en una web profesional','Sistema de reservas o citas online','Gestion basica de servicios y disponibilidad','Notificaciones basicas por email o WhatsApp segun alcance','Panel o integracion de gestion segun el caso','Pruebas funcionales antes de publicacion'],
  'Tienda online':['Catalogo inicial de productos o servicios','Carrito o flujo de pedido','Configuracion basica de pagos si aplica','Estructura de paginas legales basicas, sin redaccion legal definitiva','Formacion basica de uso','Publicacion inicial'],
  'Proyecto a medida':['Analisis funcional del flujo de trabajo','Diseno de estructura y pantallas principales','Desarrollo de funcionalidades acordadas','Integraciones descritas expresamente en el alcance','Pruebas funcionales y ajustes razonables','Publicacion o entrega inicial'],
  'Proyecto existente':['Revision del proyecto actual','Mejoras o ampliaciones descritas en el alcance','Correccion de incidencias tecnicas acordadas','Integraciones o automatizaciones seleccionadas','Pruebas sobre las partes intervenidas','Entrega de resumen de cambios'],
  'Solo mantenimiento':['Revision tecnica inicial','Actualizaciones y mantenimiento segun plan seleccionado','Correcciones menores dentro del tiempo contratado','Backups y seguimiento segun plan','Soporte mensual facturado aparte']
};

var DEADLINES={
  'Landing page':'5-10 dias laborables',
  'Web profesional':'10-20 dias laborables',
  'Web con reservas':'15-30 dias laborables',
  'Tienda online':'20-40 dias laborables',
  'Proyecto a medida':'Segun alcance',
  'Proyecto existente':'Segun alcance',
  'Solo mantenimiento':'Activacion en 2-5 dias laborables'
};

var OUT_OF_SCOPE=['Redaccion legal definitiva de textos legales','Compra de dominio','Hosting','Licencias externas','Pasarelas de pago','Fotografias profesionales','Traducciones','Campanas publicitarias','Funcionalidades no descritas expresamente'];
var PHASES=['Fase 1: Briefing y recopilacion de material','Fase 2: Diseno y estructura','Fase 3: Desarrollo','Fase 4: Revision y ajustes','Fase 5: Publicacion','Fase 6: Soporte inicial'];
var CONDITIONS=[
  'Este documento constituye una propuesta comercial/presupuesto y no una factura.',
  'La aceptacion del presupuesto por escrito, email, WhatsApp o firma implica conformidad con el alcance, precio y condiciones indicadas.',
  'El cliente se compromete a facilitar textos, imagenes, logotipos, accesos y materiales necesarios.',
  'Los retrasos en la entrega de materiales por parte del cliente pueden modificar los plazos.',
  'Se incluyen ajustes razonables durante la fase de revision. Cambios sustanciales o nuevas funcionalidades fuera del alcance se presupuestaran aparte.',
  'Dominio, hosting, licencias, pasarelas de pago, plugins premium, fotografias, traducciones y servicios de terceros no estan incluidos salvo indicacion expresa.',
  'WebImpulsa no se responsabiliza de interrupciones o cambios de condiciones de servicios externos.',
  'La entrega final se realizara una vez abonado el importe pendiente.',
  'El cliente es responsable de la veracidad del contenido facilitado y de contar con derechos de uso sobre imagenes, marcas y materiales enviados.',
  'Los textos legales definitivos, politica de privacidad, cookies, aviso legal y condiciones de contratacion deben ser revisados por un profesional legal si el proyecto lo requiere.',
  'La propuesta tiene una validez de 15 dias naturales salvo indicacion distinta.',
  'Los importes pueden estar sujetos a IVA u otros impuestos aplicables.'
];

function escapeHtml(v){return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
function eur(v){return new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(Number(v||0));}
function textOrDash(v){var s=String(v||'').trim();return s?escapeHtml(s):'&mdash;';}
function nl2br(v){return escapeHtml(v||'').replace(/\n/g,'<br>');}
function list(items,cls){return '<ul class="'+(cls||'proposal-list')+'">'+items.map(function(i){return '<li>'+escapeHtml(i)+'</li>';}).join('')+'</ul>';}
function formatDate(v){if(!v)return '';var p=String(v).split('-');return p.length===3?p[2]+'/'+p[1]+'/'+p[0]:v;}
function buildBudgetNumber(date){date=date||new Date();var y=date.getFullYear(),m=String(date.getMonth()+1).padStart(2,'0'),d=String(date.getDate()).padStart(2,'0');return 'WI-'+y+m+d+'-'+String(Math.floor(1000+Math.random()*9000));}

function buildProposalData(input){
  input=input||{};
  var projectType=input.projectType||'Landing page';
  var subtotal=(input.basePrice||0)+(input.extrasTotal||0)+(input.rushAmount||0);
  var discount=input.discountAmount||0;
  var taxableBase=Math.max(0,subtotal-discount);
  var vat=Math.round(taxableBase*VAT_RATE);
  var totalWithVat=taxableBase+vat;
  var items=[{concept:projectType,qty:1,unit:input.basePrice||0,subtotal:input.basePrice||0}];
  (input.extras||[]).forEach(function(extra){items.push({concept:'Extra: '+extra.name,qty:1,unit:extra.price,subtotal:extra.price});});
  if(input.rushAmount>0)items.push({concept:'Entrega urgente +25%',qty:1,unit:input.rushAmount,subtotal:input.rushAmount});
  return {
    company:Object.assign({},WEBIMPULSA_COMPANY,input.company||{}),
    budgetNumber:input.budgetNumber||buildBudgetNumber(),
    issueDate:input.issueDate||new Date().toISOString().slice(0,10),
    validUntilText:'15 dias naturales',
    client:input.client||{},
    project:{name:input.projectName||'',type:projectType,goal:input.goal||'',businessDescription:input.businessDescription||'',selectedFeatures:input.selectedFeatures||'',notes:input.notes||'',desiredDeadline:(input.deadline||'').trim()||DEADLINES[projectType]||'Segun alcance',startDate:input.startDate||'',paymentMethod:input.paymentMethod||'50-50',customPayment:input.customPayment||''},
    scope:PROJECT_SCOPES[projectType]||PROJECT_SCOPES['Proyecto a medida'],
    outOfScope:OUT_OF_SCOPE,
    phases:PHASES,
    conditions:CONDITIONS,
    pricing:{items:items,basePrice:input.basePrice||0,extrasTotal:input.extrasTotal||0,rushAmount:input.rushAmount||0,discountAmount:discount,taxableBase:taxableBase,vat:vat,totalWithVat:totalWithVat,maintenanceName:input.maintenanceName||'',maintenancePrice:input.maintenancePrice||0,maintenanceInfo:input.maintenanceInfo||''}
  };
}

function paymentText(data){
  var map={'50-50':'50% al aceptar y 50% antes de publicar.','3-way':'3 pagos del 33% cada uno: al aceptar, a mitad de proyecto y antes de la entrega.','full':'Pago unico del importe acordado.','custom':data.project.customPayment||'Pago personalizado pendiente de confirmar.'};
  return (map[data.project.paymentMethod]||map['50-50'])+' El proyecto comenzara tras la aceptacion del presupuesto y el abono del pago inicial acordado. La entrega/publicacion final se realizara tras la validacion del cliente y el abono del importe pendiente.';
}
function maintenanceText(data){
  if(data.pricing.maintenancePrice>0)return 'Mantenimiento '+escapeHtml(data.pricing.maintenanceName||'seleccionado')+': '+eur(data.pricing.maintenancePrice)+'/mes. '+escapeHtml(data.pricing.maintenanceInfo||'Incluye soporte y mantenimiento mensual segun el plan acordado.')+' Se factura aparte de la creacion inicial.';
  return 'No incluido en esta propuesta.';
}

function renderProposal(data){
  var clientName=data.client.name||'Cliente pendiente';
  var rows=data.pricing.items.map(function(item){return '<tr><td>'+escapeHtml(item.concept)+'</td><td class="num">'+item.qty+'</td><td class="num">'+eur(item.unit)+'</td><td class="num">'+eur(item.subtotal)+'</td></tr>';}).join('');
  return '<article class="proposal-a4"><div class="proposal-doc">'+
  '<header class="proposal-hero"><div><img class="proposal-logo" src="'+escapeHtml(data.company.logoUrl)+'" alt="WebImpulsa"><div class="proposal-kicker">Presupuesto / Propuesta comercial</div><h1>'+escapeHtml(data.project.name||'Proyecto web profesional')+'</h1><div class="proposal-number">'+escapeHtml(data.budgetNumber)+'</div></div><div class="proposal-hero-card"><div class="proposal-meta-row"><span>Fecha</span><strong>'+escapeHtml(formatDate(data.issueDate))+'</strong></div><div class="proposal-meta-row"><span>Validez</span><strong>'+escapeHtml(data.validUntilText)+'</strong></div><div class="proposal-meta-row"><span>Tipo</span><strong>'+escapeHtml(data.project.type)+'</strong></div><div class="proposal-meta-row"><span>Total IVA incl.</span><strong>'+eur(data.pricing.totalWithVat)+'</strong></div></div></header>'+
  '<section class="proposal-two-cols"><div class="proposal-party"><h2>WebImpulsa</h2><p><strong>'+escapeHtml(data.company.tradeName)+'</strong></p><p>'+textOrDash(data.company.legalName)+'</p><p>NIF/CIF/NIE: '+textOrDash(data.company.taxId)+'</p><p>Email: '+textOrDash(data.company.email)+'</p><p>Tel./WhatsApp: '+textOrDash(data.company.phone)+'</p><p>Web: '+textOrDash(data.company.website)+'</p><p>Direccion: '+textOrDash(data.company.address)+'</p></div>'+
  '<div class="proposal-party"><h2>Cliente</h2><p><strong>'+escapeHtml(clientName)+'</strong></p><p>NIF/CIF/NIE: '+textOrDash(data.client.taxId)+'</p><p>Contacto: '+textOrDash(data.client.contactPerson)+'</p><p>Email: '+textOrDash(data.client.email)+'</p><p>Telefono: '+textOrDash(data.client.phone)+'</p><p>Direccion: '+textOrDash(data.client.address)+'</p><p>Ciudad/provincia: '+textOrDash(data.client.city)+'</p><p>Tipo de negocio: '+textOrDash(data.client.businessType)+'</p></div></section>'+
  '<section class="proposal-section"><h2>Resumen ejecutivo</h2><p>WebImpulsa presenta esta propuesta para el diseno y desarrollo de una solucion web orientada a mejorar la presencia digital, captar clientes y facilitar la gestion del negocio.</p>'+(data.project.goal?'<p><strong>Objetivo principal:</strong> '+nl2br(data.project.goal)+'</p>':'')+(data.project.businessDescription?'<p><strong>Descripcion del negocio:</strong> '+nl2br(data.project.businessDescription)+'</p>':'')+'</section>'+
  '<section class="proposal-section"><h2>Alcance del proyecto</h2>'+list(data.scope,'proposal-grid-list')+(data.project.selectedFeatures?'<p><strong>Funcionalidades indicadas por el cliente:</strong><br>'+nl2br(data.project.selectedFeatures)+'</p>':'')+'</section>'+
  '<section class="proposal-section"><h2>Fuera de alcance</h2>'+list(data.outOfScope,'proposal-grid-list')+'</section>'+
  '<section class="proposal-section"><h2>Fases de trabajo</h2>'+list(data.phases,'proposal-grid-list')+'</section>'+
  '<section class="proposal-section"><h2>Plazos</h2><p>Plazo estimado: <strong>'+escapeHtml(data.project.desiredDeadline)+'</strong>.</p>'+(data.project.startDate?'<p>Fecha estimada de inicio: <strong>'+escapeHtml(formatDate(data.project.startDate))+'</strong>.</p>':'')+'</section>'+
  '<section class="proposal-section"><h2>Presupuesto economico</h2><table class="proposal-table"><thead><tr><th>Concepto</th><th class="num">Cantidad</th><th class="num">Precio unitario</th><th class="num">Subtotal</th></tr></thead><tbody>'+rows+'</tbody></table><div class="proposal-totals"><div class="proposal-total-line"><span>Subtotal antes de descuento</span><strong>'+eur(data.pricing.basePrice+data.pricing.extrasTotal+data.pricing.rushAmount)+'</strong></div><div class="proposal-total-line"><span>Descuento lanzamiento</span><strong>-'+eur(data.pricing.discountAmount)+'</strong></div><div class="proposal-total-line"><span>Base imponible</span><strong>'+eur(data.pricing.taxableBase)+'</strong></div><div class="proposal-total-line"><span>IVA 21%</span><strong>'+eur(data.pricing.vat)+'</strong></div><div class="proposal-total-line total"><span>Total IVA incluido</span><strong>'+eur(data.pricing.totalWithVat)+'</strong></div></div></section>'+
  '<section class="proposal-section"><h2>Forma de pago</h2><p>'+escapeHtml(paymentText(data))+'</p></section>'+
  '<section class="proposal-section"><h2>Mantenimiento</h2><p>'+maintenanceText(data)+'</p></section>'+
  (data.project.notes?'<section class="proposal-section"><h2>Notas adicionales</h2><p>'+nl2br(data.project.notes)+'</p></section>':'')+
  '<section class="proposal-section"><h2>Condiciones basicas de contratacion</h2>'+list(data.conditions)+'</section>'+
  '<section class="proposal-section"><h2>Proteccion de datos / nota legal minima</h2><div class="proposal-note-box">Esta propuesta no sustituye el asesoramiento legal. Las obligaciones en materia de proteccion de datos, cookies, comercio electronico o contratacion online deberan adaptarse al caso concreto del cliente.</div></section>'+
  '<section class="proposal-section"><h2>Aceptacion</h2><p>Checkbox textual: "Acepto el alcance, presupuesto y condiciones indicadas."</p><div class="proposal-acceptance"><div><div class="proposal-sign-line"></div><p>Nombre del cliente: '+textOrDash(clientName)+'</p><p>DNI/NIF/CIF: '+textOrDash(data.client.taxId)+'</p></div><div><div class="proposal-sign-line"></div><p>Fecha:</p><p>Firma:</p></div></div></section>'+
  '<footer class="proposal-footer"><span>'+escapeHtml(data.company.website)+'</span><span>'+escapeHtml(data.company.email)+'</span><span>Presupuesto '+escapeHtml(data.budgetNumber)+' · Pagina 1</span></footer>'+
  '</div></article>';
}

window.WIProposalTemplate={company:WEBIMPULSA_COMPANY,vatRate:VAT_RATE,deadlines:DEADLINES,buildBudgetNumber:buildBudgetNumber,buildProposalData:buildProposalData,renderProposal:renderProposal,eur:eur,escapeHtml:escapeHtml};
})();
