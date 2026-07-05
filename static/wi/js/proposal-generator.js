(function(){
'use strict';

var STORAGE_KEY='wi_proposal_draft_v1';
var lastData=null;
function qs(sel,root){return(root||document).querySelector(sel);}
function qsa(sel,root){return Array.prototype.slice.call((root||document).querySelectorAll(sel));}
function parseMoney(text){var clean=String(text||'').replace(/[^\d,-]/g,'').replace(/\./g,'').replace(',','.');return Number(clean||0);}

function currentCalcState(){
  var project=qs('#calcProjectGrid .calc-project.active');
  var extras=qsa('#calcExtrasGrid .calc-extra.selected').map(function(card){return{name:card.dataset.name||(qs('.calc-extra-name',card)||{}).textContent||'Extra',price:Number(card.dataset.price||0)};});
  var maintenance=qs('#calcMaintGrid .calc-maint-opt.selected');
  var subtotal=Number(project?project.dataset.base:0)+extras.reduce(function(sum,extra){return sum+extra.price;},0);
  var rush=qs('#calcRush')&&qs('#calcRush').classList.contains('selected');
  var rushAmount=rush?Math.round(subtotal*.25):0;
  return {
    projectType:project?project.dataset.name:((qs('#calcProjLabel')||{}).textContent||'Landing page'),
    basePrice:Number(project?project.dataset.base:0),
    extras:extras,
    extrasTotal:extras.reduce(function(sum,extra){return sum+extra.price;},0),
    rush:rush,
    rushAmount:rushAmount,
    discountAmount:parseMoney((qs('#calcDiscountVal')||{}).textContent),
    maintenanceName:maintenance?(maintenance.dataset.name||'').trim():'',
    maintenancePrice:Number(maintenance?maintenance.dataset.price:0),
    maintenanceInfo:maintenance?(maintenance.dataset.info||''):''
  };
}

function loadDraft(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');}catch(e){return null;}}
function saveDraft(draft){localStorage.setItem(STORAGE_KEY,JSON.stringify(draft));}
function getOrCreateBudgetNumber(){var saved=loadDraft();return saved&&saved.budgetNumber?saved.budgetNumber:window.WIProposalTemplate.buildBudgetNumber();}
function defaultDraft(){
  var calc=currentCalcState();
  return {
    budgetNumber:getOrCreateBudgetNumber(),
    issueDate:new Date().toISOString().slice(0,10),
    clientName:'',
    clientTaxId:'',
    clientEmail:'',
    clientPhone:'',
    clientAddress:'',
    clientCity:'',
    clientContactPerson:'',
    clientBusinessType:'',
    projectName:calc.projectType+' para cliente',
    goal:'',
    businessDescription:'',
    selectedFeatures:calc.extras.map(function(extra){return extra.name;}).join('\n'),
    deadline:window.WIProposalTemplate.deadlines[calc.projectType]||'',
    startDate:'',
    notes:'',
    paymentMethod:'50-50',
    customPayment:''
  };
}

function field(name,label,type,placeholder,full){return '<div class="'+(full?'proposal-field-full':'')+'"><label for="proposal_'+name+'">'+label+'</label><input id="proposal_'+name+'" name="'+name+'" type="'+(type||'text')+'" placeholder="'+(placeholder||'')+'"></div>';}
function area(name,label,placeholder){return '<div class="proposal-field-full"><label for="proposal_'+name+'">'+label+'</label><textarea id="proposal_'+name+'" name="'+name+'" placeholder="'+(placeholder||'')+'"></textarea></div>';}
function formHtml(){return ''+
'<input type="hidden" id="proposal_budgetNumber" name="budgetNumber"><input type="hidden" id="proposal_issueDate" name="issueDate">'+
'<div class="proposal-form-section"><h3>Datos del cliente</h3><div class="proposal-form-grid">'+
field('clientName','Nombre / empresa','text','Cliente pendiente')+field('clientTaxId','NIF / CIF / NIE','text','Opcional')+field('clientEmail','Email','email','cliente@email.com')+field('clientPhone','Telefono','tel','600 000 000')+field('clientAddress','Direccion','text','Opcional',true)+field('clientCity','Ciudad / provincia','text','Madrid')+field('clientContactPerson','Persona de contacto','text','Nombre')+field('clientBusinessType','Tipo de negocio','text','Restaurante, clinica, tienda...',true)+
'</div></div>'+
'<div class="proposal-form-section"><h3>Detalles del proyecto</h3><div class="proposal-form-grid">'+
field('projectName','Nombre del proyecto','text','Nueva web corporativa',true)+area('goal','Objetivo principal','Captar clientes, automatizar reservas, mejorar imagen...')+area('businessDescription','Descripcion breve del negocio','Que hace el negocio y a que cliente se dirige')+area('selectedFeatures','Funcionalidades incluidas','Se rellena con los extras seleccionados, puedes ajustar el texto')+field('deadline','Plazo deseado','text','10-20 dias laborables')+field('startDate','Fecha estimada de inicio','date','')+area('notes','Notas adicionales','Cualquier condicion o detalle relevante')+
'<div class="proposal-field-full"><label for="proposal_paymentMethod">Forma de pago preferida</label><select id="proposal_paymentMethod" name="paymentMethod"><option value="50-50">50% al aceptar y 50% antes de publicar</option><option value="3-way">3 pagos del 33% (aceptar / mitad / entrega)</option><option value="full">Pago unico</option><option value="custom">Pago personalizado</option></select></div>'+area('customPayment','Pago personalizado','Solo si seleccionas pago personalizado')+
'</div></div>';}

function createModal(){
  if(qs('#proposalGeneratorModal'))return;
  var wrapper=document.createElement('div');
  wrapper.innerHTML='<div class="modal fade proposal-modal" id="proposalGeneratorModal" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-dialog-centered modal-dialog-scrollable"><div class="modal-content"><div class="proposal-shell"><aside class="proposal-editor"><div class="d-flex align-items-start justify-content-between gap-3 mb-2"><div><h2 class="proposal-editor-title">Generador de Presupuesto Profesional</h2><p class="proposal-editor-subtitle">Los importes se toman de la calculadora actual. Completa los datos y revisa la propuesta en vivo.</p></div><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div><form id="proposalForm">'+formHtml()+'<div class="proposal-actions proposal-no-print"><button type="button" class="btn btn-primary" data-proposal-action="print">Descargar PDF</button><button type="button" class="btn btn-outline-primary" data-proposal-action="word">Descargar Word/DOC</button><button type="button" class="btn btn-outline-dark-wi" data-proposal-action="copy">Copiar resumen</button><button type="button" class="btn btn-green" data-proposal-action="whatsapp">Enviar WhatsApp</button><button type="button" class="btn btn-outline-primary" data-proposal-action="reset">Limpiar datos</button><button type="button" class="btn btn-outline-dark-wi" data-bs-dismiss="modal">Volver a editar</button></div></form></aside><main class="proposal-preview-pane"><div id="proposalPreview"></div></main></div></div></div></div>';
  document.body.appendChild(wrapper.firstElementChild);
  bindModal();
}

function bindModal(){
  var form=qs('#proposalForm');
  form.addEventListener('input',updatePreview);
  form.addEventListener('change',updatePreview);
  qsa('[data-proposal-action]').forEach(function(btn){btn.addEventListener('click',function(){runAction(btn.dataset.proposalAction);});});
}
function collectDraft(){var draft={};qsa('#proposalForm [name]').forEach(function(el){draft[el.name]=el.value;});return draft;}
function fillForm(draft){Object.keys(draft).forEach(function(k){var el=qs('#proposal_'+k);if(el)el.value=draft[k]==null?'':draft[k];});}
function proposalInputFromForm(){
  var draft=collectDraft(),calc=currentCalcState();
  return Object.assign({},calc,{budgetNumber:draft.budgetNumber||getOrCreateBudgetNumber(),issueDate:draft.issueDate,client:{name:draft.clientName,taxId:draft.clientTaxId,email:draft.clientEmail,phone:draft.clientPhone,address:draft.clientAddress,city:draft.clientCity,contactPerson:draft.clientContactPerson,businessType:draft.clientBusinessType},projectName:draft.projectName,goal:draft.goal,businessDescription:draft.businessDescription,selectedFeatures:draft.selectedFeatures,deadline:draft.deadline,startDate:draft.startDate,notes:draft.notes,paymentMethod:draft.paymentMethod,customPayment:draft.customPayment});
}
function updatePreview(){var draft=collectDraft();saveDraft(draft);lastData=window.WIProposalTemplate.buildProposalData(proposalInputFromForm());qs('#proposalPreview').innerHTML=window.WIProposalTemplate.renderProposal(lastData);}
function validateBeforeExport(){
  var draft=collectDraft();
  if(!(draft.clientName||'').trim()){if(!confirm('No has indicado cliente. ¿Usar "Cliente pendiente"?'))return false;qs('#proposal_clientName').value='Cliente pendiente';}
  if(!(draft.projectName||'').trim()){alert('Indica el nombre del proyecto antes de generar el documento.');qs('#proposal_projectName').focus();return false;}
  updatePreview();return true;
}
function runAction(action){if(action!=='reset'&&!validateBeforeExport())return;if(action==='print')printProposal();if(action==='word')exportDocx();if(action==='copy')copySummary();if(action==='whatsapp')sendWhatsApp();if(action==='reset')resetDraft();}
function documentHtml(){var cssHref=location.origin+'/static/wi/css/proposal-print.css';return '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>'+window.WIProposalTemplate.escapeHtml(lastData.budgetNumber)+'</title><link rel="stylesheet" href="'+cssHref+'"></head><body class="proposal-print-body">'+window.WIProposalTemplate.renderProposal(lastData)+'</body></html>';}
function printProposal(){var win=window.open('','_blank','noopener,noreferrer,width=960,height=900');if(!win){alert('El navegador ha bloqueado la ventana de impresion. Permite popups para descargar el PDF.');return;}win.document.open();win.document.write(documentHtml());win.document.close();setTimeout(function(){win.focus();win.print();},450);}
function exportDocx(){
  // TODO tecnico: para .docx real, anadir una libreria ZIP/DOCX ligera o endpoint backend.
  // Esta version genera un .doc HTML editable, compatible con Word/LibreOffice sin dependencias.
  var blob=new Blob(['\ufeff',documentHtml()],{type:'application/msword;charset=utf-8'});
  downloadBlob(blob,filenameBase()+'.doc');
}
function downloadBlob(blob,filename){var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},0);}
function filenameBase(){return(lastData&&lastData.budgetNumber?lastData.budgetNumber:'WI-presupuesto').replace(/[^\w-]+/g,'-');}
function generateWhatsAppText(){var data=lastData||window.WIProposalTemplate.buildProposalData(proposalInputFromForm());return 'Hola, he generado una propuesta estimada en WebImpulsa:\nCliente: '+(data.client.name||'Cliente pendiente')+'\nProyecto: '+(data.project.name||'Proyecto pendiente')+'\nTipo: '+data.project.type+'\nTotal estimado IVA incluido: '+window.WIProposalTemplate.eur(data.pricing.totalWithVat)+'\nMe gustaria revisarla y confirmar el alcance.';}
function copySummary(){var text=generateWhatsAppText();if(navigator.clipboard){navigator.clipboard.writeText(text).then(function(){alert('Resumen copiado.');});}else{window.prompt('Copia el resumen:',text);}}
function sendWhatsApp(){window.open('https://wa.me/34613708322?text='+encodeURIComponent(generateWhatsAppText()),'_blank');}
function resetDraft(){if(!confirm('¿Limpiar los datos del borrador de propuesta?'))return;localStorage.removeItem(STORAGE_KEY);fillForm(defaultDraft());updatePreview();}

function openGenerator(){
  createModal();
  var saved=loadDraft(),draft=Object.assign(defaultDraft(),saved||{}),calc=currentCalcState();
  if(!saved){draft.selectedFeatures=calc.extras.map(function(extra){return extra.name;}).join('\n');draft.deadline=window.WIProposalTemplate.deadlines[calc.projectType]||draft.deadline;draft.projectName=calc.projectType+' para cliente';}
  fillForm(draft);updatePreview();new bootstrap.Modal(qs('#proposalGeneratorModal')).show();
}

window.WIProposal={open:openGenerator,buildProposalData:function(){return window.WIProposalTemplate.buildProposalData(proposalInputFromForm());},generateWhatsAppText:generateWhatsAppText,printProposal:printProposal,exportDocx:exportDocx};
})();
