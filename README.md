# Hub CZN - steve1316 fork

A personal fork of [sostenesfreitas/hub-czn](https://github.com/sostenesfreitas/hub-czn), the gear
optimizer and damage simulator for **Chaos Zero Nightmare**.

This fork exists to harden the capture setup - the part that intercepts the game's traffic to read
your inventory, roster and rescue records. The upstream app worked, but it installed a root
certificate machine-wide with no way to remove it, left an elevated local API open to anything on
the machine, and needed mitmproxy installed separately. Those are the things being fixed here.

Changes are not sent upstream. For what the app does and how to use it, see the upstream README.

## Building

Needs Python 3.12, Node.js 22 and the Rust toolchain, the same versions the release workflow uses. From the repo root:

```
.\build.bat
```

It syncs the version from `src-tauri/tauri.conf.json`, builds the Python sidecar with PyInstaller,
builds the frontend, then bundles two installers: an MSI in `src-tauri\target\release\bundle\msi\` and
a setup `.exe` in `src-tauri\target\release\bundle\nsis\`. Use it rather than `npm run tauri build` on
its own, which fails the sidecar version check.

To run from source instead, open an Administrator terminal in the repo root and run:

```
npm start
```

It starts the Python sidecar and the app together, and stops the sidecar when you close the app.

## Changelog

### 2026-10-27

- The installed app starts much faster. Its background service now ships as a folder of files
  instead of one large exe that had to unpack itself on every launch.
- The app now waits for its background service before showing the first screen, so pages no longer
  load against a service that has not started yet.
- Pulls are recorded the moment they happen while capture runs, so the full history only has to be
  imported once. The capture log says how many new pulls each save added.
- `Rescue Records` categories now use the game's own names, such as Seasonal Combatant Rescue
  Rate-Up and Observe Prism Module.
- `Auto-Scroll` now stops by itself on the last history page, and says so if clicks stop bringing in
  new pages.
- `Debug mode` on the `Capture` page is now remembered between launches.
- `Setup` no longer warns about a stuck redirect while a capture is running, since the capture needs
  that redirect.

### 2026-10-26

- The `Simulator` and `Battle History` are merged into one `Battles` page. It shares the current
  enemy, lists recent enemies, and can simulate against any past battle's enemy.
- The `Simulator` and the `Optimizer` now use each enemy's real damage decrease from the game.
  Before this the `Optimizer` estimated it from the enemy's DEF.
- Each `Deck Builder` deck gets a `Simulate` button that opens it in the `Simulator` with its
  epiphanies, and saved decks show up in the `Simulator`'s deck list.
- Unsaved `Deck Builder` work is now kept when you leave the page or reload it.
- The app is easier to read, with a larger minimum text size, brighter text, and an `Interface size`
  setting that Ctrl +/- steps through and remembers.
- New users get a next step on `Home`, empty pages link to `Capture`, and `Setup` and `Capture` are
  simpler with plain error messages.
- The `Optimize` and `Simulate` buttons stay in view, and old results stay on screen marked as out
  of date when settings change.
- The `Encyclopedia` shows every card as an art grid with its text and epiphanies. Game keywords and
  card names in card text open a popover with their definition.
- `Guides` get search and sort, decks open straight in the `Deck Builder`, and rated sheet tables
  such as `Desire Synergy` show as tables with a rating on each row.

### 2026-10-25

- Added `Rossweisse` and her partner `Sig`, along with the `Veiled Radiance` and
  `Snowflake of Our First Meeting` sets.
- Gear now updates live while capture runs. Equipping, upgrading, creating or dismantling memory
  fragments updates the snapshot straight away, and `Combatants`, `Memory Fragments` and `Optimizer`
  refresh by themselves.
- `Rescue Records` shows pity, 50/50 status and a luck score for each banner. The luck score follows
  the game's published rates: 1% per pull, rising by 4.5% a pull from the 58th, with a sure 5-star
  on the 70th.
- 50/50 wins and losses only count on combatant rate-up banners, and the guaranteed 5-star after a
  loss no longer counts as a win.
- A new opt-in setting on `Capture` starts capture when the app opens.
- A capture that fails to start now cleans up the hosts file and certificate right away.
- Substat roll quality is now measured against the piece's own rarity, so a perfect Rare roll shows
  100%. Gear Score itself stays on the Legendary scale.
- Potential now counts one roll per level a piece has left. Fresh Legendary pieces were treated as
  having 4 rolls left instead of 5, and Rare pieces 3 instead of 4.
- Roll ranges and max levels for every rarity now come from the game's own data instead of a
  hand-kept table.
- The separate `Scoring` tab is gone. Its weights now live on `Combatants` and each combatant's
  detail view, and old `Scoring` links open `Combatants`.
- Character and fragment art that fails to load is retried, then shows a placeholder instead of a
  broken image.
- The app is now English-only. Leftover Portuguese text, such as the `Optimizer` stat group labels,
  is translated.
- Capture log lines are now timestamped.
- Every guide has the same set of pages, with set icons, labelled teams, rating colours and card
  costs. Each deck card shows its epiphany, text and cost.
- Each guide draws the author's potentials tree in their colours, with a toggle to the author's
  original picture.
- mitmproxy and Brotli are pinned to patched versions.

### 2026-10-24

- The `Deck Builder` now covers every released character with the game's own card text and art.
- The `Deck Builder`, `Encyclopedia`, gear presets and monster lists are now generated from the
  game's own files instead of kept by hand, so new characters and cards come through by themselves.
- Every character guide is now imported from the community Google Sheet.
- Saved decks keep their cards, apart from 37 epiphanies and 5 tutorial items that are no longer in
  the game.

### 2026-09-05

- Capture now stops with a clear message when a redirect left behind by a crashed run is still in
  place, and points you at `Setup` to remove it. Before this it started anyway and captured nothing.
- The game can no longer be pointed at a dead port during the moment a capture is shutting down.
- The real-time log no longer erases itself a moment after you press `Start`. It was wiping the
  startup messages it had just shown, sometimes leaving the panel blank.
- Two new Memory Fragment sets, `Battlefield Evolution` and `Sanguine Thorn`, are now recognised.
  Their fragments used to show as `Unknown` and counted for nothing when the `Optimizer` scored a
  build, so any build using them was ranked too low.
- `Line of Justice` no longer grants a 2-piece Attack bonus. The game does not give one, so builds
  holding two of its pieces were being scored higher than they actually are.
- Set data is now checked against the game's own files, the same way character data is, and a
  capture holding a set the app does not know now says so instead of failing quietly.

### 2026-09-03

- The certificate is now trusted only while a capture is running and untrusted again the moment it
  stops, so nothing is left behind on your machine between sessions.
- You no longer have to permanently trust the certificate before capture will start.
- If the app is closed or crashes mid-capture, it now removes the redirect and the certificate
  itself. Before this the game could not connect until you launched the app again.
- `Setup` now shows a leftover redirect from a previous session with a button to remove it.
- The packaged app could not reach its own API, so `Setup` reported "Could not connect to the API".
  Fixed - it affected every build, not just some machines.
- Stopping a capture on purpose is no longer reported as an unexpected disconnection.
- The `Capture` prerequisite badges now spin while the checks are still running, instead of looking
  like a result.
- The capture region is worked out from the server the game actually connected to.
- An expired certificate is now detected and reported, and `Setup` no longer re-checks it constantly.
- Added `Arabella` and her partner `Licinia`, `Hilde`, and `Fei`, along with portraits for them and
  for `Westmacott`, `Marin`, `Noel` and `Erica`.
- Corrected several wrong stats: the friendship health bonus was short from level four up, health
  potential nodes were worth 8% rather than 3%, and `Arabella` and `Adelheid` grew on the wrong
  curves. Character data is now checked against the game's own files.
- Releases are now built and published from GitHub, and the app checks this fork for updates instead
  of the project it was forked from.

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
