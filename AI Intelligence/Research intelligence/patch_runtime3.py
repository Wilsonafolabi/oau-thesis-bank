with open("security/nemoguardrails/runtime.py", "r", encoding="utf-8") as f:
    text = f.read()

if "OFF_TOPIC_PATTERNS" not in text:
    text = text.replace(
        "DOC_INSTRUCTION_PATTERNS = [",
        "OFF_TOPIC_PATTERNS = [\n"
        "    r\"(?i)\\b(write|generate|tell|give)\\b.{0,40}\\b(poem|song|joke|story|recipe)\\b\",\n"
        "    r\"(?i)\\b(what is the weather|football|movie|love letter)\\b\",\n"
        "]\nDOC_INSTRUCTION_PATTERNS = ["
    )

if "def check_off_topic" not in text:
    text = text.replace(
        "def check_input_safety(self):",
        "def check_off_topic(self):\n"
        "        text = _current_context.get().get(\"user_input\", \"\")\n"
        "        return any(re.search(p, text) for p in OFF_TOPIC_PATTERNS)\n\n"
        "    def check_input_safety(self):"
    )

if "self.check_off_topic" not in text:
    text = text.replace(
        "self.rails.register_action(self.check_input_safety",
        "self.rails.register_action(self.check_off_topic, \"check_off_topic\")\n"
        "        self.rails.register_action(self.check_input_safety"
    )

with open("security/nemoguardrails/runtime.py", "w", encoding="utf-8") as f:
    f.write(text)
print("✅ runtime.py patched with check_off_topic.")
