import 'dart:async';

import 'package:flutter/material.dart';

import 'home_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  late final Timer _splashTimer;
  bool _showSplash = true;

  @override
  void initState() {
    super.initState();
    _splashTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => _showSplash = false);
    });
  }

  @override
  void dispose() {
    _splashTimer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Load the live dashboard while the existing splash animation runs.
        ExcludeSemantics(
          excluding: _showSplash,
          child: IgnorePointer(
            ignoring: _showSplash,
            child: const HomeScreen(),
          ),
        ),
        if (_showSplash)
          Scaffold(
            backgroundColor: const Color(0xFFF47221),
            body: Image.asset(
              'assets/dashGif.gif',
              width: double.infinity,
              height: double.infinity,
              fit: BoxFit.fill,
            ),
          ),
      ],
    );
  }
}
