#!/bin/bash
# send_alert.sh — Send alert to Apex
# Usage: send_alert.sh -s source -l severity -t title [-b body]
#        echo "body" | send_alert.sh -s source -t title

SERVER="${APEX_SERVER:-${LOCALCHAT_SERVER:-https://10.8.0.2:8300}}"
TOKEN="${APEX_ALERT_TOKEN:-$LOCALCHAT_ALERT_TOKEN}"

while getopts "s:l:t:b:" opt; do
    case $opt in
        s) SOURCE="$OPTARG";;
        l) SEVERITY="$OPTARG";;
        t) TITLE="$OPTARG";;
        b) BODY="$OPTARG";;
    esac
done

if [ -z "$BODY" ] && [ ! -t 0 ]; then
    BODY=$(cat)
fi

if [ -z "$TOKEN" ]; then
    echo "Error: APEX_ALERT_TOKEN not set" >&2
    exit 1
fi

if [ -z "$TITLE" ]; then
    echo "Error: -t title required" >&2
    exit 1
fi

curl -sk -X POST "$SERVER/api/alerts" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(printf '{"source":"%s","severity":"%s","title":"%s","body":"%s"}' \
        "$SOURCE" "${SEVERITY:-info}" "$TITLE" "$BODY")"
