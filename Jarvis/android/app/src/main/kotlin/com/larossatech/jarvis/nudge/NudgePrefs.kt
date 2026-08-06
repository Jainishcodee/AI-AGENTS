package com.larossatech.jarvis.nudge

import android.content.Context
import java.util.Calendar

/**
 * Settings and the running day-count, one store per nudge kind.
 *
 * Native owns this rather than Flutter's shared_preferences: the alarm fires
 * when no Dart isolate is alive, so the receiver has to read the schedule on
 * its own.
 */
object NudgePrefs {
    private const val K_ENABLED = "enabled"
    private const val K_INTERVAL = "interval_min"
    private const val K_START = "start_min"
    private const val K_END = "end_min"
    private const val K_AMOUNT = "target_ml" // legacy key name, kept for WATER
    private const val K_COUNT_DAY = "count_day"
    private const val K_COUNT = "count"

    private fun prefs(c: Context, k: NudgeKind) =
        c.getSharedPreferences(k.prefsFile, Context.MODE_PRIVATE)

    fun enabled(c: Context, k: NudgeKind) = prefs(c, k).getBoolean(K_ENABLED, false)
    fun intervalMin(c: Context, k: NudgeKind) = prefs(c, k).getInt(K_INTERVAL, k.defIntervalMin)
    fun startMin(c: Context, k: NudgeKind) = prefs(c, k).getInt(K_START, k.defStartMin)
    fun endMin(c: Context, k: NudgeKind) = prefs(c, k).getInt(K_END, k.defEndMin)
    fun amount(c: Context, k: NudgeKind) = prefs(c, k).getInt(K_AMOUNT, k.defAmount)

    fun save(
        c: Context,
        k: NudgeKind,
        enabled: Boolean,
        intervalMin: Int,
        startMin: Int,
        endMin: Int,
        amount: Int,
    ) {
        val amountRange = if (k == NudgeKind.WATER) 500..6000 else 5..300
        prefs(c, k).edit()
            .putBoolean(K_ENABLED, enabled)
            .putInt(K_INTERVAL, intervalMin.coerceIn(5, 240))
            .putInt(K_START, startMin.coerceIn(0, 24 * 60 - 1))
            .putInt(K_END, endMin.coerceIn(0, 24 * 60 - 1))
            .putInt(K_AMOUNT, amount.coerceIn(amountRange.first, amountRange.last))
            .apply()
    }

    fun windowMinutes(c: Context, k: NudgeKind): Int {
        val s = startMin(c, k)
        val e = endMin(c, k)
        // An end before the start means the window runs past midnight.
        return if (e > s) e - s else (24 * 60 - s) + e
    }

    fun nudgesPerDay(c: Context, k: NudgeKind): Int =
        (windowMinutes(c, k) / intervalMin(c, k)).coerceAtLeast(1)

    /**
     * What one nudge is worth. Millilitres for water; for eyes the "amount" is
     * already the break length, so it passes straight through.
     */
    fun perNudge(c: Context, k: NudgeKind): Int = when (k) {
        NudgeKind.WATER -> {
            val raw = amount(c, k).toDouble() / nudgesPerDay(c, k)
            ((raw / 10.0).toInt() * 10).coerceAtLeast(50)
        }
        NudgeKind.EYES -> amount(c, k)
    }

    // ----------------------------------------------------------- day counter

    private fun today(): String {
        val cal = Calendar.getInstance()
        return "%04d-%02d-%02d".format(
            cal.get(Calendar.YEAR),
            cal.get(Calendar.MONTH) + 1,
            cal.get(Calendar.DAY_OF_MONTH),
        )
    }

    fun countToday(c: Context, k: NudgeKind): Int {
        val p = prefs(c, k)
        return if (p.getString(K_COUNT_DAY, "") == today()) p.getInt(K_COUNT, 0) else 0
    }

    fun markDone(c: Context, k: NudgeKind): Int {
        val next = countToday(c, k) + 1
        prefs(c, k).edit().putString(K_COUNT_DAY, today()).putInt(K_COUNT, next).apply()
        return next
    }
}
