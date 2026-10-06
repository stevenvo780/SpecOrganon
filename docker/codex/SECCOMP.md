# Compatibilidad del sandbox de Codex

Fuente del allowlist base: https://github.com/moby/profiles/blob/main/seccomp/default.json
Copia de desarrollo: experiments/backup_pilot/development/docker-default-seccomp.json.
El SHA256 de la copia y del perfil aplicado queda en los artefactos congelados.
El proyecto Moby publica perfiles bajo Apache-2.0.

Se añade SCMP_ACT_ALLOW exclusivamente para clone, unshare, mount, umount2,
pivot_root. Las pruebas de omisión identificaron esos cinco como necesarios;
setns no fue necesario y no se amplió. El perfil no es una copia garantizada
exacta del default incorporado en la versión del daemon local.

Docker AppArmor default bloquea los montajes de Bubblewrap aun con el perfil
seccomp corregido. Sólo el servicio Codex y contenedores de modelo del piloto
usan apparmor=unconfined. No se cambia ni descarga la política del host. Esta
excepción elimina esa capa AppArmor para dichos contenedores; no es aislamiento
completo frente a código hostil o fallos del kernel. Permanece el filtro seccomp,
cap_drop ALL, UID1000, no-new-privileges y el sandbox workspace-write/read-only de
Codex. No se usa --privileged ni CAP_SYS_ADMIN, socket Docker o filesystem host.

Las pruebas development/preflight2-{N,S,T}.jsonl demuestran escritura en /trial
permitida y en /home/codex/sandbox-outside-probe.txt rechazada. La configuración
legacy Landlock fue probada y rechazada por la CLI actual, por lo que no se usa.
El evaluador de candidatos no necesita esta excepción y conserva perfiles usuales.
