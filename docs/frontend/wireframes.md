# EITaaS Connect wireframes

These wireframes define hierarchy and behavior for the GTK 4/Libadwaita
helper `eitaas-gui`, not pixel-exact rendering. Native Libadwaita widgets and
spacing are used throughout. "Desktop.rdpw" is a sample file name.

## Readiness page

```text
┌──────────────────────────────────────────────────────────┐
│   [ Readiness ] [ Profile ] [ Connect ]                  │
├──────────────────────────────────────────────────────────┤
│ System readiness                              [ Re-check ]│
│ Each line states what was checked and what to do if it   │
│ failed. Nothing is changed on your system.               │
│                                                          │
│ ✓ Bundled remote desktop client                          │
│   Ready. The eitaas-remmina launcher and its private     │
│   client are installed (Remmina 1.4.43, FreeRDP 3.30.0). │
│ ✓ Desktop session                                        │
│   Ready. A graphical session is available (wayland).     │
│ ✗ Smart-card service                                 [⧉] │
│   Not ready. The pcscd socket is not active.             │
│   Start the service (needs administrator rights) with:   │
│   systemctl enable --now pcscd.socket                    │
│ ? Smart-card reader                                      │
│   Not checked. pcsc_scan is not installed. Install the   │
│   pcsc-tools package.                                    │
│ ✓ Card middleware (OpenSC)                               │
│ ! Diagnostic tools                                       │
└──────────────────────────────────────────────────────────┘
```

Each row shows the state word before the detail; a row with a command gains a
copy button (⧉). Re-check is disabled while `doctor` runs.

## Profile page

```text
┌──────────────────────────────────────────────────────────┐
│   [ Readiness ] [ Profile ] [ Connect ]                  │
├──────────────────────────────────────────────────────────┤
│ Get your desktop profile                                 │
│ Web client                    [ Azure US Government ▾ ]  │
│ Step 1  Open the Azure Virtual   [ Open web client ]     │
│         Desktop web client.                              │
│ Step 2  Sign in with your organization account in the    │
│         browser (it may ask for your smart card (PIV)    │
│         certificate and PIN).                            │
│ Step 3  Click the settings cog in the top right corner.  │
│ Step 4  Choose "Download the rdp file".                  │
│ Step 5  Click your desktop. Desktop.rdpw is saved to     │
│         your Downloads folder.                           │
│ Step 6  Come back here, press "I downloaded the RDP      │
│         file", and pick that file.                       │
│ ▸ Why do I need this file?                               │
│ ( I downloaded the RDP file )                            │
│                                                          │
│ Imported profiles                                        │
│ Stored privately under your user data directory.         │
│ (•) Desktop.rdpw                              [ Remove ] │
│     Azure US Government · 2048 bytes · mode 0600 ·       │
│     imported 2026-08-30 09:12:00                         │
│ ( ) Desktop-2.rdpw                            [ Remove ] │
└──────────────────────────────────────────────────────────┘
```

The radio button selects the profile Connect uses. With no import yet the list
shows a single row "No profile imported yet".

## Import banner (`eitaas-gui Desktop.rdpw` or file-manager double-click)

```text
┌──────────────────────────────────────────────────────────┐
│ Import Desktop.rdpw into your private profile store?     │
│                                              [ Import ]  │
├──────────────────────────────────────────────────────────┤
│ Get your desktop profile                                 │
│ …                                                        │
└──────────────────────────────────────────────────────────┘
```

Nothing happens until Import is pressed; the file is then moved into the store
and becomes the default. There is no automatic connect.

## Remove confirmation

```text
┌──────────────────────────────────────────────┐
│ Remove Desktop.rdpw?                         │
│                                              │
│ The imported file is deleted from your       │
│ private profile store.                       │
│                                              │
│ [ Keep ]                          [ Remove ] │
└──────────────────────────────────────────────┘
```

Keep is the default response; Remove is styled destructive.

## Connect page (idle)

```text
┌──────────────────────────────────────────────────────────┐
│   [ Readiness ] [ Profile ] [ Connect ]                  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│                        ▣                                 │
│                     Connect                              │
│                                                          │
│ Connect opens Desktop.rdpw in the bundled remote desktop │
│ client. Sign-in, certificate selection, and the PIN      │
│ prompt happen in that window. All required checks passed.│
│                                                          │
│                   (  Connect  )                          │
└──────────────────────────────────────────────────────────┘
```

Connect is enabled only when the launcher is installed and a default profile
exists; otherwise the description says which checks need attention or asks for
an import first.

## Running and cancelling

```text
┌──────────────────────────────────────────────────────────┐
│                     Connect                              │
│                                                          │
│      ◌ Remote desktop client started      [ Cancel ]     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

The phase label shows "Starting", then the `launch` progress messages. After
Cancel it reads "Stopping the remote desktop client" and the button is
disabled until the child exits. There is no Authenticating or Connected state.

## Launch error

```text
┌──────────────────────────────────────────────────────────┐
│                     Connect                              │
│                                                          │
│                   (  Connect  )                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Could not start the connection                       │ │
│ │ eitaas-remmina launcher is not installed             │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

The card holds the title for the error code, the redacted message, and the
recovery text when supplied. No child output or arguments appear.

## Disconnect and quit

```text
┌──────────────────────────────────────────────────┐
│ Disconnect and quit?                             │
│                                                  │
│ The remote desktop client is still running.      │
│                                                  │
│ [ Keep working ]          [ Disconnect and quit ] │
└──────────────────────────────────────────────────┘
```

Shown on close-request while a connection runs. Keep working is the default;
Disconnect and quit sets the cancellation event and joins the worker before
the window closes.
