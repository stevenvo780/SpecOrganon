# Pan · energía documental con dependencias versionadas

Variante de desarrollo D108. Conserva el proyecto signed y los64 eventos del
borrador alimentario D102; añade cuatro puts por MCP instalado Python3.12:
protocolo, inferencia, evidencia e indicador. **68eventos, cero fases aceptadas**.
Normas, decisión y cuatro umbrales de intervención siguen pendientes.

## Medida y alcance

La pieza del pan comercial estudiado pesa736g después del horneado. El artículo
publica0,297kWh de electricidad y0,115kWh de gas por pieza. Derivación:

`(0.297 + 0.115) / (736 / 1000) = 103/184 kWh/kg produced bread`.

El racional exacto y la representación HALF_EVEN a24decimales quedan en
[derivation.json](derivation.json). Error exclusivamente de representación:
`11/23000000000000000000000000`, dentro de5e-25. No cuantifica el error físico
de los datos empresariales; éste no está publicado. La cifra suma energía de
dos portadores para el producto histórico estudiado. No estima energía útil,
emisiones, coste, valor alimentario, un lote observado, baseline actual ni
eficacia. Tampoco equivale a toda la unidad funcional consumida del ACV.

Fuente: Svanes, Østergaard y Hanssen,
[*Effects of Packaging and Food Waste Prevention by Consumers on the
Environmental Impact of Production and Consumption of Bread in Norway*](https://doi.org/10.3390/su11010043),
publicado2018-12-21, CC BY4.0. PDF archivado SHA256
`9d64c0538b76ebaa19af86fb7ec231243cb5e1272316105ad979cfb9b6de3a32`:
§4.2,página6 para la masa; tabla5,página8 para la energía. Fecha de registros
empresariales **desconocida**. La evidencia derivada usa la fecha UTC real de
la derivación, separada de la publicación. Las copias de auditoría son las
originales D100/D102; no se efectuó otro ACV ni nueva extracción experimental.

## Uso y verificación

[manifest.json](manifest.json) contiene sólo los cuatro puts nuevos, cada uno
con versión esperada0 y versiones de sus dependencias. En este caso ya están
aplicados. Las revisiones de cualquiera de las tres evidencias originales
invalidan los cuatro descendientes. El indicador y la evidencia comparten
métrica/unidad literales y caminos hasta protocolo, problema y norma.

El constructor específico comprueba el cálculo y su contexto. `put` genérico
no verifica semánticamente una división ni autentica fuentes físicas. Esta
evidencia tampoco sustenta los cuatro indicadores de intervención pendientes.

[D108_preparation.json](D108_preparation.json) es el recibo anterior a los puts
(por eso declara0aplicados), no el estado final del ledger. Los diez archivos
se copiaron byte por byte del caso MCP positivo3.12 y su preparación, sin
locks. [Procedencia](../../experiments/development/bread_energy_derivation_2026-09-30/publication.json).

[Ejecuciones, controles y límites](../../experiments/development/bread_energy_derivation_2026-09-30/README.md).
No hay nuevo review firmado, autorización normativa, campo ni PASS de C2–C5.
