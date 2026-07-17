"""Pygame HUD for Jarvis — arc-reactor aesthetic.

Runs the pygame main loop on the program's main thread (required on Windows).
Agent state changes and log lines are pushed in from other threads; the HUD
reads them under a tiny lock each frame.
"""
from __future__ import annotations

import collections
import math
import threading
import time
from datetime import datetime
from typing import Callable, List, Tuple

import pygame


# --- palette --------------------------------------------------------------
BG_TOP = (4, 8, 20)
BG_BOTTOM = (10, 14, 32)
GRID = (16, 24, 44)
GRID_DIM = (12, 18, 32)
TITLE_CYAN = (130, 220, 255)
TEXT = (210, 226, 244)
DIM = (110, 138, 170)
ACCENT = (60, 200, 255)
ACCENT_DEEP = (30, 120, 200)
GLOW = (40, 180, 255)

STATUS_COLOR = {
    "idle":     (84, 96, 120),
    "running":  (32, 220, 140),
    "stopping": (245, 170, 60),
    "error":    (240, 90, 90),
}
STATE_COLOR = {
    "standby":   (130, 140, 160),
    "listening": (32, 220, 140),
    "thinking":  (245, 180, 60),
    "speaking":  (70, 170, 255),
}


# --- helpers --------------------------------------------------------------
def _vgrad(width: int, height: int, top, bottom) -> pygame.Surface:
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        c = (int(top[0] + (bottom[0] - top[0]) * t),
             int(top[1] + (bottom[1] - top[1]) * t),
             int(top[2] + (bottom[2] - top[2]) * t))
        pygame.draw.line(surf, c, (0, y), (width, y))
    return surf


def _glow_circle(diameter: int, color, max_alpha: int = 60) -> pygame.Surface:
    s = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    rings = 16
    for i in range(rings, 0, -1):
        a = int(max_alpha * (i / rings) ** 2)
        r = int(diameter / 2 * i / rings)
        pygame.draw.circle(s, (*color, a), (diameter // 2, diameter // 2), r)
    return s


# --- the HUD --------------------------------------------------------------
class JarvisHUD:
    WINDOW = (1280, 800)
    FPS = 60

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._lock = threading.Lock()
        self.state = "standby"
        self.log_lines: collections.deque[str] = collections.deque(maxlen=80)
        self.agent_states = {a.name: "idle" for a in jarvis.registry.list()}
        for a in jarvis.registry.list():
            a.on_status_change = self._on_agent_status
        self._click_areas: List[Tuple[pygame.Rect, Callable[[], None]]] = []
        self.running = False
        self._fullscreen = False

    # ----- thread-safe inputs (called from voice / agent threads) --------
    def log(self, line: str) -> None:
        with self._lock:
            self.log_lines.append(line)
        print(line)

    def set_state(self, state: str) -> None:
        self.state = state

    def _on_agent_status(self, agent, status: str) -> None:
        with self._lock:
            self.agent_states[agent.name] = status

    # ----- shim so jarvis._execute can call self.ui.root.after(...) ------
    @property
    def root(self):
        return self

    def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
        threading.Timer(delay_ms / 1000.0, callback).start()

    def destroy(self) -> None:
        self.running = False

    # --------------------------------------------------------------------
    def run(self) -> None:
        pygame.init()
        pygame.display.set_caption("Jarvis")
        flags = pygame.DOUBLEBUF
        screen = pygame.display.set_mode(self.WINDOW, flags)
        clock = pygame.time.Clock()
        self._fonts = {
            "title": pygame.font.SysFont("consolas", 32, bold=True),
            "h":     pygame.font.SysFont("consolas", 18, bold=True),
            "m":     pygame.font.SysFont("consolas", 14),
            "s":     pygame.font.SysFont("consolas", 11),
            "logo":  pygame.font.SysFont("consolas", 60, bold=True),
        }
        self._bg = _vgrad(*self.WINDOW, BG_TOP, BG_BOTTOM)
        self._glow_lg = _glow_circle(560, GLOW, max_alpha=70)

        self.running = True
        t0 = time.time()
        while self.running:
            tt = time.time() - t0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_F11:
                        self._toggle_fullscreen()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)

            screen.blit(self._bg, (0, 0))
            self._draw_grid(screen, tt)
            self._draw_corner_brackets(screen)
            self._draw_glow(screen, tt)
            self._draw_rings(screen, tt)
            self._draw_reactor(screen, tt)
            self._draw_radial_bars(screen, tt)
            self._draw_agents(screen)
            self._draw_console(screen)
            self._draw_topbar(screen)
            self._draw_legend(screen)
            pygame.display.flip()
            clock.tick(self.FPS)

        pygame.quit()
        if hasattr(self.jarvis, "voice") and self.jarvis.voice:
            self.jarvis.voice.shutdown()

    # --------------------------------------------------------------------
    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        flags = pygame.FULLSCREEN if self._fullscreen else 0
        pygame.display.set_mode(self.WINDOW, flags | pygame.DOUBLEBUF)

    def _handle_click(self, pos) -> None:
        for rect, cb in list(self._click_areas):
            if rect.collidepoint(pos):
                cb()
                return

    # --- drawing primitives ---------------------------------------------
    def _arc_segments(self, screen, cx, cy, radius, width, segments, gap_ratio, rotation, color):
        rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
        gap = gap_ratio * 2 * math.pi
        span = (2 * math.pi - segments * gap) / segments
        for i in range(segments):
            start = rotation + i * (span + gap)
            end = start + span
            try:
                pygame.draw.arc(screen, color, rect, start, end, width)
            except Exception:  # noqa: BLE001
                pass

    def _draw_grid(self, screen, t):
        w, h = self.WINDOW
        for x in range(0, w, 40):
            pygame.draw.line(screen, GRID_DIM, (x, 0), (x, h))
        for y in range(0, h, 40):
            pygame.draw.line(screen, GRID_DIM, (0, y), (w, y))
        # accent lines every 200px
        for x in range(0, w, 200):
            pygame.draw.line(screen, GRID, (x, 0), (x, h))
        for y in range(0, h, 200):
            pygame.draw.line(screen, GRID, (0, y), (w, y))

    def _draw_corner_brackets(self, screen):
        w, h = self.WINDOW
        L = 24
        c = ACCENT_DEEP
        for (cx, cy, dx, dy) in [(20, 20, 1, 1), (w-20, 20, -1, 1),
                                 (20, h-20, 1, -1), (w-20, h-20, -1, -1)]:
            pygame.draw.line(screen, c, (cx, cy), (cx + L*dx, cy), 2)
            pygame.draw.line(screen, c, (cx, cy), (cx, cy + L*dy), 2)

    def _draw_glow(self, screen, t):
        cx, cy = 780, 380
        screen.blit(self._glow_lg, (cx - 280, cy - 280), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_rings(self, screen, t):
        cx, cy = 780, 380
        # outermost slow segments
        self._arc_segments(screen, cx, cy, 260, 3, 6,  0.04, t*0.35, ACCENT)
        self._arc_segments(screen, cx, cy, 240, 2, 9,  0.02, -t*0.55, (90, 200, 255))
        # mid
        self._arc_segments(screen, cx, cy, 210, 4, 4,  0.10, t*0.20, (40, 160, 230))
        self._arc_segments(screen, cx, cy, 188, 1, 36, 0.004, -t*1.0, (130, 220, 255))
        # inner ticks
        self._arc_segments(screen, cx, cy, 160, 2, 72, 0.002, t*0.4, (90, 200, 255))

        # 4 cardinal markers on outer ring
        for k, ang in enumerate([0, math.pi/2, math.pi, 3*math.pi/2]):
            ang2 = ang + t*0.35
            x = cx + math.cos(ang2) * 268
            y = cy + math.sin(ang2) * 268
            pygame.draw.circle(screen, (180, 230, 255), (int(x), int(y)), 3)

    def _draw_reactor(self, screen, t):
        cx, cy = 780, 380
        speed = {"standby": 1.2, "listening": 1.8, "thinking": 3.0, "speaking": 4.8}.get(self.state, 1.2)
        breath = (math.sin(t * speed) + 1) / 2  # 0..1

        # outer ring of core
        r_out = 64 + int(breath * 10)
        pygame.draw.circle(screen, ACCENT, (cx, cy), r_out, 2)
        pygame.draw.circle(screen, (40, 130, 200), (cx, cy), r_out - 8, 1)

        # 8 triangular vanes inside the core
        vanes = 8
        for i in range(vanes):
            a = t * 0.6 + i * (2 * math.pi / vanes)
            r1, r2 = 22, r_out - 14
            x1 = cx + math.cos(a) * r1
            y1 = cy + math.sin(a) * r1
            x2 = cx + math.cos(a) * r2
            y2 = cy + math.sin(a) * r2
            pygame.draw.line(screen, (80, 200, 255), (x1, y1), (x2, y2), 2)

        # bright center disc
        cr = 18 + int(breath * 5)
        pygame.draw.circle(screen, (180, 230, 255), (cx, cy), cr)
        pygame.draw.circle(screen, (250, 252, 255), (cx, cy), cr - 6)

    def _draw_radial_bars(self, screen, t):
        cx, cy = 780, 380
        bars = 96
        radius = 296
        amp = {"standby": 3, "listening": 7, "thinking": 12, "speaking": 22}.get(self.state, 4)
        for i in range(bars):
            angle = (i / bars) * 2 * math.pi
            h = amp * 0.4 + amp * (math.sin(t * 6 + i * 0.4) + 1) * 0.5
            x1 = cx + math.cos(angle) * radius
            y1 = cy + math.sin(angle) * radius
            x2 = cx + math.cos(angle) * (radius + h)
            y2 = cy + math.sin(angle) * (radius + h)
            a = max(120, int(80 + h * 8))
            pygame.draw.line(screen, (60, 180, 255), (x1, y1), (x2, y2), 1)
            # tiny tip dot
            pygame.draw.circle(screen, (140, 220, 255), (int(x2), int(y2)), 1)

    # --- panels ---------------------------------------------------------
    def _draw_agents(self, screen):
        x, y = 28, 92
        w, h = 250, 88
        self._click_areas.clear()

        # header
        screen.blit(self._fonts["h"].render("// AGENTS", True, TITLE_CYAN), (x, y - 26))
        pygame.draw.line(screen, ACCENT_DEEP, (x, y - 6), (x + w, y - 6), 1)

        with self._lock:
            states = dict(self.agent_states)

        for a in self.jarvis.registry.list():
            self._draw_agent_card(screen, x, y, w, h, a, states.get(a.name, "idle"))
            y += h + 14

    def _draw_agent_card(self, screen, x, y, w, h, agent, status):
        rect = pygame.Rect(x, y, w, h)
        # panel
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        bg_alpha = 230 if status == "running" else 180
        pygame.draw.rect(panel, (18, 28, 50, bg_alpha), (0, 0, w, h), border_radius=10)
        border = STATUS_COLOR[status] if status != "idle" else (60, 100, 150)
        pygame.draw.rect(panel, (*border, 220), (0, 0, w, h), width=1, border_radius=10)
        screen.blit(panel, (x, y))

        # status dot + pulse halo if running
        dot_pos = (x + 18, y + 22)
        if status == "running":
            halo = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(halo, (32, 220, 140, 80), (20, 20), 12)
            screen.blit(halo, (dot_pos[0] - 20, dot_pos[1] - 20))
        pygame.draw.circle(screen, STATUS_COLOR[status], dot_pos, 7)

        # name + status text
        screen.blit(self._fonts["h"].render(agent.name, True, TEXT), (x + 36, y + 12))
        screen.blit(self._fonts["s"].render(status.upper(), True, DIM), (x + 36, y + 36))

        # buttons
        sb = pygame.Rect(x + 36, y + 56, 70, 22)
        kb = pygame.Rect(x + 114, y + 56, 70, 22)
        pygame.draw.rect(screen, (16, 96, 70), sb, border_radius=6)
        pygame.draw.rect(screen, (30, 130, 90), sb, width=1, border_radius=6)
        pygame.draw.rect(screen, (90, 26, 26), kb, border_radius=6)
        pygame.draw.rect(screen, (140, 50, 50), kb, width=1, border_radius=6)
        screen.blit(self._fonts["s"].render("START", True, TEXT), (sb.x + 18, sb.y + 5))
        screen.blit(self._fonts["s"].render("STOP",  True, TEXT), (kb.x + 22, kb.y + 5))

        # info area on hover? skip — keep it simple.
        self._click_areas.append((sb, lambda name=agent.name: self.jarvis.execute_button("start", name)))
        self._click_areas.append((kb, lambda name=agent.name: self.jarvis.execute_button("stop", name)))

    def _draw_console(self, screen):
        w, h = self.WINDOW
        top = 612
        rect = pygame.Rect(20, top, w - 40, h - top - 30)
        # panel bg
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel, (8, 14, 28, 220), (0, 0, rect.width, rect.height), border_radius=8)
        pygame.draw.rect(panel, (50, 100, 160, 220), (0, 0, rect.width, rect.height), width=1, border_radius=8)
        screen.blit(panel, rect.topleft)
        # title
        screen.blit(self._fonts["h"].render("// CONSOLE", True, TITLE_CYAN), (rect.x + 14, rect.y + 8))
        pygame.draw.line(screen, ACCENT_DEEP, (rect.x + 14, rect.y + 32), (rect.right - 14, rect.y + 32), 1)
        # lines
        with self._lock:
            lines = list(self.log_lines)
        y = rect.y + 42
        for line in lines[-8:]:
            color = TEXT
            if line.startswith("[Jarvis]"):
                color = (140, 220, 255)
            elif "WAKE" in line:
                color = (60, 230, 140)
            elif "heard" in line:
                color = (210, 210, 220)
            elif "error" in line.lower() or "crashed" in line.lower():
                color = (240, 110, 110)
            elif line.startswith("Mic:") or line.startswith("=="):
                color = DIM
            screen.blit(self._fonts["m"].render(line[:200], True, color), (rect.x + 14, y))
            y += 18

    def _draw_topbar(self, screen):
        w = self.WINDOW[0]
        screen.blit(self._fonts["title"].render("J A R V I S", True, TITLE_CYAN), (28, 18))
        screen.blit(self._fonts["s"].render("multi-agent supervisor v0.1", True, DIM), (28, 58))

        # state pill
        st_color = STATE_COLOR.get(self.state, DIM)
        pill = pygame.Rect(w - 240, 28, 210, 30)
        pygame.draw.rect(screen, (8, 16, 32), pill, border_radius=15)
        pygame.draw.rect(screen, st_color, pill, width=1, border_radius=15)
        pygame.draw.circle(screen, st_color, (pill.x + 16, pill.y + 15), 5)
        label = self._fonts["m"].render(self.state.upper(), True, TEXT)
        screen.blit(label, (pill.x + 32, pill.y + 7))

        # clock
        clock_txt = datetime.now().strftime("%H:%M:%S")
        date_txt = datetime.now().strftime("%a  %d %b %Y")
        screen.blit(self._fonts["h"].render(clock_txt, True, ACCENT), (w - 350, 24))
        screen.blit(self._fonts["s"].render(date_txt, True, DIM), (w - 350, 46))

    def _draw_legend(self, screen):
        # small key reference at bottom-right
        x = self.WINDOW[0] - 260
        y = 92
        screen.blit(self._fonts["h"].render("// SAY", True, TITLE_CYAN), (x, y))
        pygame.draw.line(screen, ACCENT_DEEP, (x, y + 24), (x + 230, y + 24), 1)
        hints = [
            '"Jarvis"  -> wake',
            '"what agents do you have"',
            '"start Mingo"',
            '"weather in <city>"',
            '"system info"',
            '"take a note <text>"',
            '"search for <query>"',
            '"stop everything"',
            '"goodbye"  -> quit',
        ]
        for i, h in enumerate(hints):
            screen.blit(self._fonts["m"].render(h, True, DIM if i else TEXT), (x, y + 36 + i * 20))

        # bottom hint
        screen.blit(self._fonts["s"].render(
            "F11 fullscreen   |   ESC quit   |   click cards to start/stop",
            True, DIM
        ), (x, y + 36 + len(hints) * 20 + 8))
