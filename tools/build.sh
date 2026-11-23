#!/bin/sh
# Build sultanc-analyzer.
#
#   tools/build.sh                   the compiler git dependency of Supax.toml,
#                                    fetched into build/deps/sultanc
#                                    -> build/deps/sultanc/build/sultanc-analyzer
#   tools/build.sh /path/to/sultanc  a local compiler checkout
#                                    -> /path/to/sultanc/build/sultanc-analyzer
#
# The server is written into the checkout's build/ so it runs next to the
# library/ it was built against (start it with that checkout as its working
# directory). Where the checkout and the compiler come from:
# tools/compiler-source.sh.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
. "$here/tools/compiler-source.sh"
check_layout
checkout=$(compiler_checkout "${1:-}")
compiler=$(compiler_executable "$checkout")
stage=$(stage_sources "$checkout")
# A copy left by an earlier version of this script.
[ -f "$checkout/sultanc_analyzer/main.sn" ] && [ -d "$checkout/sultanc_analyzer/protocol" ] && rm -rf "$checkout/sultanc_analyzer"
echo "compiler: $compiler" >&2
cd "$stage"
"$compiler" check sultanc_analyzer/main.sn
"$compiler" sultanc_analyzer/main.sn -o "$checkout/build/sultanc-analyzer"
echo "built $checkout/build/sultanc-analyzer"
