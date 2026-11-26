# Releasing

sultanc-analyzer ships as part of the SultanC toolchain, next to the compiler it was built with, as rust-analyzer ships with Rust. A release is a set of per-platform archives laid out as the toolchain prefix (`~/.supax`), published on the [releases page](https://github.com/sultan-language/sultanc-analyzer/releases) and unpacked by a toolchain installer. The VS Code extension does not carry the server: it finds the installed one.

## Supported platforms

| Compiler target | Executable |
|---|---|
| `x86_64-linux` | `bin/sultanc-analyzer` |
| `aarch64-linux-gnu` | `bin/sultanc-analyzer` |
| `x86_64-darwin` | `bin/sultanc-analyzer` |
| `arm64-darwin` | `bin/sultanc-analyzer` |
| `x86_64-windows-msvc` | `bin/sultanc-analyzer.exe` |
| `aarch64-windows-msvc` | `bin/sultanc-analyzer.exe` |

The SultanC compiler builds and links every target itself (`sultanc targets` lists them), so all archives are built on one machine.

## 1. Prepare

1. Choose the compiler sources the release is built against: `branch = "main"` in `Supax.toml`, or a `tag` of the compiler release it goes with. Have a compiler that builds those sources (`$SULTANC`, `~/.supax/bin/sultanc` or `PATH`).
2. Set the version in `Supax.toml` and in `serverInfo` (`src/protocol/encode.sn`).
3. Add the version to `CHANGELOG.md`.
4. Build and test on the host:

   ```sh
   tools/build.sh
   SUPAX=/path/to/supax tests/run.sh
   ```

## 2. Build the archives

```sh
tools/dist.sh                                   # every target above
tools/dist.sh arm64-darwin                      # one target
tools/dist.sh --checkout /path/to/sultanc       # a local checkout instead
```

Each target is checked (`sultanc check --target`), built, and packed as `dist/sultanc-analyzer-<version>-<target>.tar.gz`:

```
sultanc-analyzer-<version>-<target>/
  bin/sultanc-analyzer[.exe]
  bin/sultanc[.exe]                 only when SULTANC_COMPILER_<target> names a compiler for that target
  lib/sultanc/library/              the standard library of the checkout
  share/sultanc-analyzer/           LICENSE, README.md, BUNDLE.txt
```

`BUNDLE.txt` records the version, target, building compiler, compiler source revision and date. `dist/SHA256SUMS` lists the checksums. Installing one:

```sh
tar -xzf sultanc-analyzer-<version>-<target>.tar.gz --strip-components=1 -C ~/.supax
```

To include the compiler, point `SULTANC_COMPILER_<target>` (with `-` written `_`) at a compiler built for that target, for example `SULTANC_COMPILER_arm64_darwin=/path/to/sultanc`: the archive is then a whole toolchain.

## 3. Publish

1. Tag the commit: `git tag v<version>`.
2. Push the tag and create a GitHub release for it with the archives and `SHA256SUMS`.
