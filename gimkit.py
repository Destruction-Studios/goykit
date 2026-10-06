import time
import pyautogui
import pytesseract
import difflib
import tkinter as tk
import ctypes
import json
from pathlib import Path
from PIL import ImageOps
from pynput import mouse

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

class Toast:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.label = tk.Label(self.root, font=("Segoe UI", 14, "bold"),
                              fg="white", padx=20, pady=12)
        self.label.pack()
        self.root.withdraw()
        self._hide_id = None

    def show(self, text, color="#2e9e5b", ms=2000):
        self.label.config(text=text, bg=color)
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        self.root.geometry(f"+{self.root.winfo_screenwidth() - w - 20}+20")
        self.root.deiconify()
        if self._hide_id:
            self.root.after_cancel(self._hide_id) 
        self._hide_id = self.root.after(ms, self.root.withdraw)
        self.root.update()

    def tick(self):
        self.root.update()


toast = Toast()

DB_FILE = Path(__file__).parent / "words.json"

def loadDb():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}

def saveDb(db):
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")

def findKey(word, db):
    if word in db:
        return word
    close = difflib.get_close_matches(word, db.keys(), n=1, cutoff=0.85)
    return close[0] if close else None


def waitForClick(pr, suppress=False):
    print(pr)
    toast.show(pr)
    result = {}

    def onClick(x, y, button, pressed):
        if pressed:
            result["pos"] = (x,y)
            return False
    
    with mouse.Listener(on_click=onClick) as listener:
        listener.join()

    print(f"    got {result['pos']}")
    time.sleep(0.3)
    return result["pos"]

def defineRegion(name):
    x1, y1 = waitForClick(f"[{name}] Click the TOP-LEFT corner...", True)
    x2, y2 = waitForClick(f"[{name}] Click the BOTTOM-RIGHT corner...", True)

    left, top = min(x1, x2), min(y1, y2)
    return (left, top, abs(x2-x1), abs(y2-y1))

def getCells(img):
    w,h = img.size
    cells=[]
    for row in range(2):
        for col in range(2):
            cells.append(img.crop((col*w//2, row*h//2, (col+1)*w//2, (row+1)*h//2)))
    
    return cells

def readText(src, lang="eng", psm=7, threshold=False):
    img = pyautogui.screenshot(region=src) if isinstance(src, tuple) else src
    img = ImageOps.grayscale(img)
    img = img.resize((img.width*2, img.height*2))
    if threshold:
        img = img.point(lambda p: 255 if p > 140 else 0)

    return pytesseract.image_to_string(img, config=f"--psm {psm}", lang=lang).strip().lower()

def readLatin(reg):
    return readText(reg, lang="lat", psm=7, threshold=True)

def readCell(img):
    return readText(img, lang="eng", psm=6, threshold=False)

def cellCenter(idx, region):
    left, top, w, h = region
    row, col = divmod(idx, 2)
    return (int(left + (col + 0.5) * w / 2), int(top + (row + 0.5) * h / 2))

def attemptToAnswer(entry, region):
    target = entry["english"]

    ss = pyautogui.screenshot(region=region)
    best_score, best_idx = 0, None
    for idx, cell in enumerate(getCells(ss)):
        text = readCell(cell)
        score = difflib.SequenceMatcher(None, target,text).ratio()
        if score >best_score:
            best_score, best_idx = score, idx
        
    if best_idx is not None and best_score >= MATCH_THRESHOLD:
        pyautogui.click(*cellCenter(best_idx, region))
        print(f"{entry['latin']} -> {target} (MATCH {best_score:.3f})")
        return true
    
    print(f"Couldnt find '{target}' on screen (best {best_score:.3f})")
    toast.show(f"Couldn't find '{target}', click the right one", RED)
    return False

def learnSol(word, key, db, region):
    ss = pyautogui.screenshot(region=region)
    cells = getCells(ss)

    x,y=waitForClick(f"Adding dict entry '{word}': click correct answer")

    left,top,w,h = region

    if not (left <= x < left + w and top <= y < top +h):
        toast.show("Click was outside answers area", "RED")
        return
    
    col = 0 if x < left + w / 2 else 1
    row = 0 if y < top + h/2 else 1
    eng = readCell(cells[row * 2+col])


    if not eng:
        toast.show("can not read answer", RED)
    
    db[key] = {"latin":word, "english":eng}
    saveDb(db)
    print(f"SAVED {word} -> {eng}")

def main():
    word_region = defineRegion("Latin Word")
    answer_region = defineRegion("Answers")

    print(f"\nWords:    {word_region}")
    print(f"\nAnswers:    {answer_region}")
    db = loadDb()
    print("\n Loaded DB")

    ctypes.windll.user32.ShowWindow(
        ctypes.windll.kernel32.GetConsoleWindow(),
        6
    )

    # print("\n Watching for words... (CTRL+C TO STOP)\n")
    last = None
    while True:
        toast.tick()


        word = readLatin(word_region)

        if not word or word == last:
            time.sleep(.2)
            continue

        if readLatin(word_region) != word:
            continue

        last = word
        print(f"\n\nDetected: {word}")
        toast.show(f"Detected: {word}")

        key = findKey(word, db)
        if key and attemptToAnswer(db[key], answer_region):
            pass
        else:
            learnSol(word, key or word, db, answer_region)
        
        time.sleep(.75)
            
    



if __name__ == "__main__":
    main()