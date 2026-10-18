import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:web_view/home_screen.dart';

void main() {
  late _FakeWebViewPlatform platform;

  setUp(() {
    platform = _FakeWebViewPlatform();
    InAppWebViewPlatform.instance = platform;
  });

  Future<void> openDashboard(WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    platform.latest.params.onWebViewCreated?.call(platform.controller);
  }

  WebResourceRequest request({bool? isForMainFrame = true}) {
    return WebResourceRequest(
      url: WebUri('https://fasakhaninja.com/admin/login'),
      isForMainFrame: isForMainFrame,
    );
  }

  WebResourceError networkError() => WebResourceError(
        description: 'Host lookup failed',
        type: WebResourceErrorType.HOST_LOOKUP,
      );

  testWidgets('failed page stops loading and can be retried', (tester) async {
    await openDashboard(tester);
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);

    platform.latest.params.onReceivedError!(
      platform.controller,
      request(),
      networkError(),
    );
    await tester.pump();

    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(find.text('إعادة المحاولة'), findsOneWidget);

    // WebViews may still report completion after a failed navigation.
    platform.latest.params.onLoadStop!(platform.controller, null);
    platform.latest.params.onProgressChanged!(platform.controller, 100);
    await tester.pump();
    expect(find.text('إعادة المحاولة'), findsOneWidget);

    await tester.tap(find.text('إعادة المحاولة'));
    await tester.pump();
    expect(platform.controllerPlatform.reloadCount, 1);
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(find.text('إعادة المحاولة'), findsNothing);

    platform.latest.params.onLoadStop!(platform.controller, null);
    await tester.pump();
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(find.text('إعادة المحاولة'), findsNothing);
  });

  testWidgets('resource errors and cancellations do not hide dashboard', (
    tester,
  ) async {
    await openDashboard(tester);
    platform.latest.params.onLoadStop!(platform.controller, null);
    platform.latest.params.onReceivedError!(
      platform.controller,
      request(isForMainFrame: false),
      networkError(),
    );
    platform.latest.params.onReceivedError!(
      platform.controller,
      request(),
      WebResourceError(
        description: 'Navigation cancelled',
        type: WebResourceErrorType.CANCELLED,
      ),
    );
    await tester.pump();

    expect(find.text('إعادة المحاولة'), findsNothing);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
  });

  testWidgets('navigation error without frame metadata is recoverable', (
    tester,
  ) async {
    await openDashboard(tester);
    platform.latest.params.onReceivedError!(
      platform.controller,
      request(isForMainFrame: null),
      networkError(),
    );
    await tester.pump();
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('retry failure restores retry action', (tester) async {
    await openDashboard(tester);
    platform.controllerPlatform.failReload = true;
    platform.latest.params.onReceivedError!(
      platform.controller,
      request(),
      networkError(),
    );
    await tester.pump();
    await tester.tap(find.text('إعادة المحاولة'));
    await tester.pump();

    expect(find.text('إعادة المحاولة'), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'callbacks after closing dashboard do not update disposed state',
    (tester) async {
      await openDashboard(tester);
      final callbacks = platform.latest.params;
      await tester.pumpWidget(const SizedBox.shrink());

      callbacks.onLoadStart!(platform.controller, null);
      callbacks.onLoadStop!(platform.controller, null);
      callbacks.onProgressChanged!(platform.controller, 50);
      callbacks.onReceivedError!(
        platform.controller,
        request(),
        networkError(),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
    },
  );
}

class _FakeWebViewPlatform extends InAppWebViewPlatform {
  final controllerPlatform = _FakeWebViewController();
  late final controller = InAppWebViewController.fromPlatform(
    platform: controllerPlatform,
  );
  late _FakeWebView latest;

  @override
  PlatformInAppWebViewWidget createPlatformInAppWebViewWidget(
    PlatformInAppWebViewWidgetCreationParams params,
  ) {
    return latest = _FakeWebView(params);
  }
}

class _FakeWebView extends PlatformInAppWebViewWidget {
  _FakeWebView(super.params) : super.implementation();

  @override
  Widget build(BuildContext context) => const SizedBox.expand();

  @override
  T controllerFromPlatform<T>(PlatformInAppWebViewController controller) {
    return params.controllerFromPlatform!(controller) as T;
  }

  @override
  void dispose() {}
}

class _FakeWebViewController extends PlatformInAppWebViewController {
  _FakeWebViewController()
      : super.implementation(
          const PlatformInAppWebViewControllerCreationParams(id: 1),
        );

  int reloadCount = 0;
  bool failReload = false;

  @override
  Future<void> reload() async {
    reloadCount++;
    if (failReload) throw StateError('Reload failed');
  }
}
