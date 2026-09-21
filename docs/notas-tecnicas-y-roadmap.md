# Roadmap y próximos pasos

Qué queda pendiente, a propósito no incluido en esta PoC:

- **Gateway tipo LiteLLM** delante de OpenCode, para no llamar directo al
  proveedor.
- **PII — NER general:** hoy `core/pii.py::mask_known_pii_names` es data-driven,
  cerrado al conjunto conocido de `Responsable`. Pendiente un enfoque tipo
  Microsoft Presidio/NER para detectar nombres de persona que NO estén ya en los
  datos. Ver [pii-y-guardrails.md](pii-y-guardrails.md).
- **Guardrails — capa 2 opcional:** un clasificador LLM barato, si en uso real
  aparecen jailbreaks que la capa de regex de `core/guardrails.py` no capture.
  `core/sandbox.py` sigue sin ser un aislamiento de seguridad de nivel producción
  (proceso aislado, límites de recursos). Ver
  [pii-y-guardrails.md](pii-y-guardrails.md).
- **Estabilidad de infraestructura:** la URL del túnel (VS Code Port Forwarding /
  cloudflared) cambia en cada reinicio, y `server.py` corre con el servidor de
  desarrollo de Flask (no apto para producción). Ver
  [despliegue-y-relanzamiento.md](despliegue-y-relanzamiento.md).
- **Latencia anómala bajo tráfico concurrente (diagnosticado, no corregido):**
  dos interacciones reales registraron ~99–108 s de latencia (vs. 3–24 s
  habitual), solapadas en el tiempo con otras peticiones concurrentes. Hipótesis
  principal: `llm/opencode_client.py` usa un único `_OPENCODE_SESSION_ID` por
  proceso, compartido por todas las peticiones de todos los usuarios — si el
  backend de OpenCode serializa bajo ese header, peticiones simultáneas quedan
  encoladas. Agravante posible: reintento de entrega del webhook de Google Chat
  si no recibe ack a tiempo. Sin confirmar todavía.

## Historial de decisiones (por qué se hizo así y no de otra forma)

- **PII sin Presidio:** se optó por reglas propias deterministas
  (`core/pii.py`) en vez de Microsoft Presidio para no añadir una dependencia
  pesada (modelos NER) a una PoC de este tamaño. Es la decisión de la que parte
  también la de guardrails, más abajo.
- **Guardrails sin NeMo Guardrails:** se evaluó y descartó NeMo Guardrails a
  favor de una capa propia (`core/guardrails.py`). Habría requerido adaptar
  `llm/opencode_client.py` (SDK `openai` puro contra un endpoint custom) a la
  interfaz LangChain, dependencias pesadas (`nemoguardrails` + `langchain*` +
  embeddings), un lenguaje de configuración nuevo (Colang), y típicamente una o
  dos llamadas adicionales al LLM por petición (self-check rails) — latencia y
  coste no justificados para el tamaño de este PoC. La capa propia no añade
  dependencias, es determinista y encaja con el mismo patrón que `core/pii.py`.

Para el detalle completo de cada paso implementado, ver [../CHANGELOG.md](../CHANGELOG.md).
