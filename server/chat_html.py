"""Chat HTML assembler.

Split from the original embedded monolith into CSS, body-template, and JS modules
without changing served output.
"""

from chat_css import CHAT_CSS
from chat_js import CHAT_JS
from chat_templates import CHAT_BODY_HTML


CHAT_HTML = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ApexChat">
<meta name="theme-color" content="#0F172A">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<title>Apex{{TITLE_SUFFIX}}</title>
<style>
"""
    + CHAT_CSS
    + """
</style>
</head>
<body>
"""
    + CHAT_BODY_HTML
    + """
<script nonce="{{CSP_NONCE}}">
"""
    + CHAT_JS
    + """
</script>
</body>
</html>"""
)
