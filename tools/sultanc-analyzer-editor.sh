#!/bin/sh
# Starts sultanc-analyzer for any editor (Neovim, Helix, Emacs, Sublime Text, ...).
# The compiler finds the standard library as library/ relative to its working
# directory, so the server must run from the SultanC home.
#
#   SULTANC_HOME   a SultanC checkout or an unpacked release bundle
#                  (contains library/ and build/sultanc-analyzer)
#   SULTANC_ANALYZER    optional path to the server, default $SULTANC_HOME/build/sultanc-analyzer
set -eu
home=${SULTANC_HOME:?set SULTANC_HOME to your SultanC checkout or release bundle}
server=${SULTANC_ANALYZER:-$home/build/sultanc-analyzer}
[ -x "$server" ] || { echo "sultanc-analyzer not found at $server (run tools/build.sh)" >&2; exit 1; }
cd "$home"
exec "$server" "$@"
