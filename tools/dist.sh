#!/bin/sh
# Build release bundles of sultanc-analyzer: one per target, each a toolchain
# directory laid out like a SultanC checkout, so the server finds its
# standard library the way it does in a checkout:
#
#   sultanc-analyzer-<version>-<target>/
#     build/sultanc-analyzer[.exe]     the server, built for <target>
#     build/sultanc[.exe]         the compiler, when one is given for <target>
#     library/                    the standard library the server was built against
#     LICENSE  README.md  BUNDLE.txt
#
# usage:
#   tools/dist.sh [--checkout /path/to/sultanc] [TARGET...]
#
# The checkout is the compiler revision Supax.toml pins (fetched into
# build/deps/sultanc), or the one given with --checkout; the compiler that
# builds the bundles is found as tools/compiler-source.sh describes.
#
# TARGET is a compiler target (`sultanc targets`); the default is every target
# the VS Code extension is packaged for. The compiler cross-builds and links
# each one itself. A compiler for a target is added when
# $SULTANC_COMPILER_<TARGET> names it, with `-` written `_`
# (SULTANC_COMPILER_arm64_darwin=/path/to/sultanc); without one, the extension
# uses the compiler the user installed (sultanc.compiler.path, $SULTANC,
# ~/.supax/bin/sultanc, PATH).
#
# Output: dist/sultanc-analyzer-<version>-<target>.tar.gz and dist/SHA256SUMS.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
. "$here/tools/compiler-source.sh"
check_layout
given=
if [ "${1:-}" = "--checkout" ]; then
    given=${2:?--checkout needs a directory}
    shift 2
fi
compiler_root=$(compiler_checkout "$given")
compiler=$(compiler_executable "$compiler_root")
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$here/Supax.toml" | head -n 1)
[ -n "$version" ] || { echo "no version in Supax.toml" >&2; exit 1; }
targets=${*:-"x86_64-linux aarch64-linux-gnu x86_64-darwin arm64-darwin x86_64-windows-msvc aarch64-windows-msvc"}
src=$(stage_sources "$compiler_root")

dist="$here/dist"
mkdir -p "$dist"
for target in $targets; do
    case "$target" in
        *-windows-*) exe=.exe ;;
        *) exe= ;;
    esac
    name="sultanc-analyzer-$version-$target"
    out="$dist/$name"
    rm -rf "$out" "$out.tar.gz"
    mkdir -p "$out/build"
    echo "== $target"
    (cd "$src" && "$compiler" check --target "$target" sultanc_analyzer/main.sn)
    (cd "$src" && "$compiler" --target "$target" sultanc_analyzer/main.sn -o "$out/build/sultanc-analyzer$exe")
    variable=SULTANC_COMPILER_$(printf '%s' "$target" | tr -- '-' '_')
    bundled_compiler=$(eval "printf '%s' \"\${$variable:-}\"")
    if [ -n "$bundled_compiler" ]; then
        cp "$bundled_compiler" "$out/build/sultanc$exe"
    fi
    cp -R "$compiler_root/library" "$out/library"
    cp "$here/LICENSE" "$here/README.md" "$out/"
    {
        echo "sultanc-analyzer $version"
        echo "target: $target"
        echo "built with: $("$compiler" --version 2>/dev/null | head -n 1)"
        echo "compiler sources: $(git -C "$compiler_root" rev-parse HEAD 2>/dev/null || echo "$compiler_root")"
        if [ -n "$bundled_compiler" ]; then echo "compiler: bundled"; else echo "compiler: not bundled"; fi
        echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$out/BUNDLE.txt"
    (cd "$dist" && tar -czf "$name.tar.gz" "$name")
    rm -rf "$out"
    echo "   $dist/$name.tar.gz"
done
(cd "$dist" && sha256sum sultanc-analyzer-"$version"-*.tar.gz > SHA256SUMS 2>/dev/null || shasum -a 256 sultanc-analyzer-"$version"-*.tar.gz > SHA256SUMS)
echo "checksums: $dist/SHA256SUMS"
