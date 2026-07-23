# Desarrollo y despliegue de webimpulsa — leer antes de tocar código en este servidor

## El riesgo que esto corrige

`webimpulsa.service` corre Gunicorn con `WorkingDirectory=/home/seradmin/webimpulsa/app` — **la
misma carpeta donde vive el repo git y donde se trabaja con Claude Code**. Hasta el 2026-07-23, el
comando de Gunicorn incluía `--reload`, que vigila los ficheros de esa carpeta y reinicia workers en
cuanto cambian **sin importar qué rama de git esté activa**. Consecuencia real observada durante el
desarrollo de `prospeccion`: hacer `git checkout feature/...` o simplemente editar un fichero con el
editor bastaba para que el sitio en producción empezara a servir código sin revisar, sin que nadie
ejecutara `systemctl restart` ni hiciera un merge — el propio `git checkout` ya era, de facto, un
despliegue.

**Ya corregido**: `--reload` se quitó del `ExecStart` de producción (ver `deploy/webimpulsa.service`
en este repo, que es la copia de referencia versionada del unit real en
`/etc/systemd/system/webimpulsa.service` — si un día se edita el unit real, hay que reflejar el mismo
cambio aquí en un commit, para que nunca queden desincronizados). A partir de ahora, cambiar ficheros
o cambiar de rama en esta carpeta **no** reinicia nada — hace falta un `systemctl restart` explícito.

## Regla de oro

**Nunca hagas `git checkout <rama-feature>` dentro de `/home/seradmin/webimpulsa/app`.** Esa carpeta
es la que sirve producción; su working tree debe estar en `master` siempre que el servicio esté
activo. Para revisar o seguir trabajando en una rama sin tocar lo que ve el público, usa un
`git worktree` aparte (ver más abajo) — nunca la carpeta de producción.

## Cómo revisar una rama sin arriesgar producción

```bash
mkdir -p /home/seradmin/review
cd /home/seradmin/webimpulsa/app
git worktree add /home/seradmin/review/webimpulsa-<nombre-rama> <nombre-rama>
```

Eso crea una copia de trabajo independiente en `/home/seradmin/review/webimpulsa-<nombre-rama>/`,
con su propia carpeta pero compartiendo el mismo historial de commits — puedes correr
`manage.py runserver` en otro puerto ahí, revisar el diff, correr tests, lo que haga falta, sin que
Gunicorn se entere (esa carpeta no es su `WorkingDirectory`). Nota: esa copia necesita su propio
`.env` y probablemente su propia base de datos/venv si se quiere levantar el servidor de verdad —
para solo leer código y correr tests contra una copia de la BD, con clonar el árbol de ficheros basta.

Cuando termines de revisar:
```bash
git worktree remove /home/seradmin/review/webimpulsa-<nombre-rama>
```

Alternativa igual de válida: un `git clone` aparte del repo (`git clone /home/seradmin/webimpulsa/app
/home/seradmin/review/webimpulsa-copia`) si se prefiere una copia totalmente independiente en vez de
un worktree que comparte el `.git`.

## Orden correcto para desplegar un cambio

1. `git checkout -b feature/...` — **en una copia de revisión**, no en la carpeta de producción,
   salvo que el propio cambio sea justo pasar esa carpeta a `master` (paso 5).
2. Desarrollar, `manage.py check`, `manage.py test`.
3. Revisión (propia o de Sergey) del diff — sin fusionar todavía.
4. `git merge` a `master` — puede hacerse desde cualquier copia con acceso de escritura al remoto;
   no hace falta estar en la carpeta de producción para fusionar.
5. **Solo entonces**, en `/home/seradmin/webimpulsa/app`: `git checkout master` (si no lo estaba ya) y
   `git pull` si el merge se hizo en otra copia.
6. `manage.py migrate` si hay migraciones nuevas.
7. `manage.py collectstatic` si el cambio toca estáticos y el proyecto los sirve así (confirmar si
   aplica antes de asumirlo — hoy Nginx sirve `static/` directo, no vía `collectstatic`, pero
   revisarlo si eso cambia).
8. `sudo systemctl restart webimpulsa.service` — **el único momento en el que el código nuevo pasa a
   servirse**, ahora que no hay `--reload`.
9. Verificar con `curl` (directo a `127.0.0.1:8001` y por el dominio público) antes de dar el
   despliegue por bueno.

## Notas

- El unit real vive en `/etc/systemd/system/webimpulsa.service` (root, fuera del repo). Este
  `deploy/webimpulsa.service` es solo la copia de referencia para llevar el cambio bajo control de
  versiones — no se aplica sola, hay que copiarla a `/etc/systemd/system/` y hacer
  `sudo systemctl daemon-reload` para que surta efecto.
- Antes de cualquier cambio al unit real: `sudo cp /etc/systemd/system/webimpulsa.service
  /etc/systemd/system/webimpulsa.service.bak-$(date +%Y%m%d_%H%M%S)`.
