# Windows Installer Build Guide

This guide explains how to create and distribute a normal Windows installer for GMonster and WUM.

The produced installer is named like this:

```text
GMonster-2.2.1-Setup.exe
```

It installs both applications:

```text
GMonster.exe
WUM.exe
```

## Current setup

- The application source to package is on the `installer` branch.
- The GitHub Actions workflow used to build installers lives on `main` so GitHub can run it manually.
- Running the workflow does **not** merge `installer` into `main`.
- The workflow checks out the branch specified by `source_ref`, builds it on a Windows GitHub runner, smoke-tests both EXEs, and uploads the setup file as an artifact.

The workflow is named **Build Installer From Branch** in the GitHub Actions tab.

## Build a new installer

### 1. Push the branch you want to package

Usually this is the `installer` branch:

```bash
git switch installer
git push origin installer
```

Make sure the branch contains the exact code you want customers to receive.

### 2. Keep the application version in sync

Before creating a new public version, update the internal GMonster version in `var.py` if needed:

```python
version = '2.2.1'
```

Commit and push that change to `installer`.

Use the same numeric version in the workflow input. For example, use `2.2.1` in both places. This keeps the in-app version and installer filename consistent.

### 3. Open the installer workflow

In GitHub, open:

```text
moeezmujahid70/Gmonster-App → Actions → Build Installer From Branch
```

Click **Run workflow** and use these inputs:

| Input | Normal value | Purpose |
| --- | --- | --- |
| `source_ref` | `installer` | GMonster branch, tag, or full commit SHA to package. |
| `release_version` | `2.2.1` | Version in the installer filename and Windows installer metadata. |
| `wum_ref` | Leave default unless WUM changed | WUM source revision to compile and include. |
| `console_build` | `false` | Keeps GMonster as a normal windowed desktop app. Set to `true` only for build diagnostics. |

Click **Run workflow**.

### 4. Wait for all three jobs

A successful build has these jobs:

1. `build-wum` — builds `WUM.exe`.
2. `build-gmonster` — builds `GMonster.exe` from `source_ref`.
3. `package-installer` — smoke-tests both EXEs, installs Inno Setup, and creates the setup file.

The final job is important. It confirms that both EXEs can start from the command line before the installer is created.

### 5. Download the installer

After the run succeeds, open its **Artifacts** section and download:

```text
GMonster-2.2.1-Setup
```

GitHub downloads artifacts as a ZIP file. Extract it, then distribute the contained file:

```text
GMonster-2.2.1-Setup.exe
```

Do not distribute the separate `gmonster-exe` or `wum-exe` artifacts. They are intermediate build outputs; customers should receive the combined setup EXE.

## Updating WUM

When WUM changes:

1. Push the desired WUM code to `moeezmujahid70/WUM-App` first.
2. Run WUM's Windows workflow and confirm it succeeds.
3. In the GMonster installer workflow, set `wum_ref` to either:
   - a pushed WUM branch such as `develop`, or
   - the full 40-character WUM commit SHA.

For repeatable public builds, prefer the full commit SHA. Do not use a shortened SHA such as `227101e`; GitHub Actions can interpret it as a branch name when checking out another repository.

The current known-good WUM source revision is:

```text
227101e8aedddf8dad2dcff51d8df4fd01d3f48b
```

## Where installed data is stored

The installer deliberately does not include your local `data/` folder. That folder can contain account settings, contacts, logs, spreadsheets, and credentials.

On a customer's Windows machine, first launch creates writable application data at:

```text
%LOCALAPPDATA%\GMonster\data
```

Both installed apps use that same location:

```text
%LOCALAPPDATA%\GMonster\data\gmonster_config
%LOCALAPPDATA%\GMonster\data\wum_config
%LOCALAPPDATA%\GMonster\data\sheets
%LOCALAPPDATA%\GMonster\data\logs
```

Safe packaged defaults, including the configuration template and certificate, are copied there only when missing. Existing customer settings and sheets are preserved during upgrades.

For local Mac development, nothing changes: running `python3 var.py` still uses the repository's local `data/` folder.

## Installation and upgrades

The setup EXE installs both applications into the selected program folder and creates the GMonster shortcut.

For an upgrade, a customer runs the newer setup EXE. Their data under `%LOCALAPPDATA%\GMonster\data` remains separate from the installed EXEs, so it is preserved.

The uninstaller asks before removing user data. Do not select data removal unless the customer explicitly wants to erase their local GMonster settings, sheets, logs, and WUM settings.

## Troubleshooting a failed build

Open the failed workflow run and check the failed job:

- `build-wum` failure: verify `wum_ref` exists in the public WUM repository and that the WUM workflow succeeds independently.
- `build-gmonster` failure: inspect the PyInstaller output for the selected `source_ref`.
- `package-installer` failure: inspect the smoke-test or Inno Setup step.

If a GMonster smoke test fails without a useful error message, rerun **Build Installer From Branch** with:

```text
console_build: true
```

This creates a one-off console build so Python/PyInstaller startup diagnostics appear in the Actions log. Do not use that diagnostic build as the customer release; rerun with `console_build: false` after fixing the error.

## First successful installer

The first combined installer was built from:

```text
GMonster source: installer branch
Installer version: 2.2.0
WUM source: 227101e8aedddf8dad2dcff51d8df4fd01d3f48b
```

Its Actions artifact is named `GMonster-2.2.0-Setup`.
