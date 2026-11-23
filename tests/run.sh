#!/bin/sh
# Runs the end-to-end tests of sultanc-analyzer.
#
#   tests/run.sh                                   the server tools/build.sh built
#                                                  from the compiler's git dependency
#   tests/run.sh /path/to/sultanc [path/to/server]  a local checkout (the server
#                                                  defaults to its build/sultanc-analyzer)
#
# The server runs with the checkout as its working directory. The checks
# compare against the compiler (`sultanc fmt`, `sultanc test`) found as
# tools/build.sh finds it. Set SUPAX to a Supax executable to include the
# Supax package tests.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if [ "$#" -eq 0 ]; then
    set -- "$here/../build/deps/sultanc"
fi
exec python3 "$here/integration/lsp_integration.py" "$@"
