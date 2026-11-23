# Releasing

A release is a set of per-platform bundles of the server, published on the [releases page](https://github.com/sultan-language/sultanc-analyzer/releases), and the VS Code extension's platform-specific packages built from them.

## Supported platforms

| Compiler target | VS Code target | Executable |
|---|---|---|
| `x86_64-linux` | `linux-x64` | `sultanc-analyzer` |
| `aarch64-linux-gnu` | `linux-arm64` | `sultanc-analyzer` |
| `x86_64-darwin` | `darwin-x64` | `sultanc-analyzer` |
| `arm64-darwin` | `darwin-arm64` | `sultanc-analyzer` |
| `x86_64-windows-msvc` | `win32-x64` | `sultanc-analyzer.exe` |
| `aarch64-windows-msvc` | `win32-arm64` | `sultanc-analyzer.exe` |

The SultanC compiler builds and links every target itself (`sultanc targets` lists them), so all bundles are built on one machine.

## 1. Prepare

1. Choose the compiler sources the release is built against: `branch = "main"` in `Supax.toml`, or a `tag` of the compiler release it goes with. Have a compiler that builds those sources (`$SULTANC`, `~/.supax/bin/sultanc` or `PATH`).
2. Set the version in `Supax.toml` and in `serverInfo` (`src/protocol/encode.sn`).
3. Add the version to `CHANGELOG.md`.
4. Build and test on the host:

   ```sh
   tools/build.sh
   SUPAX=/path/to/supax tests/run.sh
   ```

## 2. Build the bundles

```sh
tools/dist.sh                                   # every target above
tools/dist.sh arm64-darwin                      # one target
tools/dist.sh --checkout /path/to/sultanc       # a local checkout instead
```

Each target is checked (`sultanc check --target`), built, and packed as `dist/sultanc-analyzer-<version>-<target>.tar.gz`:

```
sultanc-analyzer-<version>-<target>/
  build/sultanc-analyzer[.exe]
  build/sultanc[.exe]     only when SULTANC_COMPILER_<target> names a compiler for that target
  library/                the standard library of the checkout
  LICENSE  README.md  BUNDLE.txt
```

`BUNDLE.txt` records the version, target, building compiler, compiler source revision and date. `dist/SHA256SUMS` lists the checksums.

To include the compiler, point `SULTANC_COMPILER_<target>` (with `-` written `_`) at a compiler built for that target, for example `SULTANC_COMPILER_arm64_darwin=/path/to/sultanc`. Without one, editors use the compiler the user installed.

## 3. Package the VS Code extension

In `sultanc-language-support/editors/vscode`:

```sh
npm ci
npm run package:platforms -- /path/to/sultanc-analyzer/dist
```

This writes `dist/sultanc-<version>-<vscode target>.vsix` for each platform, with the bundle unpacked in the package's `sultanc/` folder, plus a universal `dist/sultanc-<version>.vsix` without a server, and `dist/SHA256SUMS`. The extension finds the bundled server after a configured `sultanc.server.path`, a server in the open SultanC checkout and `$SULTANC_HOME`; the bundled server always runs against its own `library/`.

Check a bundle in VS Code before publishing:

```sh
SULTANC_BUNDLE=/path/to/sultanc-analyzer/dist/sultanc-analyzer-<version>-x86_64-linux.tar.gz \
SULTANC=/path/to/sultanc/build/sultanc npm run test:integration
```

## 4. Publish

1. Tag the commit: `git tag v<version>`.
2. Push the tag and create a GitHub release for it with the six bundles and `SHA256SUMS`.
3. Publish the extension packages, all with the same version:

   ```sh
   npx @vscode/vsce publish --packagePath dist/sultanc-<version>-*.vsix dist/sultanc-<version>.vsix
   ```

   For Open VSX: `npx ovsx publish --packagePath <file>` for each package.
