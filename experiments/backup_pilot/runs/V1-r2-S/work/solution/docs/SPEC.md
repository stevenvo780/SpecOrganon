# Especificación V1 (derivada antes de implementar)

Fuente normativa: `/trial/CONTRACT.md`, sin modificaciones. Variante V1:
árboles de documentos, contenido binario y directorios vacíos. Todas las
garantías base del contrato siguen siendo obligatorias.

## Criterios de aceptación y trazabilidad

| Criterio | Comportamiento observable | Prueba prevista |
| --- | --- | --- |
| C01 | CLI create/verify/restore/list; éxito 0, un objeto JSON exacto | CLI y ejemplo reproducible |
| C02 | Árbol exacto: archivos, bytes arbitrarios, Unicode, espacios, directorios vacíos | roundtrip y árbol vacío |
| C03 | Repositorio autosuficiente; fuente no cambia | comparar fuente; retirarla antes de restore |
| C04 | IDs válidos, inexistentes rechazados, orden de list, ID existente inmutable | IDs y snapshots sucesivos |
| C05 | Rechazar symlinks y especiales en fuente, repo, destino y snapshots; no seguirlos | enlaces directos/ancestros/internos, FIFO y socket |
| C06 | Fuente y repo no se solapan en ningún sentido | igualdad y ambas inclusiones |
| C07 | Destino no vacío conserva sus bytes; destino vacío aceptado | destino protegido y vacío |
| C08 | Alterar o eliminar datos o metadatos impide verify/restore correcto | matriz de corrupción y estructura |
| C09 | Publicación atómica; SIGKILL preserva anteriores y permite repetir ID incompleto | interrupción con staging observable |
| C10 | list solo devuelve snapshots completos; repo nuevo vacío devuelve [] | vacío, staging abandonado e incompleto |
| C11 | Python 3.12, solo biblioteca estándar; errores no afirman éxito | subprocess, compilación y revisión |
| C12 | create acepta --max-bytes N opcional, entero >= 0; conserva la interfaz anterior | argumentos válidos/ inválidos y create sin límite |
| C13 | Tras éxito, suma de st_size de todos los archivos regulares del repo <= N, incluida metadata y restos | límite alto, exacto, metadata, snapshots previos y staging |
| C14 | Rechazo por capacidad preserva snapshots previos y no deja crecimiento permanente de archivos | N inferior al uso existente, un byte insuficiente, repetición y fuente intacta |
| C15 | Tras SIGKILL se puede repetir el ID incompleto también con límite alcanzable | interrupción real, limpieza de staging abandonado y roundtrip |

## Decisiones del formato y alcance

- Repo: `snapshots/ID/{manifest.json,manifest.sha256,data/}` y `.staging/`
  para creaciones privadas. Repo ausente o vacío es válido para list; create
  inicializa el formato. Otros archivos en la raíz del repo se rechazan.
- Manifiesto versionado, con ID, todas las rutas de directorios (raíz implícita),
  y rutas/tamaños/SHA-256 de archivos. `manifest.sha256` contiene el hash del
  manifiesto. Se comprueba la estructura exacta, sin entradas extra ni duplicadas.
- El sello detecta corrupción accidental; no ofrece autenticidad frente a quien
  reemplaza coordinadamente los datos, el manifiesto y su sello.
- Se inspeccionan componentes de las rutas y árboles gestionados con lstat;
  se rechazan enlaces y tipos que no sean directorio o archivo regular.
  El origen debe ser directorio; IDs usan exactamente el patrón contractual.
- create nunca publica staging hasta terminar los datos y metadatos; renombra
  el directorio completo. Un ID ya publicado se rechaza incluso si está corrupto.
- Cambio solicitado: `create --max-bytes N` es opcional; sin él se conserva el
  comportamiento sin límite. N debe ser un entero decimal no negativo. El
  presupuesto es la suma lógica de `st_size`, no bloques asignados: incluye
  manifiestos, sellos, snapshots previos (incluso incompletos/corruptos) y staging.
  ID, rutas, tamaños, hashes y versión están en el manifiesto regular; no hay
  metadata persistente en xattrs ni solo en nombres.
- create serializa sus escrituras mediante flock sobre el directorio del repo
  (bloqueo transitorio, sin archivo ni registro persistente). Bajo ese bloqueo
  comprueba el uso inicial: si ya supera N, rechaza sin cambiar los archivos.
  Después elimina staging abandonado, que no pertenece a snapshots publicados;
  SIGKILL libera el bloqueo automáticamente. Copia en staging y antes de rename
  vuelve a sumar todos los archivos regulares, incluyendo los recién creados.
  Si supera N, elimina su staging y falla. El límite es sobre el resultado
  exitoso; puede superarse transitoriamente durante la copia.
- verify comprueba el sello, esquema, ID, rutas, árbol completo, tamaños y hashes.
  list valida los snapshots publicados e incluye solo los íntegros; los
  incompletos/corruptos se omiten. Una ruta insegura en el repo causa error.
- restore valida antes de preparar el destino y copia a un directorio hermano
  privado; vuelve a comprobar los bytes copiados y publica mediante rename.
  Destino ausente o directorio vacío válido; no se permite solaparlo con repo.
- No se preservan permisos, UID, ACL, tiempos ni identidad de hardlinks.
  Se presupone fuente estable y ausencia de sustitución concurrente maliciosa
  de componentes. No se promete transacción simultánea con actores externos
  que modifiquen repo/destino, ni recuperación tras fallo de energía.
- Plataforma de verificación: Python 3.12 en Linux; sin paquetes externos.

## Actualización de alcance

Se leyó íntegro el contrato actualizado antes de adaptar código y pruebas.
C01–C11 permanecen obligatorios; C12–C15 derivan del cambio --max-bytes.
CONTRACT.md no se modifica. La suite heredada intentaba crear un socket por
bind, prohibido por el contenedor. Se ajusta la prueba para crear un inode
real S_IFSOCK mediante mknod cuando bind falla; se comprobará su tipo con
lstat antes de ejercer el rechazo. Si tampoco se permite mknod, se registra
una omisión sin afirmar cobertura real.

## Interfaz de errores

Éxito: una línea JSON en stdout con los campos exactos del contrato.
Error: código no cero, stdout vacío y diagnóstico en stderr. Los errores de
argumentos también fallan. Ninguna operación devuelve `valid: true` sin verificar.
