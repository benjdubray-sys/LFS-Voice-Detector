; Installateur LFS Voice (Inno Setup 6)  -  compile avec : ISCC.exe installer.iss
; Lance d'abord PyInstaller (build.bat le fait pour toi) : dist\LFSVoice doit exister.
#define AppName "LFS Voice"
#define AppVersion "1.0.0"
#define AppExe "LFSVoice.exe"

[Setup]
AppId={{B3C1F0E2-6D54-4F0B-9A71-5E2C7A4D8F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=LFS Voice
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=installer_output
OutputBaseFilename=LFSVoice-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Pas besoin des droits administrateur (installation dans le profil de l'utilisateur)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

; Chaque langue n'est ajoutee que si son fichier existe dans ton Inno Setup :
; une langue absente est simplement ignoree au lieu de faire echouer la compilation.
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(CompilerPath + "Languages\French.isl")
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
#endif
#if FileExists(CompilerPath + "Languages\German.isl")
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
#endif
#if FileExists(CompilerPath + "Languages\Spanish.isl")
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Italian.isl")
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
#endif
#if FileExists(CompilerPath + "Languages\Dutch.isl")
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
#endif
#if FileExists(CompilerPath + "Languages\Portuguese.isl")
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
#endif
#if FileExists(CompilerPath + "Languages\Polish.isl")
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Czech.isl")
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
#endif
#if FileExists(CompilerPath + "Languages\Slovak.isl")
Name: "slovak"; MessagesFile: "compiler:Languages\Slovak.isl"
#endif
#if FileExists(CompilerPath + "Languages\Slovenian.isl")
Name: "slovenian"; MessagesFile: "compiler:Languages\Slovenian.isl"
#endif
#if FileExists(CompilerPath + "Languages\Bulgarian.isl")
Name: "bulgarian"; MessagesFile: "compiler:Languages\Bulgarian.isl"
#endif
#if FileExists(CompilerPath + "Languages\Danish.isl")
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Finnish.isl")
Name: "finnish"; MessagesFile: "compiler:Languages\Finnish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Greek.isl")
Name: "greek"; MessagesFile: "compiler:Languages\Greek.isl"
#endif
#if FileExists(CompilerPath + "Languages\Hungarian.isl")
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\LFSVoice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Les réglages et le modèle vocal sont dans %APPDATA%\LFSVoice : ils ne sont pas
; supprimés à la désinstallation (le modèle pèse plusieurs centaines de Mo).
