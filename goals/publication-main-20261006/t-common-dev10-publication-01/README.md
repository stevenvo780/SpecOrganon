# Publicación prospectiva dev10, ingeniería parcial

El snapshot público de fuente y web es `425b7fb089447ff4aa6dd54652f9f181b42451e1`.
Su árbol Git `1241c76e76c19395d97b227475fecdf818172aa0` coincide byte por byte con
el snapshot local archivado. La fuente candidata local original es `0f0d0934`;
`commit-provenance.json` distingue esos commits y los picks preservados.

La publicación utilizó el conector GitHub de la misma cuenta `stevenvo780`,
con lease contra main y force=false, después de dos esperas fallidas del helper
CLI. Ambos errores están conservados. No se cambiaron cuentas, perfiles ni
credenciales. La historia anterior de main y la rama local de integración quedan
preservadas. No hubo modelos, pruebas de código, Docker o pilotos nuevos en la
publicación.

Vercel confirmó producción READY `dpl_91teJUnW2cgeEAK2EfiP8rDKYHEi`.
[Web compartible](https://specorganon.stevenvallejo.com/#avance-dev10) y
[repositorio main](https://github.com/stevenvo780/SpecOrganon/tree/main).
El build pasó. Las pruebas reales de navegador comprobaron escritorio/móvil,
16 enlaces main por vista, cero errores/desbordamiento del cuerpo y las 99
descargas con SHA, preservando las 94 históricas y nueve manifiestos anteriores.
Las cinco nuevas descargas tienen otro manifiesto. El control inicial de móvil
detectó desbordamiento de la tabla; se corrigió el contenedor y la repetición
pasó. El warning de EOF de una prueba original se conserva sin normalizar bytes.

El padre verificó por HTTP anónimo 45 módulos y las dos GOALs en el commit
público, y 26 archivos de la web: los recibos originales están en
`../../method-superiority-v1/evidence/parent-publication-verification-17/`.
La verificación de HTTP no acredita UI renderizada; navegador/capturas son
controles del publisher, con atribución separada.

Dev10 sigue parcial: cuatro hallazgos tienen correcciones; el deadline común
del transporte y la recuperación verificada de fallos nativos no cero siguen
abiertos. El código final necesita revisión independiente. No hay nueva admisión
T, generaciones nativas, versión completa congelada, calificación, F externo
ni superioridad. Los seis originales dev8 mantienen cuatro fallidos y dos
review_ready, con common_complete/F null. La goal permanece ACTIVE.
