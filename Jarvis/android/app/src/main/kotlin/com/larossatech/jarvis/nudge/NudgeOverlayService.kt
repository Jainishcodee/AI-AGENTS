package com.larossatech.jarvis.nudge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateInterpolator
import android.view.animation.DecelerateInterpolator
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Draws a nudge over whatever you're doing: Jarvis slides in from the edge,
 * acts it out, and gets out of the way again.
 *
 * The window is deliberately non-focusable and not touch-modal, so it never
 * steals keyboard input and taps outside the card go straight through to the
 * app underneath. Only the card itself is tappable.
 */
class NudgeOverlayService : Service() {

    companion object {
        const val EXTRA_FOREGROUND = "as_foreground"
        private const val CHANNEL = "jarvis_nudge_overlay"
        private const val NOTIF_ID = 90211

        /** How long a water card stays if it's ignored. */
        private const val WATER_VISIBLE_MS = 14_000L
        private const val FRAME_MS = 280L
        private const val HOLD_MS = 1_800L
    }

    private val main = Handler(Looper.getMainLooper())
    private var wm: WindowManager? = null
    private var root: View? = null
    private var art: ImageView? = null
    private var countdown: TextView? = null
    private var headline: TextView? = null

    private lateinit var kind: NudgeKind
    private var frame = 0
    private var secondsLeft = 0
    private var dismissing = false

    /** Water loops the sip; eyes play once and settle on the resting pose. */
    private val frameTick = object : Runnable {
        override fun run() {
            val iv = art ?: return
            val frames = kind.frames
            iv.setImageResource(frames[frame])
            val last = frame == frames.size - 1
            if (last && kind == NudgeKind.EYES) return // stay resting
            frame = if (last) 0 else frame + 1
            main.postDelayed(this, if (last) HOLD_MS else FRAME_MS)
        }
    }

    private val secondTick = object : Runnable {
        override fun run() {
            secondsLeft -= 1
            if (secondsLeft > 0) {
                countdown?.text = secondsLeft.toString()
                main.postDelayed(this, 1_000L)
            } else {
                countdown?.text = "✓"
                headline?.text = "Eyes rested."
                NudgePrefs.markDone(this@NudgeOverlayService, kind)
                main.postDelayed({ dismiss() }, 1_400L)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.getBooleanExtra(EXTRA_FOREGROUND, false) == true) goForeground()
        kind = NudgeKind.from(intent?.getStringExtra(NudgeAlarmReceiver.EXTRA_KIND))

        // Already on screen (two alarms landed close together) — leave it alone.
        if (root != null) return START_NOT_STICKY

        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (!pm.isInteractive) {
            // Screen is off; a card nobody sees would just time out. Skip it.
            stopSelf()
            return START_NOT_STICKY
        }

        try {
            show()
        } catch (_: Throwable) {
            stopSelf()
        }
        return START_NOT_STICKY
    }

    // ------------------------------------------------------------------ view

    private fun dp(v: Int) = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics,
    ).toInt()

    private fun show() {
        val accent = Color.parseColor(kind.accent)
        val per = NudgePrefs.perNudge(this, kind)
        val target = NudgePrefs.nudgesPerDay(this, kind)
        val done = NudgePrefs.countToday(this, kind)

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = GradientDrawable().apply {
                cornerRadius = dp(20).toFloat()
                setColor(Color.parseColor("#F218101A"))
                setStroke(dp(1), Color.parseColor("#33FFFFFF"))
            }
            elevation = dp(12).toFloat()
        }

        art = ImageView(this).apply {
            setImageResource(kind.frames[0])
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            layoutParams = LinearLayout.LayoutParams(dp(126), dp(172))
        }
        card.addView(art)

        headline = TextView(this).apply {
            text = kind.title
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            typeface = Typeface.DEFAULT_BOLD
        }
        card.addView(headline)

        card.addView(TextView(this).apply {
            text = when (kind) {
                NudgeKind.WATER -> "about $per ml  ·  $done of $target today"
                NudgeKind.EYES -> "something 20 feet away  ·  $done today"
            }
            setTextColor(Color.parseColor("#B3FFFFFF"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(0, dp(2), 0, dp(8))
        })

        // Eyes get a live countdown — the whole point is holding the look.
        if (kind == NudgeKind.EYES) {
            secondsLeft = per
            countdown = TextView(this).apply {
                text = secondsLeft.toString()
                setTextColor(accent)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 30f)
                typeface = Typeface.DEFAULT_BOLD
                setPadding(0, 0, 0, dp(6))
            }
            card.addView(countdown)
        }

        card.addView(TextView(this).apply {
            text = if (kind == NudgeKind.EYES) "  Skip  " else "  Done  "
            setTextColor(accent)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            typeface = Typeface.DEFAULT_BOLD
            setPadding(dp(16), dp(7), dp(16), dp(7))
            background = GradientDrawable().apply {
                cornerRadius = dp(999).toFloat()
                setColor(accent and 0x22FFFFFF)
                setStroke(dp(1), accent and 0x66FFFFFF)
            }
        })

        card.setOnClickListener {
            // Water counts on tap; eyes only count if the break was actually held.
            if (kind == NudgeKind.WATER) NudgePrefs.markDone(this, kind)
            dismiss()
        }

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE

        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = dp(12)
            y = dp(96)
        }

        wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        wm?.addView(card, lp)
        root = card

        card.alpha = 0f
        card.translationX = dp(180).toFloat()
        card.animate()
            .alpha(1f).translationX(0f)
            .setDuration(420)
            .setInterpolator(DecelerateInterpolator())
            .start()

        frame = 0
        main.post(frameTick)

        if (kind == NudgeKind.EYES) {
            main.postDelayed(secondTick, 1_000L)
            // Hard ceiling in case the tick is starved, so it can't stick forever.
            main.postDelayed({ dismiss() }, (per + 6) * 1_000L)
        } else {
            main.postDelayed({ dismiss() }, WATER_VISIBLE_MS)
        }
    }

    private fun dismiss() {
        if (dismissing) return
        dismissing = true
        main.removeCallbacks(frameTick)
        main.removeCallbacks(secondTick)
        val v = root
        if (v == null) {
            stopSelf()
            return
        }
        v.animate()
            .alpha(0f).translationX(dp(180).toFloat())
            .setDuration(280)
            .setInterpolator(AccelerateInterpolator())
            .withEndAction { stopSelf() }
            .start()
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        root?.let { v ->
            try { wm?.removeView(v) } catch (_: Throwable) {}
        }
        root = null
        art = null
        countdown = null
        headline = null
        super.onDestroy()
    }

    // Only used when background-start restrictions force a foreground service.
    private fun goForeground() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        try {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL) == null) {
                nm.createNotificationChannel(
                    NotificationChannel(CHANNEL, "Nudges", NotificationManager.IMPORTANCE_MIN)
                        .apply { setShowBadge(false) },
                )
            }
            val n: Notification = Notification.Builder(this, CHANNEL)
                .setContentTitle("Jarvis")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .build()
            startForeground(NOTIF_ID, n)
        } catch (_: Throwable) {
            // Android 14+ wants a declared service type; without it we just run
            // as a plain service, which the overlay grant already permits.
        }
    }
}
