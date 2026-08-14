#!/bin/sh
set -eu

: "${GEOCOMPONENTS_API_URL:?GEOCOMPONENTS_API_URL must be set}"
: "${GCIMPORT_API_URL:?GCIMPORT_API_URL must be set}"

envsubst '$GEOCOMPONENTS_API_URL $GCIMPORT_API_URL' \
  < /opt/gcmapview/runtime-config.js.template \
  > /usr/share/nginx/html/runtime-config.js