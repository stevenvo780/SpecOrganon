# D-106 · Repetición de conteos desde filas archivadas

Plan registrado en `3a710a8`; ejecutor corregido, entorno y fuentes congelados
en `401d402`, antes de una única ejecución del analizador histórico.

## Resultado observado

El [Parquet público fijado](https://github.com/NYCComptroller/citi-bike-gbfs/blob/4c36513cf3842efe9a2940a78974bf45cb13fc0b/dataset.parquet)
contiene 10.853.196 bytes, SHA256 `661221e1…b52fc4` y Git blob SHA1
`6efe8e7c…50facdf`. Se verificaron ambos hashes y se copiaron los mismos bytes
a un `memfd` con los cuatro sellos efectivos, máscara 15. Las lecturas de
hash, Parquet y tamaño del analizador original resolvieron ese descriptor.
El código original, SHA256 `e384b43d…3bf949`, se ejecutó desde stdin sin editar.

[execution.json](execution.json) conserva exit0, sin timeout ni reintento,
0,955 s del tramo medido —lanzamiento, análisis y cotejos posteriores— y sus
streams; preparación e instalación quedan fuera de esa cifra. [report.json](report.json),
stdout y el JSON histórico son **byte idénticos: 1.599 bytes, SHA256
`352ef988…c7ee1`**. Esto reproduce:

- 1.812.548 filas; 3.512 excluidas; 1.809.036 elegibles.
- Numeradores de alquiler/devolución: 1.725.248 y 1.682.386.
- 820 instantáneas, 2.212 IDs de estación, 37 huecos mayores de 30 minutos.
- Tipos, nulos, IDs, pares únicos y flags binarios comprobados por el script;
  ambas acciones se cuentan dentro de la máscara elegible declarada.

El entorno nuevo fuera del árbol usa Python3.11.15, PyArrow21.0.0 y
tzdata2026.4. Instalación offline con caché explícita, sin config, keyring,
build o descargas. Pip check pasó; 1.382 archivos públicos de dependencias
permanecieron idénticos. No se modificaron entornos del toolkit.

## Integridad y alcance

La revisión previa detectó dos P2: referencias prospectivas que podían
sustituirse y un marcador que afirmaba ejecución antes de lanzar el proceso.
La fuente inicial nunca se ejecutó y permanece como
[run_raw_counts.reviewed_initial.py](run_raw_counts.reviewed_initial.py).
El ejecutor corregido fija por SHA el plan y el manifiesto ambiental,
coteja los originales al usarlos y conserva recibos terminales y flags
observados. Las revisiones inicial y corregida están en el dossier.

`subset_membership_verified_from_rows=true` se refiere a estas filas y a
esta regla descriptiva; no autentica el estado físico reportado. Verdad de
fuente, custodia externa, efecto de campo y causalidad siguen sin verificar.
La regla histórica y el reporte eran conocidos: esto es reproducción de
desarrollo expuesta, no evaluación final independiente o prerregistro del
estudio de marzo. No es una segunda implementación independiente del cálculo.

D-105 no se reescribe ni recibe aprobación retroactiva. Sin nuevas
generaciones experimentales, Q, comparación final, intervención o corrida24.
GOAL y matriz intactos; aceptación **1/5, C2–C5 No demostrados**.
