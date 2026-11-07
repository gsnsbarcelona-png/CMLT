document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const feedback = document.getElementById("login-feedback");
  const button = event.target.querySelector("button");
  feedback.textContent = "";
  button.disabled = true;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: document.getElementById("login-password").value }),
    });
    if (res.ok) {
      window.location.replace("/");
      return;
    }
    const body = await res.json().catch(() => null);
    feedback.textContent = body?.detail || `Error ${res.status}`;
  } catch (e) {
    feedback.textContent = "No se pudo conectar con el servidor.";
  } finally {
    button.disabled = false;
  }
});
