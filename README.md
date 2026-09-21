# Chatbot BI — PoC (Paso 1)

Chatbot de analítica de marketing, instalado como **Chat App de Google Chat**, que
responde preguntas de negocio en lenguaje coloquial sobre
`marketing_performance_1000_t2o.xlsx`, usando una capa semántica (`semantic_layer.yaml`)
para traducir sinónimos y aplicar las fórmulas oficiales (CTR, CPA, ROAS...).

**Principio clave:** el LLM nunca "calcula de memoria". Su único trabajo es traducir
la pregunta a código pandas. El número que ves siempre sale de ejecutar ese código
contra los datos reales — por eso el propio código generado se incluye en cada
respuesta, para poder verificarlo.

> **Nota sobre cuentas Google:** la documentación oficial de Google dice que la
> plataforma de desarrollo de Chat apps "solo está disponible para cuentas de Google
> Workspace" y que no se puede desarrollar ni probar con un @gmail.com personal. En la
> práctica, hemos comprobado de punta a punta que sí funciona con una cuenta Gmail
> personal — este proyecto es la prueba. Si en algún momento deja de funcionar,
> probablemente sea por un cambio de política de Google, no por algo mal configurado aquí.

## 1. Instalación

```bash
cd chatbot_bi_poc
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Configuración

```bash
cp .env.example .env
```

Rellena en `.env`:

- **`LLM_PROVIDER`**: qué proveedor de LLM usar (`opencode` por defecto — es el único
  probado en producción; `anthropic` y `openai` son plantillas de ejemplo, ver sección
  "Cambiar de proveedor de LLM" más abajo).
- **`OPENCODE_API_KEY`**: la obtienes en https://opencode.ai/auth
- **`OPENCODE_BASE_URL`**: `https://opencode.ai/zen/go/v1` para la suscripción mensual
  Go, o `https://opencode.ai/zen/v1` para Zen (pago por saldo).
- **`OPENCODE_MODEL`**: el identificador exacto del modelo (compruébalo con `/models`
  en la CLI de opencode). Ej: `glm-5.2`.
- **`GOOGLE_CHAT_PROJECT_NUMBER`**: el "Número de proyecto (ID de app)" que aparece
  arriba del todo en la pestaña "Configuración" de la Google Chat API en Cloud Console.
- **`GOOGLE_CHAT_WEBHOOK_URL`**: la URL pública completa del webhook, incluyendo
  `/googlechat` al final, tal cual está puesta en "URL del extremo HTTP" en esa misma
  pestaña. **Debe coincidir carácter por carácter** — Google firma el token con esa URL
  exacta como "audience". Hay que actualizarla cada vez que cambie la URL del túnel.
- **`LOG_USER_ID_SECRET`**: clave secreta usada para pseudonimizar (HMAC-SHA256) el
  email del usuario antes de guardarlo en `logs/interactions.jsonl`. Genera la tuya con
  `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`CONTEXT_MAX_TURNS`** / **`CONTEXT_INACTIVITY_MINUTES`**: controlan la memoria de
  conversación de corto plazo (ver sección 6). Valores por defecto: `3` turnos previos,
  `20` minutos de inactividad.

## 3. Ejecutar en terminal (para probar el motor sin depender de Google Chat)

```bash
python chatbot.py
```

Preguntas de ejemplo:
- `¿Cuál ha sido el ROAS de las campañas de Search (SEM) durante el primer trimestre del año?`
- `¿Cuánta pasta nos hemos gastado en captación para el sector de Retail y Moda?`
- `Dime el CPA medio de las campañas de Social Ads frente a Programmatic.`
- `¿Cómo han ido las ventas este mes?` → el bot debería pedir aclaración
- `Dame la lista de nombres y emails de todos los responsables de campaña` → debe negarse
- `¿Cuánto presupuesto gestiona Almudena Barreiro?` → debe negarse (ver sección 6,
  enmascarado de PII): ni el email ni el nombre completo de un Responsable real llegan
  nunca al LLM.

Para probar los endpoints del servidor sin pasar por Google Chat (health check y los
distintos tipos de evento del webhook), usa `requests.http`.

## 4. Ejecutar como Chat App de Google Chat

### 4.1. Crear y configurar la Chat App (una sola vez)

1. Crea un proyecto en https://console.cloud.google.com (funciona con Gmail personal).
2. Habilita la "Google Chat API" (APIs y servicios → Biblioteca).
3. Ve a la pestaña "Configuración" de esa API y rellena:
   - Nombre de la app, avatar (URL HTTPS de una imagen cuadrada), descripción.
   - Habilita "funciones interactivas" y marca "Unirse a espacios y conversaciones grupales".
   - Configuración de conexión → "URL del extremo HTTP" → de momento pon una URL
     de prueba, la actualizaremos en el paso 4.3.
   - Visibilidad → añade tu propio email de Gmail.
   - Guarda.
4. Busca el nombre de tu app en https://chat.google.com (botón "+" junto a Mensajes
   directos) y ábrela para crear el chat 1:1.

### 4.2. Arrancar el servidor local

```bash
python server.py
```

Debería imprimir `Datos cargados: 1000 filas...` y quedarse escuchando en el puerto
8080 (o el que pongas en `PORT`).

### 4.3. Exponerlo a internet con VS Code Port Forwarding

1. Panel **PORTS** en VS Code (junto a Terminal/Debug Console) → si el 8080 no aparece,
   "Forward a Port" → `8080`.
2. Clic derecho sobre esa fila → **"Port Visibility" → "Public"** (pide iniciar sesión
   con GitHub/Microsoft la primera vez).
3. Comprueba que de verdad quedó público: abre la "Forwarded Address" en el navegador
   (o haz un GET) y confirma que responde `Chatbot BI webhook activo.` directamente,
   **sin** ninguna pantalla de login de por medio. Si te pide login, la visibilidad no
   se aplicó bien — vuelve a ponerla en "Public".
4. Copia esa URL + `/googlechat` y pégala en:
   - "URL del extremo HTTP" en Google Cloud Console (Chat API → Configuración)
   - `GOOGLE_CHAT_WEBHOOK_URL` en tu `.env`
5. Reinicia `server.py` si has cambiado el `.env`.

> Alternativa sin VS Code: `cloudflared tunnel --url http://localhost:8080`.
> La URL pública cambia cada vez que reinicias el túnel — hay que repetir el paso 4 y 5.

### 4.4. Probar

Escríbele a "Chatbot BI" en Google Chat. Debería responder con el código pandas
ejecutado y el resultado real calculado sobre los 1,000 registros.

## 5. Logging de trazabilidad

Cada interacción (pregunta, decisión del LLM, código generado, resultado o error de
ejecución, respuesta final, estado, modelo, versión de la capa semántica y latencia) se
registra en `logs/interactions.jsonl` (una línea JSON por interacción, formato JSONL),
vía `logger.py`. El logging es *best-effort*: si falla la escritura en disco, se avisa
por stderr pero nunca rompe la respuesta al usuario. `logs/` está excluido de git
(`.gitignore`).

El email del usuario **nunca se guarda en claro**: se pseudonimiza con HMAC-SHA256
(`logger.pseudonymize_user_email`, clave `LOG_USER_ID_SECRET`) antes de escribirse como
`user_id`. Es determinista (el mismo email siempre da el mismo `user_id`, así se pueden
agrupar interacciones de un mismo usuario) pero no reversible sin el secreto.

Si el código generado falla en el sandbox, el usuario recibe siempre un mensaje
genérico ("No he podido calcular la respuesta a tu pregunta...") — el traceback real
solo queda en `execution_error` dentro del log, nunca se expone en el chat.

## 6. Enmascarado de PII

Tres mecanismos deterministas y sin dependencias de NLP/NER, todos en `core/pii.py`
(y `core/data_engine.py` para el primero):

1. **Esquema que ve el LLM (`describe_schema`):** las columnas marcadas `pii_sensitive:
   true` en `semantic_layer.yaml` (hoy solo `Responsable`) nunca muestran valores de
   ejemplo reales en el bloque de esquema del prompt — se sustituyen por
   `<PII - valor no expuesto>`. El LLM sigue viendo que la columna existe y su tipo,
   nunca un dato real. Determinista por código: aunque el LLM ignorase la regla del
   prompt, el dato ni siquiera está ahí.
2. **Emails en texto libre (`mask_emails`):** cualquier email (regex genérico, no solo
   del dominio del dataset) se sustituye por `<EMAIL-PII>`.
3. **Nombres conocidos (`mask_known_pii_names`):** data-driven contra los valores
   reales de las columnas `pii_sensitive` del propio DataFrame — en este dataset, los
   "Responsable" son un conjunto finito y cerrado. Detecta el nombre en cualquier orden
   (`Nombre Apellido` / `Apellido Nombre`) y sin distinguir mayúsculas/minúsculas,
   sustituyéndolo por `<NOMBRE-PII>`.

Los dos enmascarados de texto libre se aplican **en el punto de entrada**, antes de que
la pregunta del usuario cruce hacia el LLM (`server.py::answer_question` /
`chatbot.py::main`) — no solo antes de loguear. Ningún dato PII llega al modelo, ni
siquiera dentro de la pregunta. Como defensa en profundidad, también se aplican sobre
`execution_result`, `final_response` y `generated_code` justo antes de loguear/responder,
por si el código generado expusiera el dato de otra forma (p. ej. un `.unique()` sobre
la columna PII).

`llm/base.py` (regla 4 del prompt de sistema) le dice al LLM cómo comportarse cuando la
pregunta trae `<EMAIL-PII>` o `<NOMBRE-PII>`: si responder exige identificar a esa
persona concreta, debe responder `action: "refuse"` con una explicación honesta ("no
puedo identificar a esa persona porque ese dato está protegido..."); si la pregunta es
un agregado que no depende de ese valor (por sector, canal, etc.), responde con
normalidad.

> **Alcance actual:** esto protege el email (patrón genérico, cualquier dominio) y los
> nombres que YA existen en los datos (`Responsable`). No es un NER general — un nombre
> de persona que no esté en el dataset no se detecta. Ver "Qué queda para los próximos
> pasos" para el enfoque más robusto (tipo Microsoft Presidio) previsto más adelante.

### Tests

```bash
pip install -r requirements.txt  # incluye pytest
pytest tests/ -v
```

`tests/test_pii.py` cubre los tres mecanismos anteriores (unitarios) y dos escenarios
de integración end-to-end contra `server.answer_question` (mockeando el LLM): una
pregunta que exige identificar a una persona por email o por nombre (debe dar
`refuse`, sin que el dato llegue al LLM, al log ni al historial) y una pregunta
agregada que no depende de PII (debe funcionar con normalidad — para detectar un
`refuse` disparándose de más).

## 7. Memoria de conversación de corto plazo

Cada pregunta se procesaba de forma aislada: el LLM no tenía memoria de turnos
anteriores, así que si el bot pedía una aclaración ("¿te refieres a conversiones o a
ingresos en euros?"), la respuesta del usuario ("en euros") le llegaba sin contexto.

`core/context.py` reconstruye ese contexto a partir del propio `logs/interactions.jsonl`
(no hay estado en memoria del proceso): dada la pareja `(user_id, space_id)`, busca sus
últimas `CONTEXT_MAX_TURNS` interacciones y las convierte en pares de mensajes
`{"role": "user", ...}` / `{"role": "assistant", ...}`, que `llm.ask_llm_for_code`
inserta entre el `system_prompt` y la pregunta actual. Si la última interacción de esa
conversación supera `CONTEXT_INACTIVITY_MINUTES` de antigüedad, se trata como conversación
nueva y no se incluye historial. La lectura del log es *best-effort* igual que la
escritura: si falla, se responde sin contexto en vez de romper la respuesta.

> **Por qué `(user_id, space_id)` y no `thread_id`:** en espacios de Google Chat sin
> "threaded history" activado, cada mensaje entrante llega con un `thread_id` distinto
> aunque sea la misma conversación seguida — comportamiento normal de la plataforma, no
> un error de parseo. Agrupar por `thread_id` (como en una versión anterior) hacía que
> nunca se encontrara historial. `thread_id` se sigue guardando en el log como metadata
> de Google Chat, solo dejó de usarse como clave de agrupación del historial.

## 8. Cambiar de proveedor de LLM

Todo el código específico de cada proveedor vive en dos sitios, compartimentados por
proveedor y por responsabilidad:

- `config/providers/<proveedor>.py`: lee las variables de entorno del proveedor y
  expone `validate()`, que comprueba que están todas (API key, modelo...) y, si falta
  algo, lanza `RuntimeError` diciendo exactamente qué falta.
- `llm/<proveedor>_client.py`: el "archivo de conexión" — construye el cliente del SDK
  correspondiente y expone `ask_llm_for_code()` con la misma firma para todos.

`llm/__init__.py` es el orquestador: lee `LLM_PROVIDER` de `.env`, carga el archivo de
conexión correspondiente y llama a su `validate()` **antes** de cargar datos o levantar
el servidor — si falta configuración, la ejecución se detiene ahí mismo con el error
concreto, en vez de fallar más tarde a mitad de una conversación.

Hoy solo `opencode` está probado en producción. `anthropic` y `openai` son plantillas
de ejemplo listas para usar (cambia `LLM_PROVIDER` en `.env` y rellena sus variables);
para `anthropic` hace falta además `pip install anthropic`. Para añadir un proveedor
nuevo: copia uno de los ejemplos en ambas carpetas y regístralo en
`llm/__init__.py::_PROVIDER_MODULES`.

## 9. Notas técnicas descubiertas durante la implementación

Estas son particularidades reales con las que nos encontramos (no están en la
documentación "de libro" de Google/OpenCode, o están dispersas):

- **OpenCode Go exige la cabecera `x-opencode-session`** en cada petición (desde el
  5 de septiembre de 2026), o responde 400 `MissingSessionID`. Ya está implementado en
  `llm/opencode_client.py` con un UUID estable por proceso.
- **El formato de eventos de Google Chat no es el "clásico"** (`{"type": "MESSAGE", ...}`).
  Con "funciones interactivas" habilitadas, Google manda el formato de **complemento de
  Workspace**: el tipo de evento se deduce de qué clave hay dentro de `chat`
  (`messagePayload` / `addedToSpacePayload` / `removedFromSpacePayload`), y el texto está
  en `chat.messagePayload.message.argumentText` / `.text`.
- **El formato de respuesta también cambia**: hay que envolver el texto en
  `{"hostAppDataAction": {"chatDataAction": {"createMessageAction": {"message": {"text": ...}}}}}`.
  Un `{"text": ...}` a secas se descarta en silencio (Google responde 200 pero no
  muestra nada en el chat).
- **El token JWT de verificación** viene firmado por
  `service-<GOOGLE_CHAT_PROJECT_NUMBER>@gcp-sa-gsuiteaddons.iam.gserviceaccount.com`
  (no por `chat@system.gserviceaccount.com`, que es el emisor de las apps "clásicas"),
  y su `audience` es la URL completa del webhook, no el número de proyecto — de ahí las
  dos variables `GOOGLE_CHAT_PROJECT_NUMBER` y `GOOGLE_CHAT_WEBHOOK_URL` en `config/settings.py`.
- **El reloj del sistema debe estar sincronizado**: la verificación del JWT falla con
  "Token used too early" si el reloj de Windows está desajustado unos segundos.

## 10. Qué queda para los próximos pasos (no incluido aquí a propósito)

- **Paso 3** — Gateway tipo LiteLLM delante de OpenCode, para no llamar directo al proveedor.
- **Paso 4** — ✅ mecánica base implementada (ver sección 6): esquema sin valores PII
  reales, emails enmascarados por regex, y nombres conocidos (los que ya existen en el
  dataset) enmascarados antes de llegar al LLM, con `refuse` cuando la pregunta depende
  de identificar a esa persona concreta. Pendiente: un enfoque tipo Microsoft
  Presidio/NER para detectar nombres de persona que NO estén ya en los datos — hoy
  `mask_known_pii_names` es data-driven, cerrado al conjunto conocido de `Responsable`.
- **Paso 5** — Guardarraíles reales contra prompt injection (NeMo Guardrails o similar).
  El `core/sandbox.py` actual bloquea patrones obvios (`import`, `open(`, `os.`...) pero es
  un filtro básico, no una defensa de producción.
- **Paso 6** — Perfiles de usuario (más/menos preguntas de afinado según el nivel técnico).
- Estabilidad de infraestructura: la URL del túnel cambia en cada reinicio, y `server.py`
  corre con el servidor de desarrollo de Flask (no apto para producción).
- **Latencia anómala bajo tráfico concurrente (diagnosticado, no corregido):** dos
  interacciones reales registraron ~99–108 s de latencia (vs. 3–24 s habitual),
  solapadas en el tiempo con otras peticiones concurrentes. Hipótesis principal:
  `llm/opencode_client.py` usa un único `_OPENCODE_SESSION_ID` por proceso, compartido
  por todas las peticiones de todos los usuarios — si el backend de OpenCode serializa
  bajo ese header, peticiones simultáneas quedan encoladas. Agravante posible: reintento
  de entrega del webhook de Google Chat si no recibe ack a tiempo. Sin confirmar todavía.

## Estructura del proyecto

```
chatbot_bi_poc/
├── chatbot.py               # punto de entrada CLI (bucle de chat en terminal)
├── server.py                 # punto de entrada Google Chat (servidor webhook Flask)
├── requests.http              # peticiones de prueba para los endpoints del servidor
├── config/                    # configuración (por responsabilidad, no por archivo suelto)
│   ├── settings.py             # variables generales (rutas, Google Chat, logging, contexto, LLM_PROVIDER)
│   └── providers/               # un archivo de config por proveedor de LLM, cada uno con validate()
│       ├── opencode.py           # activo por defecto
│       ├── anthropic.py          # ejemplo
│       └── openai.py             # ejemplo
├── llm/                        # orquestador de proveedores de LLM + un "archivo de conexión" por proveedor
│   ├── __init__.py              # decide qué proveedor usar (LLM_PROVIDER) y valida su config al arrancar
│   ├── base.py                   # prompt de sistema y parseo de la respuesta, común a todos
│   ├── opencode_client.py        # activo por defecto (genera código, no texto)
│   ├── anthropic_client.py       # ejemplo
│   └── openai_client.py          # ejemplo
├── core/                       # lógica de negocio, independiente del proveedor de LLM
│   ├── semantic_layer.py         # carga y formatea semantic_layer.yaml
│   ├── data_engine.py             # carga el Excel a pandas; describe_schema sin PII real
│   ├── pii.py                     # enmascarado determinista de emails y nombres conocidos
│   ├── sandbox.py                 # ejecuta el código generado de forma acotada
│   └── context.py                 # memoria de conversación de corto plazo (a partir del log)
├── observability/
│   └── logger.py                 # logging de trazabilidad en logs/interactions.jsonl
├── tests/
│   └── test_pii.py                # tests del enmascarado de PII (unitarios + integración)
├── data/                       # copia del Excel y el YAML de origen
├── logs/                       # interactions.jsonl (generado en runtime, ignorado por git)
├── requirements.txt
└── .env.example
```
