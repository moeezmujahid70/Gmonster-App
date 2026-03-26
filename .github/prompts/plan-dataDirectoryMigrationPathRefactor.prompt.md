## Plan: Data Directory Migration and Path Refactor

Replace the legacy database directory with the new data hierarchy in staged order: centralize all paths first, then refactor path consumers, then move files, then validate runtime flows. This minimizes breakage and avoids blind string replacement.

### Steps

1. Baseline and move-map
1. Capture a complete source to destination map for everything currently under database plus runtime outputs in Email verification and logs.
1. Confirm optional-file behavior (blacklists, autoReply file) so missing files fail gracefully after migration.

1. Centralize runtime paths in one place (blocking step)
1. In var.py, introduce a full path model rooted at data, including constants for sheets, tools, results, archive, logs, gmonster_config, backups, scripts, and campaign scheduler.
1. Convert existing globals in var.py to use centralized constants for config, DB, scheduler, cert, updater, and APScheduler jobstore.
1. Add startup directory creation for required writable folders, especially data/gmonster_config/campaign_scheduler and data/logs/gmonster.

1. Contextual code refactor (parallelizable after step 2)
1. Update database.py to use centralized constants for SQLite DB and xlsx locations.
1. Update hardcoded path calls in main.py for verify_blacklist, blacklist, autoReply_address, and verification output folder.
1. Update report/followup writers in smtp.py to write into data/results.
1. Update scheduler JSON writes in utils.py to use campaign scheduler path constants.
1. Move logger output path in logger.py to data/logs/gmonster.
1. Update updater path logic in var.py to scripts/updater.bat.

1. Physical migration to new layout (after step 3 is ready)
1. Create:
1. data/sheets, data/email_verification, data/tools, data/results, data/logs/gmonster, data/logs/wum, data/logs/app, data/gmonster_config, data/gmonster_config/campaign_scheduler, data/backups, scripts.
1. Move files contextually:
1. group_a.xlsx, group_b.xlsx, target.xlsx to data/sheets.
1. email_verify.exe and email_verify_befi.exe to data/email/tools.
1. database.csv, report.csv, followup_report.csv to data/email/results.
1. config/json/txt/pem/prompts/emails/campaign_scheduler and SQLite runtime files to data/gmonster_config.
1. group_b11.xlsx and other unused assets to data/backups.
1. updater.bat to scripts/updater.bat.
1. Move root verification outputs from Email verification to data/email/email_verification.
1. Move runtime logs from logs to data/logs/gmonster.
1. Move wum_config under data/wum_config.
1. Remove legacy database folder only after validation passes.

1. Non-runtime references and docs
1. Update ignore rules in .gitignore for new data paths.
1. Update dev workflows that still reference database paths in .agent/workflows/run_app.md and .agent/workflows/build_app.md.
1. Confirm packaging assumptions in Gmonster.spec and GMonster2.spec.

1. Validation
1. Static check: zero remaining runtime references to database paths in source/docs (excluding generated artifacts under build/dist/app bundles).
1. Startup check: app launches and loads config from data/gmonster_config.
1. Scheduler check: create and execute a scheduled campaign config from data/gmonster_config/campaign_scheduler and verify jobs.sqlite persistence.
1. Reporting check: report.csv and followup_report.csv write under data/results.
1. Email verification check: outputs appear under data/email_verification.
1. Logging check: logs write/rotate under data/logs/gmonster.
1. Windows check: scripts/updater.bat is generated and usable.

### Relevant files

- var.py
- database.py
- main.py
- smtp.py
- utils.py
- logger.py
- .gitignore
- .agent/workflows/run_app.md
- .agent/workflows/build_app.md
- Gmonster.spec
- GMonster2.spec

### Confirmed decisions included in this plan

1. SQLite runtime files go to data/gmonster_config.
1. Move wum_config under data/wum_config.
1. Runtime logs move to data/logs/gmonster.
1. updater.bat moves to scripts/updater.bat.
