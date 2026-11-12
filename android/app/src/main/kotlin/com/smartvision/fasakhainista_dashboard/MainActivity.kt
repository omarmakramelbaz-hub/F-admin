package com.smartvision.fasakhainista_dashboard

import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewTreeObserver
import android.view.WindowInsets
import android.view.WindowInsetsController
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    private var keyboardVisible = false
    private val restoreImmersive = Runnable { hideSystemBars() }
    private val layoutListener = ViewTreeObserver.OnGlobalLayoutListener {
        val visible = isKeyboardVisible()
        if (keyboardVisible && !visible) {
            // Android protects system UI changes for one second after IME close.
            window.decorView.removeCallbacks(restoreImmersive)
            window.decorView.postDelayed(restoreImmersive, 1100L)
        }
        keyboardVisible = visible
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.viewTreeObserver.addOnGlobalLayoutListener(layoutListener)
    }

    override fun onPostResume() {
        super.onPostResume()
        window.decorView.post(restoreImmersive)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) window.decorView.post(restoreImmersive)
    }

    private fun isKeyboardVisible(): Boolean {
        val decor = window.decorView
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return decor.rootWindowInsets?.isVisible(WindowInsets.Type.ime()) == true
        }
        val visibleFrame = Rect()
        decor.getWindowVisibleDisplayFrame(visibleFrame)
        return decor.rootView.height - visibleFrame.bottom > decor.rootView.height * 0.2
    }

    @Suppress("DEPRECATION")
    private fun hideSystemBars() {
        // Login and other forms keep their keyboard; restore only after it closes.
        if (!window.decorView.hasWindowFocus() || isKeyboardVisible()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.apply {
                systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                hide(WindowInsets.Type.systemBars())
            }
        } else {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_FULLSCREEN
        }
    }

    override fun onDestroy() {
        window.decorView.removeCallbacks(restoreImmersive)
        window.decorView.viewTreeObserver.removeOnGlobalLayoutListener(layoutListener)
        super.onDestroy()
    }
}
