# Publicación de main y verificación de la web

El repositorio público tiene `main` como rama predeterminada. La web enlaza esa
rama, su guía clona `--branch main` y las fuentes reconstruibles están en `website/`.
El recibo `publication-receipt.json` identifica el despliegue y las comprobaciones.

Se comprobaron dos tamaños de pantalla, cuatro enlaces al repositorio por vista,
la guía descargable y la metadata de rama. Se cotejaron las 42 celdas del informe
histórico, sus tablas funcionales, comparaciones y diagnóstico; las 32 descargas
se verificaron por HTTP y SHA-256. La publicación conserva los resultados adversos
y distingue el primer caso de desarrollo de una demostración de superioridad.

El primer control completo de producción agotó el timeout al localizar un
control de la página. Su stderr se conserva. La segunda ejecución pasó, y se
repitieron los controles después del despliegue final. Una repetición exitosa
no borra el intento fallido ni constituye una nueva ejecución experimental.

Estos son controles de publicación, sin llamadas a modelos ni nuevos sujetos.
La suite específica del toolkit está documentada en el recibo de integración.
La suite global del host no está validada; sus fallos y errores se conservan.
La meta de superioridad sigue activa y no se declara lograda por publicar.

Los scripts de navegador usan Playwright del runtime del operador. Para usarlos
en otro entorno debe adaptarse ese import a una instalación local de Playwright.
Los datos `web/` aquí son los acompañantes sellados del control de publicación;
las fuentes completas de la presentación están en la carpeta `website/` del repo.
