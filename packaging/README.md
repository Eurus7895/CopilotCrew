# Packaging Crew as a desktop app

Crew's desktop GUI is a FastAPI + PyWebView app bundled with PyInstaller.
The same spec file (`packaging/crew_gui.spec`) builds:

- `dist/Crew.app` — macOS (signable `.app` bundle)
- `dist/Crew/Crew.exe` — Windows
- `dist/Crew/Crew` — Linux

## Build locally

From the repo root:

```bash
pip install -e '.[gui,package]'
python packaging/build.py
```

Output lands in `dist/`. Double-click the artefact to launch. On Linux,
you can wrap the folder in an AppImage with `appimagetool` as a separate
post-step.

## Icons

Drop platform-specific artwork into `packaging/` before the first
release:

- `packaging/Crew.icns` — macOS icon (512×512 `.icns`)
- `packaging/Crew.ico`  — Windows icon (`.ico` with multiple sizes)

The spec picks them up automatically when present. Without them,
PyInstaller falls back to its default icon.

## Code signing

Unsigned bundles trigger "unidentified developer" dialogs on macOS and
Windows SmartScreen warnings. Both are cheap to solve once you have the
certificates:

**macOS** — set `codesign_identity` in `packaging/crew_gui.spec` to
your Developer ID Application certificate, e.g.
`"Developer ID Application: Your Name (TEAMID)"`. After the build:

```bash
codesign --deep --force --options=runtime \
  --entitlements packaging/entitlements.plist \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  dist/Crew.app
xcrun notarytool submit dist/Crew.app.zip --keychain-profile "AC_PASSWORD" --wait
xcrun stapler staple dist/Crew.app
```

**Windows** — sign the resulting `.exe` with
`signtool sign /tr http://timestamp.sectigo.com /fd sha256 /a dist/Crew/Crew.exe`
using your EV Code Signing certificate.

**Linux** — no signing required; just ship the folder or an AppImage.

## Cross-platform CI

Build runners don't cross-compile — each OS builds its own artefact.
Suggested GitHub Actions matrix (not shipped in this repo yet):

```yaml
strategy:
  matrix:
    os: [macos-latest, windows-latest, ubuntu-latest]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: "3.11" }
  - run: pip install -e '.[gui,package]'
  - run: python packaging/build.py
  - uses: actions/upload-artifact@v4
    with:
      name: Crew-${{ matrix.os }}
      path: dist/
```

Sign inside the job using certs stored as encrypted GitHub secrets, then
attach the resulting artefacts to a release.

## What gets bundled

The spec hauls in:

- The frozen Python runtime + `crew` package.
- `crew/gui/templates/`, `crew/gui/static/`, `crew/gui/fixtures/` — the
  three design-language bundles + seed JSONL.
- `uvicorn`, `starlette`, `sse_starlette`, `fastapi`, `jinja2`, `anyio`,
  `pywebview` + its platform-specific runtime assets.

The Copilot SDK is **not** required by the bundled GUI — the window is a
viewer plus a launcher; the standup pipeline imports the SDK lazily only
when "Regenerate" is clicked. A desktop user who wants live pipeline
runs still needs a local Crew installation with the SDK configured; the
bundled app can talk to it via `~/.crew/` on the same machine.
