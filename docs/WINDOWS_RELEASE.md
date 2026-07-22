# Rust Companion+ Development and Windows Release

Rust Companion+ now has separate **source testing** and **release building**
workflows.

## Daily functional testing

Double-click:

```text
Run_Rust_Companion_Plus_Source.bat
```

This launches the current `test-live-sync` source through the project `.venv`.
It uses the same LocalAppData profiles, credentials, maps, logs, and caches as
the installed application.

The bootloader console remains visible while it is needed. After the GUI
appears, the source launcher's own console is hidden.

This command does **not** run PyInstaller, create an EXE, compile an installer,
or install anything.

## Test suite only

Double-click:

```text
Run_Rust_Companion_Plus_Source.bat (tests run first)
```

This runs the complete Python test suite and `git diff --check`. It does not
launch the application and does not build a release.

## Build a Windows release manually

Only after the source version is confirmed ready, double-click:

```text
Build_Rust_Companion_Plus.bat
```

The manual builder uses only the current local checkout as application source.
It:

1. Creates an isolated `.release-venv`.
2. Installs runtime dependencies from `requirements.txt`.
3. Installs PyInstaller from `requirements/build.txt`.
4. Runs the complete test suite unless explicitly skipped.
5. Builds `RustCompanionPlus.exe` with an embedded Python runtime.
6. Runs the packaged executable self-test.
7. Creates a per-user Windows installer with Inno Setup.
8. Writes a SHA-256 source/build manifest beside the executable.

Output:

- `release/app/RustCompanionPlus/RustCompanionPlus.exe`
- `release/RustCompanionPlus-Setup-<version>.exe`

The installed application uses:

- Program files: `%LOCALAPPDATA%\Programs\Rust Companion+`
- Application data: `%LOCALAPPDATA%\RustCompanionPlus\Rust Companion+`

The uninstaller is available from the Rust Companion+ sidebar, Start Menu,
and Windows Apps & Features. Uninstalling removes the installed application
and all associated Rust Companion+ application data.
