/**
 * WaiBin — shared frontend utilities.
 * Included on all pages that need msg(), escapeHtml(), and auth checks.
 */

/** Show a temporary message banner. type is "success" or "error". */
function msg(type, text) {
  var box = document.getElementById("msgBox");
  if (!box) {
    // Create a floating toast if no dedicated msgBox element
    box = document.createElement("div");
    box.id = "msgToast";
    box.style.cssText = "position:fixed;top:1rem;right:1rem;z-index:9999;max-width:360px;transition:opacity 0.3s";
    document.body.appendChild(box);
  }
  box.textContent = text;
  box.className = "mb-6 p-4 rounded-xl text-sm " +
    (type === "error"
      ? "bg-red-50 border border-red-200 text-red-800"
      : "bg-green-50 border border-green-200 text-green-800");
  box.style.display = "block";
  clearTimeout(box._msgTimer);
  box._msgTimer = setTimeout(function () {
    box.style.display = "none";
  }, 3500);
}

/** Escape HTML entities to prevent XSS. */
function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Check auth state.
 * Calls /api/auth/me and redirects to /login if not authenticated.
 * Pass a callback to run on authenticated, or omit to redirect.
 * Uses a global guard to prevent duplicate redirects.
 */
var _authRedirecting = false;

function requireAuth(callback) {
  fetch("/api/auth/me")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.authenticated) {
        if (!_authRedirecting) {
          _authRedirecting = true;
          window.location.href = "/login";
        }
        return;
      }
      if (callback) callback(data);
    })
    .catch(function () {
      if (!_authRedirecting) {
        _authRedirecting = true;
        window.location.href = "/login";
      }
    });
}
