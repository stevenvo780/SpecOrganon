# D-E: caso público de energía para desarrollo

El [paquete visible](../cases/building_energy/task.md) usa el conjunto [*Appliances Energy Prediction* de UCI](https://archive.ics.uci.edu/dataset/374/appliances%2Benergy%2Bprediction), DOI [10.24432/C5VC8G](https://doi.org/10.24432/C5VC8G), atribuido a Luis Candanedo y publicado bajo CC BY 4.0. El registro describe un edificio de bajo consumo, mediciones cada diez minutos durante unos 4,5 meses y condiciones interiores junto con meteorología aeroportuaria interpolada. La variable `Appliances` está expresada en Wh por intervalo; **no** es una acción de control ni un efecto de intervención.

La [selección congelada](../cases/building_energy/source_manifest.json) toma por regla temporal los primeros siete días de calendario completos posteriores al día de apertura parcial: 2016-01-12 00:00 hasta 2016-01-19 00:00, sin zona horaria inferida. Contiene 1008 registros continuos. El ZIP descargado del servidor de UCI tenía SHA-256 `2fccf354445d886e7917620b0195db1f3e3e34d5a067a93b844694a4c561255a`; su CSV interno, `2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`; la muestra conservada, `c7f66ffaadc4e38375a7edf03091bae4fc861880510867903487eec83f05e6ba`. Una comprobación independiente de la muestra sumó **118 280 Wh** de `Appliances` y **5 320 Wh** de `lights`; son consumos observados en la semana, no ahorros.

Para reconstruir el corte sin guardar el ZIP completo en el repositorio:

```sh
curl -fLsS https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip -o /ruta/temporal/uci-374.zip
python3 scripts/build_energy_case.py --archive /ruta/temporal/uci-374.zip --output-dir cases/building_energy
```

El constructor verifica hashes del ZIP y del CSV, exige una semana sin intervalos faltantes y se niega a reemplazar archivos existentes que difieran. La copia de filas conserva los bytes de las líneas originales. Si UCI cambia el archivo, la reconstrucción se detiene y se registra un nuevo corte; no se sustituye silenciosamente por datos distintos.

**Alcance de investigación:** una semana y una sola vivienda no muestran representatividad, ocupación, acciones sobre aparatos, costes, perjuicios o un contrafactual. No se puede atribuir una diferencia temporal de consumo a una intervención ausente. El caso permite evaluar cómo los métodos formulan el problema, detectan evidencia insuficiente, comparan diseños y proponen una prueba causal. Toda aprobación de fines, umbrales, confort y actuación en el hogar requeriría personas competentes y registro propio. Este paquete se considera **desarrollo expuesto**, por lo que no servirá como reserva confirmatoria ni como prueba de impacto.

El [piloto N/SDD/T de desarrollo](../experiments/development/energy_pilot/README.md) conserva prompts, una guía sin puntuar, cinco intentos de un mismo modelo y sus salidas. T3 registra llamadas locales al CLI; faltaron aislamiento técnico, presupuesto global verificable y telemetría comparable. Por eso no estima ventaja de método. El [protocolo confirmatorio](protocolo_experimental.md) no se alimenta con este caso ni se simulan recibos de proveedor.
