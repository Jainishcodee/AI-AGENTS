package com.larossatech.jarvis.water

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.util.Calendar

/**
 * Arms the next water nudge.
 *
 * One alarm at a time, re-armed after each fire, rather than a repeating alarm:
 * setRepeating can't be exact on modern Android, and re-arming is what lets the
 * interval or the waking window change without cancelling anything.
 */
object WaterScheduler {
    private const val REQUEST = 7311

    private fun pendingIntent(c: Context): PendingIntent {
        val intent = Intent(c, WaterAlarmReceiver::class.java).setAction(WaterAlarmReceiver.ACTION_NUDGE)
        var flags = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags = flags or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getBroadcast(c.applicationContext, REQUEST, intent, flags)
    }

    fun cancel(c: Context) {
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.cancel(pendingIntent(c))
    }

    /** Re-arms if enabled, cancels if not. Safe to call from anywhere, repeatedly. */
    fun sync(c: Context) {
        if (!WaterPrefs.enabled(c)) {
            cancel(c)
            return
        }
        val at = nextFireAt(c, System.currentTimeMillis())
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pi = pendingIntent(c)

        val exact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S || am.canScheduleExactAlarms()
        if (exact) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        } else {
            // Without the exact-alarm grant the nudge still lands, just loosely.
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        }
    }

    /**
     * Next nudge at [from] + interval, pushed to the start of the window if that
     * lands outside waking hours. Exposed for the settings screen's "next at" line.
     */
    fun nextFireAt(c: Context, from: Long): Long {
        val interval = WaterPrefs.intervalMin(c) * 60_000L
        val candidate = from + interval
        return clampIntoWindow(c, candidate)
    }

    private fun clampIntoWindow(c: Context, at: Long): Long {
        val start = WaterPrefs.startMin(c)
        val end = WaterPrefs.endMin(c)
        if (start == end) return at // 24h window, nothing to clamp

        val cal = Calendar.getInstance().apply { timeInMillis = at }
        val minute = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)

        val inside = if (end > start) minute in start until end
                     else minute >= start || minute < end // window crosses midnight
        if (inside) return at

        // Outside the window: jump to the next window opening.
        val open = Calendar.getInstance().apply {
            timeInMillis = at
            set(Calendar.HOUR_OF_DAY, start / 60)
            set(Calendar.MINUTE, start % 60)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (open.timeInMillis <= at) open.add(Calendar.DAY_OF_YEAR, 1)
        return open.timeInMillis
    }
}
