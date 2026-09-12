from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from tinyagent.graph import DEBUG

def model() -> str: return os.getenv("MODEL", "claude-opus-5")
PRICE = os.getenv("PRICE", "")   # "$in,$out" per million tokens. put your own numbers in, they change weekly

class Device:
  def sample(self, ctx:str, temp:float=0.0) -> tuple[str, int, int]: raise NotImplementedError
  def cost(self, tin:int, tout:int) -> float:
    if not PRICE: return 0.0
    pin, pout = (float(x) for x in PRICE.split(","))
    return (tin*pin + tout*pout) / 1e6

def post(url:str, body:dict, headers:dict) -> dict:
  req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", **headers})
  for attempt in range(5):
    try: return json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
      err = e.read().decode(errors="replace")
      if e.code not in (408, 429, 500, 502, 503, 529) or attempt == 4: raise RuntimeError(f"{e.code} {err[:400]}") from None
      if DEBUG >= 1: print(f"{e.code}, retry in {2**attempt}s")
      time.sleep(2**attempt)
  raise RuntimeError("unreachable")

class Anthropic(Device):
  def sample(self, ctx, temp=0.0):
    r = post("https://api.anthropic.com/v1/messages",
             {"model": model(), "max_tokens": 8192, "temperature": temp, "messages": [{"role": "user", "content": ctx}]},
             {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    return "".join(b.get("text", "") for b in r["content"]), r["usage"]["input_tokens"], r["usage"]["output_tokens"]

class OpenAI(Device):
  # also every local server that speaks /v1/chat/completions. MODEL=qwen3 OPENAI_BASE=http://localhost:8080/v1
  def sample(self, ctx, temp=0.0):
    base = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
    r = post(f"{base}/chat/completions", {"model": model(), "temperature": temp, "messages": [{"role": "user", "content": ctx}]},
             {"authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'none')}"})
    u = r.get("usage") or {}
    return r["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), u.get("completion_tokens", 0)

class Mock(Device):
  # MODEL=mock, script in MOCK as newline-separated turns with \n escaped. the test suite runs on this
  def __init__(self): self.turns = [t.replace("\\n", "\n") for t in os.getenv("MOCK", "DONE nothing to do").split("|")]
  def sample(self, ctx, temp=0.0):
    out = self.turns.pop(0) if self.turns else "DONE out of script"
    return out, len(ctx)//4, len(out)//4

def device() -> Device: return Mock() if (m:=model()).startswith("mock") else (Anthropic() if m.startswith("claude") else OpenAI())
