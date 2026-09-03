# Hub CZN - steve1316 fork

A personal fork of [sostenesfreitas/hub-czn](https://github.com/sostenesfreitas/hub-czn), the gear
optimizer and damage simulator for **Chaos Zero Nightmare**.

This fork exists to harden the capture setup - the part that intercepts the game's traffic to read
your inventory, roster and rescue records. The upstream app worked, but it installed a root
certificate machine-wide with no way to remove it, left an elevated local API open to anything on
the machine, and needed mitmproxy installed separately. Those are the things being fixed here.

Changes are not sent upstream. For what the app does and how to use it, see the upstream README.

## Changelog

### 2026-09-02

- Forked from upstream `v0.4.6`.
- The CA is now installed for your Windows account only, instead of for every account on the PC.
- `Setup` gained a **Remove** button, and uninstalling the app now untrusts the certificate. Before
  this there was no way to undo it at all.
- Generating the certificate no longer takes three seconds or needs mitmproxy on your PATH.
- The Windows security prompt that appears when trusting the certificate is now visible. It was
  being hidden, which made the app hang and then report a misleading error.
- mitmproxy ships inside the app, so `Setup` no longer asks you to install anything.
- Capture no longer leaves your game unable to connect if the app crashes mid-session - leftover
  redirects are cleaned up the next time it starts.
- Starting capture now reports a real error when it fails. It used to report success regardless.
- The proxy listens on this machine only, rather than accepting connections from the local network.
- The app's local API now requires a token, so another program - or a web page you happen to open -
  can no longer drive it while it is running as administrator.
- The endpoint that could run an elevated `pip install` has been removed.
- Captured account data is excluded from git instead of sitting untracked in the repo.
