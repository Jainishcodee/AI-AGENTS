package com.larossatech.jarvis.water

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
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
import com.larossatech.jarvis.R

/**
 * Draws the water nudge over whatever you're doing: Jarvis slides in from the
 * edge, drinks, and gets out of the way again.
 *
 * The window is deliberately non-focusable and not touch-modal, so it never
 * steals keyboard input and taps outside the card go straight through to the
 * app underneath. Only the card itself is tappable.
 */
class WaterOverlayService : Service() {

    companion object {
        const val EXTRA_FOREGROUND = "as_foreground"
        private const val CHANNEL = "jarvis_water_overlay"
        private const val NOTIF_ID = 90211

        /** How long the card stays up if it's ignored. */
        private const val VISIBLE_MS = 14_000L
        private const val FRAME_MS = 280L
        private const val HOLD_MS = 1_800L

        private val SIP_FRAMES = intArrayOf(
            R.drawable.sip_0, R.drawable.sip_1, R.drawable.sip_2,
            R.drawable.sip_3, R.drawable.sip_4,
        )
    }

    private val main = Handler(Looper.getMainLooper())
    private var wm: WindowManager? = null
    private var root: View? = null
    private var art: ImageView? = null
    private var frame = 0
    private var dismissing = false

    private val sipTick = object : Runnable {
        override fun run() {
            val iv = art ?: return
            iv.setImageResource(SIP_FRAMES[frame])
            val last = frame == SIP_FRAMES.size - 1
            frame = if (last) 0 else frame + 1
            main.postDelayed(this, if (last) HOLD_MS else FRAME_MS)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.getBooleanExtra(EXTRA_FOREGROUND, false) == true) goForeground()

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
        val ml = WaterPrefs.perNudgeMl(this)
        val target = WaterPrefs.nudgesPerDay(this)
        val done = WaterPrefs.countToday(this)

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
            setImageResource(SIP_FRAMES[0])
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            layoutParams = LinearLayout.LayoutParams(dp(132), dp(168))
        }
        card.addView(art)

        card.addView(TextView(this).apply {
            text = "Water break"
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
        })

        card.addView(TextView(this).apply {
            text = "about $ml ml  ·  $done of $target today"
            setTextColor(Color.parseColor("#B3FFFFFF"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(0, dp(2), 0, dp(8))
        })

        card.addView(TextView(this).apply {
            text = "  Done  "
            setTextColor(Color.parseColor("#00E5C9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(dp(16), dp(7), dp(16), dp(7))
            background = GradientDrawable().apply {
                cornerRadius = dp(999).toFloat()
                setColor(Color.parseColor("#2200E5C9"))
                setStroke(dp(1), Color.parseColor("#6600E5C9"))
            }
        })

        card.setOnClickListener {
            WaterPrefs.markDrunk(this)
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

        // Slide in from the edge it's anchored to.
        card.alpha = 0f
        card.translationX = dp(180).toFloat()
        card.animate()
            .alpha(1f).translationX(0f)
            .setDuration(420)
            .setInterpolator(DecelerateInterpolator())
            .start()

        frame = 0
        main.post(sipTick)
        main.postDelayed({ dismiss() }, VISIBLE_MS)
    }

    private fun dismiss() {
        if (dismissing) return
        dismissing = true
        main.removeCallbacks(sipTick)
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
        super.onDestroy()
    }

    // Only used when background-start restrictions force a foreground service.
    private fun goForeground() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Water nudge", NotificationManager.IMPORTANCE_MIN)
                    .apply { setShowBadge(false) },
            )
        }
        val n: Notification = Notification.Builder(this, CHANNEL)
            .setContentTitle("Water break")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .build()
        startForeground(NOTIF_ID, n)
    }
}
