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
  bool _isLoading = true;
  bool _hasLoadError = false;

  void _startLoading() {
    if (!mounted) return;

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
    if (!mounted) return;

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
      appBar: const CustomAppBar(),
      body: Stack(
        children: [
          InAppWebView(
            initialUrlRequest: URLRequest(
              url: WebUri('https://fasakhaninja.com/admin/login'),
            ),
            initialSettings: InAppWebViewSettings(
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
          ),
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
            const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CupertinoActivityIndicator(radius: 15),
                  SizedBox(height: 10),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class CustomAppBar extends StatelessWidget implements PreferredSizeWidget {
  const CustomAppBar({super.key});

  @override
  Widget build(BuildContext context) {
    return AppBar(
      flexibleSpace: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xffFD7201), Color(0xffFF9D4D)],
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
          ),
        ),
      ),
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(10);
}
