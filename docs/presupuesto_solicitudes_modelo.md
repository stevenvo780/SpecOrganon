# Despacho medido de una solicitud de desarrollo

`scripts/run_managed_response.py` ofrece una ruta **de desarrollo** para una
solicitud de texto a OpenAI Responses. Usa el endpoint de
[conteo de entrada](https://developers.openai.com/api/docs/guides/token-counting)
antes del envío y fija `max_output_tokens`, que según la documentación de
OpenAI incluye salida visible y razonamiento. El ledger privado
`scripts/managed_token_ledger.py` reserva la suma antes de enviar, comparte
el tope entre roles que usan la misma carpeta y conserva la reserva cuando
el resultado es incierto.
El esquema 2 opcional añade una reserva local de coste en microUSD a partir de
un perfil de tarifas declarado por el operador. La reserva de tokens y coste
ocurre en la misma escritura durable; **el perfil no es una tarifa autenticada
ni el cálculo es una factura**.

`scripts/run_managed_conversation.py` compone esa ruta en una corrida de **2 a
32 turnos de texto del mismo modelo**. Prepara un plan privado, conserva cada
solicitud, respuesta y recibo, y usa un único ledger y un plazo activo local
para toda la conversación. Con `store:false`, reenvía los elementos completos
de `response.output`, incluidos razonamiento cifrado y `phase`, siguiendo la
[guía oficial de estado de conversación](https://developers.openai.com/api/docs/guides/conversation-state).
Si aparece una respuesta incompleta, no textual o sin razonamiento preservable,
termina `truncated`; una salida incierta deja `indeterminate` y bloquea la
reejecución. No llama herramientas.

## Contrato local

1. El operador crea **una sola** carpeta de ledger por corrida, fuera del
   workspace visible al modelo. Fija el máximo de tokens y de solicitudes. Para
   usar `send` o `execute` desde la CLI debe fijar además un techo de microUSD
   y un perfil de tarifas para un modelo exacto; los ledgers antiguos de solo
   tokens siguen legibles para pruebas offline, pero la CLI no envía con ellos.
2. Cada agente entrega un ID de solicitud único, su rol y un JSON con
   `model`, `input`, `max_output_tokens` y opcionalmente `instructions` y
   `reasoning: {"effort": "..."}`. Una solicitud con coste exige
   `service_tier: "default"`, concordancia exacta de modelo con el perfil y
   confirma el tier devuelto antes de conciliar. El adaptador admite definiciones
   estrictas de funciones y cuenta sus esquemas, pero por sí solo no ejecuta
   las llamadas; el puente descrito abajo coordina una herramienta sellada.
3. El transportador solicita al proveedor el conteo de esa entrada. El ledger
   reserva, bajo un lock entre procesos, entrada contada más el techo de salida.
   Con perfil de coste, reserva también el coste máximo local: todos los tokens
   de entrada al mayor precio declarado entre entrada normal, lectura de caché
   y escritura de caché, más el máximo de salida al precio declarado de salida,
   redondeado hacia arriba al microUSD por solicitud. Si cualquiera de los
   topes no admite la reserva, no se llama a `/responses`. Solo puede quedar
   una solicitud pendiente a la vez por ledger; una muerte del proceso tras
   reservar impide enviar otra
   hasta revisar ese intento.
4. Tras el envío se guarda el JSON completo de respuesta en un archivo nuevo
   bajo una carpeta privada. Solo entonces se concilian
   `input_tokens + output_tokens = total_tokens`; el caché está incluido en
   entrada y el razonamiento en salida, sin volver a sumarlos. Para el coste,
   concilia lectura y escritura de caché cuando el proveedor informa su
   desglose; los tokens de entrada no clasificados conservan la mayor tarifa
   declarada. Un desglose inválido retiene la reserva y bloquea la corrida.
5. Si el envío, la escritura o la telemetría fallan, la reserva queda retenida
   y el ledger impide otras solicitudes hasta revisión. No hay reintento
   automático. Una respuesta `incomplete` con uso válido se concilia y el
   orquestador puede enviar otra solicitud; la política del estudio debe decidir
   cuándo una corrida está truncada e impedir sustituirla por una favorable.

La preparación local no llama al proveedor:

```sh
python3 scripts/run_managed_response.py init /ruta/privada/corrida-01/ledger \
  --limit-tokens 80000 --max-requests 100 \
  --price-profile /ruta/privada/tarifa.json \
  --cost-limit-micro-usd "$TOPE_MICRO_USD"
```

El JSON `tarifa.json` debe contener exactamente `model` y cuatro enteros no
negativos: `input_rate_micro_usd_per_million`,
`cached_input_rate_micro_usd_per_million`,
`cache_write_rate_micro_usd_per_million` y
`output_rate_micro_usd_per_million`; entrada normal y salida deben ser mayores
que cero. La unidad es **microUSD por millón de tokens**. Antes de usar la ruta
con dinero, el operador debe cotejar el perfil y el modelo con la
[tarifa aplicable](https://developers.openai.com/api/docs/pricing), incluidos
tramos de contexto y tier. La
[guía de caché](https://developers.openai.com/api/docs/guides/prompt-caching)
distingue lectura y escritura; sus tokens son clases de entrada y no cargos
adicionales sobre la misma entrada. `TOPE_MICRO_USD` es un valor que el
operador debe establecer: esta documentación no fija un presupuesto ni precios.
El conteo previo puede diferir del uso que reporte la respuesta: se detecta
**después** del envío y se bloquean solicitudes posteriores, pero el cargo
ya pudo superar la reserva y el techo local. Un límite estricto del gasto real
requiere control externo del proveedor o custodio, además de verificar la
tarifa, el tier efectivo y la factura. Esta ruta no los implementa.

Para una conversación, crear primero un JSON privado como este:

```json
{
  "schema": 1,
  "model": "modelo-exacto-verificado",
  "service_tier": "default",
  "instructions": "Examina la evidencia aportada y declara incertidumbres.",
  "reasoning": {"effort": "low"},
  "turns": [
    {"user": "Resume el problema y las fuentes que faltan.", "max_output_tokens": 300},
    {"user": "Revisa tu respuesta anterior y señala supuestos refutables.", "max_output_tokens": 300}
  ]
}
```

El ID del ejemplo es un marcador: debe sustituirse por un modelo disponible en
la API y coincidir exactamente con `tarifa.json`. El uso de Luna como subagente
nativo de Codex no demuestra disponibilidad ni precio de Luna en esta API.

```sh
python3 scripts/run_managed_conversation.py prepare plan.json /ruta/privada/corrida-02 \
  --limit-tokens 80000 --active-limit-seconds 5400 \
  --price-profile /ruta/privada/tarifa.json \
  --cost-limit-micro-usd "$TOPE_MICRO_USD"
python3 scripts/run_managed_conversation.py status /ruta/privada/corrida-02
```

`prepare` y `status` son locales y no facturan. `execute` requiere
`--allow-paid-requests` y `OPENAI_API_KEY`; solo debe usarse después de la
autorización humana. La CLI exige el techo y perfil declarados antes de enviar;
no comprueba que coincidan con la factura. El temporizador
monotónico del proceso cubre conteo, envíos y escritura local mientras la
ejecución está activa. No pausa esperas humanas y una interrupción mata la
posibilidad de continuar esa misma corrida automáticamente. Una carpeta nueva
no sustituye el resultado truncado o incierto en un estudio registrado.
Un transporte que ignore indefinidamente la alarma del proceso puede impedir
un corte duro; la comprobación monotónica posterior evita continuar o marcar
`completed` si finalmente devuelve el control. Ese límite requiere aislamiento
externo antes de usar la ruta como presupuesto confirmatorio.

El subcomando `send` requiere `--allow-paid-request` y `OPENAI_API_KEY`, además
del ledger con techo de coste, JSON de solicitud, archivo nuevo de respuesta,
ID y rol. **Esa bandera no acredita autorización humana; el techo es una
estimación local sobre tarifas aportadas por el operador.** No
se ejecutó `send` contra un proveedor para este desarrollo. Las pruebas usan
un transporte falso y un servidor HTTP local, sin gasto ni credenciales.

## Conversación de desarrollo con una herramienta sellada

[`run_managed_tool_conversation.py`](../scripts/run_managed_tool_conversation.py)
une el ledger anterior con una [sesión de herramienta sellada](preparacion_matriz.md#sesión-local-de-herramientas-consecutivas)
para un `run_id` del calendario candidato. Prepara dos turnos de usuario, un
modelo y una función de parámetros primitivos estrictos cuyo `tool_id` y
ejecutable coinciden con la política y los bytes del stage. Cuenta el esquema
de la función en cada solicitud, reserva tokens y coste declarado antes de
enviar y usa un plazo activo del proceso y cupos locales de solicitudes y
herramientas. Una llamada del modelo se valida antes de lanzar el ejecutable;
su `call_id`, el digest de argumentos y el terminal quedan ligados en recibos
privados. El siguiente input incluye `function_call` y su
`function_call_output`, como exige la [guía de llamadas de función](https://developers.openai.com/api/docs/guides/function-calling).

El plan privado de esquema 1 identifica `run_id`, `model`, `service_tier` de
valor `default`, dos `turns`, una `functions` con definición estricta,
`tool_id` y ruta absoluta `executable`, además de `max_model_requests`,
`max_tool_calls` y `tool_wall_seconds`. Modelo y esfuerzo deben coincidir con
el calendario; el perfil de tarifas debe nombrar ese mismo modelo. Por ejemplo,
una vez preparados el calendario, el stage y el plan:

```sh
python3 scripts/run_managed_tool_conversation.py prepare \
  /ruta/privada/calendario.json /ruta/privada/stage /ruta/privada/plan.json \
  /ruta/privada/corrida-herramienta --limit-tokens 80000 \
  --active-limit-seconds 5400 --price-profile /ruta/privada/tarifa.json \
  --cost-limit-micro-usd "$TOPE_MICRO_USD"
python3 scripts/run_managed_tool_conversation.py status /ruta/privada/corrida-herramienta
```

`prepare` y `status` son locales. `execute` exige
`--allow-paid-requests`, clave `OPENAI_API_KEY` y autorización humana previa;
no se usó con proveedor real. Una corrida iniciada, truncada o incierta no se
reintenta automáticamente. Un fallo de herramienta conserva reserva y terminal
sin inventar una respuesta satisfactoria. Los argumentos viajan como `argv`
al ejecutable: otro proceso local podría leerlos en `/proc`. No deben usarse
para pasar secretos. Los recibos son evidencia bajo el mismo UID, no custodia
externa ni prueba de gasto real.

### Plazo fijado por el calendario

Desde D-095, `prepare` exige que `active_limit_seconds` sea positivo, no supere
el máximo local ni `per_run_limits.active_seconds` del calendario fijado. La
comprobación ocurre antes de crear el directorio o reservar recursos. `status`
y `execute` vuelven a cotejar ese techo al cargar: editar coherentemente el
plan y el estado local no permite exceder el calendario sin cambiar sus bytes
fijados. Las cinco regresiones nuevas incluyen igualdad, un límite menor y
rechazo sin escrituras ni llamadas. Esta corrección aplica a este puente;
no establece un deadline común para todos los agentes o proveedores.

## Límite de la evidencia

Estos controles cubren únicamente las solicitudes que pasan por estos
ejecutores y comparten el mismo ledger. Rechazan redirecciones HTTP con la
clave adjunta.
La CLI opaca de `run_development_arm.py` sigue analizando uso al terminar y no
adopta este control. El ledger, el temporizador y los recibos son locales, sin
custodia independiente ni recibo de factura. El plazo nuevo solo cubre la
conversación secuencial de un proceso y no agrega varios agentes. Faltan
herramientas compartidas entre agentes, tarifa y gasto autenticados,
versiones efectivas de modelo, agentes coordinados, familias adicionales,
reservas, jueces ciegos y evaluación de campo. Hasta integrar y verificar
esas condiciones, el piloto facturable y el criterio 4 continúan **NO-GO / no
demostrado**. El máximo de 80 000 tokens procede del
[protocolo prospectivo](protocolo_experimental.md#3-brazos-panel-y-comparabilidad);
no es por sí mismo una autorización para consumirlo.

Las pruebas del ledger cubren muerte del proceso y reapertura local. Las de
conversación usan transporte falso: dos turnos, razonamiento cifrado preservado,
límites, fallo de envío, muerte del proceso hijo durante `send` y alteración de
un archivo. No ensayan apagón del host,
plazo largo real ni garantías del dispositivo de almacenamiento. El journal
tampoco tiene custodia externa frente a cambios coherentes del mismo usuario.
