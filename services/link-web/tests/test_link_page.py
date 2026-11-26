from link_web.page import FIREBASE_CDN, IdentityConfig, render_link_page


def test_page_is_served_with_config_and_no_referrer(client):
    response = client.get("/link", params={"t": "some-token"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert '"apiKey": "public-api-key"' in response.text
    assert f"{FIREBASE_CDN}/firebase-auth.js" in response.text
    assert "Continuar con Google" in response.text
    # The token is read client-side from the URL, never rendered by the server.
    assert "some-token" not in response.text


def test_config_cannot_break_out_of_the_script_tag():
    html = render_link_page(
        IdentityConfig("</script><script>alert(1)</script>", "demo.firebaseapp.com")
    )

    assert "</script><script>alert(1)" not in html


def test_privacy_policy_is_public_and_names_the_deletion_channel(client):
    response = client.get("/privacy")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Política de privacidad" in response.text
    assert "borrar mis datos" in response.text
    assert "noindex" not in response.text
