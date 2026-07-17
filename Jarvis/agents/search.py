"""Search agent — opens a DuckDuckGo search in the default browser."""
import urllib.parse
import webbrowser

from .base import Agent


class SearchAgent(Agent):
    name = "Search"
    description = "Searches the web via DuckDuckGo."

    def start(self, args: str = "") -> str:
        q = args.strip()
        if not q:
            return "What would you like me to search, sir?"
        self._set_status("running")
        try:
            webbrowser.open("https://duckduckgo.com/?q=" + urllib.parse.quote(q))
            return f"Searching the web for {q}, sir."
        finally:
            self._set_status("idle")
