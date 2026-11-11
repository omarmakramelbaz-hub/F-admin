# F-admin browser WebView

This browser version starts with the mobile app's original `assets/dashGif.gif` opening for three seconds while the dashboard loads behind it. It then displays the existing Fasakhansta dashboard inside a full-height frame with the mobile app's orange top bar. It provides loading, retry, and direct-open controls; a failed opening image immediately reveals the dashboard/loading state.

Deployment target: `https://fasakhaninja.com/f-admin-webview.html`.

The page must be served from `https://fasakhaninja.com` so `/admin/login` uses the dashboard's existing first-party login session. The wrapper does not collect credentials, proxy authenticated requests, or change the dashboard's authentication and cookie settings.

Source: `web-preview/index.html`. The pinned installer under `deployment/webview-20261111` adds only `public/f-admin-webview.html` on the existing server, verifies its served hash, and checks that the login page permits same-origin framing. It refuses to overwrite an unrelated file and supports an already matching installation. It does not run PHP commands, migrations, or database operations.

The Android and iOS app sources continue to use `lib/home_screen.dart`; the browser wrapper has no native build dependency.

After the initial web preview is installed, the pinned upgrade in `deployment/webview-opening-20261111` updates only `public/f-admin-webview.html` and adds `public/f-admin-webview-opening.gif`. It verifies the known installed HTML baseline, retains a private copy for rollback, installs the original GIF before the updated page, and checks both served file hashes. The GIF is reused unchanged from the app's assets.
