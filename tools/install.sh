#!/bin/sh
# Install sultanc-analyzer into the SultanC toolchain, next to the compiler it
# matches, as rust-analyzer is installed next to rustc:
#
#   ~/.supax/bin/sultanc              the compiler (Supax's tools/install.sh)
#   ~/.supax/bin/sultanc-analyzer     this server
#   ~/.supax/lib/sultanc/library      the standard library both use
#
# usage:
#   tools/install.sh                  build against the compiler sources named
#                                     in Supax.toml, then install
#   tools/install.sh /path/to/sultanc build against that checkout (the one the
#                                     installed compiler was built from)
#
# Set SUPAX_HOME to install elsewhere. Editors find the server there: the VS
# Code extension looks in $SUPAX_HOME/bin (default ~/.supax/bin), other
# editors start `sultanc-analyzer` from PATH.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
. "$here/tools/compiler-source.sh"
check_layout
prefix=${SUPAX_HOME:-$HOME/.supax}
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) exe=.exe ;;
    *) exe= ;;
esac

checkout=$(compiler_checkout "${1:-}")
"$here/tools/build.sh" "$checkout"
built="$checkout/build/sultanc-analyzer"

# The server analyses with the standard library next to it, which must be the
# one it was built against: the installed library when the compiler is
# installed, else this checkout's.
installed_library="$prefix/lib/sultanc/library"
if [ -d "$installed_library/std" ]; then
    if ! diff -rq "$checkout/library" "$installed_library" >/dev/null 2>&1; then
        echo "warning: $installed_library differs from $checkout/library, which the server was built against." >&2
        echo "         Install the compiler from the same checkout (Supax's tools/install.sh $checkout), or pass that checkout here." >&2
    fi
else
    echo "no SultanC standard library in $installed_library: installing $checkout/library there" >&2
    mkdir -p "$prefix/lib/sultanc"
    rm -rf "$installed_library.tmp.$$"
    cp -R "$checkout/library" "$installed_library.tmp.$$"
    mv "$installed_library.tmp.$$" "$installed_library"
fi

mkdir -p "$prefix/bin"
target="$prefix/bin/sultanc-analyzer$exe"
cp "$built" "$target.tmp.$$"
chmod 755 "$target.tmp.$$"
mv "$target.tmp.$$" "$target"
echo "installed $target"
case ":${PATH:-}:" in
    *":$prefix/bin:"*) ;;
    *) echo "add $prefix/bin to PATH for editors other than VS Code (Supax's installer does)" ;;
esac
