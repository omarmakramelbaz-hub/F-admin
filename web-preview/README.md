# F-admin browser WebView

This browser version opens the existing Fasakhansta dashboard directly inside a full-height frame. There is no opening screen, video, visible loading screen, artificial delay, or top bar. The frame is visible immediately and throughout retries. A bounded 250ms check recognizes a same-origin document once its DOM is interactive or complete, without waiting for remote assets; it reads only document readiness and body element presence. Only failed, blank, or timed-out loads reveal troubleshooting with retry and direct-open controls. The wrapper and recovery screen use a dark background; the actual dashboard retains its own styling.

Deployment target: `https://fasakhaninja.com/f-admin-webview.html`.

The page must be served from `https://fasakhaninja.com` so `/admin/login` uses the dashboard's existing first-party login session. The wrapper does not collect credentials, proxy authenticated requests, or change the dashboard's authentication and cookie settings.

Source: `web-preview/index.html`. Both the favicon and Apple touch icon use the existing GO brand at `/f-admin-dashboard-icon.png`. The wrapper hides only the dashboard document's `html` and `body` scrollbar visuals on each same-origin page load. Scrolling remains enabled, and internal lists and tables retain their own scrollbars. Later external pages are left untouched.

The browser wrapper has no native build dependency. It uses the real `/admin/login` page and keeps dashboard navigation and authentication in the existing application.

The scoped pinned installer verifies known installed baselines and file hashes, keeps private rollback copies, and checks the served page. The direct version needs only the HTML wrapper and GO icon; it does not deploy an opening video, change global dashboard styles, run PHP commands or migrations, or alter database data.

The native app now starts `HomeScreen` directly and opens this wrapper. Its orange AppBar is removed. Android uses the native system-bar controller, restores immersive display after app focus and keyboard dismissal, and permits temporary system gestures. iOS requests hidden status UI and automatic home-indicator hiding; system gestures remain controlled by iOS. The standard operating-system launch is dark and contains no timed animation.

`assets/dashboard-icon.svg` preserves the existing GO vector paths and white/cyan gradient. `assets/dashboard-icon.png` is the approved 1024px render. Run `python scripts/generate_app_icons.py` after installing Pillow 13.0.0 to package the Android/iOS bitmap resources. The script preserves its source and produces opaque Apple icons.

Validation: `node web-preview/test-direct.cjs`, `python -m unittest discover -s deployment/webview-direct-20261111 -p 'test_install.py'`, `python -m unittest discover -s test -p 'test_generate_app_icons.py'`, `flutter analyze`, and `flutter test`. The branch-scoped Native preview workflow also builds a debug Android APK and compiles the iOS simulator app without signing. The Android debug package ends in `.preview`, so it installs beside the store app; release identifiers and signing configuration remain unchanged.

Deploy the direct wrapper before testing the rebuilt mobile app. Updating HTML alone cannot hide Android system bars or change the installed app's launcher icon. Store distribution requires a normal signed app release.
