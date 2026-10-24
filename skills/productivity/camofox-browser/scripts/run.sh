#!/bin/bash
# Launched by launchd (com.laansdole.camofox). Mode: ~/.camofox/mode (off|desktop).
set -a; source "$HOME/.camofox/env"; set +a
export CAMOFOX_PORT=9377 CAMOFOX_INTERACTIVE="$(cat "$HOME/.camofox/mode" 2>/dev/null || echo off)"
cd "$HOME/Projects/camofox-browser"
exec "$HOME/.hermes/node/bin/node" server.js
