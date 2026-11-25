"""Security headers for the pages we serve.

The main one is the Content-Security-Policy. It tells the browser what a page may load and run. Our pages use only their own files,
so a script that sneaked in from anywhere else (an answer, a web page, a chat title) cannot run, and nothing can be sent to another
site. The exceptions are the two things the pages really need: Google Fonts, and the Supabase project the sign-in talks to.
"""
import re
from urllib.parse import urlsplit

HOST = re.compile(r"[A-Za-z0-9.-]+(:\d+)?")  # a plain host name or address with an optional port, nothing that could add a rule


def supabase_origin(url: str) -> str:
    """https://abc.supabase.co/ -> https://abc.supabase.co. Empty when there is no usable address, and then only our own server is allowed."""
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme in ("http", "https") and HOST.fullmatch(parts.netloc) else ""


def page_headers(supabase_url: str) -> dict[str, str]:
    policy = "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",  # our own files only: no inline scripts, no eval
            "style-src 'self' https://fonts.googleapis.com",
            "style-src-attr 'unsafe-inline'",  # a few style="..." attributes in the landing, Vault and Settings pages. A <style> block is still refused
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",  # data: is the landing page's paper and felt textures
            f"connect-src 'self' {supabase_origin(supabase_url)}".strip(),  # our server, and Supabase for the sign-in
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",  # no other site can show our pages in a frame (clickjacking)
        ]
    )
    return {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",  # the older way to say what frame-ancestors says
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
