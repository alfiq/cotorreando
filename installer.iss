; Inno Setup script for Cotorreando. Built by build.ps1 after the Nuitka step.
; Installs per user (no administrator rights needed).

#define AppVersion "0.0.2"

[Setup]
AppId={{6F2C3B1E-8A4D-4C55-9E21-C0770EA2D0F1}
AppName=Cotorreando
AppVersion={#AppVersion}
AppPublisher=Alfiq
AppPublisherURL=https://github.com/alfiq
AppSupportURL=https://github.com/alfiq/cotorreando
DefaultDirName={localappdata}\Programs\Cotorreando
DefaultGroupName=Cotorreando
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=Cotorreando-{#AppVersion}-setup
SetupIconFile=cotorreando\icon.ico
UninstallDisplayIcon={app}\Cotorreando.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\cotorreando.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cotorreando"; Filename: "{app}\Cotorreando.exe"
Name: "{group}\{cm:UninstallProgram,Cotorreando}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cotorreando"; Filename: "{app}\Cotorreando.exe"; Tasks: desktopicon

[Registry]
; Remove the "start with Windows" entry the app may have created.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Cotorreando"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Cotorreando.exe"; Description: "{cm:LaunchProgram,Cotorreando}"; Flags: nowait postinstall skipifsilent
