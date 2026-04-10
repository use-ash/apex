"""Apex Dashboard HTML assembler.

Split from the original embedded monolith into CSS, body-template, and JS modules
without changing served output.
"""

from dashboard_css import DASHBOARD_CSS
from dashboard_js import DASHBOARD_JS
from dashboard_templates import DASHBOARD_BODY_HTML


DASHBOARD_HTML = (
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0F172A">
<title>Apex Dashboard</title>
<style>
"""
    + DASHBOARD_CSS
    + """
</style>
</head>
"""
    + DASHBOARD_BODY_HTML
    + """

<script nonce="{{CSP_NONCE}}">
"""
    + DASHBOARD_JS
    + """</script>
</body>
</html>"""
)
