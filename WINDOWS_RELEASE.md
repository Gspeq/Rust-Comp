# Rust Companion+ Windows Release

Run `Build_Rust_Companion_Plus.bat` from the repository root.

The builder uses only the current local checkout as application source. It:

1. Creates an isolated `.release-venv`.
2. Installs runtime dependencies from `requirements.txt`.
3. Installs PyInstaller from `requirements-build.txt`.
4. Runs the complete test suite.
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

The uninstaller is available from:

- Rust Companion+ sidebar
- Start Menu
- Windows Apps & Features

Uninstalling removes the installed application and all associated Rust Companion+ application data.
