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
        try {
            if (exact) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
            } else {
                // Without the exact-alarm grant the nudge still lands, just loosely.
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
            }
        } catch (e: SecurityException) {
            // The grant can be revoked between the check above and this call.
            // Throwing here would kill the receiver and with it the whole chain,
            // so drop to an inexact alarm rather than stop nudging entirely.
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        }
    }

    fun syncAll(c: Context) {
        NudgeKind.entries.forEach { sync(c, it) }
        syncWatchdog(c)
    }

    // ---------------------------------------------------------- watchdog

    private const val WATCHDOG_ACTION = "com.larossatech.jarvis.NUDGE_WATCHDOG"
    private const val WATCHDOG_REQUEST = 7399
    private const val WATCHDOG_PERIOD = AlarmManager.INTERVAL_HALF_HOUR

    private fun watchdogIntent(c: Context): PendingIntent {
        val intent = Intent(c, NudgeAlarmReceiver::class.java).setAction(WATCHDOG_ACTION)
        var flags = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags = flags or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getBroadcast(c.applicationContext, WATCHDOG_REQUEST, intent, flags)
    }

    fun isWatchdog(action: String?) = action == WATCHDOG_ACTION

    /**
     * A slow repeating alarm whose only job is to re-arm the exact ones.
     *
     * The per-nudge alarms form a chain — each fire schedules the next — so a
     * single dropped link stops them forever. A dropped link is not exotic:
     * aggressive OEM battery managers, a force-stop, or a revoked exact-alarm
     * grant will all do it, which is what made the nudges work for a day and
     * then quietly stop. This is inexact and repeating, so the system owns it
     * and keeps redelivering even when the chain is broken.
     */
    fun syncWatchdog(c: Context) {
        val am = c.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pi = watchdogIntent(c)
        val anyOn = NudgeKind.entries.any { NudgePrefs.enabled(c, it) }
        if (!anyOn) {
            am.cancel(pi)
            return
        }
        am.setInexactRepeating(
            AlarmManager.RTC_WAKEUP,
            System.currentTimeMillis() + WATCHDOG_PERIOD,
            WATCHDOG_PERIOD,
            pi,
        )
    }

    /** Re-arms any enabled nudge whose alarm has gone missing. */
    fun heal(c: Context) {
        NudgeKind.entries.forEach { k ->
            if (NudgePrefs.enabled(c, k)) sync(c, k)
        }
    }

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
