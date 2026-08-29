# Frontend state wireframes

These wireframes define hierarchy and behavior, not pixel-exact rendering.
GTK and Qt should use native widgets and spacing.

## First run

```text
┌──────────────────────────────────────────────────────────┐
│ EITaaS-Linux                                             │
│ Community AVD connection helper                         │
│                                                          │
│ Connect to your assigned desktop from Linux using a      │
│ profile exported from your authorized AVD web client.    │
│                                                          │
│ This is independent community software.                  │
│                                                          │
│ [ Choose desktop profile ]   [ Run system check ]        │
│                                                          │
│ Privacy and security                      About           │
└──────────────────────────────────────────────────────────┘
```

## Ready desktop

```text
┌──────────────┬───────────────────────────────────────────┐
│ Desktops     │ Your desktops                             │
│ System Check │                                           │
│ Settings     │ ┌───────────────────────────────────────┐ │
│              │ │  ▣  Enterprise Desktop               │ │
│              │ │     Ready · Automatic backend        │ │
│              │ │                         [ Connect ]   │ │
│              │ └───────────────────────────────────────┘ │
│              │                                           │
│              │ [ Add desktop profile ]                   │
└──────────────┴───────────────────────────────────────────┘
```

## Degraded readiness

```text
┌──────────────────────────────────────────────────────────┐
│ Enterprise Desktop                         Needs attention│
│                                                          │
│ ✓ Profile protected                                     │
│ ! Compatible FreeRDP client not found                   │
│ ✓ Smart-card service available                          │
│ ! Reader not detected                                   │
│                                                          │
│ [ View system check ]                         [ Close ]   │
└──────────────────────────────────────────────────────────┘
```

There is no **Connect anyway** action for a missing required capability or
certificate-validation failure.

## Connection options

```text
┌──────────────────────────────────────────────────────────┐
│ Connect to Enterprise Desktop                            │
│                                                          │
│ Smart-card passthrough                         On        │
│ Clipboard sharing                              Off       │
│                                                          │
│ Advanced                                                 │
│ Display backend                                Automatic │
│                                                          │
│ [ Cancel ]                                  [ Connect ]   │
└──────────────────────────────────────────────────────────┘
```

## Connecting and cancellation

```text
┌──────────────────────────────────────────────────────────┐
│ Connecting to Enterprise Desktop                         │
│                                                          │
│ ◌ Selecting a compatible remote desktop client…          │
│                                                          │
│ Authentication is handled by the remote desktop client.  │
│                                                          │
│                                             [ Cancel ]    │
└──────────────────────────────────────────────────────────┘
```

## Authentication handoff

```text
┌──────────────────────────────────────────────────────────┐
│ Authentication required                                  │
│                                                          │
│ Complete sign-in using the FreeRDP authentication flow.  │
│ EITaaS-Linux does not read or store your authentication   │
│ response.                                                 │
│                                                          │
│ [ Cancel connection ]                                    │
└──────────────────────────────────────────────────────────┘
```

No callback URL, code, username, tenant, or browser contents appear here.

## Failure

```text
┌──────────────────────────────────────────────────────────┐
│ Could not start the connection                           │
│                                                          │
│ No compatible FreeRDP 3 client with AAD and smart-card   │
│ support was found.                                       │
│                                                          │
│ [ Run system check ]  [ Copy safe details ]  [ Close ]   │
└──────────────────────────────────────────────────────────┘
```

## Connected and disconnecting

The FreeRDP window represents the connected desktop. The launcher card may
show **Connection process running**, not **Connected**, unless the core gains a
verified session signal.

```text
┌──────────────────────────────────────────────────────────┐
│ Enterprise Desktop                         Process running│
│                                                          │
│ The remote desktop client is active.                     │
│                                                          │
│ [ Disconnect ]                                [ Hide ]    │
└──────────────────────────────────────────────────────────┘
```

## Certificate inspection

```text
┌──────────────────────────────────────────────────────────┐
│ Certificate bundle                                       │
│                                                          │
│ File       Certificates_PKCS7…p7b                        │
│ SHA-256    12:34:…                                       │
│                                                          │
│ ▸ DoD Root CA …        Self-signed candidate             │
│ ▸ DoD ID CA …          Intermediate                      │
│                                                          │
│ Inspection does not add trust.                           │
│                                             [ Close ]     │
└──────────────────────────────────────────────────────────┘
```
