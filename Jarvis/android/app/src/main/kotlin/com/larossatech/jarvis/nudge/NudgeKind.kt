package com.larossatech.jarvis.nudge

import com.larossatech.jarvis.R

/**
 * The two things Jarvis interrupts you for. Everything that differs between
 * them — schedule defaults, artwork, alarm identity, copy — lives here, so the
 * scheduler, receiver and overlay stay kind-agnostic.
 */
enum class NudgeKind(
    val key: String,
    val prefsFile: String,
    val action: String,
    val requestCode: Int,
    val defIntervalMin: Int,
    val defStartMin: Int,
    val defEndMin: Int,
    /** Water: millilitres to drink per day. Eyes: seconds to look away for. */
    val defAmount: Int,
) {
    /**
     * 45 min over 07:00-22:00 is ~20 nudges of ~150 ml, which is the ~3 L of
     * drinking water the NASEM adequate intake implies once the ~20% that comes
     * from food is removed.
     */
    WATER(
        key = "water",
        prefsFile = "jarvis_water", // unchanged, so existing settings survive
        action = "com.larossatech.jarvis.WATER_NUDGE",
        requestCode = 7311,
        defIntervalMin = 45,
        defStartMin = 7 * 60,
        defEndMin = 22 * 60,
        defAmount = 3000,
    ),

    /**
     * The 20-20-20 rule: every 20 minutes, look at something 20 feet away for
     * 20 seconds. Endorsed by the American Optometric Association; the evidence
     * for the exact numbers is thin, which is why the break length is settable.
     */
    EYES(
        key = "eyes",
        prefsFile = "jarvis_eyes",
        action = "com.larossatech.jarvis.EYES_NUDGE",
        requestCode = 7312,
        defIntervalMin = 20,
        defStartMin = 9 * 60,
        defEndMin = 23 * 60,
        defAmount = 20,
    );

    /** Frames played while the card is up. */
    val frames: IntArray
        get() = when (this) {
            WATER -> intArrayOf(
                R.drawable.sip_0, R.drawable.sip_1, R.drawable.sip_2,
                R.drawable.sip_3, R.drawable.sip_4,
            )
            EYES -> intArrayOf(
                R.drawable.rest_0, R.drawable.rest_1, R.drawable.rest_2,
                R.drawable.rest_3, R.drawable.rest_4,
            )
        }

    val title: String
        get() = when (this) {
            WATER -> "Water break"
            EYES -> "Look away"
        }

    /** Accent used on the card's button. */
    val accent: String
        get() = when (this) {
            WATER -> "#00E5C9"
            EYES -> "#FFB347"
        }

    companion object {
        fun from(key: String?): NudgeKind =
            entries.firstOrNull { it.key == key } ?: WATER
    }
}
