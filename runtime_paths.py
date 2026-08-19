"""Runtime path resolution for development and installed GMonster builds."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import traceback


@dataclass(frozen=True)
class RuntimePaths:
    app_dir: Path
    resource_dir: Path
    data_dir: Path
    is_frozen_windows: bool


RUNTIME_DATA_DIRECTORIES = (
    "sheets",
    "email",
    "email/email_verification",
    "email/tools",
    "email/results",
    "logs",
    "logs/gmonster",
    "logs/wum",
    "logs/app",
    "gmonster_config",
    "wum_config",
    "backups",
)


def resolve_runtime_paths(
    *,
    frozen: bool,
    platform_name: str,
    executable: str | Path,
    resource_dir: str | Path,
    working_dir: str | Path,
    local_app_data: str | Path,
) -> RuntimePaths:
    """Resolve immutable application files separately from writable data."""
    is_frozen_windows = frozen and platform_name == "win32"
    app_dir = Path(executable).resolve().parent if frozen else Path(working_dir).resolve()
    data_dir = (
        Path(local_app_data).resolve() / "GMonster" / "data"
        if is_frozen_windows
        else app_dir / "data"
    )
    return RuntimePaths(
        app_dir=app_dir,
        resource_dir=Path(resource_dir).resolve(),
        data_dir=data_dir,
        is_frozen_windows=is_frozen_windows,
    )


def initialize_runtime_data(
    data_dir: str | Path,
    defaults_dir: str | Path,
    legacy_data_dir: str | Path | None,
    starter_data_dir: str | Path | None = None,
) -> None:
    """Create missing runtime folders and safely seed or migrate user data."""
    destination = Path(data_dir)
    defaults = Path(defaults_dir)
    for relative_dir in RUNTIME_DATA_DIRECTORIES:
        (destination / relative_dir).mkdir(parents=True, exist_ok=True)

    config_dir = destination / "gmonster_config"
    for filename in ("config.json", "cacert.pem"):
        source = defaults / filename
        if filename == "config.json" and not source.is_file():
            source = defaults / "config.example.json"
        target = config_dir / filename
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)

    if legacy_data_dir is not None:
        legacy = Path(legacy_data_dir)
        migration_marker = config_dir / ".legacy_data_migrated"
        if legacy.is_dir() and not migration_marker.exists():
            for source in legacy.rglob("*"):
                if not source.is_file():
                    continue
                target = destination / source.relative_to(legacy)
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            migration_marker.touch()

    if starter_data_dir is None:
        return

    starter_sheets = Path(starter_data_dir) / "sheets"
    if not starter_sheets.is_dir():
        return

    for source in starter_sheets.rglob("*"):
        if not source.is_file():
            continue
        target = destination / "sheets" / source.relative_to(starter_sheets)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def wum_executable_path(app_dir: str | Path) -> Path:
    """Return the WUM executable installed beside GMonster on Windows."""
    return Path(app_dir) / "WUM.exe"


def update_staging_dir(data_dir: str | Path) -> Path:
    """Return a writable location for downloaded installer updates."""
    return Path(data_dir) / "updates"


def run_smoke_test(
    data_dir: str | Path,
    defaults_dir: str | Path | None = None,
    starter_data_dir: str | Path | None = None,
) -> int:
    """Verify runtime storage can initialize without loading GUI dependencies."""
    initialize_runtime_data(
        data_dir,
        defaults_dir or Path(),
        legacy_data_dir=None,
        starter_data_dir=starter_data_dir,
    )
    return 0


def run_smoke_test_with_diagnostics(
    data_dir: str | Path,
    diagnostic_path: str | Path | None,
    defaults_dir: str | Path | None = None,
    starter_data_dir: str | Path | None = None,
) -> int:
    """Run the smoke test and record a traceback if a windowed build fails."""
    try:
        return run_smoke_test(data_dir, defaults_dir, starter_data_dir)
    except Exception:
        if diagnostic_path is not None:
            diagnostic = Path(diagnostic_path)
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            diagnostic.write_text(traceback.format_exc(), encoding="utf-8")
        return 1
