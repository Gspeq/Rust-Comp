# Rust Companion+ launchers

Use only these three root-level BAT files:

1. `Run_Rust_Companion_Plus_Source.bat` runs the existing application from source. It never builds an EXE.
2. `Test_Rust_Companion_Plus.bat` installs or verifies dependencies, compiles the Python modules, runs every unit test, and checks the Git diff. It never builds an EXE.
3. `Build_Rust_Companion_Plus.bat` is the only user-facing manual EXE and release builder.

The root PowerShell and Python files are implementation files used by those launchers. A normal user does not need to open them directly.

Older duplicate BAT launchers are retained as non-runnable `.bat.txt` copies under `tools/legacy_launchers`.
