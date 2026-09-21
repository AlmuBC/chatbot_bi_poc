# Despliegue y relanzamiento tras un parón

Runbook operativo para retomar el proyecto después de un parón (portátil apagado,
VS Code cerrado, etc.) cuando **ya está todo instalado y configurado una vez**
(ver [instalacion-y-puesta-en-marcha.md](instalacion-y-puesta-en-marcha.md) si es
la primera vez). Sigue el orden — el orden importa.

**Proyecto de Google Cloud:** `tu-proyecto-id`
**Enlace directo a la configuración de la Chat API:**
```
https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=tu-proyecto-id
```
**Enlace directo a las cuentas de servicio (IAM):**
```
https://console.cloud.google.com/iam-admin/serviceaccounts?project=tu-proyecto-id
```

---

## 1. Arranca el servidor Flask local

Desde la terminal integrada de VS Code, dentro de la carpeta del proyecto:

```bash
python server.py
```

Debería imprimir algo como `Datos cargados: 1000 filas...` y quedarse escuchando
en el puerto **8080** (o el que tengas puesto en `PORT` dentro de `.env`).

⚠️ No cierres esta terminal mientras trabajes.

---

## 2. Expón el servidor con VS Code Port Forwarding

1. Abre el panel **PORTS** (junto a TERMINAL, PROBLEMS y DEBUG CONSOLE, en el panel
   inferior). Si no lo ves: `Ctrl+Shift+P` → "Ports: Focus on Ports View".
2. Si el puerto 8080 no aparece detectado automáticamente, pulsa **"Forward a Port"**
   y escribe `8080`.
3. Clic derecho sobre esa fila → **"Port Visibility" → "Public"**. La primera vez
   pedirá iniciar sesión con GitHub o Microsoft (no hace falta que sea la misma
   cuenta que usas en Google Cloud).

### ⚠️ Paso crítico: verifica que de verdad quedó público

Abre la **"Forwarded Address"** directamente en el navegador, en una pestaña de
incógnito (sin sesión iniciada). Debe responder:

```
Chatbot BI webhook activo.
```

**Si en vez de eso te aparece una pantalla de login de GitHub** pidiendo autorizar
"Dev Tunnels", la visibilidad NO se aplicó bien (es un comportamiento conocido de VS
Code que a veces se revierte solo). Repite el paso 3 hasta que la respuesta sea
directa, sin login. Este fue el motivo por el que la primera vez "no funcionaba" sin
dar ningún error visible.

---

## 3. Copia la URL pública y actualízala en DOS sitios

Copia la "Forwarded Address" (tiene una forma parecida a
`https://xxxxxxx-8080.euw.devtunnels.ms`).

Pégala + `/googlechat` en:

1. **Google Cloud Console** → usa el [enlace directo](https://console.cloud.google.com/apis/api/chat.googleapis.com/hangouts-chat?project=tu-proyecto-id)
   de arriba → sección "Configuración de conexión" → campo **"URL del extremo HTTP"**.
   Ejemplo: `https://xxxxxxx-8080.euw.devtunnels.ms/googlechat`. Guarda.
2. **`.env`** del proyecto, variable `GOOGLE_CHAT_WEBHOOK_URL`. Debe coincidir
   **carácter por carácter** con lo que pusiste en Cloud Console — Google firma el
   token JWT usando esa URL exacta como "audience".

---

## 4. Reinicia el servidor si tocaste el `.env`

Si cambiaste `GOOGLE_CHAT_WEBHOOK_URL`, para `server.py` (Ctrl+C) y vuelve a lanzarlo:

```bash
python server.py
```

---

## 5. Prueba en Google Chat

Ve a [chat.google.com](https://chat.google.com), abre el chat 1:1 con tu Chat App
("Chatbot BI") y escríbele una pregunta real, por ejemplo:

> ¿Cuál ha sido el ROAS de las campañas de Search (SEM) durante el primer trimestre
> del año?

Debería responder con el resultado calculado y el código pandas usado.

---

## 6. Verifica que el log se está generando

Revisa `logs/interactions.jsonl` en el proyecto: debería aparecer una línea nueva por
cada pregunta, con estos campos: `interaction_id`, `timestamp`, `user_email`,
`space_id`, `thread_id`, `question`, `llm_action`, `generated_code`,
`execution_result`, `execution_error`, `final_response`, `status`, `latency_ms`,
`user_profile`, `profile_confidence`. Ver
[logging-y-trazabilidad.md](logging-y-trazabilidad.md) para el detalle.

---

## Notas / cosas que ya sabemos que pueden fallar

- **La URL de VS Code Port Forwarding cambia** cada vez que reinicias el túnel o VS
  Code, salvo que uses un túnel con nombre fijo. Hay que repetir los pasos 3 y 4 cada
  vez.
- **La visibilidad "Public" a veces se revierte sola.** Si Google Chat deja de
  responder sin error visible, lo primero a comprobar es el paso 2 (abrir la URL en
  incógnito y ver si pide login de GitHub).
- El endpoint `/` (health check) en local vs en la URL pública puede dar respuestas
  distintas si el túnel no está realmente público — es la forma más rápida de
  diagnosticar el problema del punto anterior.
- El token JWT que verifica `server.py` usa la URL del webhook como "audience": si no
  coincide carácter por carácter entre Cloud Console y `.env`, la verificación falla
  con 401 aunque todo lo demás esté bien configurado.
- Si la cuenta de servicio (la clave JSON en `secrets/`) se pierde, se revoca o
  caduca, hay que generar una nueva desde
  [IAM → Cuentas de servicio](https://console.cloud.google.com/iam-admin/serviceaccounts?project=tu-proyecto-id)
  y actualizar `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE` — ver el paso 3 de
  [instalacion-y-puesta-en-marcha.md](instalacion-y-puesta-en-marcha.md).
- Estabilidad de infraestructura: la URL del túnel cambia en cada reinicio, y
  `server.py` corre con el servidor de desarrollo de Flask (no apto para
  producción). Ver [notas-tecnicas-y-roadmap.md](notas-tecnicas-y-roadmap.md).
