package com.larossatech.jarvis.water

import android.content.Context
import java.util.Calendar

/**
 * Settings and the running day-count for the water nudge.
 *
 * Native owns this store rather than Flutter's shared_preferences: the alarm
 * fires when no Dart isolate is alive, so the receiver has to be able to read
 * the schedule on its own.
 */
object WaterPrefs {
    private const val FILE = "jarvis_water"

    private const val K_ENABLED = "enabled"
    private const val K_INTERVAL = "interval_min"
    private const val K_START = "start_min"
    private const val K_END = "end_min"
    private const val K_TARGET = "target_ml"
    private const val K_COUNT_DAY = "count_day"
    private const val K_COUNT = "count"

    // 45 min over a 07:00-22:00 window lands ~20 nudges of ~150 ml, which is the
    // ~3 L/day of drinking water the NASEM adequate intake implies for an adult
    // male once the ~20% that comes from food is taken out.
    const val DEF_INTERVAL = 45
    const val DEF_START = 7 * 60
    const val DEF_END = 22 * 60
    const val DEF_TARGET = 3000

    private fun prefs(c: Context) = c.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun enabled(c: Context) = prefs(c).getBoolean(K_ENABLED, false)
    fun intervalMin(c: Context) = prefs(c).getInt(K_INTERVAL, DEF_INTERVAL)
    fun startMin(c: Context) = prefs(c).getInt(K_START, DEF_START)
    fun endMin(c: Context) = prefs(c).getInt(K_END, DEF_END)
    fun targetMl(c: Context) = prefs(c).getInt(K_TARGET, DEF_TARGET)

    fun save(
        c: Context,
        enabled: Boolean,
        intervalMin: Int,
        startMin: Int,
        endMin: Int,
        targetMl: Int,
    ) {
        prefs(c).edit()
            .putBoolean(K_ENABLED, enabled)
            .putInt(K_INTERVAL, intervalMin.coerceIn(15, 240))
            .putInt(K_START, startMin.coerceIn(0, 24 * 60 - 1))
            .putInt(K_END, endMin.coerceIn(0, 24 * 60 - 1))
            .putInt(K_TARGET, targetMl.coerceIn(500, 6000))
            .apply()
    }

    /** How many nudges fit in the waking window, so each one carries a real amount. */
    fun nudgesPerDay(c: Context): Int {
        val window = windowMinutes(c)
        return (window / intervalMin(c)).coerceAtLeast(1)
    }

    fun windowMinutes(c: Context): Int {
        val s = startMin(c)
        val e = endMin(c)
        // An end before the start means the window runs past midnight.
        return if (e > s) e - s else (24 * 60 - s) + e
    }

    /** Millilitres to suggest per nudge, rounded to something pourable. */
    fun perNudgeMl(c: Context): Int {
        val raw = targetMl(c).toDouble() / nudgesPerDay(c)
        return ((raw / 10.0).toInt() * 10).coerceAtLeast(50)
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

    fun countToday(c: Context): Int {
        val p = prefs(c)
        return if (p.getString(K_COUNT_DAY, "") == today()) p.getInt(K_COUNT, 0) else 0
    }

    fun markDrunk(c: Context): Int {
        val next = countToday(c) + 1
        prefs(c).edit().putString(K_COUNT_DAY, today()).putInt(K_COUNT, next).apply()
        return next
    }
}
