"""CustomTkinter dashboard for Jarvis.

Thread-safety: every method that touches widgets is invoked from the main
(Tk) thread. The voice loop runs in a worker thread and pushes updates via
`root.after(0, ...)`.
"""
from __future__ import annotations

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_STATUS_COLORS = {
    "idle":     "#4a4a55",
    "running":  "#10b981",
    "stopping": "#f59e0b",
    "error":    "#ef4444",
}
_STATE_LABEL = {
    "standby":   ("● standby",   "#888"),
    "listening": ("● listening", "#10b981"),
    "thinking":  ("● thinking",  "#f59e0b"),
    "speaking":  ("● speaking",  "#3b82f6"),
}


class AgentCard(ctk.CTkFrame):
    def __init__(self, master, agent, jarvis):
        super().__init__(master, corner_radius=12, fg_color="#1a1a26", border_width=1, border_color="#2a2a3a")
        self.agent = agent
        self.jarvis = jarvis
        self.grid_columnconfigure(1, weight=1)

        self.dot = ctk.CTkLabel(self, text="●", font=ctk.CTkFont(size=24),
                                text_color=_STATUS_COLORS["idle"])
        self.dot.grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=12)

        self.name_lbl = ctk.CTkLabel(self, text=agent.name,
                                     font=ctk.CTkFont(size=16, weight="bold"))
        self.name_lbl.grid(row=0, column=1, sticky="w", padx=4, pady=(10, 0))

        self.desc_lbl = ctk.CTkLabel(self, text=agent.description,
                                     font=ctk.CTkFont(size=11), text_color="#8a8a98")
        self.desc_lbl.grid(row=1, column=1, sticky="w", padx=4, pady=(0, 10))

        self.start_btn = ctk.CTkButton(self, text="Start", width=72, height=30, command=self._start)
        self.start_btn.grid(row=0, column=2, rowspan=2, padx=4, pady=10)
        self.stop_btn = ctk.CTkButton(self, text="Stop", width=72, height=30,
                                      fg_color="#3a3a4a", hover_color="#55556a", command=self._stop)
        self.stop_btn.grid(row=0, column=3, rowspan=2, padx=(4, 14), pady=10)

    def _start(self):
        self.jarvis.execute_button("start", self.agent.name)

    def _stop(self):
        self.jarvis.execute_button("stop", self.agent.name)

    def set_status(self, status: str):
        self.dot.configure(text_color=_STATUS_COLORS.get(status, _STATUS_COLORS["idle"]))


class JarvisUI:
    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.root = ctk.CTk()
        self.root.title("Jarvis")
        self.root.geometry("820x760")
        self.root.minsize(720, 600)
        self.root.configure(fg_color="#0e0e18")

        # ----- header --------------------------------------------------
        header = ctk.CTkFrame(self.root, height=80, corner_radius=0, fg_color="#080814")
        header.pack(fill="x")
        header.grid_propagate(False)
        title = ctk.CTkLabel(header, text="J A R V I S",
                             font=ctk.CTkFont(size=30, weight="bold"),
                             text_color="#7dd3fc")
        title.pack(side="left", padx=28, pady=20)
        subtitle = ctk.CTkLabel(header, text="multi-agent supervisor",
                                font=ctk.CTkFont(size=11), text_color="#5a5a70")
        subtitle.pack(side="left", padx=0, pady=(36, 0))

        self.state_lbl = ctk.CTkLabel(header, text="● standby",
                                      font=ctk.CTkFont(size=13), text_color="#888")
        self.state_lbl.pack(side="right", padx=28, pady=28)

        # ----- agent cards --------------------------------------------
        self.cards_frame = ctk.CTkScrollableFrame(
            self.root, label_text="  Agents",
            label_font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#10101c",
        )
        self.cards_frame.pack(fill="both", expand=True, padx=18, pady=(14, 8))
        self.cards: dict[str, AgentCard] = {}
        for a in jarvis.registry.list():
            card = AgentCard(self.cards_frame, a, jarvis)
            card.pack(fill="x", pady=6, padx=4)
            self.cards[a.name] = card
            a.on_status_change = self._on_agent_status

        # ----- console / transcript -----------------------------------
        console_frame = ctk.CTkFrame(self.root, corner_radius=12, fg_color="#10101c")
        console_frame.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkLabel(console_frame, text="  Console",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#aaa").pack(anchor="w", padx=10, pady=(8, 0))
        self.log_box = ctk.CTkTextbox(console_frame, height=170, wrap="word",
                                      font=ctk.CTkFont(family="Consolas", size=12),
                                      fg_color="#0a0a14", text_color="#cdd9e5")
        self.log_box.pack(fill="x", padx=10, pady=10)
        self.log_box.configure(state="disabled")

    # ----- thread-safe updaters ---------------------------------------
    def log(self, line: str):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        try:
            self.root.after(0, _do)
        except RuntimeError:
            pass  # root closed

    def set_state(self, state: str):
        text, color = _STATE_LABEL.get(state, (f"● {state}", "#888"))
        try:
            self.root.after(0, lambda: self.state_lbl.configure(text=text, text_color=color))
        except RuntimeError:
            pass

    def _on_agent_status(self, agent, status):
        card = self.cards.get(agent.name)
        if not card:
            return
        try:
            self.root.after(0, lambda: card.set_status(status))
        except RuntimeError:
            pass

    def run(self):
        self.root.mainloop()
