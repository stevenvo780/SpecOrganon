# Verificación independiente del padre: controles dev6 parciales

Observación HTTP anónima del 6 de octubre de 2026, **06:17:17 UTC**, sobre
main fuente `0eeb94c79b53b6239239f8648bb003dc776a0a71`. El verificador terminó
exit0: **94 descargas con HTTP200 y SHA correcto**, nueve manifests, los SHA de
las 86 descargas anteriores intactos y **22 fuentes/recibos** iguales entre
commit remoto, checkout de publicación y candidata del padre. Repositorio público,
rama predeterminada main. `manifest-byte-verification.json` comprueba además los
bytes exactos de los nueve manifests por HTTP. Ninguna llamada nueva a modelos o
ejecución experimental pertenece a esta verificación.

La página canónica respondió HTTP200. Su HTML y cinco assets JS/preload/CSS
coinciden byte por byte con el build publicado; el bundle contiene el hito
controles-dev6 y su conteo627. Es una SPA: la primera invocación del verificador
esperaba erróneamente esos textos en HTML sin ejecutar JS y falló la aserción.
Se conserva en stderr-01, junto al HTML observado. La versión corregida comprueba
el HTML y los assets; no atribuye un render propio a una lectura HTTP. La UI real
es comprobación del subagente de publicación: escritorio/móvil, sin errores ni
overflow, diez enlaces tree/main y24 referencias relevantes main por vista.
Recibo: `goals/publication-main-20261006/staged-controls-publication-01/publication-receipt.json`.

Despliegue READY: `dpl_22NJp9MvyN1eCMfMBAJNjSBAnw3M`.
URL canónica: https://specorganon.stevenvallejo.com/#controles-dev6.
Los commits documentales posteriores deben conservar los bytes comparados.
`local-integration-verification.json` registra el control local previo de17
fuentes/recibos, sin confundirlo con esta observación remota posterior.

Hito limitado: selección627passed/16skipped, trece controles Docker reales con
roles sintéticos/simulador explícito, wheel local36módulos+CLI/MCP host24herramientas,
revisión independiente focalizada de recuperación aceptada. No imagen dev6
instalada, nueva wheel liberada, proveedor nativo dev6, versión completa congelada
ni superioridad. Cero generaciones nativas dev6 y reservados; F/common_complete
siguen desconocidos. El cierre original dev4 permanece5/10, no9/10. Meta ACTIVE.
