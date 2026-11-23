// Sign-in for the browser. The only file that talks to Supabase Auth, through the official library in vendor/supabase.js.
// The server never trusts this file: it checks every token itself (app/supabase/auth.py).

const Auth = (() => {
  const LOGIN = "login.html";
  const OFF = { title: "Accounts are not set up", text: "Chats are saved to a Supabase account, and no Supabase project is connected yet. Follow supabase/README.md, then restart the server." };
  const DOWN = { title: "Cannot reach the server", text: "Check that the server is running, then reload this page." };
  const BROKEN = { title: "Sign-in did not load", text: "A file this page needs could not be loaded. Reload the page." };

  // What the sign-in service says, in plain words. Anything not listed shows the service's own message.
  const FRIENDLY = {
    invalid_credentials: "That email and password do not match. Check them and try again.",
    email_not_confirmed: "This email is not confirmed yet. Open the link we sent you, or send it again.",
    user_already_exists: "That email already has an account. Sign in instead.",
    email_exists: "That email already has an account. Sign in instead.",
    over_request_rate_limit: "Too many attempts. Wait a few minutes and try again.",
    over_email_send_rate_limit: "Too many emails were sent. Wait a while before asking for another.",
    email_address_invalid: "That email address is not accepted. Use a real one.",
    email_address_not_authorized: "Emails can only go to the project's team members until a mail service is set up. See supabase/README.md.",
    signup_disabled: "New accounts are switched off for this project.",
    validation_failed: "Enter a valid email address and a password.",
    user_banned: "This account is blocked.",
  };

  let client = null; // the Supabase client, made once /api/config says which project to use
  let setup = null; // the one-time setup, shared by every caller
  let leaving = false; // true once this page has started going to the login page

  async function configure() {
    if (typeof supabase === "undefined") return BROKEN;
    let res;
    try {
      res = await fetch("/api/config", { signal: AbortSignal.timeout?.(8000) });
    } catch {
      return DOWN;
    }
    const body = await res.json().catch(() => ({}));
    if (res.status === 503) return { title: OFF.title, text: typeof body.detail === "string" ? body.detail : OFF.text };
    if (!res.ok) return DOWN;
    if (!body.supabase) return OFF;
    // The defaults are what we want: the session is kept in localStorage, renewed before it runs out,
    // and read from the link in a confirmation email.
    client = supabase.createClient(body.supabase.url, body.supabase.publishable_key);
    return null;
  }

  // Resolves to null when sign-in can work, otherwise { title, text } for the page to show.
  const init = () => (setup ??= configure());

  async function session() {
    if (!client) return null;
    const { data } = await client.auth.getSession(); // renews the token first when it is about to run out
    return data.session;
  }

  const token = async () => (await session())?.access_token ?? "";

  async function user() {
    const current = await session();
    return current ? { id: current.user.id, email: current.user.email } : null;
  }

  function friendly(error) {
    if (FRIENDLY[error.code]) return FRIENDLY[error.code];
    if (error.name === "AuthRetryableFetchError") return "Could not reach the sign-in service. Check your connection and try again.";
    return error.message || "Something went wrong. Please try again.";
  }
  const failed = (error) => ({ error: friendly(error), code: error.code });
  const confirmLink = () => new URL(LOGIN, location.href).href; // the page the email link opens
  const unavailable = { error: "Sign-in is not available right now. Reload the page and try again." };

  // A form can be used a moment before the setup has finished.
  async function ready() {
    await init();
    return Boolean(client);
  }

  async function signIn(email, password) {
    if (!(await ready())) return unavailable;
    const { error } = await client.auth.signInWithPassword({ email, password });
    return error ? failed(error) : {};
  }

  // Resolves to {} when signed in at once, { confirm: true } when an email must be opened first, or { error, code }.
  async function signUp(email, password) {
    if (!(await ready())) return unavailable;
    const { data, error } = await client.auth.signUp({ email, password, options: { emailRedirectTo: confirmLink() } });
    if (error) return failed(error);
    if (data.session) return {};
    // This is how Supabase says an email is taken, without telling the world which emails have accounts.
    if (data.user?.identities?.length === 0) return { error: FRIENDLY.user_already_exists, code: "user_already_exists" };
    return { confirm: true };
  }

  async function resend(email) {
    if (!(await ready())) return unavailable;
    const { error } = await client.auth.resend({ type: "signup", email, options: { emailRedirectTo: confirmLink() } });
    return error ? failed(error) : {};
  }

  function toLogin(reason = "") {
    leaving = true;
    location.replace(reason ? `${LOGIN}?reason=${reason}` : LOGIN);
  }

  // Signs out of this browser only ("local"), then goes to the login page.
  async function leave(reason) {
    leaving = true;
    await client?.auth.signOut({ scope: "local" });
    toLogin(reason);
  }

  // For pages that need a signed-in user: go to the login page when the person signs out in another tab,
  // or when their sign-in can no longer be renewed.
  function watch() {
    client?.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_OUT" && !leaving) toLogin();
    });
  }

  return { init, user, token, signIn, signUp, resend, toLogin, watch, signOut: () => leave(""), expired: () => leave("expired") };
})();
