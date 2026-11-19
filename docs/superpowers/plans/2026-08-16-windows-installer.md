
# Window Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a single signed `GMonster-<version>-Setup.exe` that installs GMonster, WUM, required bundled tools, and per-user runtime data like a normal Windows desktop application.

**Architecture:** Keep immutable `GMonster.exe`, `WUM.exe`, and bundled assets under `{autopf}\GMonster`; both applications use `%LOCALAPPDATA%\GMonster\data` when frozen on Windows, with separate `gmonster_config`, `wum_config`, and log subdirectories beneath that shared root. Unfrozen development runs keep using each repository's existing `data/` directory. GMonster's release workflow checks out and builds the public WUM repository at a pinned ref, then Inno Setup packages both fresh EXEs into one installer.

**Tech Stack:** Python 3.10, PyInstaller, Inno Setup 6, GitHub Actions Windows runner, optional Authenticode code signing.

## Global Constraints

- Build Windows executables on Windows; do not cross-compile the release artifact from macOS or Linux.
- Never package or overwrite a developer's `data/` directory, credentials, SQLite databases, campaign files, logs, or API keys.
- A frozen Windows build must use `%LOCALAPPDATA%\GMonster\data`; an unfrozen development run continues to use the repository `data/` directory.
- Existing ZIP-install users must have a one-time, non-destructive migration path from `<old-app-folder>\data`.
- Package both `GMonster.exe` and `WUM.exe`; the release workflow must check out the public `moeezmujahid70/WUM-App` repository at an explicit commit SHA or tag and build WUM from source.
- Do not use expiring GitHub Actions artifacts from earlier WUM workflow runs as installer inputs.
- Every Windows release workflow must run `GMonster.exe --smoke-test` and `WUM.exe --smoke-test` before packaging; each command must initialize paths without opening a GUI or making network requests and exit with status `0`.
- Updates must use a new installer release instead of overwriting binaries from the current ZIP updater inside `Program Files`.
- The installer must preserve `%LOCALAPPDATA%\GMonster\data` by default during uninstall and offer an explicit opt-in removal choice.

---

## File Structure

- Create: `runtime_paths.py` — deterministic application/resource/runtime-data path resolution and first-run migration helpers.
- Create: `tests/test_runtime_paths.py` — standard-library tests for frozen Windows, development, initial seeding, and non-destructive migration behavior.
- Modify: `var.py` — replace current-working-directory runtime storage with `runtime_paths`, and expose stable paths to the existing application.
- Modify: `logger.py`, `main.py`, `update_checker.py`, `progressbar.py` — consume application/runtime paths rather than `os.getcwd()` for data, WUM, and update locations.
- Modify: `WUM-App/var.py` and create `WUM-App/tests/test_runtime_paths.py` — make WUM use the same frozen-Windows data root while retaining its repository `data/` directory during development.
- Modify: `GMonster.spec` — bundle only immutable defaults and application assets; do not include user runtime data.
- Create: `packaging/default-data/config.json` — safe first-run configuration copied from `config.example.json`, with no credentials.
- Create: `scripts/stage_windows_release.ps1` — stages GMonster, a freshly built WUM EXE supplied by the workflow, defaults, and bundled tools for Inno Setup.
- Create: `installer/GMonster.iss` — Inno Setup definition for install, shortcuts, upgrade, uninstall, and optional launch.
- Create: `.github/workflows/release-windows-installer.yml` — tag/manual Windows release workflow that produces the setup EXE.
- Modify: `README.md` — developer build and installer release instructions.

### Task 1: Make runtime and application paths explicit

**Files:**

- Create: `runtime_paths.py`
- Create: `tests/test_runtime_paths.py`
- Modify: `var.py:22-145`
- Modify: `logger.py:1-20`

**Interfaces:**

- Consumes: `sys.frozen`, `sys.executable`, `sys._MEIPASS`, `LOCALAPPDATA`, and an injectable current working directory.
- Produces: `RuntimePaths(app_dir: Path, resource_dir: Path, data_dir: Path, is_frozen_windows: bool)` and `resolve_runtime_paths(...) -> RuntimePaths`.

- [ ] **Step 1: Write failing path-resolution tests**

```python
def test_frozen_windows_uses_local_app_data_for_writable_data(tmp_path):
    paths = resolve_runtime_paths(
        frozen=True,
        platform_name="win32",
        executable=tmp_path / "Program Files" / "GMonster" / "GMonster.exe",
        resource_dir=tmp_path / "resources",
        working_dir=tmp_path / "ignored",
        local_app_data=tmp_path / "Users" / "A" / "AppData" / "Local",
    )

    assert paths.app_dir == tmp_path / "Program Files" / "GMonster"
    assert paths.data_dir == tmp_path / "Users" / "A" / "AppData" / "Local" / "GMonster" / "data"


def test_development_uses_repository_data_directory(tmp_path):
    paths = resolve_runtime_paths(
        frozen=False,
        platform_name="darwin",
        executable=tmp_path / "ignored",
        resource_dir=tmp_path / "ignored",
        working_dir=tmp_path / "repo",
        local_app_data=tmp_path / "ignored",
    )

    assert paths.data_dir == tmp_path / "repo" / "data"
```

- [ ] **Step 2: Run the new tests and confirm they fail because `runtime_paths` does not exist**

Run: `python -m unittest tests.test_runtime_paths -v`

Expected: import failure for `runtime_paths`.

- [ ] **Step 3: Implement only the required path boundary**

```python
@dataclass(frozen=True)
class RuntimePaths:
    app_dir: Path
    resource_dir: Path
    data_dir: Path
    is_frozen_windows: bool


def resolve_runtime_paths(*, frozen, platform_name, executable, resource_dir, working_dir, local_app_data):
    is_frozen_windows = frozen and platform_name == "win32"
    app_dir = Path(executable).resolve().parent if frozen else Path(working_dir).resolve()
    data_dir = (Path(local_app_data) / "GMonster" / "data" if is_frozen_windows else app_dir / "data")
    return RuntimePaths(app_dir, Path(resource_dir), data_dir, is_frozen_windows)
```

Update `var.py` to derive all `DATA_*`, `SCRIPTS_DIR`, `update_temp_path`, and certificate paths from this boundary. Update `logger.py` to write beneath `var.DATA_LOGS_GMONSTER_DIR` rather than a current-working-directory path.

- [ ] **Step 4: Verify the focused tests and import compilation**

Run: `python -m unittest tests.test_runtime_paths -v && python -m py_compile runtime_paths.py var.py logger.py`

Expected: all focused tests pass and all three modules compile.

- [ ] **Step 5: Commit the path boundary**

```bash
git add runtime_paths.py tests/test_runtime_paths.py var.py logger.py
git commit -m "feat: separate installed assets from runtime data"
```

### Task 2: Seed defaults and migrate existing ZIP data without overwriting users

**Files:**

- Modify: `runtime_paths.py`
- Modify: `tests/test_runtime_paths.py`
- Modify: `var.py:104-145`
- Create: `packaging/default-data/config.json`

**Interfaces:**

- Consumes: `RuntimePaths.data_dir`, a bundled `packaging/default-data` directory, and the former `<app_dir>/data` directory.
- Produces: `initialize_runtime_data(paths: RuntimePaths) -> None`, which creates missing folders, seeds missing defaults, and copies legacy files only when their destination does not exist.

- [ ] **Step 1: Write failing initialization and migration tests**

```python
def test_initialize_runtime_data_seeds_config_only_when_missing(tmp_path):
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "config.json").write_text('{"config": {}}', encoding="utf-8")
    destination = tmp_path / "runtime" / "data"

    initialize_runtime_data(destination, defaults, legacy_data_dir=None)
    assert (destination / "gmonster_config" / "config.json").read_text(encoding="utf-8") == '{"config": {}}'

    (destination / "gmonster_config" / "config.json").write_text('{"config": {"user": true}}', encoding="utf-8")
    initialize_runtime_data(destination, defaults, legacy_data_dir=None)
    assert (destination / "gmonster_config" / "config.json").read_text(encoding="utf-8") == '{"config": {"user": true}}'


def test_initialize_runtime_data_copies_missing_legacy_files_without_replacing_newer_data(tmp_path):
    legacy = tmp_path / "legacy" / "data"
    (legacy / "sheets").mkdir(parents=True)
    (legacy / "sheets" / "targets.xlsx").write_bytes(b"legacy")
    destination = tmp_path / "runtime" / "data"
    (destination / "sheets").mkdir(parents=True)
    (destination / "sheets" / "targets.xlsx").write_bytes(b"current")

    initialize_runtime_data(destination, tmp_path / "defaults", legacy)
    assert (destination / "sheets" / "targets.xlsx").read_bytes() == b"current"
```

- [ ] **Step 2: Run the tests and confirm they fail because initialization is missing**

Run: `python -m unittest tests.test_runtime_paths -v`

Expected: import failure for `initialize_runtime_data`.

- [ ] **Step 3: Implement first-run seeding and one-time non-destructive migration**

Create the complete data subdirectory structure already listed in `var.py`. Copy `packaging/default-data/config.json` to `gmonster_config/config.json` only if the destination does not exist. Copy a bundled CA file only if missing. When frozen Windows uses `%LOCALAPPDATA%`, copy files from `<app_dir>/data` only when the matching destination is absent; log file names and counts, never file contents or credentials. Add a marker file under `gmonster_config` after migration so it is not repeated.

Generate `packaging/default-data/config.json` from `config.example.json`; do not copy any repository `data/gmonster_config/config.json`, spreadsheets, databases, logs, or other local files.

- [ ] **Step 4: Verify initialization behavior and code compilation**

Run: `python -m unittest tests.test_runtime_paths -v && python -m py_compile runtime_paths.py var.py`

Expected: all tests pass.

- [ ] **Step 5: Commit safe data initialization**

```bash
git add runtime_paths.py tests/test_runtime_paths.py var.py packaging/default-data/config.json
git commit -m "feat: seed and preserve installed app data"
```

### Task 3: Make both applications share installed data and support terminal smoke tests

**Files:**

- Modify: `main.py:1627-1640`
- Modify: `update_checker.py:10-55`
- Modify: `progressbar.py:30-120`
- Modify: `var.py:139-180`
- Create: `tests/test_installed_paths.py`
- Modify: `/Users/moeezmujahid/Projects/emailSaas/wum/var.py:1-140, 510-530`
- Create: `/Users/moeezmujahid/Projects/emailSaas/wum/tests/test_runtime_paths.py`

**Interfaces:**

- Consumes: `var.APP_DIR`, `var.RESOURCE_DIR`, `var.DATA_DIR`, and `var.UPDATE_TEMP_DIR` established in Tasks 1-2, plus WUM's equivalent frozen-Windows path resolver.
- Produces: WUM launch path `<app_dir>/WUM.exe`, shared frozen Windows data path `%LOCALAPPDATA%\GMonster\data`, update staging path `<data_dir>/updates`, and a `--smoke-test` command in both EXEs.

- [ ] **Step 1: Write failing installed-path tests**

```python
def test_wum_path_is_next_to_the_installed_application(tmp_path):
    assert wum_path(tmp_path / "GMonster") == tmp_path / "GMonster" / "WUM.exe"


def test_update_staging_is_writable_runtime_data(tmp_path):
    assert update_staging_dir(tmp_path / "Local" / "GMonster" / "data") == tmp_path / "Local" / "GMonster" / "data" / "updates"


def test_smoke_test_initializes_paths_without_starting_the_gui(tmp_path):
    result = run_smoke_test(data_dir=tmp_path / "GMonster" / "data")
    assert result == 0
    assert (tmp_path / "GMonster" / "data" / "gmonster_config").is_dir()
```

- [ ] **Step 2: Run the tests and confirm they fail before the helpers are extracted**

Run: `python -m unittest tests.test_installed_paths -v`

Expected: import failure for `wum_path`, `update_staging_dir`, and `run_smoke_test`.

- [ ] **Step 3: Implement the installed-path helpers and retire executable-overwrite updates**

Move `main.launch_wum()` from `os.getcwd()` to `var.APP_DIR`. Put updater downloads below `var.DATA_DIR / "updates"`. Disable the current `scripts/updater.bat` self-replacement workflow for frozen Windows and show a release-installer update prompt instead; it cannot safely replace binaries in `Program Files` without elevation. Keep the existing macOS behavior unchanged.

In the WUM repository, replace the relative `data/...` values in `var.py` with a small resolver matching GMonster's behavior: frozen Windows uses `%LOCALAPPDATA%\GMonster\data`, while `python var.py` continues using WUM's repository `data/` directory. Preserve `gmonster_config`, `wum_config`, `sheets`, and `logs/wum` as subdirectories of the shared root. Add an early `--smoke-test` branch in each app's `var.py`, before UI imports; it must create required directories, verify readable default configuration/certificate resources, print a concise success line where a console is available, and exit `0` without starting Qt, calling APIs, or modifying campaign data.

- [ ] **Step 4: Verify helper tests and changed-module compilation**

Run: `python -m unittest tests.test_installed_paths -v && python -m py_compile main.py update_checker.py progressbar.py var.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit installed executable behavior**

```bash
git add main.py update_checker.py progressbar.py var.py tests/test_installed_paths.py
git commit -m "fix: use installed paths for WUM and updates"

In the WUM repository:

```bash
git add var.py tests/test_runtime_paths.py
git commit -m "fix: share installed GMonster data path"
```

```

### Task 4: Stage deterministic installer inputs from freshly built EXEs

**Files:**
- Modify: `GMonster.spec`
- Create: `scripts/stage_windows_release.ps1`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `requirements-updated.txt`, `GMonster.spec`, `packaging/default-data`, `dist/GMonster.exe`, a freshly built `WUM.exe` passed as `-WumExePath`, `icons`, and `data/tools/google_maps_scraper`.
- Produces: `release/stage/GMonster.exe`, `release/stage/WUM.exe`, `release/stage/default-data/config.json`, and the immutable tools/assets required by the installer.

- [ ] **Step 1: Write a failing PowerShell staging assertion**

```powershell
& .\scripts\stage_windows_release.ps1 -WumExePath .\wum-dist\WUM.exe
if (-not (Test-Path .\release\stage\WUM.exe)) { throw "WUM.exe was not staged" }
if (-not (Test-Path .\release\stage\default-data\config.json)) { throw "Default configuration was not staged" }
```

- [ ] **Step 2: Run it with a missing WUM path and confirm it fails clearly**

Run: `pwsh -File scripts/stage_windows_release.ps1 -WumExePath .\missing\WUM.exe`

Expected: failure `WUM executable was not found at .\missing\WUM.exe`.

- [ ] **Step 3: Implement the deterministic build script**

The script must remove only `release/stage`, copy `config.example.json` to `packaging/default-data/config.json`, copy the CA bundle from the build environment, verify that `dist/GMonster.exe` and the `-WumExePath` argument exist, copy both to `release/stage`, and stage required immutable tools. Add `release/` to `.gitignore`. The workflow, rather than this script, owns the separate PyInstaller builds for GMonster and WUM.

- [ ] **Step 4: Verify staging with a supplied test WUM artifact on a Windows runner**

Run: `pwsh -File scripts/stage_windows_release.ps1 -WumExePath .\wum-dist\WUM.exe`

Expected: `release/stage/GMonster.exe`, `release/stage/WUM.exe`, and `release/stage/default-data/config.json` exist.

- [ ] **Step 5: Commit reproducible release staging**

```bash
git add GMonster.spec scripts/stage_windows_release.ps1 packaging/default-data/config.json .gitignore
git commit -m "build: stage Windows installer inputs"
```

### Task 5: Create the normal Windows installer

**Files:**

- Create: `installer/GMonster.iss`
- Create: `installer/LICENSE.txt` if the repository license needs a displayed installer page
- Create: `tests/test_installer_script.py`

**Interfaces:**

- Consumes: `release/stage` from Task 4.
- Produces: `release/GMonster-<version>-Setup.exe`, installed app files at `{autopf}\GMonster`, a Start Menu shortcut, an optional desktop shortcut, an uninstaller, and preserved `%LOCALAPPDATA%\GMonster\data`.

- [ ] **Step 1: Write failing installer-script contract tests**

```python
def test_installer_packages_both_executables_and_launches_gmonster():
    script = Path("installer/GMonster.iss").read_text(encoding="utf-8")
    assert 'Source: "..\\release\\stage\\GMonster.exe"; DestDir: "{app}"' in script
    assert 'Source: "..\\release\\stage\\WUM.exe"; DestDir: "{app}"' in script
    assert 'Filename: "{app}\\GMonster.exe"; Description: "Launch GMonster"' in script


def test_uninstall_keeps_local_app_data_unless_user_explicitly_selects_removal():
    script = Path("installer/GMonster.iss").read_text(encoding="utf-8")
    assert "Remove user data" in script
    assert "DelTree" in script
```

- [ ] **Step 2: Run the contract tests and confirm they fail because the installer script is absent**

Run: `python -m unittest tests.test_installer_script -v`

Expected: `FileNotFoundError` for `installer/GMonster.iss`.

- [ ] **Step 3: Implement the Inno Setup script**

Use `DefaultDirName={autopf}\GMonster`, `ArchitecturesAllowed=x64compatible`, `ArchitecturesInstallIn64BitMode=x64compatible`, `OutputDir=..\release`, and an immutable `AppId`. Include `GMonster.exe`, `WUM.exe`, bundled tools, and `default-data` from `release/stage`; do not copy runtime data into `{app}`. Add Start Menu and optional desktop shortcuts. Add a `[Run]` entry that launches `GMonster.exe` with `postinstall nowait skipifsilent`. Implement a custom uninstall checkbox named `Remove user data`; call `DelTree(ExpandConstant('{localappdata}\GMonster\data'), True, True, True)` only when the checkbox is selected.

- [ ] **Step 4: Compile and inspect the installer on Windows**

Run: `& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\GMonster.iss`

Expected: `release/GMonster-<version>-Setup.exe` is created with no compiler errors.

- [ ] **Step 5: Commit the installer**

```bash
git add installer/GMonster.iss tests/test_installer_script.py installer/LICENSE.txt
git commit -m "build: add Windows installer"
```

### Task 6: Automate signed release creation and verify real install scenarios

**Files:**

- Create: `.github/workflows/release-windows-installer.yml`
- Modify: `README.md:74-95`

**Interfaces:**

- Consumes: a version tag `v*`, a `wum_ref` workflow input defaulting to WUM's `main` commit SHA, `WINDOWS_SIGNING_CERTIFICATE_BASE64`, and `WINDOWS_SIGNING_CERTIFICATE_PASSWORD`.
- Produces: a signed installer uploaded as a GitHub Release asset and a SHA-256 checksum file.

- [ ] **Step 1: Write a failing workflow validation test**

```python
def test_release_workflow_builds_and_uploads_the_setup_executable():
    workflow = Path(".github/workflows/release-windows-installer.yml").read_text(encoding="utf-8")
    assert "windows-latest" in workflow
    assert "stage_windows_release.ps1" in workflow
    assert "ISCC.exe" in workflow
    assert "GMonster-*-Setup.exe" in workflow
```

- [ ] **Step 2: Run it and confirm it fails before the workflow exists**

Run: `python -m unittest tests.test_installer_script -v`

Expected: missing workflow-file failure.

- [ ] **Step 3: Implement the tagged/manual release workflow**

Trigger on `workflow_dispatch` and pushed tags matching `v*`. The manual trigger accepts a required `wum_ref` input; tagged releases use the WUM commit SHA recorded in the release configuration. Use three Windows jobs: `build-wum` checks out `moeezmujahid70/WUM-App` at `wum_ref`, installs its requirements, builds `WUM.spec`, and uploads `WUM.exe`; `build-gmonster` checks out this repository, installs `requirements-updated.txt`, builds `GMonster.spec`, and uploads `GMonster.exe`; `package-installer` downloads both artifacts from those jobs, runs `GMonster.exe --smoke-test` and `WUM.exe --smoke-test`, runs the staging script and Inno Setup, signs both EXEs before compiling the installer, then signs the setup EXE, produces a SHA-256 checksum, and uploads the setup EXE and checksum to the GitHub Release. Keep the existing pull-request EXE build separate and unsigned.

- [ ] **Step 4: Validate on a clean Windows VM or sandbox**

Run these manual checks in order:

1. Install `GMonster-<version>-Setup.exe` as a standard user and launch from the Start Menu.
2. Confirm `%LOCALAPPDATA%\GMonster\data\gmonster_config\config.json` is created and `{autopf}\GMonster\data` is absent.
3. Change configuration, create a spreadsheet, and close the app.
4. Install a newer setup EXE and verify the configuration and spreadsheet remain unchanged.
5. From PowerShell, run `& "{autopf}\GMonster\GMonster.exe" --smoke-test` and `& "{autopf}\GMonster\WUM.exe" --smoke-test`; both commands must return `0` without a GUI.
6. Verify `WUM.exe` launches from the installed app directory and reads its configuration from `%LOCALAPPDATA%\GMonster\data\wum_config`.
7. Uninstall without selecting `Remove user data` and confirm runtime data remains.
8. Reinstall, uninstall with `Remove user data` selected, and confirm the runtime data directory is removed.

- [ ] **Step 5: Commit release automation and documentation**

```bash
git add .github/workflows/release-windows-installer.yml README.md tests/test_installer_script.py
git commit -m "ci: publish signed Windows installer releases"
```

## Plan Self-Review

- **Coverage:** Tasks 1-3 separate install files from writable data, preserve existing ZIP users, make WUM share the same installed data root, and add terminal smoke tests; Tasks 4-5 stage and package fresh GMonster/WUM builds with safe defaults; Task 6 checks out the public WUM source at a pinned ref, builds both applications, signs, publishes, and validates upgrade/uninstall behavior.
- **Scope:** This plan is limited to Windows packaging and related safe runtime-path changes. It does not change campaign, SMTP, or UI behavior.
- **Dependencies:** The public `moeezmujahid70/WUM-App` repository must retain a working `WUM.spec` and Windows-compatible requirements; code-signing certificate secrets are required before a signed public release can be built.
- **Consistency:** `RuntimePaths.data_dir` is the sole writable-data root throughout the plan; `{app}` stores only executables and immutable assets.
