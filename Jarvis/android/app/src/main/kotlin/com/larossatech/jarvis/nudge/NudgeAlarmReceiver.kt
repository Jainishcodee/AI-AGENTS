package com.larossatech.jarvis.nudge

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
class NudgeAlarmReceiver : BroadcastReceiver() {

    companion object {
        const val EXTRA_KIND = "kind"

        /** Starts the overlay, preferring a plain start so there's no notification. */
        fun showOverlay(context: Context, kind: NudgeKind) {
            if (!Settings.canDrawOverlays(context)) return
            val svc = Intent(context, NudgeOverlayService::class.java)
                .putExtra(EXTRA_KIND, kind.key)
            try {
                context.startService(svc)
            } catch (_: Throwable) {
                // Background-start restrictions: fall back to a foreground service.
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    svc.putExtra(NudgeOverlayService.EXTRA_FOREGROUND, true)
                    try {
                        context.startForegroundService(svc)
                    } catch (_: Throwable) {
                        // Nothing more to try; the next alarm will have another go.
                    }
                }
            }
        }
    }

    override fun onReceive(context: Context, intent: Intent?) {
        val app = context.applicationContext
        when (intent?.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            "android.intent.action.QUICKBOOT_POWERON" -> NudgeScheduler.syncAll(app)

            else -> {
                val kind = NudgeKind.from(intent?.getStringExtra(EXTRA_KIND))
                if (NudgePrefs.enabled(app, kind)) showOverlay(app, kind)
                // Re-arm even when the overlay was skipped, or the chain stops here.
                NudgeScheduler.sync(app, kind)
            }
        }
    }
}
