"""
Un archivo de configuración por proveedor de LLM soportado. Cada módulo:

  - lee sus propias variables de entorno (con valores por defecto razonables
    cuando aplica);
  - expone una función `validate()` que comprueba que están todos los datos
    necesarios para funcionar (API key, modelo...) y, si falta alguno, lanza
    `RuntimeError` indicando exactamente qué falta y cómo conseguirlo.

`validate()` NO se ejecuta al importar el módulo: solo se llama para el
proveedor que efectivamente se selecciona con LLM_PROVIDER (ver llm/__init__.py),
así que tener rellenas las variables de un proveedor que no usas es opcional.
"""
