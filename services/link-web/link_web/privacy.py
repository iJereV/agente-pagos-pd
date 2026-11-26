"""Public privacy policy page (Spanish copy, static HTML, inline CSS).

Meta requires a privacy policy URL before a WhatsApp app can be switched to Live mode.
Contact goes through the shop's own WhatsApp number, so no personal address lives here.
"""

PRIVACY_PAGE = """<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de privacidad</title>
<style>
  :root {
    --bg: #f4f1ea; --card: #ffffff; --text: #1f2421; --muted: #5d6661; --border: #e3ded3;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #141816; --card: #1d2320; --text: #eef1ee; --muted: #a3aca6; --border: #2c3430; }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px; background: var(--bg); color: var(--text);
    font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  main {
    max-width: 720px; margin: 24px auto; padding: 32px 24px; border-radius: 20px;
    background: var(--card); border: 1px solid var(--border);
  }
  h1 { font-size: 26px; margin: 0 0 4px; }
  h2 { font-size: 18px; margin: 28px 0 8px; }
  p, li { color: var(--muted); }
  ul { padding-left: 20px; }
  .updated { font-size: 14px; margin: 0 0 24px; }
</style>
</head>
<body>
<main>
  <h1>Política de privacidad</h1>
  <p class="updated">Última actualización: 26 de noviembre de 2026</p>

  <p>Este servicio es un asistente de WhatsApp que vende imágenes de animales generadas
  con inteligencia artificial, con pago por transferencia bancaria. Esta página explica
  qué datos usamos, para qué y cómo pedir que se borren.</p>

  <h2>Qué datos recopilamos</h2>
  <ul>
    <li>Tu número de WhatsApp y el nombre de tu perfil.</li>
    <li>Los mensajes, imágenes y documentos que nos enviás por el chat.</li>
    <li>Los comprobantes de transferencia: monto, fecha, nombre del titular y
    datos de la operación.</li>
    <li>Si iniciás sesión con Google: tu identificador de cuenta y tu email.</li>
    <li>Tus pedidos, pagos y saldo.</li>
  </ul>

  <h2>Para qué los usamos</h2>
  <ul>
    <li>Responder tus mensajes y tomar tus pedidos.</li>
    <li>Verificar que cada transferencia exista y corresponda a tu cuenta.</li>
    <li>Llevar el registro de tus pedidos, pagos y saldo.</li>
    <li>Enviarte las imágenes que compraste.</li>
  </ul>
  <p>No vendemos tus datos ni los usamos para publicidad.</p>

  <h2>Con quién se comparten</h2>
  <ul>
    <li>Meta (WhatsApp), para enviar y recibir los mensajes.</li>
    <li>Google Cloud, donde se alojan el servicio, los datos y los modelos de
    inteligencia artificial que procesan los mensajes y los comprobantes.</li>
    <li>Mercado Pago, para confirmar que una transferencia se haya acreditado.</li>
  </ul>

  <h2>Cuánto tiempo los guardamos</h2>
  <p>Guardamos los datos mientras tengas una cuenta activa o mientras sean necesarios
  para registrar pedidos y pagos. Después se eliminan.</p>

  <h2>Tus derechos</h2>
  <p>Podés pedir acceso, corrección o eliminación de tus datos escribiendo
  "borrar mis datos" al mismo número de WhatsApp del servicio. Respondemos dentro de
  los 10 días hábiles. También podés dirigirte a la Agencia de Acceso a la Información
  Pública, autoridad de control de la Ley 25.326 de Protección de Datos Personales.</p>
</main>
</body>
</html>
"""
