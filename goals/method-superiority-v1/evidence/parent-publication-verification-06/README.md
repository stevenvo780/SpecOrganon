# Verificación independiente del padre: dev6 parcial y cierre dev4

Observación HTTP anónima del 6 de octubre de 2026, 04:34:10 UTC. El script
`verify_http.py` terminó con exit0: ocho manifests, 86 descargas con HTTP200 y
SHA correcto, y las 73 descargas anteriores sin alterar. Confirmó repositorio
público y rama predeterminada main. Doce archivos en total (diez de fuente/control
y dos resúmenes del cierre) se cotejaron entre GitHub main, checkout de publicación y
candidata del padre. No hubo llamadas o tests experimentales.

`public-http-verification.json` conserva el commit observado91abf5f7 y los hashes
de cada descarga/fuente. Es un snapshot fechado; los commits documentales
posteriores deben conservar estos bytes. `stdout` y `stderr` guardan el resultado.

La comprobación UI pertenece al subagente de publicación, con recibo en
`goals/publication-main-20261006/dev6-publication-01/publication-receipt.json`:
desktop1440 y mobile390, sin errores/overflow, nueve enlaces tree/main y 23
referencias al repositorio main por viewport. Su control público comprobó las
86 descargas y los textos de dev6 parcial y dev4 final; el mirror web contiene
177 archivos iguales a las fuentes externas. La consulta del indexador web
del padre no pudo acceder a esta página; no se usa como verificación. HTTP
directo y el navegador real del subagente sí la comprobaron.

Despliegue READY: `dpl_Go1dx8r3fRCe3R32ewaZ3fU22tcq`.
URL canónica: https://specorganon.stevenvallejo.com.
Esto acredita publicación e integridad, no superioridad. Dev6 continúa como
infraestructura parcial; última wheel publicada dev5. El cierre dev4 es5/10,
sin reemplazos ni sujetos reservados. La meta sigue activa.
