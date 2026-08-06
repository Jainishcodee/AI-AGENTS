package com.larossatech.jarvis.nudge

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import java.util.Calendar

/**
 * Arms the next nudge of a given kind.
 *
 * One alarm at a time per kind, re-armed after each fire, rather than a
 * repeating alarm: setRepeating can't be exact on modern Android, and re-arming
 * is what lets the interval or window change without cancelling anything.
 *
 * The two kinds must not collide, so each carries its own action string *and*
 * request code — extras alone don't distinguish PendingIntents.
 */
object NudgeScheduler {

    private fun pendingIntent(c: Context, k: NudgeKind): PendingIntent {
        val intent = Intent(c, NudgeAlarmReceiver::class.java)
            .setAction(k.action)
            .putExtra(NudgeAlarmReceiver.EXTRA_KIND, k.key)
        var flags = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags = flags or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getBroadcast(c.applicationContext, k.requestCode, intent, flags)
    }

    fun cancel(c: Context, k: NudgeKind) {
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.cancel(pendingIntent(c, k))
    }

    /** Re-arms if enabled, cancels if not. Safe to call anywhere, repeatedly. */
    fun sync(c: Context, k: NudgeKind) {
        if (!NudgePrefs.enabled(c, k)) {
            cancel(c, k)
            return
        }
        val at = nextFireAt(c, k, System.currentTimeMillis())
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pi = pendingIntent(c, k)

        val exact = Build.VERSION.SDK_INT < Build.VERSION_CODES.S || am.canScheduleExactAlarms()
        if (exact) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        } else {
            // Without the exact-alarm grant the nudge still lands, just loosely.
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        }
    }

    fun syncAll(c: Context) = NudgeKind.entries.forEach { sync(c, it) }

    /**
     * Next nudge at [from] + interval, pushed to the start of the window if
     * that lands outside waking hours.
     */
    fun nextFireAt(c: Context, k: NudgeKind, from: Long): Long =
        clampIntoWindow(c, k, from + NudgePrefs.intervalMin(c, k) * 60_000L)

    private fun clampIntoWindow(c: Context, k: NudgeKind, at: Long): Long {
        val start = NudgePrefs.startMin(c, k)
        val end = NudgePrefs.endMin(c, k)
        if (start == end) return at // 24h window, nothing to clamp

        val cal = Calendar.getInstance().apply { timeInMillis = at }
        val minute = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)

        val inside = if (end > start) minute in start until end
                     else minute >= start || minute < end // window crosses midnight
        if (inside) return at

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
