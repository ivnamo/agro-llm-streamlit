He montado un sistema que hace esto:

 Los sensores del invernadero (humedad del suelo, temperatura, radiación, etc.)
→ mandan datos a un servidor.

 Yo programé una cosa que coge todos esos datos automáticamente todos los días
→ y los guarda en Google Cloud.

 Luego monté una base de datos en BigQuery que ordena y limpia los datos
→ para que no parezcan escritos por un mono.

 Después creé un “cerebro” con Gemini (la IA de Google)
→ que mira los datos del invernadero
→ entiende la humedad, la salinidad, la radiación solar, etc.
→ y decide cuánta agua hay que echar para regar bien sin pasarse.

 Finalmente construí una app web en Streamlit
→ tiene un botón que pone "Obtener recomendación ahora”
→ lo pulsas
→ y la IA te dice cuánto regar hoy, cuántos litros por metro cuadrado,
→ en cuántos ciclos, a qué horas
→ y te explica por qué.

Básicamente:

👉 He hecho un ChatGPT que te dice cómo regar un invernadero como un ingeniero agrónomo de verdad.
👉 Y funciona en tiempo real.
👉 Y se ve bonito.
👉 Y todo automático

En resumen:

YO: he creado Skynet del riego
MIS AMIGOS: “bro, pásame el enlace”
EL INVERNADERO: hidratadísimo
