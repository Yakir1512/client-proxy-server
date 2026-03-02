# client.py
import argparse, socket, json, sys

# --- 1. פונקציית עזר לבחירת ביטויים (CALC) ---
def get_calc_expression() -> str:
    """
    מציג תפריט של ביטויים מתמטיים מוגדרים מראש או מאפשר קלט חופשי.
    """
    # ביטויים לדוגמה (שלושה לבחירת המשתמש)
    PREDEFINED_EXPRS = [
        "2 * (4 + 6) / 5",
        "sqrt(9) + tan(0)",
        "5**2 + 3 * log(e)"
    ]
    
    print("\n--- בחירת ביטוי מתמטי (CALC) ---")
    print("בחר ביטוי מהרשימה או הקלד ביטוי משלך:")
    
    for i, expr in enumerate(PREDEFINED_EXPRS):
        print(f"  {i + 1}. {expr}")
        
    print("  4. הקלדת ביטוי חופשי")

    while True:
        choice = input("הכנס מספר (1-4): ").strip()

        if choice.isdigit():
            idx = int(choice) - 1
            
            if 0 <= idx < len(PREDEFINED_EXPRS):
                return PREDEFINED_EXPRS[idx]
            
            elif idx == 3: # אפשרות 4 - קלט חופשי
                free_expr = input("הקלד את הביטוי האלגברי/לוגי: ").strip()
                if free_expr:
                    return free_expr
            
            else:
                print("בחירה לא חוקית. נסה שוב.")
        else:
            print("קלט לא חוקי. נסה שוב.")

# --- 2. פונקציית שליחת הבקשה (REQUEST) ---
def request(sock: socket.socket, payload: dict) -> dict:
    """שליחת בקשה וקבלת תשובה על סוקט קיים"""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)
    buff = b""
    
    while True:
        chunk = sock.recv(4096)# מתחילה לקבל את כל המידע ששולח השרת אבל עד 4096 בתים
        if not chunk:
            break
        
        buff += chunk # פההבאפר אוסף את כל החבילות ואוסף אותן למשתנה אחד
        if b"\n" in buff:
            line, _, _ = buff.partition(b"\n")# מחברת את כל החבילות שהתקבלו לאחת שלמה
            return json.loads(line.decode("utf-8"))# השורה הזו מחזירה את התשובה הסופית אחרי פיענוח
            
    return {"ok": False, "error": "No response"}

# --- 3. הפונקציה הראשית (MAIN) ---
def main():
    # קלט מהמשתמש
    #user_mode = input("mode you want (calc/gpt): ").strip()
        
    
    ap = argparse.ArgumentParser(description="Client (calc/gpt over JSON TCP)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    # שינוי: required=False כדי שלא יזרוק שגיאה אם לא עבר בטרמינל
    ap.add_argument("--mode", choices=["calc", "gpt"], required=False)
    ap.add_argument("--expr", help="Expression for mode=calc")
    ap.add_argument("--prompt", help="Prompt for mode=gpt")
    ap.add_argument("--no-cache", action="store_true", help="Disable caching")
    ap.add_argument("--repeat", type=int, default=1)
       
        
    args = ap.parse_args()
    # # עדכון הערך בתוך args (אם לא הוכנס בטרמינל, נשתמש בקלט מה-input)
    # if not args.mode:
    #     args.mode = user_mode

    # # 1. בניית ה-Payload
    # if args.mode == "calc":
    #     if not args.expr:
    #         # הפעלת האינטראקטיביות אם לא סופק ביטוי בשורת הפקודה
    #         args.expr = get_calc_expression()
            
    #     if not args.expr:
    #         print("לא נבחר ביטוי לחישוב.", file=sys.stderr); 
    #         main() # קורא שוב לMAIN לאחר קלט לא מתאים.calc
            
    #     payload = {"mode": "calc", "data": {"expr": args.expr}, "options": {"cache": not args.no_cache}}
        
    # elif args.mode == "gpt":
    #     if not args.prompt:
    #         # הפעלת האינטראקטיביות אם לא סופק פרומפט בשורת הפקודה
    #         print("\n--- בחירת פרומפט ל-GPT ---")
    #         args.prompt = input("הקלד את הפרומפט שלך: ").strip()
            
    #     if not args.prompt:
    #         print("לא נבחר פרומפט.", file=sys.stderr); 
            
    #     payload = {"mode": "gpt", "data": {"prompt": args.prompt}, "options": {"cache": not args.no_cache}}

    # 2. לולאת החזרות (REPEATER) עם חיבור רציף
    # payload = {"mode": "calc", "data": {"expr": None}, "options": {"cache": True}}
    # if payload is None:
    #     print("שגיאה: Payload לא הוגדר.", file=sys.stderr); sys.exit(3)
        
    try:
        # פתיחת החיבור פעם אחת בלבד עבור כל הבקשות
        with socket.create_connection((args.host, args.port), timeout=10) as sock:
            # לולאה שמאפשרת למשתמש לבקש שוב ושוב
            while True:
                if not args.mode:
                    # א. בחירת מוד לכל בקשה חדשה
                    user_mode = input("\nEnter mode (calc/gpt) or 'exit': ").strip().lower()
                    if user_mode == 'exit':
                        break
                    if user_mode not in ['calc', 'gpt']:
                        print("Invalid mode!")
                        continue

                # ב. בניית ה-Payload בהתאם למוד
                if user_mode == "calc":
                    expr = get_calc_expression()
                    payload = {"mode": "calc", "data": {"expr": expr}, "options": {"cache": True}}
                else:
                    prompt = input("Enter your prompt: ").strip()
                    payload = {"mode": "gpt", "data": {"prompt": prompt}, "options": {"cache": True}}

                # ג. שליחת הבקשה על הסוקט הקיים
                print("Sending request...")
                resp = request(sock, payload)
                
                # ד. הדפסת התשובה
                print("--- Server Response ---")
                print(json.dumps(resp, ensure_ascii=False, indent=2))
                
    except Exception as e:
        print(f"שגיאת תקשורת: {e}")
            
if __name__ == "__main__":
    main()