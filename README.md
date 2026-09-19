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

Para probar solo la conexión con OpenCode (sin cargar nada de Google Chat), usa
`test_opencode.py`. Para probar los endpoints del servidor sin pasar por Google Chat
(health check y los distintos tipos de evento del webhook), usa `requests.http`.

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

## 5. Notas técnicas descubiertas durante la implementación

Estas son particularidades reales con las que nos encontramos (no están en la
documentación "de libro" de Google/OpenCode, o están dispersas):

- **OpenCode Go exige la cabecera `x-opencode-session`** en cada petición (desde el
  5 de septiembre de 2026), o responde 400 `MissingSessionID`. Ya está implementado en
  `llm_client.py` con un UUID estable por proceso.
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
  dos variables `GOOGLE_CHAT_PROJECT_NUMBER` y `GOOGLE_CHAT_WEBHOOK_URL` en `config.py`.
- **El reloj del sistema debe estar sincronizado**: la verificación del JWT falla con
  "Token used too early" si el reloj de Windows está desajustado unos segundos.

## 6. Qué queda para los próximos pasos (no incluido aquí a propósito)

- **Paso 2** — Logging: guardar en disco cada pregunta, el código generado y la respuesta.
- **Paso 3** — Gateway tipo LiteLLM delante de OpenCode, para no llamar directo al proveedor.
- **Paso 4** — Enmascarado automático de PII con una herramienta tipo Microsoft Presidio
  (hoy el control de PII es solo una regla en el prompt del LLM, no una detección robusta).
- **Paso 5** — Guardarraíles reales contra prompt injection (NeMo Guardrails o similar).
  El `sandbox.py` actual bloquea patrones obvios (`import`, `open(`, `os.`...) pero es
  un filtro básico, no una defensa de producción.
- **Paso 6** — Perfiles de usuario (más/menos preguntas de afinado según el nivel técnico).
- Estabilidad de infraestructura: la URL del túnel cambia en cada reinicio, y `server.py`
  corre con el servidor de desarrollo de Flask (no apto para producción).

## Estructura del proyecto

```
chatbot_bi_poc/
├── chatbot.py            # punto de entrada CLI (bucle de chat en terminal)
├── server.py              # punto de entrada Google Chat (servidor webhook Flask)
├── test_opencode.py        # prueba aislada de la conexión con OpenCode
├── requests.http           # peticiones de prueba para los endpoints del servidor
├── llm_client.py          # llamada al LLM vía OpenCode (genera código, no texto)
├── semantic_layer.py       # carga y formatea semantic_layer.yaml
├── data_engine.py          # carga el Excel a pandas
├── sandbox.py              # ejecuta el código generado de forma acotada
├── config.py               # variables de entorno
├── data/                    # copia del Excel y el YAML de origen
├── requirements.txt
└── .env.example
```
