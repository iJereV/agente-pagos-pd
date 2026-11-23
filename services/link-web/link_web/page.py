"""The customer-facing sign-in page (Spanish copy, no framework, inline CSS)."""

import json
from dataclasses import dataclass

FIREBASE_SDK_VERSION = "13.2.0"
FIREBASE_CDN = f"https://www.gstatic.com/firebasejs/{FIREBASE_SDK_VERSION}"


@dataclass(frozen=True)
class IdentityConfig:
    api_key: str
    auth_domain: str


def render_link_page(config: IdentityConfig) -> str:
    # The link token is read by the browser from the URL, never echoed by the server.
    config_json = json.dumps({"apiKey": config.api_key, "authDomain": config.auth_domain})
    return _PAGE.replace("__CONFIG_JSON__", config_json.replace("<", "\\u003c")).replace(
        "__FIREBASE_CDN__", FIREBASE_CDN
    )


_PAGE = """<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Vincular tu WhatsApp</title>
<style>
  :root {
    --bg: #f4f1ea; --card: #ffffff; --text: #1f2421; --muted: #5d6661;
    --accent: #1f7a5a; --accent-text: #ffffff; --border: #e3ded3;
    --ok: #1f7a5a; --error: #b3412e;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #141816; --card: #1d2320; --text: #eef1ee; --muted: #a3aca6;
      --accent: #4cc596; --accent-text: #0d1411; --border: #2c3430;
      --ok: #4cc596; --error: #f08a74;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
    background: var(--bg); color: var(--text);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  main {
    width: 100%; max-width: 400px; padding: 32px 24px; border-radius: 20px;
    background: var(--card); border: 1px solid var(--border);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.08); text-align: center;
  }
  .badge { font-size: 44px; line-height: 1; margin-bottom: 12px; }
  h1 { font-size: 22px; margin: 0 0 8px; }
  p { margin: 0 0 20px; color: var(--muted); }
  button {
    width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 10px;
    padding: 14px 18px; border: 0; border-radius: 12px; cursor: pointer;
    background: var(--accent); color: var(--accent-text); font: 600 16px/1 inherit;
  }
  button:disabled { opacity: 0.6; cursor: progress; }
  .status { margin: 20px 0 0; font-weight: 600; }
  .status.ok { color: var(--ok); }
  .status.error { color: var(--error); }
  .hint { margin: 8px 0 0; font-size: 14px; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<main>
  <div class="badge" aria-hidden="true">🐾</div>
  <h1 id="title">Ingresá con Google</h1>
  <p id="lead">
    Así confirmamos que sos vos y podés pedir imágenes y consultar tu saldo por WhatsApp.
  </p>
  <button id="signin" type="button">Continuar con Google</button>
  <p id="status" class="status" role="status" aria-live="polite" hidden></p>
  <p id="hint" class="hint" hidden>Ya podés volver a WhatsApp.</p>
</main>
<script id="identity-config" type="application/json">__CONFIG_JSON__</script>
<script type="module">
  import { initializeApp } from "__FIREBASE_CDN__/firebase-app.js";
  import {
    GoogleAuthProvider, browserPopupRedirectResolver, browserSessionPersistence,
    getRedirectResult, initializeAuth, signInWithPopup, signInWithRedirect, signOut,
  } from "__FIREBASE_CDN__/firebase-auth.js";

  const MESSAGES = {
    linked: "¡Listo! Tu WhatsApp quedó vinculado a tu cuenta de Google.",
    reauthenticated: "¡Listo! Ya confirmamos que sos vos.",
    token_used: "Este enlace ya se usó. Pedí uno nuevo por WhatsApp.",
    token_expired: "Este enlace venció. Pedí uno nuevo por WhatsApp.",
    token_not_found: "Este enlace no es válido. Pedí uno nuevo por WhatsApp.",
    token_mismatch: "Este enlace no es válido. Pedí uno nuevo por WhatsApp.",
    invalid_link: "Este enlace no es válido o venció. Pedí uno nuevo por WhatsApp.",
    not_linked: "Tu número todavía no está vinculado. Pedí un enlace nuevo por WhatsApp.",
    number_linked_to_other_account:
      "Este WhatsApp ya está vinculado a otra cuenta de Google. Probá con esa cuenta.",
    account_linked_to_other_number:
      "Esta cuenta de Google ya está vinculada a otro número de WhatsApp.",
    account_mismatch:
      "Esa no es la cuenta de Google vinculada a tu WhatsApp. Probá con la cuenta correcta.",
    google_account_required: "Necesitamos una cuenta de Google con email. Probá de nuevo.",
    invalid_identity: "No pudimos verificar tu cuenta de Google. Probá de nuevo.",
    unexpected: "Algo salió mal. Probá de nuevo en unos minutos.",
  };
  const RETRYABLE = new Set([
    "number_linked_to_other_account", "account_mismatch", "google_account_required",
    "invalid_identity", "unexpected",
  ]);

  const USE_REDIRECT = new Set([
    "auth/popup-blocked", "auth/operation-not-supported-in-this-environment",
  ]);
  const POPUP_DISMISSED = new Set(["auth/popup-closed-by-user", "auth/cancelled-popup-request"]);

  const button = document.getElementById("signin");
  const statusEl = document.getElementById("status");
  const hintEl = document.getElementById("hint");
  const linkToken = new URLSearchParams(window.location.search).get("t");

  function show(code, ok) {
    statusEl.textContent = MESSAGES[code] || MESSAGES.unexpected;
    statusEl.className = "status " + (ok ? "ok" : "error");
    statusEl.hidden = false;
    hintEl.hidden = !ok;
    button.hidden = ok || !RETRYABLE.has(code);
    button.disabled = false;
    if (ok) {
      document.getElementById("title").textContent = "¡Todo listo!";
      document.getElementById("lead").hidden = true;
    }
  }

  if (!linkToken) {
    show("invalid_link", false);
  } else {
    const config = JSON.parse(document.getElementById("identity-config").textContent);
    const auth = initializeAuth(initializeApp(config), {
      persistence: browserSessionPersistence,
      popupRedirectResolver: browserPopupRedirectResolver,
    });
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });

    async function complete(user) {
      button.disabled = true;
      try {
        const response = await fetch("/api/link", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ link_token: linkToken, id_token: await user.getIdToken() }),
        });
        const body = await response.json().catch(() => ({}));
        show(body.status || "unexpected", response.ok);
      } catch {
        show("unexpected", false);
      } finally {
        await signOut(auth).catch(() => {});
      }
    }

    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await signInWithPopup(auth, provider);
        await complete(result.user);
      } catch (error) {
        if (USE_REDIRECT.has(error.code)) {
          await signInWithRedirect(auth, provider);
        } else if (POPUP_DISMISSED.has(error.code)) {
          button.disabled = false;
        } else {
          show("invalid_identity", false);
        }
      }
    });

    getRedirectResult(auth)
      .then((result) => result && complete(result.user))
      .catch(() => show("invalid_identity", false));
  }
</script>
</body>
</html>
"""
