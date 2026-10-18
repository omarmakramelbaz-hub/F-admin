# Fasakhansta Dashboard

Flutter shell for the Fasakhansta admin dashboard at
`https://fasakhaninja.com/admin/login`.

## Code layout

- `lib/main.dart`: application and theme.
- `lib/splash_screen.dart`: starts the live dashboard behind the existing
  three-second splash, then reveals the same WebView without restarting it.
- `lib/home_screen.dart`: WebView, loading indicator, and retry after a failed
  page load. Dashboard authentication and business logic live in the backend.

## Checks

Use Flutter 3.47.0 (Dart 3.13.0), matching the code-quality workflow and the
verified dependency lock file.

```sh
flutter pub get
dart format --output=none --set-exit-if-changed lib/home_screen.dart lib/splash_screen.dart test
flutter analyze
flutter test
```

The tests substitute the WebView platform to check failed page loads, retries,
resource errors, cancelled navigation, and late callbacks after closing the
screen. They also check that loading starts during the splash and that loading
updates and splash completion preserve the existing WebView. Native Android/iOS
builds and live dashboard flows still need device verification.

## Native configuration

The FileProvider in `android/app/src/main/AndroidManifest.xml` follows the
[InAppWebView setup](https://inappwebview.dev/docs/intro/).
The `.flutter_inappwebview_android.fileprovider` authority matches
`InAppWebViewFileProvider.fileProviderAuthorityExtension` in the locked
`flutter_inappwebview_android` 1.1.3 package. Its `provider_paths.xml` resource is
supplied by that package; Android reads the resource through the
`android.support.FILE_PROVIDER_PATHS` metadata key. Verify gallery and camera
uploads on Android before distributing a new build.

iOS version and build numbers follow `pubspec.yaml` through
`FLUTTER_BUILD_NAME` and `FLUTTER_BUILD_NUMBER` in `Info.plist`, so Flutter build
overrides also reach the app bundle.
