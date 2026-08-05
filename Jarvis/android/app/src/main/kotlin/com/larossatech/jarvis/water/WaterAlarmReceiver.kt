package com.larossatech.jarvis.water

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings

/**
 * Fires on the alarm: show the overlay, then arm the next one.
 *
 * Also handles BOOT_COMPLETED — alarms don't survive a reboot, so without this
 * the nudges would silently stop until the app was opened again.
 */
class WaterAlarmReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_NUDGE = "com.larossatech.jarvis.WATER_NUDGE"

        /** Starts the overlay service, preferring a plain start so there's no notification. */
        fun showOverlay(context: Context) {
            if (!Settings.canDrawOverlays(context)) return
            val svc = Intent(context, WaterOverlayService::class.java)
            try {
                context.startService(svc)
            } catch (_: Throwable) {
                // Background-start restrictions: fall back to a foreground service.
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    svc.putExtra(WaterOverlayService.EXTRA_FOREGROUND, true)
                    context.startForegroundService(svc)
                }
            }
        }
    }

    override fun onReceive(context: Context, intent: Intent?) {
        val app = context.applicationContext
        when (intent?.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            "android.intent.action.QUICKBOOT_POWERON" -> {
                WaterScheduler.sync(app)
            }
            else -> {
                if (WaterPrefs.enabled(app)) showOverlay(app)
                // Re-arm even when the overlay was skipped, or the chain stops here.
                WaterScheduler.sync(app)
            }
        }
    }
}
