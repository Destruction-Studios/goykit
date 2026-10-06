import ctypes
import json
import re
import time
import tkinter as tk
import unicodedata
from pathlib import Path

import pyautogui
import pytesseract
from PIL import ImageOps
from pynput import mouse

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------- SETTINGS ----------------
DB_FILE = Path(__file__).parent / "words.json"
AUTO_CLICK = False        # False = only learn + show known answers. True = click known answers.
MATCH_THRESHOLD = 0.6     # how close the OCR'd answer must be to the stored one (0-1)
UI_INSENSITIVE = True     # treat u and i as the same letter when matching Latin words
# ------------------------------------------


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
ORANGE, GREEN, RED = "#e08a00", "#2e9e5b", "#c0392b"


# ---------------- JSON ----------------
def loadDb():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}


def saveDb(db):
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------- TEXT HELPERS ----------------
def stripMacrons(text):
    d = unicodedata.normalize("NFD", text)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def cleanLatin(text):
    text = stripMacrons(text).lower()
    return re.sub(r"[^a-z -]", "", text).strip()


def cleanEnglish(text):
    text = text.lower()
    text = re.sub(r"[^a-z' -]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def makeKey(word):
    return word.replace("u", "i") if UI_INSENSITIVE else word


def findKey(word, db):
    """Return the db key matching this Latin word (exact, then fuzzy), or None."""
    key = makeKey(word)
    if key in db:
        return key
    close = difflib.get_close_matches(key, db.keys(), n=1, cutoff=0.85)
    return close[0] if close else None


# ---------------- OCR ----------------
def readText(src, lang="eng", psm=7, threshold=False):
    """src is either a region tuple (screenshot it) or an already-captured PIL image."""
    img = pyautogui.screenshot(region=src) if isinstance(src, tuple) else src
    img = ImageOps.grayscale(img)
    img = img.resize((img.width * 2, img.height * 2))
    if threshold:
        img = img.point(lambda p: 255 if p > 140 else 0)
    return pytesseract.image_to_string(img, config=f"--psm {psm}", lang=lang).strip().lower()


def readLatin(region):
    return cleanLatin(readText(region, lang="lat", psm=7, threshold=True))


def readAnswerCell(img):
    return cleanEnglish(readText(img, lang="eng", psm=6, threshold=False))


# ---------------- SCREEN / CLICKS ----------------
def waitForClick(pr):
    print(pr)
    toast.show(pr, ORANGE, ms=60000)
    result = {}

    def onClick(x, y, button, pressed):
        if pressed:
            result["pos"] = (x, y)
            return False

    with mouse.Listener(on_click=onClick) as listener:
        listener.join()

    print(f"    got {result['pos']}")
    time.sleep(0.3)
    return result["pos"]


def defineRegion(name):
    x1, y1 = waitForClick(f"[{name}] Click the TOP-LEFT corner...")
    x2, y2 = waitForClick(f"[{name}] Click the BOTTOM-RIGHT corner...")
    left, top = min(x1, x2), min(y1, y2)
    return (left, top, abs(x2 - x1), abs(y2 - y1))


def getCells(img):
    """Split the answer screenshot into 4 images. Index = row * 2 + col."""
    w, h = img.size
    cells = []
    for row in range(2):
        for col in range(2):
            cells.append(img.crop((col * w // 2, row * h // 2,
                                   (col + 1) * w // 2, (row + 1) * h // 2)))
    return cells


def cellCenter(idx, answer_region):
    left, top, w, h = answer_region
    row, col = divmod(idx, 2)
    return (int(left + (col + 0.5) * w / 2), int(top + (row + 0.5) * h / 2))


# ---------------- LEARN / ANSWER ----------------
def learn(word, key, db, answer_region):
    # Screenshot BEFORE the click: the game will change the screen afterwards
    shot = pyautogui.screenshot(region=answer_region)
    cells = getCells(shot)

    x, y = waitForClick(f"New word '{word}': click the correct answer")

    left, top, w, h = answer_region
    if not (left <= x < left + w and top <= y < top + h):
        toast.show("Click was outside the answers area, not saved", RED)
        return

    col = 0 if x < left + w / 2 else 1
    row = 0 if y < top + h / 2 else 1
    english = readAnswerCell(cells[row * 2 + col])

    if not english:
        toast.show("Couldn't read that answer, not saved", RED)
        return

    db[key] = {"latin": word, "english": english}
    saveDb(db)
    print(f"Saved: {word} -> {english}")
    toast.show(f"Saved: {word} = {english}")


def answer(entry, answer_region):
    """Handle a known word. Returns True if handled, False if the answer wasn't found."""
    target = entry["english"]

    if not AUTO_CLICK:
        toast.show(f"{entry['latin']} = {target}")
        return True

    shot = pyautogui.screenshot(region=answer_region)
    best_score, best_idx = 0, None
    for idx, cell in enumerate(getCells(shot)):
        text = readAnswerCell(cell)
        score = difflib.SequenceMatcher(None, target, text).ratio()
        if score > best_score:
            best_score, best_idx = score, idx

    if best_idx is not None and best_score >= MATCH_THRESHOLD:
        pyautogui.click(*cellCenter(best_idx, answer_region))
        print(f"{entry['latin']} -> {target} (match {best_score:.2f})")
        return True

    print(f"Couldn't find '{target}' on screen (best {best_score:.2f})")
    toast.show(f"Couldn't find '{target}', click the right one", RED)
    return False


# ---------------- MAIN ----------------
def main():
    word_region = defineRegion("Latin Word")
    answer_region = defineRegion("Answers")

    print(f"\nWord region:    {word_region}")
    print(f"Answer region:  {answer_region}")

    db = loadDb()
    print(f"Loaded {len(db)} words from {DB_FILE}")
    print("\nWatching for words... (CTRL+C TO STOP)\n")
    toast.show(f"Loaded {len(db)} words. Watching...")

    last = None
    while True:
        toast.tick()

        word = readLatin(word_region)
        if not word or word == last:
            time.sleep(0.2)
            continue

        # Stability check so we don't act on a half-drawn word
        time.sleep(0.15)
        if readLatin(word_region) != word:
            continue

        last = word
        print(f"\nDetected: {word}")

        key = findKey(word, db)
        if key and answer(db[key], answer_region):
            pass
        else:
            learn(word, key or makeKey(word), db, answer_region)

        time.sleep(0.5)  # let the next word appear


if __name__ == "__main__":
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 6)  # minimize console
    main()