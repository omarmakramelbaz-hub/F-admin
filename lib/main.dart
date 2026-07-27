import 'package:flutter/material.dart';

import 'splash_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Faskhangy Dashboard",
      debugShowCheckedModeBanner: false,
      theme: ThemeData(primaryColor: const Color(0xFFFFFFFF), scaffoldBackgroundColor: const Color(0xFFFFFFFF)),
      home: const SplashScreen(),
    );
  }
}
