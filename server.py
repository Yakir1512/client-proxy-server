# server.py
import argparse, socket, json, time, threading, math, os, ast, operator, collections
from typing import Any, Dict
# ייבוא עבור GPT - נדרש אם אתה משתמש במימוש אמיתי
try:
    from openai import OpenAI
except ImportError:
    pass

# ---------------- LRU Cache (simple) ----------------
class LRUCache:
    """Minimal LRU cache based on OrderedDict."""
    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self._d = collections.OrderedDict()

    def get(self, key):
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def set(self, key, value):
        self._d[key] = value
        self._d.move_to_end(key)
        if len(self._d) > self.capacity:
            self._d.popitem(last=False)

# ---------------- Safe Math Eval (no eval) ----------------
_ALLOWED_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
    "log": math.log, "exp": math.exp, "max": max, "min": min, "abs": abs,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}
_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}

def _eval_node(node):
    """Evaluate a restricted AST node safely."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("illegal constant type")
    if hasattr(ast, "Num") and isinstance(node, ast.Num):  # legacy fallback
        return node.n
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTS:
            return _ALLOWED_CONSTS[node.id]
        raise ValueError(f"unknown symbol {node.id}")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError("illegal function call")
        args = [_eval_node(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError("illegal expression")

def safe_eval_expr(expr: str) -> float:
    """Parse and evaluate the expression safely using ast (no eval)."""
    tree = ast.parse(expr, mode="eval")
    return float(_eval_node(tree.body))

# ---------------- GPT Call (Stub or Real Implementation) ----------------
# אתחול הלקוח של OpenAI פעם אחת (בצורה גלובלית ליעילות)
try:
    OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    OPENAI_CLIENT = None
    print("[SERVER] Warning: OpenAI client could not be initialized (API key missing or bad import). Using Stub.")


def call_gpt(prompt: str) -> str:
    """
    Real implementation for GPT call using OpenAI API or Stub if client fails.
    """
    if OPENAI_CLIENT is None:
        # Stub/Fallback (כנדרש אם המפתח אינו זמין) [cite: 72]
        return f"[GPT-STUB] Received a prompt of length {len(prompt)} chars. (API inactive)\n aggread ans is: 'NETWORKS'"

    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful and concise assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[GPT-ERROR] Failed to get response from API: {e}"

# ---------------- Server core ----------------
def handle_request(msg: Dict[str, Any], cache: LRUCache) -> Dict[str, Any]:
    mode = msg.get("mode")
    data = msg.get("data") or {}
    options = msg.get("options") or {}
    use_cache = bool(options.get("cache", True))

    started = time.time()
    # מייצרים מפתח מטמון מתוך ההודעה המלאה
    cache_key = json.dumps(msg, sort_keys=True) 

    if use_cache:#תשתמש במטמון אם הוקלד כך בהגדרות
        hit = cache.get(cache_key)#תבדוק אם הייתה קריאה כזו 
        if hit is not None:# אם הייתה קריאה כזו אז תחזיר את התשובה שהחזרת פעם קודמת בלי לחשב
            return {"ok": True, "result": hit, "meta": {"from_cache": True, "took_ms": int((time.time()-started)*1000)}}

    try:
        if mode == "calc":# אם הוקלד מוד המחשבון
            expr = data.get("expr")#שואבים ביטוי מתוך הביטויים שהוכנו מראש
            if not expr or not isinstance(expr, str):
                return {"ok": False, "error": "Bad request: 'expr' is required (string)"}
            res = safe_eval_expr(expr)#תחשב ותשים ב RES
        elif mode == "gpt":
            prompt = data.get("prompt")
            if not prompt or not isinstance(prompt, str):
                return {"ok": False, "error": "Bad request: 'prompt' is required (string)"}
            res = call_gpt(prompt)# אם זה GPT אז שים את התשובה שיחזיר בRES
        else:
            return {"ok": False, "error": "Bad request: unknown mode"}

        took = int((time.time()-started)*1000)#זמן שלקח לחישוב או לשליפה מהמטמון
        if use_cache:
            cache.set(cache_key, res)#עכשיו בגלל שלא נצצא במטמון תכניס אותו
            
        # הוספת ה-meta data של השרת
        #את כל התשובה תחזיר וגם את המידע על השרת ואיך שחישב
        return {"ok": True, "result": res, "meta": {"from_cache": False, "took_ms": took}}
    except Exception as e:
        return {"ok": False, "error": f"Server error: {e}"}

def serve(host: str, port: int, cache_size: int):
    # ... (קוד serve נשאר זהה) ...
    cache = LRUCache(cache_size)# יצירת מטמון חדש שבו נשמור את הבקשות מהלקוחות.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:# הקמת צינור חדש לתקשורת 
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))#הגדרת הפורט והכתובת לפי מה שהחלטנו בראש
        s.listen(16)#פה הוא יקשיב וישים בהמתנה עד 16 בקשות עד שינתק אותן
        print(f"[server] listening on {host}:{port} (cache={cache_size})")
        while True:
            conn, addr = s.accept()#ממתין ללקוח ולא ממשיך עד שחוזר אובייקט .
            #אחרי זה משייך אותו לכתובת ולפורט מתאים
            
            # מפעיל תהליכון נפרד לטיפול בלקוח
            #משייך את הלקוח הפורט וכו שריבלנו לתהליכון חדש
            threading.Thread(target=handle_client, args=(conn, addr, cache), daemon=True).start()

def handle_client(conn: socket.socket, addr, cache: LRUCache):
    """ מטפל בלקוח יחיד ותומך בבקשות מרובות (Persistent Connection) """
    with conn:
        try:
            raw = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
                #אם מה שקיבלת ונאגר בCHUNK הוא ריק אז צא, אחרת, תכניס אותו לRAW
                
                # לולאה פנימית לטיפול בבקשות מרובות שנשלחו ב-Pipe
                while b"\n" in raw:#אם אתה מבין שהגעת לסוף הודעה בגלל" /n" אז תתחיל לעבד את ההודעה.
                    line, _, rest = raw.partition(b"\n")
                    raw = rest  #אם ההודעה שקיבלת מכילה מעבר ל "/n"  אז את כל מה שמעבר תשמור ב RAW.
                    
                    # 1. עיבוד
                    msg = json.loads(line.decode("utf-8")) #תפרש את הקובץ המקודד ותשמור אותו ב MSG 
                    resp = handle_request(msg, cache) #תיגש לפונקציה הזו ותבין אם זה עבור GPT או אחר.
                    
                    # 2. שליחה חזרה
                    #תשלח את מה שקיבלת חזרה ב resp לאחר קידוד שתכניס ל out.
                    out = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                    conn.sendall(out)
                
                # אם ה-chunk ריק, יוצא מהלולאה החיצונית (Break)
                if not chunk:
                    break
                    
        except Exception as e:
            # במקרה של שגיאה (כמו JSON שגוי), ננסה לשלוח הודעת שגיאה ולסגור את החיבור
            try:
                conn.sendall((json.dumps({"ok": False, "error": f"Malformed: {e}"} ) + "\n").encode("utf-8"))
            except Exception:
                pass

def main():
    ap = argparse.ArgumentParser(description="JSON TCP server (calc/gpt) — supports Persistence and Caching")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--cache-size", type=int, default=128)
    args = ap.parse_args()
    serve(args.host, args.port, args.cache_size)

if __name__ == "__main__":
    main()