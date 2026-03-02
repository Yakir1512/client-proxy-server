# proxy.py
import argparse, socket, threading, json, time, collections

#  LRU Cache (Copy from server.py) ד
class LRUCache:
    """Minimal LRU cache based on OrderedDict."""
    def __init__(self, capacity: int = 256): # הגדלנו קצת את גודל ברירת המחדל
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

# --- גלובלי ---
PROXY_CACHE = None
CACHE_LOCK = threading.Lock() # מנעול לריבוי תהליכונים

def handle_request_with_cache(c: socket.socket, sh: str, sp: int, cache: LRUCache):
    """
    מקבלת חיבור מהלקוח, קוראת את הבקשה, בודקת מטמון, ומעבירה לשרת אם יש Miss.
    """
    # 1. קליטת הבקשה המלאה מהלקוח (עד \n)
    try:
        raw = b""
        # שימוש בלולאה פנימית כדי לאפשר בקשות מרובות (Persistence)
        while True:
            chunk = c.recv(4096)
            if not chunk:
                break
            raw += chunk
            
            # לולאה פנימית לטיפול בבקשות מרובות שנשלחו ב-Pipe
            while b"\n" in raw:
                line, _, rest = raw.partition(b"\n")
                raw = rest # שומרים את היתרה לבדיקה הבאה
                
                try:
                    msg = json.loads(line.decode("utf-8"))
                    
                    # 2. קביעת מפתח המטמון (Cache Key)
                    key_data = msg.get('data', {})
                    # המפתח כולל את mode ונתוני ה-data ממוינים (כדי להיות עקבי)
                    cache_key = (msg['mode'],) + tuple(sorted(key_data.items()))
                    
                    # 3. בדיקת מטמון (Cache Hit)
                    with CACHE_LOCK:
                        resp = cache.get(cache_key)
                    
                    if resp:
                        # Cache HIT - מחזירים תשובה מהירה
                        if resp.get('meta'):
                            # מוסיפים אינדיקציה שהתשובה הגיעה מהפרוקסי
                            resp['meta']['from_proxy_cache'] = True 
                        
                        print(f"[proxy] Cache HIT for mode={msg['mode']}. Sending cached response.")
                        
                    else:
                        # 4. החטאת מטמון (Cache Miss) - פנייה לשרת
                        print(f"[proxy] Cache MISS for mode={msg['mode']}. Forwarding to server...")
                        
                        server_request = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
                        
                        try:
                            # יצירת חיבור חדש לשרת האמיתי ושליחה
                            with socket.create_connection((sh, sp), timeout=5) as s:
                                s.sendall(server_request)
                                
                                # קריאת התגובה המלאה מהשרת (עד \n)
                                server_buff = b""
                                while True:
                                    server_chunk = s.recv(4096)
                                    if not server_chunk:
                                        break
                                    server_buff += server_chunk
                                    if b"\n" in server_buff:
                                        server_line, _, _ = server_buff.partition(b"\n")
                                        resp = json.loads(server_line.decode("utf-8"))
                                        break
                                
                            # 5. עדכון מטמון (אם הצלחנו לקבל תשובה)
                            with CACHE_LOCK:
                                cache.set(cache_key, resp) 

                        except Exception as e:
                            print(f"[proxy] Error communicating with server: {e}")
                            resp = {"ok": False, "error": f"Proxy failed to connect to server: {e}"}

                    # 6. שליחת התגובה (מטמון או שרת) בחזרה ללקוח
                    out = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                    c.sendall(out)
                
                except Exception as e:
                    # שגיאה בפענוח JSON או עיבוד לוגי של הבקשה הנוכחית
                    print(f"[proxy] Malformed request received: {e}")
                    try: 
                        c.sendall((json.dumps({"ok": False, "error": f"Proxy malformed request: {e}"}) + "\n").encode("utf-8"))
                    except Exception: pass
            
            # אם לא נשאר chunk, זה יצא מהלולאה החיצונית (break)
            if not chunk:
                break
    except Exception: pass             

def handle(c, sh, sp):
    """ הפונקציה המופעלת בתהליכון חדש לכל חיבור לקוח. """
    with c:
        # מטפלת בכל הבקשות הנשלחות בחיבור הזה (Persistent Connection)
        handle_request_with_cache(c, sh, sp, PROXY_CACHE)


def main():
    global PROXY_CACHE
    #ארגומנטים להוספה בתחילת ההרצה של התכנית
    ap = argparse.ArgumentParser(description="Application-level TCP proxy with Caching (Persistent Connection)")
    ap.add_argument("--listen-host", default="127.0.0.1")
    ap.add_argument("--listen-port", type=int, default=5554)
    ap.add_argument("--server-host", default="127.0.0.1")
    ap.add_argument("--server-port", type=int, default=5555)
    ap.add_argument("--cache-size", type=int, default=256, help="Capacity of the proxy cache")
    args = ap.parse_args()
    #יצירת מטמון חדש עבור הפרוקסי
    PROXY_CACHE = LRUCache(capacity=args.cache_size)
    #אותו דבר שיש בקוד הלקוח 
    #פתיחת סוקט וקישור שלו לתהליכון לכל לקוח
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.listen_host, args.listen_port))
        s.listen(16)
        print(f"[proxy] Listening on {args.listen_host}:{args.listen_port}. Caching enabled (size={args.cache_size}).")
        print(f"[proxy] Forwarding to {args.server_host}:{args.server_port}")
        
        while True:
            c, addr = s.accept()
            # הפרוקסי תומך ב-Persistent Connection: כל לקוח מקבל תהליכון משלו
            threading.Thread(target=handle, args=(c, args.server_host, args.server_port), daemon=True).start()

if __name__ == "__main__":
    main()