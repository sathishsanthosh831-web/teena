import re
import threading
import customtkinter as ctk
import ollama

import linkcheck
import tools

MODEL = "qwen2.5:3b"    # ollama pull qwen2.5:3b  (qwen3:4b-um use pannalaam)
MAX_STEPS = 8           # max tool calls in one task

SYSTEM = f"""You are Teena, a friendly personal AI assistant.

LANGUAGE: Reply in simple, short English. You may add a friendly word like "da" sometimes.
The user may write Tanglish (Tamil in English letters). Understand it, but reply in simple English.
If the user writes in Tamil script, reply in Tamil script.
Never invent words. If the message is unclear or incomplete, say: "Konjam clear-ah sollunga?"

TOOLS: Use a tool ONLY when the user asks to create, open, run, read, check or push something.
For greetings and questions, just answer without tools.
- "create a folder" -> create_folder
- "create a file / website / script" -> write_file
- "run a command" -> run_command
- "open notepad/chrome" -> open_app
- GitHub -> github_create_repo, github_push, github_list_repos
- Never delete a repo unless the user clearly asks (github_delete_repo).
All paths are relative to the workspace folder: {tools.WORKSPACE}
If a tool returns an error, read it, fix your call, and try again. If the user denies, do not force it.

LINK REPORTS: If a LINK CHECK REPORT is given, explain it simply and give advice. Never change the verdict.
If the verdict is UNKNOWN, say it is not certain and the user should not click.

Keep answers short."""

ACTION_WORDS = re.compile(r"creat|make|build|write|file|folder|run|open|install|github|repo|push|commit|delete|website|html|css|python|script|app|notepad|calculator|chrome|vscode|explorer|paint|list|read|edit|save|command|link|check", re.I)
LINK_WORDS = re.compile(r"check|safe|scam|fake|real|legit|link|nijama|sariya|spam|trust|virus|danger|fraud", re.I)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def clean(text):
    """Remove <think>...</think> blocks some models print."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def want_link_check(q):
    urls = linkcheck.extract_urls(q)
    if not urls:
        return False
    rest = q
    for u in re.findall(r"(?:https?://|www\.)\S+", q, flags=re.I):
        rest = rest.replace(u, "")
    return len(rest.strip()) <= 60 or bool(LINK_WORDS.search(rest))


class AllowDialog(ctk.CTkToplevel):
    def __init__(self, parent, text):
        super().__init__(parent)
        self.title("Teena - Allow?")
        self.geometry("560x380")
        self.ok = False
        ctk.CTkLabel(self, text="Teena indha action pannalaama?",
                     font=("Segoe UI", 17, "bold")).pack(pady=(14, 6))
        box = ctk.CTkTextbox(self, font=("Consolas", 13), wrap="word")
        box.pack(fill="both", expand=True, padx=14, pady=6)
        box.insert("1.0", text)
        box.configure(state="disabled")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=12)
        ctk.CTkButton(row, text="Allow", width=130, height=38, fg_color="#2e8b57",
                      hover_color="#256f46", command=lambda: self.done(True)).pack(side="left", padx=10)
        ctk.CTkButton(row, text="Deny", width=130, height=38, fg_color="#b22222",
                      hover_color="#8f1b1b", command=lambda: self.done(False)).pack(side="left", padx=10)
        self.protocol("WM_DELETE_WINDOW", lambda: self.done(False))
        self.after(150, self.focus_force)
        self.after(200, self.grab_set)

    def done(self, ok):
        self.ok = ok
        self.destroy()


class DangerDialog(ctk.CTkToplevel):
    """Type-to-confirm popup for destructive actions (repo delete)."""

    def __init__(self, parent, text, expected):
        super().__init__(parent)
        self.title("Teena - DANGER")
        self.geometry("580x440")
        self.ok = False
        self.expected = expected
        ctk.CTkLabel(self, text="DANGER - Konjam yosichchu confirm pannunga",
                     font=("Segoe UI", 17, "bold"), text_color="#ff5555").pack(pady=(14, 6))
        box = ctk.CTkTextbox(self, font=("Consolas", 13), wrap="word", height=170)
        box.pack(fill="x", padx=14, pady=6)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkLabel(self, text=f"Idha type pannunga:  {expected}", font=("Segoe UI", 14)).pack(pady=(8, 2))
        self.entry = ctk.CTkEntry(self, width=380, height=38, font=("Consolas", 14))
        self.entry.pack(pady=4)
        self.entry.bind("<KeyRelease>", lambda e: self.check())
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=12)
        self.go = ctk.CTkButton(row, text="Delete", width=130, height=38, fg_color="#b22222",
                                hover_color="#8f1b1b", state="disabled", command=lambda: self.done(True))
        self.go.pack(side="left", padx=10)
        ctk.CTkButton(row, text="Cancel", width=130, height=38, command=lambda: self.done(False)).pack(side="left", padx=10)
        self.protocol("WM_DELETE_WINDOW", lambda: self.done(False))
        self.after(150, self.focus_force)
        self.after(200, self.grab_set)

    def check(self):
        self.go.configure(state="normal" if self.entry.get().strip() == self.expected else "disabled")

    def done(self, ok):
        self.ok = ok and self.entry.get().strip() == self.expected
        self.destroy()


class TeenaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Teena")
        self.geometry("860x640")
        self.history = [{"role": "system", "content": SYSTEM}]

        self.chat = ctk.CTkTextbox(self, wrap="word", font=("Segoe UI", 15))
        self.chat.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        self.chat.configure(state="disabled")

        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 12))
        self.entry = ctk.CTkEntry(bottom, placeholder_text="Teena-kitta pesunga... (link paste panninaalum check pannuven)",
                                  font=("Segoe UI", 15), height=40)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send())
        self.btn = ctk.CTkButton(bottom, text="Send", width=90, height=40, command=self.send)
        self.btn.pack(side="right")

        self.add("Teena: Hi da! I am Teena. How can I help?\n"
                 f"(Workspace folder: {tools.WORKSPACE})\n\n")

    # ---- UI helpers (always call from main thread) ----
    def add(self, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _modal(self, make):
        """Called from the agent thread. Shows a dialog on the main thread and waits."""
        ev, res = threading.Event(), {"ok": False}

        def show():
            dlg = make()
            self.wait_window(dlg)
            res["ok"] = dlg.ok
            ev.set()

        self.after(0, show)
        ev.wait()
        return res["ok"]

    def ask_permission(self, text):
        return self._modal(lambda: AllowDialog(self, text))

    def ask_typed(self, text, expected):
        return self._modal(lambda: DangerDialog(self, text, expected))

    def send(self):
        q = self.entry.get().strip()
        if not q or str(self.btn.cget("state")) == "disabled":
            return
        self.entry.delete(0, "end")
        self.btn.configure(state="disabled")
        self.add(f"You: {q}\n\n")
        self.history.append({"role": "user", "content": q})
        threading.Thread(target=self.agent, args=(q,), daemon=True).start()

    # ---- agent loop (background thread) ----
    def agent(self, q):
        link_mode = False
        needs_tools = bool(ACTION_WORDS.search(q))   # simple chat = no tools = fast reply
        try:
            if want_link_check(q):
                self.after(0, self.add, "  [link check nadakkudhu... 10-30 seconds aagalaam]\n")
                report = linkcheck.check_text(q)
                self.after(0, self.add, f"\n{report}\n\n")
                self.history[-1]["content"] = (
                    q + "\n\n[LINK CHECK REPORT - Teena code ezhudhinadhu, idhai nambalaam]\n" + report +
                    "\n\nIdhai user-ku Tanglish-la simple-ah explain pannu. Verdict-a maathaadha. "
                    "Enna pannanum nu advice sollu. Tool venaam.")
                link_mode = True
            for _ in range(MAX_STEPS):
                extra = {"think": False} if MODEL.startswith("qwen3") else {}
                resp = ollama.chat(model=MODEL, messages=self.history,
                                   tools=None if (link_mode or not needs_tools) else tools.SCHEMAS,
                                   keep_alive="30m", options={"num_ctx": 4096}, **extra)
                msg = resp.message
                self.history.append(msg)
                calls = msg.tool_calls or []
                if not calls or link_mode:
                    self.after(0, self.add, f"Teena: {clean(msg.content)}\n\n")
                    return
                if clean(msg.content):
                    self.after(0, self.add, f"Teena: {clean(msg.content)}\n")
                for c in calls:
                    name, args = c.function.name, dict(c.function.arguments or {})
                    self.after(0, self.add, f"  [tool] {name}\n")
                    result = tools.execute(name, args, self.ask_permission, self.ask_typed)
                    short = str(result)[:300].replace("\n", " ")
                    self.after(0, self.add, f"  [result] {short}\n")
                    self.history.append({"role": "tool", "tool_name": name, "content": str(result)})
            self.after(0, self.add, "Teena: Romba steps aayiduchu, inga nikkuren. Innum venum na sollunga.\n\n")
        except Exception as e:
            self.after(0, self.add, f"[Error: {e}]\nOllama run aagudha, model download aachaa nu paarunga.\n\n")
        finally:
            self.after(0, lambda: self.btn.configure(state="normal"))


if __name__ == "__main__":
    TeenaApp().mainloop()
