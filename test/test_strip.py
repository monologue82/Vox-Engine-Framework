import sys, io, re
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def _strip_sensevoice_tags(text):
    """去除 SenseVoice 特殊标记（<|...|>），保留纯文本"""
    cleaned = re.sub(r'<\|[^|]*\|>', '', text)
    return ' '.join(cleaned.split())

text1 = "<|zh|><|HAPPY|><|Speech|><|withitn|>是。"
text2 = "<|zh|><|NEUTRAL|><|Speech|><|withitn|>是这样。"
text3 = "<|zh|><|NEUTRAL|><|Speech|><|withitn|>是这样没。"
text4 = "<|zh|><|NEUTRAL|><|Speech|><|withitn|>是这样，没错。"

for name, t in [("text1", text1), ("text2", text2), ("text3", text3), ("text4", text4)]:
    c = _strip_sensevoice_tags(t)
    print(f"{name}: {repr(c)} (len={len(c)}, bytes={c.encode('utf-8')})")

c1 = _strip_sensevoice_tags(text1)
c2 = _strip_sensevoice_tags(text2)
c3 = _strip_sensevoice_tags(text3)
c4 = _strip_sensevoice_tags(text4)

print(f"\nc2.startswith(c1): {c2.startswith(c1)}  # Expected: True")
print(f"c3.startswith(c2): {c3.startswith(c2)}  # Expected: True")
print(f"c4.startswith(c3): {c4.startswith(c3)}  # Expected: True")
print(f"Incremental c1→c2: {repr(c2[len(c1):])}  # Expected: '这样。'")
print(f"Incremental c2→c3: {repr(c3[len(c2):])}  # Expected: '没。'")
print(f"Incremental c3→c4: {repr(c4[len(c3):])}  # Expected: '，没错。'")