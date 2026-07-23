# Rollback de `prospeccion` (chequeo digital rework + mapa) — verificado 2026-07-23

Corrige la nota de rollback dada tras el despliegue del 2026-07-23: **`git revert -m 1 79cdaa1`
revierte solo el código, no las migraciones `prospeccion.0001_initial` ni `crm.0009_alter_lead_source`**.
Como esas migraciones solo hacen `CreateModel`/`AddIndex` (prospeccion) y un `AlterField` de solo
metadatos (`choices` en `crm.Lead.source`, sin tocar el tipo de columna), son reversibles sin pérdida
de datos — verificado en una copia descartable de la BD (nunca sobre la real): `manage.py migrate
prospeccion zero` + `manage.py migrate crm 0008_...` y vuelta a aplicar, sin errores.

Backups disponibles:
- `/home/seradmin/webimpulsa/db.sqlite3.bak-prospeccion-20260723_083043` — **antes** de que
  `prospeccion`/`crm.0009` tocaran la BD por primera vez (Etapa 0 del plan). Úsalo solo para el
  rollback de emergencia (escenario A) — restaurarlo pierde cualquier dato de `prospeccion` (empresas,
  chequeos, leads/presupuestos vía Mapa Digital) creado después de esa hora.
- `/home/seradmin/webimpulsa/db.sqlite3.backup-postdeploy-audit-<fecha>` — copia consistente hecha con
  `sqlite3.backup()` (no un `cp` a pelo) durante la auditoría post-deploy, con la BD ya en su estado
  actual (post-despliegue). Sirve como punto de restauración más reciente si algo se rompe *después*
  de esta auditoría.

## Escenario A — Rollback completo de emergencia (pierde datos nuevos de `prospeccion`)

Úsalo solo si el sitio está roto de verdad y hay que volver al estado de antes de este feature ya,
aceptando perder lo que se haya cargado en el mapa desde el despliegue.

```bash
sudo systemctl stop webimpulsa.service

# por si acaso, guarda el estado roto antes de sobrescribir nada
cp /home/seradmin/webimpulsa/app/db.sqlite3 \
   /home/seradmin/webimpulsa/db.sqlite3.before-emergency-rollback-$(date +%Y%m%d_%H%M%S)

# restaura la BD a como estaba ANTES de que prospeccion existiera
cp /home/seradmin/webimpulsa/db.sqlite3.bak-prospeccion-20260723_083043 \
   /home/seradmin/webimpulsa/app/db.sqlite3

cd /home/seradmin/webimpulsa/app
git revert -m 1 79cdaa1   # deshace todo el merge en un commit nuevo, no reescribe historia

sudo systemctl start webimpulsa.service
curl -s -o /dev/null -w "%{http_code}\n" https://webimpulsa.es/chequeo-digital/
```

## Escenario B — Rollback suave (no pierde datos nuevos)

**B1 — el problema está en el mapa/CRM, no en el chequeo público:** el chequeo público
(`/chequeo-digital/`) depende de los endpoints `questionnaire_json`/`submit_public_audit` en
`prospeccion/urls.py` — no los toques. Comenta solo las rutas de `/panel/prospeccion/*` y
`/mapa-digital/*` en `prospeccion/urls.py`, deja las de `chequeo-digital/api/...` y
`chequeo-digital/e/<token>/...` intactas, y reinicia el servicio. Cero cambios de BD, cero pérdida de
datos, reversible con el mismo diff al revés.

**B2 — hay que deshacer también las migraciones sin perder filas ya creadas:** dado que son
reversibles (verificado arriba), basta con:
```bash
cd /home/seradmin/webimpulsa/app
python manage.py migrate prospeccion zero
python manage.py migrate crm 0008_proposal_accepted_consents_proposal_accepted_ip_and_more
```
Esto **borra las tablas `prospeccion_*`** (con sus filas) al deshacer `0001_initial` — por tanto B2
solo evita perder datos de **otras** apps (`crm`/`core`/`planner`), no los de `prospeccion` en sí. Si
lo que hay que preservar son justamente los prospectos/audits ya cargados, usa B1 en su lugar (deja
las tablas como están, solo desactiva las rutas nuevas) o haz un `dumpdata prospeccion` antes de B2
para poder recuperarlos después con `loaddata`.

**El rollback del propio rediseño del chequeo (`debbc81`, `3104479`) no es un revert de un commit
suelto**: los commits posteriores (mapa, CRM, PDF) siguen añadiendo código sobre los mismos ficheros
(`prospeccion/views_public.py`, `templates/chequeo_digital.html`), así que un `git revert 3104479`
suelto chocaría con ellos. Si el defecto está en el núcleo del chequeo (no en el mapa), la opción
segura es un commit de arreglo dirigido (forward-fix) en vez de revertir un commit antiguo a ciegas, o
el rollback completo (escenario A) si es urgente.
