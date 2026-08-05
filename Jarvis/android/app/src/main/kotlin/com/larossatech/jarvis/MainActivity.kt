package com.larossatech.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.larossatech.jarvis.water.WaterAlarmReceiver
import com.larossatech.jarvis.water.WaterPrefs
import com.larossatech.jarvis.water.WaterScheduler
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private val channel = "com.larossatech.jarvis/water"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channel)
            .setMethodCallHandler { call, result ->
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
                            val am = getSystemService(android.app.AlarmManager::class.java)
                            am.canScheduleExactAlarms()
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

                    "getSettings" -> result.success(settingsMap())

                    "saveSettings" -> {
                        WaterPrefs.save(
                            this,
                            enabled = call.argument<Boolean>("enabled") ?: false,
                            intervalMin = call.argument<Int>("intervalMin") ?: WaterPrefs.DEF_INTERVAL,
                            startMin = call.argument<Int>("startMin") ?: WaterPrefs.DEF_START,
                            endMin = call.argument<Int>("endMin") ?: WaterPrefs.DEF_END,
                            targetMl = call.argument<Int>("targetMl") ?: WaterPrefs.DEF_TARGET,
                        )
                        WaterScheduler.sync(this)
                        result.success(settingsMap())
                    }

                    // Lets the settings screen prove the overlay works without
                    // waiting out a whole interval.
                    "preview" -> {
                        if (!Settings.canDrawOverlays(this)) {
                            result.success(false)
                        } else {
                            WaterAlarmReceiver.showOverlay(applicationContext)
                            result.success(true)
                        }
                    }

                    else -> result.notImplemented()
                }
            }
    }

    private fun settingsMap(): Map<String, Any> = mapOf(
        "enabled" to WaterPrefs.enabled(this),
        "intervalMin" to WaterPrefs.intervalMin(this),
        "startMin" to WaterPrefs.startMin(this),
        "endMin" to WaterPrefs.endMin(this),
        "targetMl" to WaterPrefs.targetMl(this),
        "perNudgeMl" to WaterPrefs.perNudgeMl(this),
        "nudgesPerDay" to WaterPrefs.nudgesPerDay(this),
        "countToday" to WaterPrefs.countToday(this),
        "nextFireAt" to WaterScheduler.nextFireAt(this, System.currentTimeMillis()),
    )
}
