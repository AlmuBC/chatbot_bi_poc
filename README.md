# Chatbot BI — PoC

Chatbot de analítica de marketing, instalado como **Chat App de Google Chat**, que
responde preguntas de negocio en lenguaje coloquial sobre
`marketing_performance_1000_t2o.xlsx`, usando una capa semántica
(`semantic_layer.yaml`) para traducir sinónimos y aplicar las fórmulas oficiales
(CTR, CPA, ROAS...).

**Principio clave:** el LLM nunca "calcula de memoria". Su único trabajo es
traducir la pregunta a código pandas. El número que ves siempre sale de ejecutar
ese código contra los datos reales — por eso el propio código generado se incluye
en cada respuesta, para poder verificarlo.

> **Nota sobre cuentas Google:** la documentación oficial de Google dice que la
> plataforma de desarrollo de Chat apps "solo está disponible para cuentas de
> Google Workspace" y que no se puede desarrollar ni probar con un @gmail.com
> personal. En la práctica, hemos comprobado de punta a punta que sí funciona con
> una cuenta Gmail personal — este proyecto es la prueba. Si en algún momento deja
> de funcionar, probablemente sea por un cambio de política de Google, no por
> algo mal configurado aquí.

## Puesta en marcha

Si es la **primera vez** que instalas este proyecto (o quieres probar la PoC
desde cero), sigue la guía completa:

**→ [docs/instalacion-y-puesta-en-marcha.md](docs/instalacion-y-puesta-en-marcha.md)**

Cubre, en orden: instalar dependencias, configurar `.env`, crear la cuenta de
servicio de Google Cloud, crear y configurar la Chat App, arrancar el servidor y
exponerlo a internet, y probarlo en Google Chat.

Si el proyecto **ya estaba funcionando** y solo necesitas retomarlo tras un
parón (portátil apagado, túnel caído, etc.), usa el runbook corto:

**→ [docs/despliegue-y-relanzamiento.md](docs/despliegue-y-relanzamiento.md)**

### Arranque rápido (solo motor, sin Google Chat)

Para probar el motor (capa semántica, PII, guardrails, memoria) en la terminal,
sin montar el circuito completo de Google Chat:

```bash
cd chatbot_bi_poc
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell; Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # y rellena LLM_PROVIDER + sus credenciales
python chatbot.py
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/instalacion-y-puesta-en-marcha.md](docs/instalacion-y-puesta-en-marcha.md) | Instalación desde cero: dependencias, `.env`, cuenta de servicio, Chat App, servidor, túnel |
| [docs/despliegue-y-relanzamiento.md](docs/despliegue-y-relanzamiento.md) | Runbook corto para retomar el proyecto tras un parón (checklist + problemas conocidos) |
| [docs/logging-y-trazabilidad.md](docs/logging-y-trazabilidad.md) | Qué se registra en `logs/interactions.jsonl` y cómo se protege el email del usuario |
| [docs/pii-y-guardrails.md](docs/pii-y-guardrails.md) | Enmascarado de PII (esquema, emails, nombres conocidos) y guardrail contra prompt injection / extracción masiva |
| [docs/memoria-y-perfilado.md](docs/memoria-y-perfilado.md) | Memoria de conversación de corto plazo y perfilado adaptativo técnico/negocio |
| [docs/proveedores-llm.md](docs/proveedores-llm.md) | Cómo cambiar o añadir un proveedor de LLM, y particularidades técnicas descubiertas (OpenCode, Google Chat) |
| [docs/notas-tecnicas-y-roadmap.md](docs/notas-tecnicas-y-roadmap.md) | Qué queda pendiente y por qué se tomaron ciertas decisiones de diseño |
| [CHANGELOG.md](CHANGELOG.md) | Historial detallado de cada paso implementado |

## Tests

```bash
pip install -r requirements.txt  # incluye pytest
pytest tests/ -v
```

`tests/test_pii.py` y `tests/test_guardrails.py` cubren, respectivamente, el
enmascarado de PII y el guardrail contra prompt injection / extracción masiva,
con tests unitarios y de integración end-to-end contra `server.answer_question`
(LLM mockeado).

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
│   ├── guardrails.py              # guardrail contra prompt injection y extracción masiva de PII
│   ├── sandbox.py                 # ejecuta el código generado de forma acotada
│   └── context.py                 # memoria de conversación de corto plazo (a partir del log)
├── observability/
│   └── logger.py                 # logging de trazabilidad en logs/interactions.jsonl
├── tests/
│   ├── test_pii.py                # tests del enmascarado de PII (unitarios + integración)
│   └── test_guardrails.py         # tests del guardrail (unitarios + integración)
├── docs/                       # documentación detallada (ver tabla arriba)
├── data/                       # copia del Excel y el YAML de origen
├── logs/                       # interactions.jsonl (generado en runtime, ignorado por git)
├── secrets/                    # claves de cuentas de servicio (ignorado por git)
├── requirements.txt
└── .env.example
```
