# Shared by tools/build.sh and tools/dist.sh (sourced, POSIX sh).
#
# The server links the compiler's frontend, so it is built against a SultanC
# compiler checkout: its `compiler/` (the frontend) and `library/` (the
# standard library the server ships with). The checkout is
#
#   - the one given on the command line, or
#   - the `compiler` git dependency of Supax.toml
#     (`compiler = { git = …, branch = "main" }`), fetched into
#     build/deps/sultanc.
#
# The compiler that builds the server is the first of: <checkout>/build/sultanc,
# $SULTANC, ~/.supax/bin/sultanc (Supax's installer), `sultanc` on PATH. It
# must be able to compile that checkout's sources: the same revision, or one
# close to it.

# The `git` and `rev` of the `compiler` dependency in Supax.toml.
pinned_compiler_field() {
    sed -n 's/^compiler *= *{.*'"$1"' *= *"\([^"]*\)".*}$/\1/p' "$here/Supax.toml" | head -n 1
}

# Prints the checkout directory: $1 when given, else the `compiler` git
# dependency of Supax.toml (its `rev`, `tag` or `branch`), fetched into
# build/deps/sultanc. A branch is fetched again when its head moved; offline,
# the last fetched commit is used.
compiler_checkout() {
    if [ -n "${1:-}" ]; then
        (cd "$1" && pwd)
        return
    fi
    url=$(pinned_compiler_field git)
    rev=$(pinned_compiler_field rev)
    ref=$(pinned_compiler_field tag)
    [ -n "$ref" ] || ref=$(pinned_compiler_field branch)
    [ -n "$url" ] && { [ -n "$rev" ] || [ -n "$ref" ]; } || {
        echo "Supax.toml: no compiler = { git = \"…\", branch|tag|rev = \"…\" } dependency" >&2
        exit 1
    }
    dir="$here/build/deps/sultanc"
    have=$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)
    if [ -z "$rev" ]; then
        rev=$(git ls-remote "$url" "refs/tags/$ref^{}" "refs/tags/$ref" "refs/heads/$ref" 2>/dev/null | head -n 1 | cut -f 1)
        if [ -z "$rev" ]; then
            [ -n "$have" ] || { echo "cannot reach $url for $ref" >&2; exit 1; }
            echo "cannot reach $url; using the fetched $have" >&2
            rev=$have
        fi
    fi
    if [ "$have" != "$rev" ]; then
        echo "fetching $url at $rev into build/deps/sultanc" >&2
        rm -rf "$dir"
        mkdir -p "$dir"
        git -C "$dir" init -q
        git -C "$dir" fetch -q --depth 1 "$url" "$rev"
        git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
    fi
    [ -f "$dir/compiler/Supax.toml" ] && [ -d "$dir/library/std" ] || {
        echo "$url at $rev has no compiler/Supax.toml or library/std" >&2
        exit 1
    }
    echo "compiler sources: $url $rev" >&2
    printf '%s\n' "$dir"
}

# Prints the compiler for the checkout $1.
compiler_executable() {
    for candidate in "$1/build/sultanc" "${SULTANC:-}" "$HOME/.supax/bin/sultanc"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    if command -v sultanc >/dev/null 2>&1; then
        command -v sultanc
        return
    fi
    echo "no SultanC compiler: build $1 (./build.sh), set SULTANC, or install it with Supax" >&2
    exit 1
}

# Stops when files of the old sultanc-lsp layout are still here (copied over by
# unpacking a new version onto an old folder): main.sn and the module folders
# moved into src/, so the old copies import `sultanc_lsp.…`, which no longer
# exists.
check_layout() {
    stale=
    for old in main.sn analysis protocol server transport workspace tests/lsp_integration.py tests/fixtures \
            tools/sultanc-lsp-editor.sh tools/update-compiler.sh tools/sultanc-analyzer-editor.sh; do
        [ -e "$here/$old" ] && stale="$stale $old"
    done
    if [ -n "$stale" ]; then
        echo "files from the old sultanc-lsp layout (sources are in src/ now):$stale" >&2
        echo "remove them: (cd $here && rm -rf$stale)" >&2
        exit 1
    fi
}

# Assembles the module tree in $1/build/sultanc-analyzer-src: src/ as sultanc_analyzer/,
# with the checkout's compiler/ and library/ linked. Prints its path.
stage_sources() {
    stage="$1/build/sultanc-analyzer-src"
    rm -rf "$stage"
    mkdir -p "$stage/sultanc_analyzer"
    cp -R "$here/src/." "$stage/sultanc_analyzer/"
    ln -s ../../compiler "$stage/compiler"
    ln -s ../../library "$stage/library"
    printf '%s\n' "$stage"
}
