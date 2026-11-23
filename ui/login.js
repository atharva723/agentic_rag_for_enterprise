// Login page: sign in or create an account, then open the chat.

const REASONS = { expired: "Your sign-in ended. Please sign in again." };
let mode = "in"; // "in" is sign in, "up" is create an account

const note = (text, tone = "") => {
  $("auth-note").textContent = text;
  $("auth-note").className = `form-note ${tone}`.trim();
};

function setMode(next) {
  mode = next;
  const signingIn = next === "in";
  $("tab-in").setAttribute("aria-pressed", String(signingIn));
  $("tab-up").setAttribute("aria-pressed", String(!signingIn));
  $("auth-title").textContent = signingIn ? "Sign in" : "Create your account";
  $("auth-submit").textContent = signingIn ? "Sign In" : "Create Account";
  $("password").autocomplete = signingIn ? "current-password" : "new-password";
  $("password-hint").hidden = signingIn;
  // Only a new password must be long enough. An existing one may be older than that rule.
  if (signingIn) $("password").removeAttribute("minlength");
  else $("password").minLength = 8;
  $("resend").hidden = true;
  note("");
}

function showBlocked({ title, text }) {
  $("auth-title").textContent = title;
  $("auth-lead").textContent = text;
  $("tabs").hidden = true;
  $("auth-form").hidden = true;
}

$("tab-in").addEventListener("click", () => setMode("in"));
$("tab-up").addEventListener("click", () => setMode("up"));

$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isBusy("#auth-submit")) return;
  const email = $("email").value.trim();
  const password = $("password").value;
  setBusy("#auth-submit", true);
  $("resend").hidden = true;
  note(mode === "in" ? "Signing in…" : "Creating your account…");
  const result = await (mode === "in" ? Auth.signIn(email, password) : Auth.signUp(email, password));
  setBusy("#auth-submit", false);

  if (result.error) {
    if (result.code === "user_already_exists") setMode("in");
    note(result.error, "bad");
    $("resend").hidden = result.code !== "email_not_confirmed";
  } else if (result.confirm) {
    note(`Check your email. We sent a link to ${email}. Open it and you will be signed in.`, "good");
    $("resend").hidden = false;
  } else {
    location.replace("chat.html");
  }
});

$("resend").addEventListener("click", async () => {
  if (isBusy("#resend")) return;
  setBusy("#resend", true);
  const result = await Auth.resend($("email").value.trim());
  setBusy("#resend", false);
  note(result.error ?? "We sent the email again. It can take a minute to arrive.", result.error ? "bad" : "good");
});

(async function start() {
  const reason = new URLSearchParams(location.search).get("reason");
  const linkFailed = new URLSearchParams(location.hash.slice(1)).has("error_description"); // an email link that did not work
  const blocked = await Auth.init();
  if (blocked) return showBlocked(blocked);
  // Someone already signed in, or just arrived from the link in their confirmation email, goes straight to the chat.
  if (!reason && !linkFailed && (await Auth.user())) return location.replace("chat.html");

  if (linkFailed) {
    history.replaceState(null, "", location.pathname);
    note("That email link is invalid or has expired. Sign in and we can send you a new one.", "bad");
  } else if (REASONS[reason]) {
    note(REASONS[reason]);
  }
  if (matchMedia("(pointer: fine)").matches) $("email").focus(); // not on a phone: it would open the keyboard before anyone asked
})();
