; PDF Compressor installer (Inno Setup)
; Build with: ISCC.exe installer.iss  ->  outputs Output\PDFCompressor-Setup.exe

#define AppName "PDF Compressor"
#define AppVersion "1.0.0"
#define AppPublisher "Caio Gadotti"
#define AppExeName "PDFCompressor.exe"
#define AppURL "https://github.com/caiogadotti/pdf-compressor"

[Setup]
AppId={{E1C4A7F8-5B92-4E3D-8A61-PDFCOMPRESS1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\PDFCompressor
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=Output
OutputBaseFilename=PDFCompressor-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableWelcomePage=no
ShowLanguageDialog=yes
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\PDFCompressor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; IconIndex: 0
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; IconIndex: 0; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
