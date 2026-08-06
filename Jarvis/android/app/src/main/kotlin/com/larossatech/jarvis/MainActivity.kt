package com.larossatech.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.larossatech.jarvis.nudge.NudgeAlarmReceiver
import com.larossatech.jarvis.nudge.NudgeKind
import com.larossatech.jarvis.nudge.NudgePrefs
import com.larossatech.jarvis.nudge.NudgeScheduler
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    // Named for the first nudge that used it; carries both kinds now.
    private val channel = "com.larossatech.jarvis/water"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channel)
            .setMethodCallHandler { call, result ->
                val kind = NudgeKind.from(call.argument<String>("kind"))

                when (call.method) {
                    "canDrawOverlays" -> result.success(Settings.canDrawOverlays(this))

                    "requestOverlayPermission" -> {
                        // Android only lets the user grant this from Settings; we can
                        // deep-link there but not read the outcome synchronously.
                        startActivity(
                            Intent(
                                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                Uri.parse("package:$packageName"),
                            ),
                        )
                        result.success(null)
                    }

                    "canScheduleExactAlarms" -> {
                        val ok = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                            getSystemService(android.app.AlarmManager::class.java)
                                .canScheduleExactAlarms()
                        } else true
                        result.success(ok)
                    }

                    "requestExactAlarmPermission" -> {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                            startActivity(
                                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
                                    .setData(Uri.parse("package:$packageName")),
                            )
                        }
                        result.success(null)
                    }

                    "getSettings" -> result.success(settingsMap(kind))

                    "saveSettings" -> {
                        NudgePrefs.save(
                            this,
                            kind,
                            enabled = call.argument<Boolean>("enabled") ?: false,
                            intervalMin = call.argument<Int>("intervalMin") ?: kind.defIntervalMin,
                            startMin = call.argument<Int>("startMin") ?: kind.defStartMin,
                            endMin = call.argument<Int>("endMin") ?: kind.defEndMin,
                            amount = call.argument<Int>("amount") ?: kind.defAmount,
                        )
                        NudgeScheduler.sync(this, kind)
                        result.success(settingsMap(kind))
                    }

                    // Lets the settings screen prove the overlay works without
                    // waiting out a whole interval.
                    "preview" -> {
                        if (!Settings.canDrawOverlays(this)) {
                            result.success(false)
                        } else {
                            NudgeAlarmReceiver.showOverlay(applicationContext, kind)
                            result.success(true)
                        }
                    }

                    else -> result.notImplemented()
                }
            }
    }

    private fun settingsMap(k: NudgeKind): Map<String, Any> = mapOf(
        "kind" to k.key,
        "enabled" to NudgePrefs.enabled(this, k),
        "intervalMin" to NudgePrefs.intervalMin(this, k),
        "startMin" to NudgePrefs.startMin(this, k),
        "endMin" to NudgePrefs.endMin(this, k),
        "amount" to NudgePrefs.amount(this, k),
        "perNudge" to NudgePrefs.perNudge(this, k),
        "nudgesPerDay" to NudgePrefs.nudgesPerDay(this, k),
        "countToday" to NudgePrefs.countToday(this, k),
        "nextFireAt" to NudgeScheduler.nextFireAt(this, k, System.currentTimeMillis()),
    )
}
