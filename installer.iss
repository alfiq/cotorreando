; Inno Setup script for Cotorreando. Built by build.ps1 after the Nuitka step.
; Installs per user (no administrator rights needed).
; The wizard is our own: a frameless window with the feathers behind it, which first
; tells what Cotorreando is and then installs. Inno Setup's pages stay underneath,
; doing the work; [Code] covers them with a single stage and changes its text.

#define AppVersion "0.0.7"

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
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
ShowLanguageDialog=no
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Cotorreando-{#AppVersion}-setup
SetupIconFile=cotorreando\icon.ico
UninstallDisplayIcon={app}\Cotorreando.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dark
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
es.Hello=Hola, soy Cotorreando
es.HelloText=Hablas y yo escribo, en cualquier programa de Windows: el correo, un chat, un documento… donde esté tu cursor.%n%nAntes de instalarme, te platico rápido cómo funciono.
es.Bubble=Te acompaño en una burbuja
es.BubbleText=Una burbuja flotante se queda a la mano: se mueve cuando te escucha y cambia de color mientras escribe.%n%nArrástrala a donde quieras y dale clic derecho para abrir las opciones. Si te pones a teclear, me espero.
es.Private=Lo que dices se queda contigo
es.PrivateText=Reconozco tu voz aquí, en tu equipo. La primera vez descargo el modelo de voz (unos 670 MB) y, si quieres, aprendo tu forma de hablar.%n%nMi código es libre, con licencia MIT. El modelo es Parakeet TDT 0.6B v3 de NVIDIA, con licencia CC BY 4.0. Los demás créditos están en Acerca de.
es.Desktop=Poner un acceso directo en el escritorio
es.Install=Instalar
es.Closing=Un momento
es.ClosingText=Hay un Cotorreando abierto. Lo cierro para poder actualizarlo: pulsa Siguiente para continuar.
es.Copying=Ya voy
es.CopyingText=Estoy acomodando mis plumas en tu equipo…
es.Done=¡Listo!
es.DoneText=Busca la burbuja en tu pantalla y empieza a platicar. La primera vez tardo un poco, mientras descargo el modelo.
en.Hello=Hi, I'm Cotorreando
en.HelloText=You talk and I type, in any Windows program: your email, a chat, a document… wherever your cursor is.%n%nBefore installing, let me quickly tell you how I work.
en.Bubble=I keep you company in a bubble
en.BubbleText=A floating bubble stays close by: it moves when it hears you and changes colour while it types.%n%nDrag it anywhere and right-click it for the options. If you start typing, I wait.
en.Private=What you say stays with you
en.PrivateText=I recognise your voice here, on your computer. The first time I download the voice model (about 670 MB) and, if you like, I learn the way you speak.%n%nMy code is free software, under the MIT licence. The model is Parakeet TDT 0.6B v3 by NVIDIA, under CC BY 4.0. The other credits are in About.
en.Desktop=Add a shortcut to the desktop
en.Install=Install
en.Closing=One moment
en.ClosingText=Cotorreando is open. I'll close it so it can be updated: press Next to continue.
en.Copying=On my way
en.CopyingText=Settling my feathers on your computer…
en.Done=All set!
en.DoneText=Look for the bubble on your screen and start talking. The first time takes a little longer, while I download the model.

[Files]
Source: "dist\installer-art.bmp"; Flags: dontcopy
Source: "dist\cotorreando.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cotorreando"; Filename: "{app}\Cotorreando.exe"
Name: "{group}\{cm:UninstallProgram,Cotorreando}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cotorreando"; Filename: "{app}\Cotorreando.exe"; Check: WantsDesktopIcon

[Registry]
; Remove the "start with Windows" entry the app may have created.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Cotorreando"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Cotorreando.exe"; Description: "{cm:LaunchProgram,Cotorreando}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WINDOW_W = 720;
  WINDOW_H = 460;
  TEXT_X = 40;
  TEXT_W = 340;
  WINDOW_BACK = $1B1716;  // #16171b, the colour of the app's windows (BGR)
  WM_NCLBUTTONDOWN = $00A1;
  HTCAPTION = 2;
  DWMWA_WINDOW_CORNER_PREFERENCE = 33;
  DWMWCP_ROUND = 2;

var
  Stage: TPanel;
  TitleText, BodyText: TLabel;
  DesktopBox: TNewCheckBox;
  StoryBubble, StoryPrivate: TWizardPage;

function ReleaseCapture: BOOL; external 'ReleaseCapture@user32.dll stdcall';
function SendMessage(hWnd: HWND; Msg: UINT; wParam, lParam: Longint): Longint;
  external 'SendMessageW@user32.dll stdcall';
function DwmSetWindowAttribute(hWnd: HWND; Attribute: DWORD; var Value: DWORD; Size: DWORD): Longint;
  external 'DwmSetWindowAttribute@dwmapi.dll stdcall delayload';

function WantsDesktopIcon: Boolean;
begin
  Result := DesktopBox.Checked;
end;

procedure DragWindow(Sender: TObject; Button: TMouseButton; Shift: TShiftState; X, Y: Integer);
begin
  ReleaseCapture;
  SendMessage(WizardForm.Handle, WM_NCLBUTTONDOWN, HTCAPTION, 0);
end;

procedure CloseClicked(Sender: TObject);
begin
  if WizardForm.CurPageID = wpFinished then begin
    // Setup ignores closing here; leave through Finish without opening the program.
    WizardForm.RunList.Checked[0] := False;
    WizardForm.NextButton.OnClick(WizardForm.NextButton);
  end else
    WizardForm.Close;
end;

function NewLabel(Left, Top, Width, Height, Size: Integer; Style: TFontStyles; Color: Integer): TLabel;
begin
  Result := TLabel.Create(Stage);
  Result.Parent := Stage;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Transparent := True;
  Result.Font.Name := 'Segoe UI';
  Result.Font.Size := Size;
  Result.Font.Style := Style;
  Result.Font.Color := Color;
  Result.SetBounds(ScaleX(Left), ScaleY(Top), ScaleX(Width), ScaleY(Height));
  Result.OnMouseDown := @DragWindow;
end;

procedure RoundCorners;
var
  Corner: DWORD;
begin
  Corner := DWMWCP_ROUND;
  try
    DwmSetWindowAttribute(WizardForm.Handle, DWMWA_WINDOW_CORNER_PREFERENCE, Corner, SizeOf(Corner));
  except
    // Older than Windows 11: square corners.
  end;
end;

procedure InitializeWizard;
var
  Art: TBitmapImage;
  CloseMark: TLabel;
begin
  WizardForm.BorderStyle := bsNone;
  WizardForm.ClientWidth := ScaleX(WINDOW_W);
  WizardForm.ClientHeight := ScaleY(WINDOW_H);
  WizardForm.Position := poScreenCenter;
  WizardForm.CancelButton.Visible := False;

  Stage := TPanel.Create(WizardForm);
  Stage.Parent := WizardForm;
  Stage.BevelOuter := bvNone;
  Stage.Color := WINDOW_BACK;
  Stage.SetBounds(0, 0, WizardForm.ClientWidth, WizardForm.ClientHeight);

  ExtractTemporaryFile('installer-art.bmp');
  Art := TBitmapImage.Create(Stage);
  Art.Parent := Stage;
  Art.SetBounds(0, 0, Stage.Width, Stage.Height);
  Art.Stretch := True;
  Art.Bitmap.LoadFromFile(ExpandConstant('{tmp}\installer-art.bmp'));

  // Our title bar: dragging it moves the window.
  NewLabel(14, 10, WINDOW_W - 58, 26, 9, [], $998F8B).Caption := 'Cotorreando';
  TitleText := NewLabel(TEXT_X, 92, TEXT_W, 80, 22, [fsBold], $F6F4F3);
  BodyText := NewLabel(TEXT_X, 186, TEXT_W, 160, 11, [], $C2B9B6);

  CloseMark := NewLabel(WINDOW_W - 40, 6, 32, 28, 11, [], $B0A7A4);
  CloseMark.Caption := '✕';
  CloseMark.Alignment := taCenter;
  CloseMark.Cursor := crHand;
  CloseMark.OnMouseDown := nil;
  CloseMark.OnClick := @CloseClicked;

  DesktopBox := TNewCheckBox.Create(Stage);
  DesktopBox.Parent := Stage;
  DesktopBox.SetBounds(ScaleX(TEXT_X), ScaleY(350), ScaleX(TEXT_W), ScaleY(22));
  DesktopBox.Caption := CustomMessage('Desktop');
  DesktopBox.Visible := False;

  WizardForm.BackButton.Parent := Stage;
  WizardForm.NextButton.Parent := Stage;
  WizardForm.NextButton.SetBounds(ScaleX(TEXT_X), ScaleY(400), ScaleX(120), ScaleY(32));
  WizardForm.BackButton.SetBounds(ScaleX(TEXT_X + 130), ScaleY(400), ScaleX(100), ScaleY(32));
  WizardForm.ProgressGauge.Parent := Stage;
  WizardForm.ProgressGauge.SetBounds(ScaleX(TEXT_X), ScaleY(300), ScaleX(TEXT_W), ScaleY(10));
  WizardForm.RunList.Parent := Stage;
  WizardForm.RunList.SetBounds(ScaleX(TEXT_X), ScaleY(340), ScaleX(TEXT_W), ScaleY(34));

  // Blank pages: they only give the story its Back and Next.
  StoryBubble := CreateCustomPage(wpWelcome, '', '');
  StoryPrivate := CreateCustomPage(StoryBubble.ID, '', '');
  CreateCustomPage(wpWelcome, '', '');

  Stage.BringToFront;
  RoundCorners;
end;

procedure Say(const Title, Body: String);
begin
  TitleText.Caption := CustomMessage(Title);
  BodyText.Caption := CustomMessage(Body);
  // A caption change adjusts the label's height to the old text; give it back.
  TitleText.Height := ScaleY(80);
  BodyText.Height := ScaleY(160);
  Stage.Repaint;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  DesktopBox.Visible := CurPageID = StoryPrivate.ID;
  WizardForm.ProgressGauge.Visible := CurPageID = wpInstalling;
  TitleText.BringToFront;
  BodyText.BringToFront;
  if CurPageID = StoryBubble.ID then
    Say('Bubble', 'BubbleText')
  else if CurPageID = StoryPrivate.ID then begin
    Say('Private', 'PrivateText');
    WizardForm.NextButton.Caption := CustomMessage('Install');
  end else if CurPageID = wpPreparing then
    Say('Closing', 'ClosingText')
  else if CurPageID = wpInstalling then
    Say('Copying', 'CopyingText')
  else if CurPageID = wpFinished then
    Say('Done', 'DoneText')
  else
    Say('Hello', 'HelloText');
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  // Nothing has been touched yet while the story is being told.
  Confirm := CurPageID = wpInstalling;
end;
