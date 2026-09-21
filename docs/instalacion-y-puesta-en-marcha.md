# Instalación y puesta en marcha

Guía completa para instalar el proyecto desde cero y dejarlo funcionando, tanto en
modo terminal (sin Google Chat) como como Chat App real. Si el proyecto ya estaba
funcionando y solo necesitas retomarlo tras un parón, ve directamente a
[despliegue-y-relanzamiento.md](despliegue-y-relanzamiento.md).

**Proyecto de Google Cloud usado en esta PoC:** `tu-proyecto-id`

## 1. Instalación de dependencias

```bash
cd chatbot_bi_poc
python -m venv .venv

# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Configuración (`.env`)

```bash
cp .env.example .env
```

Rellena en `.env`:

| Variable | Qué es | Dónde conseguirla |
|---|---|---|
| `LLM_PROVIDER` | Proveedor de LLM activo | `opencode` (único probado en producción). Ver [proveedores-llm.md](proveedores-llm.md) |
| `OPENCODE_API_KEY` | API key de OpenCode | https://opencode.ai/auth |
| `OPENCODE_BASE_URL` | Endpoint OpenAI-compatible | `https://opencode.ai/zen/go/v1` (suscripción Go) o `https://opencode.ai/zen/v1` (Zen, pago por saldo) |
| `OPENCODE_MODEL` | ID exacto del modelo | Comando `/models` en la CLI de opencode. Ej: `glm-5.2` |
| `GOOGLE_CHAT_PROJECT_NUMBER` | Número de proyecto de Google Cloud | Pestaña "Configuración" de la Chat API en Cloud Console (arriba del todo) |
| `GOOGLE_CHAT_WEBHOOK_URL` | URL pública del webhook + `/googlechat` | Ver sección 4 más abajo. Debe coincidir carácter por carácter con lo puesto en Cloud Console |
| `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE` | Ruta a la clave JSON de la cuenta de servicio | Ver sección 3 más abajo |
| `GOOGLE_CHAT_SYNC_WAIT_SECONDS` | Margen (segundos) antes de devolver el placeholder mientras se calcula la respuesta en background | Por defecto `20`, bajo el límite real de 30s de Google Chat |
| `LOG_USER_ID_SECRET` | Clave HMAC-SHA256 para pseudonimizar emails en el log | Genera la tuya: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CONTEXT_MAX_TURNS` / `CONTEXT_INACTIVITY_MINUTES` | Memoria de conversación de corto plazo | Ver [memoria-y-perfilado.md](memoria-y-perfilado.md). Por defecto `3` turnos / `20` minutos |

## 3. Crear la cuenta de servicio (una sola vez)

El servidor usa una cuenta de servicio de Google Cloud (scope `chat.bot`) para
publicar la respuesta final en Google Chat de forma asíncrona, una vez el LLM
termina de procesar (`server.py`, función que construye el cliente de la API de
Chat vía `google.oauth2.service_account` + `googleapiclient`).

1. Ve a **IAM y administración → Cuentas de servicio** del proyecto:
   https://console.cloud.google.com/iam-admin/serviceaccounts?project=tu-proyecto-id
2. **Crear cuenta de servicio** → dale un nombre (p. ej. `chatbot-bi-webhook`) → no
   hace falta asignarle roles de proyecto adicionales (el permiso real lo da el
   scope `chat.bot` al llamar a la API de Chat, no un rol IAM).
3. Entra en la cuenta de servicio recién creada → pestaña **Claves** → **Agregar
   clave** → **Crear clave nueva** → tipo **JSON** → se descarga un archivo.
4. Mueve ese archivo a la carpeta `secrets/` del proyecto (ya está en
   `.gitignore`, nunca se sube al repo) y apunta `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE`
   en `.env` a esa ruta, por ejemplo:
   ```
   GOOGLE_CHAT_SERVICE_ACCOUNT_FILE=secrets/google-chat-service-account.json
   ```

> Si cambias de proyecto de Google Cloud, repite este paso — la clave JSON está
> ligada al proyecto en el que se creó la cuenta de servicio.

## 4. Ejecutar en terminal (sin depender de Google Chat)

Útil para probar el motor (capa semántica, PII, guardrails, memoria) sin montar
todo el circuito de Google Chat.

```bash
python chatbot.py
```

Preguntas de ejemplo:

- `¿Cuál ha sido el ROAS de las campañas de Search (SEM) durante el primer trimestre del año?`
  → señal técnica (terminología exacta de la capa semántica), perfil inferido `tecnico`.
- `¿Cuánta pasta nos hemos gastado en captación para el sector de Retail y Moda?`
  → señal de negocio (lenguaje coloquial), perfil inferido `negocio`.
- `Dime el CPA medio de las campañas de Social Ads frente a Programmatic.`
- `¿Cómo han ido las ventas este mes?` → ambigua, el bot debería pedir aclaración;
  con perfil `negocio` la pregunta de aclaración es guiada y en lenguaje llano.
- `Dame la lista de nombres y emails de todos los responsables de campaña` → debe negarse.
- `¿Cuánto presupuesto gestiona Almudena Barreiro?` → debe negarse (enmascarado de
  PII): ni el email ni el nombre completo de un Responsable real llegan nunca al LLM.

Para probar los endpoints del servidor sin pasar por Google Chat (health check y
los distintos tipos de evento del webhook), usa `requests.http`.

## 5. Crear y configurar la Chat App de Google (una sola vez)

1. Crea (o reutiliza) un proyecto en https://console.cloud.google.com — funciona
   con una cuenta Gmail personal (ver nota al final del README principal).
2. Habilita la **Google Chat API** (APIs y servicios → Biblioteca).
3. Ve a la pestaña **Configuración** de esa API — enlace directo:
   https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=tu-proyecto-id
   y rellena:
   - Nombre de la app, avatar (URL HTTPS de una imagen cuadrada), descripción.
   - Habilita **funciones interactivas** y marca **"Unirse a espacios y
     conversaciones grupales"**.
   - Configuración de conexión → **"URL del extremo HTTP"** → de momento pon una
     URL de prueba, la actualizaremos en el paso 7.
   - Visibilidad → añade tu propio email de Gmail.
   - Guarda.
4. Busca el nombre de tu app en https://chat.google.com (botón "+" junto a
   Mensajes directos) y ábrela para crear el chat 1:1.

## 6. Arrancar el servidor local

```bash
python server.py
```

Debería imprimir algo como `Datos cargados: 1000 filas...` y quedarse escuchando
en el puerto **8080** (o el que pongas en `PORT` dentro de `.env`).

⚠️ No cierres esta terminal mientras trabajes.

## 7. Exponerlo a internet con VS Code Port Forwarding

1. Abre el panel **PORTS** (junto a Terminal/Problems/Debug Console, panel
   inferior). Si no lo ves: `Ctrl+Shift+P` → "Ports: Focus on Ports View".
2. Si el puerto 8080 no aparece detectado automáticamente, pulsa **"Forward a
   Port"** y escribe `8080`.
3. Clic derecho sobre esa fila → **"Port Visibility" → "Public"**. La primera
   vez pedirá iniciar sesión con GitHub o Microsoft (no hace falta que sea la
   misma cuenta que usas en Google Cloud).
4. **Verifica que de verdad quedó público**: abre la "Forwarded Address"
   directamente en el navegador, en una pestaña de incógnito (sin sesión
   iniciada). Debe responder `Chatbot BI webhook activo.` directamente, sin
   ninguna pantalla de login de por medio. Si pide login de GitHub autorizando
   "Dev Tunnels", la visibilidad no se aplicó bien — repite el paso 3. Ver
   [despliegue-y-relanzamiento.md](despliegue-y-relanzamiento.md) para más
   detalle sobre este problema conocido.
5. Copia la "Forwarded Address" (forma parecida a
   `https://xxxxxxx-8080.euw.devtunnels.ms`) y pégala + `/googlechat` en:
   - **Google Cloud Console** → el [enlace directo](https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=tu-proyecto-id)
     de arriba → "Configuración de conexión" → campo **"URL del extremo HTTP"**.
   - **`.env`**, variable `GOOGLE_CHAT_WEBHOOK_URL`. Debe coincidir **carácter
     por carácter** con lo puesto en Cloud Console — Google firma el token JWT
     usando esa URL exacta como "audience".
6. Reinicia `server.py` (Ctrl+C y vuelve a lanzarlo) si has cambiado el `.env`.

> Alternativa sin VS Code: `cloudflared tunnel --url http://localhost:8080`. La
> URL pública cambia cada vez que reinicias el túnel — hay que repetir el paso 5.

## 8. Probar

Ve a [chat.google.com](https://chat.google.com), abre el chat 1:1 con tu Chat App
("Chatbot BI") y escríbele una pregunta real (ver ejemplos en la sección 4).
Debería responder con el código pandas ejecutado y el resultado real calculado
sobre los 1,000 registros.

## 9. Verificar que el log se está generando

Revisa `logs/interactions.jsonl` en el proyecto: debería aparecer una línea nueva
por cada pregunta. Ver [logging-y-trazabilidad.md](logging-y-trazabilidad.md) para
el detalle de qué campos incluye y cómo se protege el email del usuario.
