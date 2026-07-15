; Rust Companion+ per-user Windows installer

#ifndef MyAppVersion
  #define MyAppVersion "0.5.0"
#endif

#ifndef SourceDir
  #error SourceDir must be provided by build_windows_release.ps1
#endif

#ifndef OutputDir
  #error OutputDir must be provided by build_windows_release.ps1
#endif

#define MyAppName "Rust Companion+"
#define MyAppPublisher "Taylor Marshall"
#define MyAppExeName "RustCompanionPlus.exe"
#define MyAppId "{{90E9FA8A-2DD8-4A5E-AE24-50931E919D97}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/Gspeq/Rust-Comp
AppSupportURL=https://github.com/Gspeq/Rust-Comp
DefaultDirName={localappdata}\Programs\Rust Companion+
DefaultGroupName=Rust Companion+
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=RustCompanionPlus-Setup-{#MyAppVersion}
SetupIconFile=rust_companion_plus.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Windows Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
ChangesAssociations=no
ChangesEnvironment=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Rust Companion+"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall Rust Companion+"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Rust Companion+"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Rust Companion+"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\RustCompanionPlus\Rust Companion+"
Type: filesandordirs; Name: "{userprofile}\.rust_companion_plus"
