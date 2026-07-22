# Rust Companion+ launchers

The repository root intentionally exposes only two runnable BAT files:

1. `Run_Rust_Companion_Plus_Source.bat`
   - Verifies the local checkout exactly matches `origin/test-live-sync`.
   - Verifies or creates the source virtual environment.
   - Installs dependencies without using pip's cache.
   - Compiles the source.
   - Runs the complete unit-test suite.
   - Runs `git diff --check`.
   - Rechecks local/remote synchronization.
   - Starts the application only after every check passes.

2. `Build_Rust_Companion_Plus.bat`
   - Manually builds the Windows release and installer.
   - Is never called by the source launcher or by hotfixes.

PowerShell implementation files live under `tools/windows`.
Release documentation lives under `docs`.
Secondary requirement files live under `requirements`.
Older launchers and the obsolete root PyInstaller spec are retained as non-runnable text copies under `tools/legacy_launchers` and `tools/legacy_build`.
