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
  el directorio completo. Los restos de SIGKILL se ignoran, sin eliminarlos ni
  bloquear la repetición. Un ID ya publicado se rechaza incluso si está corrupto.
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

## Interfaz de errores

Éxito: una línea JSON en stdout con los campos exactos del contrato.
Error: código no cero, stdout vacío y diagnóstico en stderr. Los errores de
argumentos también fallan. Ninguna operación devuelve `valid: true` sin verificar.
