import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  InAppWebViewController? _webViewController;
  late final InAppWebView _webView;
  bool _isLoading = true;
  bool _hasLoadError = false;

  @override
  void initState() {
    super.initState();
    // Loading overlays can rebuild without reconstructing the native view.
    _webView = _createWebView();
  }

  InAppWebView _createWebView() {
    return InAppWebView(
      initialUrlRequest: URLRequest(
        url: WebUri('https://fasakhaninja.com/f-admin-webview.html'),
      ),
      initialSettings: InAppWebViewSettings(
        transparentBackground: true,
        javaScriptEnabled: true,
        allowFileAccess: true,
        mediaPlaybackRequiresUserGesture: false,
        allowsInlineMediaPlayback: true,
        preferredContentMode: UserPreferredContentMode.MOBILE,
      ),
      onWebViewCreated: (controller) => _webViewController = controller,
      onLoadStart: (_, __) => _startLoading(),
      onLoadStop: (_, __) => _setLoading(false),
      onProgressChanged: (_, progress) => _setLoading(progress < 100),
      onReceivedError: (_, request, error) {
        // Failed images and cancelled navigations must not hide a working
        // dashboard. iOS may omit isForMainFrame for navigation errors.
        if (request.isForMainFrame == false ||
            error.type == WebResourceErrorType.CANCELLED) {
          return;
        }
        _showLoadError();
      },
    );
  }

  void _startLoading() {
    if (!mounted || (_isLoading && !_hasLoadError)) return;

    setState(() {
      _isLoading = true;
      _hasLoadError = false;
    });
  }

  void _setLoading(bool isLoading) {
    if (!mounted || _hasLoadError || _isLoading == isLoading) return;

    setState(() => _isLoading = isLoading);
  }

  void _showLoadError() {
    if (!mounted || (_hasLoadError && !_isLoading)) return;

    setState(() {
      _isLoading = false;
      _hasLoadError = true;
    });
  }

  Future<void> _retryLoading() async {
    final controller = _webViewController;
    if (controller == null) return;

    _startLoading();
    try {
      await controller.reload();
    } catch (_) {
      _showLoadError();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF091320),
      body: Stack(
        fit: StackFit.expand,
        children: [
          _webView,
          if (_hasLoadError)
            Positioned.fill(
              child: ColoredBox(
                color: Theme.of(context).scaffoldBackgroundColor,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'تعذّر تحميل الصفحة. تأكد من اتصال الإنترنت وحاول مرة أخرى.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: _retryLoading,
                          child: const Text('إعادة المحاولة'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          if (_isLoading)
            const Positioned(
              top: 12,
              right: 12,
              child: IgnorePointer(
                child: CupertinoActivityIndicator(
                  radius: 10,
                  color: Color(0xFF28C5E9),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
