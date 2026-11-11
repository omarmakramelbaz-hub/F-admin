# F-admin browser WebView

This browser version displays the existing Fasakhansta dashboard inside a full-height frame with the mobile app's orange top bar. It provides loading, retry, and direct-open controls.

Deployment target: `https://fasakhaninja.com/f-admin-webview.html`.

The page must be served from `https://fasakhaninja.com` so `/admin/login` uses the dashboard's existing first-party login session. The wrapper does not collect credentials, proxy authenticated requests, or change the dashboard's authentication and cookie settings.

Source: `web-preview/index.html`. The pinned installer under `deployment/webview-20261111` adds only `public/f-admin-webview.html` on the existing server, verifies its served hash, and checks that the login page permits same-origin framing. It refuses to overwrite an unrelated file and supports an already matching installation. It does not run PHP commands, migrations, or database operations.

The Android and iOS app sources continue to use `lib/home_screen.dart`; the browser wrapper has no native build dependency.
